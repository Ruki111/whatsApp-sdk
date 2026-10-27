"""Async client for the WhatsApp Cloud API (Meta Graph API): templates, messages, media,
sending limits, and webhook subscriptions."""

import httpx

__all__ = ["TEMPLATE_FIELDS", "WhatsApp", "WhatsAppError"]

# Include review details and components so sync can report rejections and detect external edits.
TEMPLATE_FIELDS = (
    "id,name,status,category,language,quality_score,rejected_reason,"
    "components,parameter_format"
)


class WhatsAppError(Exception):
    """A non-2xx response, or a 200 carrying an `error` object."""

    def __init__(self, status_code: int, payload: dict | None) -> None:
        self.status_code = status_code
        self.payload = payload or {}
        error = self.payload.get("error", {})
        self.code = error.get("code")
        self.subcode = error.get("error_subcode")
        self.title = error.get("error_user_title")
        # error_user_msg is the human-readable one ("Variables can't be at the
        # start or end of the template."); `message` is the generic fallback.
        self.message = (
            error.get("error_user_msg")
            or error.get("message")
            or "WhatsApp Cloud API request failed"
        )
        super().__init__(self.message)

    @property
    def detail(self) -> dict:
        return {
            "message": self.message,
            "title": self.title,
            "code": self.code,
            "subcode": self.subcode,
        }


def _error(message: str) -> WhatsAppError:
    return WhatsAppError(502, {"error": {"message": message}})


def _parse(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    # Non-object bodies (e.g. from a proxy) count as empty so they can't escape WhatsAppError.
    if not isinstance(payload, dict):
        payload = {}
    if response.status_code >= 400 or "error" in payload:
        raise WhatsAppError(response.status_code, payload)
    return payload


class WhatsApp:
    """One set of credentials. Pass a shared `client` to pool connections across many sends;
    without one, each call opens and closes its own."""

    def __init__(
        self,
        access_token: str,
        *,
        waba_id: str = "",
        phone_number_id: str = "",
        graph_version: str = "v21.0",
        timeout: httpx.Timeout | float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.access_token = access_token
        self.waba_id = waba_id
        self.phone_number_id = phone_number_id
        self.base_url = f"https://graph.facebook.com/{graph_version}"
        self.timeout = timeout
        self.client = client

    async def request(
        self, method: str, path: str, *, timeout: httpx.Timeout | float | None = None, **kwargs
    ) -> dict:
        """Call any Graph API path; extra kwargs go to httpx (json, params, data, files)."""
        # Explicit per-call timeout: a shared client's own default must not apply here.
        timeout = timeout or self.timeout
        headers = {"Authorization": f"Bearer {self.access_token}"}
        client = self.client or httpx.AsyncClient(timeout=timeout)
        try:
            response = await client.request(
                method, f"{self.base_url}/{path}", headers=headers, timeout=timeout, **kwargs
            )
        except httpx.HTTPError as exc:
            raise _error(f"Could not reach the Graph API: {exc}") from exc
        finally:
            if client is not self.client:
                await client.aclose()
        return _parse(response)

    # Templates

    async def create_message_template(
        self,
        *,
        name: str,
        language: str,
        category: str,
        components: list[dict],
        parameter_format: str | None = None,
        sub_category: str | None = None,
        message_send_ttl_seconds: int | None = None,
    ) -> dict:
        """Submit a template for review. Returns {id, status, category}."""
        payload: dict = {
            "name": name,
            "language": language,
            "category": category,
            "components": components,
        }
        # Omitted rather than sent as null: Meta rejects an explicit null on
        # sub_category, and defaults the other two on its own.
        if parameter_format:
            payload["parameter_format"] = parameter_format
        if sub_category:
            payload["sub_category"] = sub_category
        if message_send_ttl_seconds is not None:
            payload["message_send_ttl_seconds"] = message_send_ttl_seconds
        return await self.request("POST", f"{self.waba_id}/message_templates", json=payload)

    async def update_message_template(
        self,
        meta_template_id: str,
        *,
        components: list[dict],
        category: str | None = None,
        parameter_format: str | None = None,
        message_send_ttl_seconds: int | None = None,
    ) -> dict:
        """Replace all components; name/language are immutable. The prior approved version sends
        while the edit is reviewed."""
        payload: dict = {"components": components}
        if category:
            payload["category"] = category
        if parameter_format:
            payload["parameter_format"] = parameter_format
        if message_send_ttl_seconds is not None:
            payload["message_send_ttl_seconds"] = message_send_ttl_seconds
        return await self.request("POST", str(meta_template_id), json=payload)

    async def get_message_template(
        self, meta_template_id: str, timeout: httpx.Timeout | float | None = None
    ) -> dict:
        return await self.request(
            "GET", str(meta_template_id), timeout=timeout, params={"fields": TEMPLATE_FIELDS}
        )

    async def list_message_templates(self, limit: int = 100, after: str | None = None) -> dict:
        params: dict = {"fields": TEMPLATE_FIELDS, "limit": limit}
        if after:
            params["after"] = after
        return await self.request("GET", f"{self.waba_id}/message_templates", params=params)

    async def delete_message_template(self, name: str, meta_template_id: str | None = None) -> dict:
        # Without hsm_id Meta deletes every language variant sharing the name.
        params: dict = {"name": name}
        if meta_template_id:
            params["hsm_id"] = str(meta_template_id)
        return await self.request("DELETE", f"{self.waba_id}/message_templates", params=params)

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
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(
                    f"{self.base_url}/{upload_id}",
                    # The upload edge wants the OAuth scheme, not Bearer.
                    headers={"Authorization": f"OAuth {self.access_token}", "file_offset": "0"},
                    content=content,
                )
        except httpx.HTTPError as exc:
            raise _error(f"Could not reach the Graph API: {exc}") from exc
        handle = _parse(response).get("h")
        if not handle:
            raise _error("Meta returned no media handle")
        return handle

    # Messages

    async def send_message(self, payload: dict, *, phone_number_id: str | None = None) -> dict:
        """Send any message body (text, media, interactive, ...) as Meta defines it."""
        return await self.request(
            "POST", f"{phone_number_id or self.phone_number_id}/messages",
            json=payload, timeout=httpx.Timeout(15),
        )

    async def send_template_message(
        self,
        *,
        to: str,
        name: str,
        language: str,
        components: list[dict] | None = None,
        marketing_messages: bool = False,
        phone_number_id: str | None = None,
        timeout: httpx.Timeout | float | None = None,
        callback_data: str | None = None,
    ) -> dict:
        """Send one template; `marketing_messages` uses MM Lite with Cloud API fallback.
        callback_data is echoed back in delivery webhooks."""
        template: dict = {"name": name, "language": {"code": language}}
        if components:
            template["components"] = components
        payload: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": template,
        }
        if callback_data:
            payload["biz_opaque_callback_data"] = callback_data
        edge = "messages"
        if marketing_messages:
            edge = "marketing_messages"
            payload["product_policy"] = "CLOUD_API_FALLBACK"
        return await self.request(
            "POST", f"{phone_number_id or self.phone_number_id}/{edge}",
            json=payload, timeout=timeout,
        )

    async def mark_message_read(self, wamid: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request(
            "POST", f"{phone_number_id or self.phone_number_id}/messages",
            json={"messaging_product": "whatsapp", "status": "read", "message_id": wamid},
        )

    async def upload_message_media(
        self, *, file_name: str, file_type: str, content: bytes, phone_number_id: str | None = None
    ) -> str:
        """Upload send-time media and return its ID (templates use upload_template_sample)."""
        response = await self.request(
            "POST", f"{phone_number_id or self.phone_number_id}/media",
            data={"messaging_product": "whatsapp", "type": file_type},
            files={"file": (file_name, content, file_type)},
        )
        media_id = response.get("id")
        if not media_id:
            raise _error("Meta returned no media ID")
        return str(media_id)

    # Account

    async def get_sending_limits(self, phone_number_id: str | None = None) -> dict:
        """Throughput, coexistence, and messaging limit as Meta reports them; absent fields are
        None."""
        payload = await self.request(
            "GET", phone_number_id or self.phone_number_id,
            params={"fields": "throughput,is_on_biz_app,whatsapp_business_manager_messaging_limit"},
            timeout=10,
        )
        throughput = payload.get("throughput")
        level = throughput.get("level") if isinstance(throughput, dict) else None
        return {
            "throughput": str(level) if level else None,
            "is_on_biz_app": payload.get("is_on_biz_app") is True,
            "messaging_limit": payload.get("whatsapp_business_manager_messaging_limit"),
        }

    async def list_subscribed_apps(self) -> dict:
        """Apps currently receiving webhooks for this WABA."""
        return await self.request("GET", f"{self.waba_id}/subscribed_apps")

    async def subscribe_app_to_waba(self) -> dict:
        """Subscribe the token's app to WABA webhooks; dashboard setup alone doesn't deliver."""
        return await self.request("POST", f"{self.waba_id}/subscribed_apps")

    async def app_id(self) -> str:
        """The Meta app the access token belongs to."""
        payload = await self.request("GET", "debug_token", params={"input_token": self.access_token})
        app_id = (payload.get("data") or {}).get("app_id")
        if not app_id:
            raise _error("Could not determine the Meta app for this token")
        return str(app_id)
