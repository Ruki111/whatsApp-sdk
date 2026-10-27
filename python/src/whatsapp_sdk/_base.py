"""Shared request plumbing every API area builds on."""

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx

from .errors import _error, _parse, _unreached

GRAPH_URL = "https://graph.facebook.com"

# Media download URLs live on these hosts; the access token is never sent anywhere else.
MEDIA_HOSTS = (".fbsbx.com", ".facebook.com", ".whatsapp.net")

# Include review details and components so sync can report rejections and detect external edits.
TEMPLATE_FIELDS = (
    "id,name,status,category,language,quality_score,rejected_reason,"
    "components,parameter_format"
)


def _recipient(to: str) -> dict:
    # BSUIDs ("US.13491208655302741918") go in `recipient`; phone numbers never contain a dot.
    return {"recipient": to} if "." in to else {"to": to}


def _clean(values: dict) -> dict:
    """Drop unset values: Meta rejects explicit nulls on several fields."""
    return {k: v for k, v in values.items() if v is not None}


def _query(**values) -> dict:
    # Graph expects arrays and objects in the query string as JSON.
    return {
        k: json.dumps(v) if isinstance(v, (list, dict)) else v
        for k, v in _clean(values).items()
    }


def _page(fields=None, limit=None, after=None, before=None, **extra) -> dict:
    return _query(fields=fields, limit=limit, after=after, before=before, **extra)


class _Base:
    def __init__(
        self,
        access_token: str,
        *,
        waba_id: str = "",
        phone_number_id: str = "",
        graph_version: str = "v26.0",
        timeout: httpx.Timeout | float = 30.0,
        client: httpx.AsyncClient | None = None,
        app_secret: str | None = None,
    ) -> None:
        """`app_secret` signs every call with `appsecret_proof`, which Meta requires when the
        app has "Require app secret" switched on."""
        self.access_token = access_token
        self.waba_id = waba_id
        self.phone_number_id = phone_number_id
        self.base_url = f"{GRAPH_URL}/{graph_version}"
        self.timeout = timeout
        self.client = client
        self.appsecret_proof = hmac.new(
            app_secret.encode(), access_token.encode(), hashlib.sha256).hexdigest() if app_secret else None

    async def _send(self, method: str, url: str, *, timeout=None, auth: str = "Bearer",
                    headers: dict | None = None, **kwargs) -> httpx.Response:
        # Explicit per-call timeout: a shared client's own default must not apply here.
        timeout = timeout or self.timeout
        headers = {"Authorization": f"{auth} {self.access_token}", **(headers or {})}
        client = self.client or httpx.AsyncClient(timeout=timeout)
        try:
            return await client.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise _unreached(exc, method) from exc
        finally:
            if client is not self.client:
                await client.aclose()

    async def request(
        self, method: str, path: str, *, timeout: httpx.Timeout | float | None = None,
        params: dict | None = None, **kwargs
    ) -> dict:
        """Call any Graph API path; extra kwargs go to httpx (json, data, files)."""
        if self.appsecret_proof:
            params = {**(params or {}), "appsecret_proof": self.appsecret_proof}
        return _parse(await self._send(method, f"{self.base_url}/{path}", timeout=timeout,
                                       params=params, **kwargs), method)

    async def paginate(self, path: str, **params) -> AsyncIterator[dict]:
        """Yield every item of a list endpoint, following `paging.cursors.after`."""
        params = _query(**params)
        while True:
            page = await self.request("GET", path, params=params)
            for item in page.get("data", []):
                yield item
            after = (page.get("paging") or {}).get("cursors", {}).get("after")
            if not after or not (page.get("paging") or {}).get("next"):
                return
            params = {**params, "after": after}

    def _phone(self, phone_number_id: str | None) -> str:
        return phone_number_id or self.phone_number_id

    def _waba(self, waba_id: str | None) -> str:
        return waba_id or self.waba_id

    async def iter_media(self, url: str, *, max_bytes: int | None = None,
                         chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """Stream a media URL from get_media in chunks. The token is only ever sent to Meta's
        own HTTPS hosts, redirects are refused, and `max_bytes` stops oversized files."""
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.port not in (None, 443) or not parts.hostname.endswith(MEDIA_HOSTS)):
            raise _error("Untrusted media URL")
        client = self.client or httpx.AsyncClient()
        try:
            async with client.stream(
                "GET", url, headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=httpx.Timeout(120.0, connect=10.0), follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    raise _error("Media redirects are not followed")
                if response.status_code >= 400:
                    await response.aread()
                    _parse(response)
                length = response.headers.get("content-length")
                if max_bytes is not None and length and length.isdigit() and int(length) > max_bytes:
                    raise _error("Media exceeds the size limit")
                size = 0
                async for chunk in response.aiter_bytes(chunk_size):
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise _error("Media exceeds the size limit")
                    yield chunk
        except httpx.HTTPError as exc:
            raise _unreached(exc, "GET") from exc
        finally:
            if client is not self.client:
                await client.aclose()

    async def download_media(self, media_id: str, *, max_bytes: int | None = None,
                             phone_number_id: str | None = None) -> bytes:
        """Whole file in memory; use get_media + iter_media to stream large files to disk."""
        url = (await self.get_media(media_id, phone_number_id=phone_number_id)).get("url")
        if not url:
            raise _error("Meta returned no media URL")
        return b"".join([chunk async for chunk in self.iter_media(str(url), max_bytes=max_bytes)])

    async def upload_template_sample(self, *, file_name: str, file_type: str, content: bytes) -> str:
        """Upload sample media through an app-scoped resumable session; returns the handle a
        template's header_handle expects."""
        session = await self.request(
            "POST",
            f"{await self.app_id()}/uploads",
            params={"file_name": file_name, "file_length": len(content), "file_type": file_type},
        )
        upload_id = session.get("id")
        if not upload_id:
            raise _error("Upload session was not opened")
        # The upload edge wants the OAuth scheme, not Bearer.
        response = await self._send("POST", f"{self.base_url}/{upload_id}", auth="OAuth",
                                    headers={"file_offset": "0"}, content=content,
                                    params=_query(appsecret_proof=self.appsecret_proof),
                                    timeout=httpx.Timeout(120.0))
        handle = _parse(response, "POST").get("h")
        if not handle:
            raise _error("Meta returned no media handle")
        return handle

    async def debug_token(self, input_token: str | None = None) -> dict:
        """App, expiry, scopes, and granular asset access of a token (default: this one)."""
        payload = await self.request("GET", "debug_token",
                                     params={"input_token": input_token or self.access_token})
        return payload.get("data") or {}

    async def app_id(self) -> str:
        """The Meta app the access token belongs to."""
        app_id = (await self.debug_token()).get("app_id")
        if not app_id:
            raise _error("Could not determine the Meta app for this token")
        return str(app_id)
