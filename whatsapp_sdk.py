"""Async client for the WhatsApp Business Platform (Meta Graph API): Cloud API messaging,
Business Management, Flows, Groups, Calling, and Multi-Partner Solutions.

Endpoint reference: https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/llms.txt
Anything not wrapped here: `await wa.request(method, path, params=..., json=...)`."""

import hashlib
import hmac
import json

import httpx

__all__ = ["TEMPLATE_FIELDS", "WhatsApp", "WhatsAppError", "verify_signature"]

GRAPH_URL = "https://graph.facebook.com"

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


def verify_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """Check a webhook's `X-Hub-Signature-256` header against the raw request body."""
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


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


class WhatsApp:
    """One set of credentials. Pass a shared `client` to pool connections across many sends;
    without one, each call opens and closes its own.

    `waba_id` and `phone_number_id` are defaults; every method that uses one also accepts it
    as an argument."""

    def __init__(
        self,
        access_token: str,
        *,
        waba_id: str = "",
        phone_number_id: str = "",
        graph_version: str = "v26.0",
        timeout: httpx.Timeout | float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.access_token = access_token
        self.waba_id = waba_id
        self.phone_number_id = phone_number_id
        self.base_url = f"{GRAPH_URL}/{graph_version}"
        self.timeout = timeout
        self.client = client

    async def _send(self, method: str, url: str, *, timeout=None, auth: str = "Bearer",
                    headers: dict | None = None, **kwargs) -> httpx.Response:
        # Explicit per-call timeout: a shared client's own default must not apply here.
        timeout = timeout or self.timeout
        headers = {"Authorization": f"{auth} {self.access_token}", **(headers or {})}
        client = self.client or httpx.AsyncClient(timeout=timeout)
        try:
            return await client.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:
            raise _error(f"Could not reach the Graph API: {exc}") from exc
        finally:
            if client is not self.client:
                await client.aclose()

    async def request(
        self, method: str, path: str, *, timeout: httpx.Timeout | float | None = None, **kwargs
    ) -> dict:
        """Call any Graph API path; extra kwargs go to httpx (json, params, data, files)."""
        return _parse(await self._send(method, f"{self.base_url}/{path}", timeout=timeout, **kwargs))

    def _phone(self, phone_number_id: str | None) -> str:
        return phone_number_id or self.phone_number_id

    def _waba(self, waba_id: str | None) -> str:
        return waba_id or self.waba_id

    # Messages

    async def send_message(self, payload: dict, *, phone_number_id: str | None = None) -> dict:
        """Send any message body (text, media, interactive, ...) as Meta defines it."""
        return await self.request(
            "POST", f"{self._phone(phone_number_id)}/messages",
            json=payload, timeout=httpx.Timeout(15),
        )

    async def _send_to(self, to: str, type_: str, content: dict, *, reply_to: str | None = None,
                       phone_number_id: str | None = None) -> dict:
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual",
                   "to": to, "type": type_, type_: content}
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        return await self.send_message(payload, phone_number_id=phone_number_id)

    async def send_text(self, to: str, body: str, *, preview_url: bool = False,
                        reply_to: str | None = None, phone_number_id: str | None = None) -> dict:
        return await self._send_to(to, "text", {"body": body, "preview_url": preview_url},
                                   reply_to=reply_to, phone_number_id=phone_number_id)

    async def send_media(self, to: str, kind: str, *, media_id: str | None = None,
                         link: str | None = None, caption: str | None = None,
                         filename: str | None = None, reply_to: str | None = None,
                         phone_number_id: str | None = None) -> dict:
        """`kind` is image, video, audio, document, or sticker; give either `media_id` or `link`."""
        content = _clean({"id": media_id, "link": link, "caption": caption, "filename": filename})
        return await self._send_to(to, kind, content, reply_to=reply_to,
                                   phone_number_id=phone_number_id)

    async def send_location(self, to: str, latitude: float, longitude: float, *,
                            name: str | None = None, address: str | None = None,
                            reply_to: str | None = None, phone_number_id: str | None = None) -> dict:
        content = _clean({"latitude": latitude, "longitude": longitude, "name": name, "address": address})
        return await self._send_to(to, "location", content, reply_to=reply_to,
                                   phone_number_id=phone_number_id)

    async def send_contacts(self, to: str, contacts: list[dict], *, reply_to: str | None = None,
                            phone_number_id: str | None = None) -> dict:
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual",
                   "to": to, "type": "contacts", "contacts": contacts}
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        return await self.send_message(payload, phone_number_id=phone_number_id)

    async def send_interactive(self, to: str, interactive: dict, *, reply_to: str | None = None,
                               phone_number_id: str | None = None) -> dict:
        """Buttons, lists, CTA URLs, flows, products, location requests: `interactive` is
        Meta's object as-is."""
        return await self._send_to(to, "interactive", interactive, reply_to=reply_to,
                                   phone_number_id=phone_number_id)

    async def send_reaction(self, to: str, message_id: str, emoji: str, *,
                            phone_number_id: str | None = None) -> dict:
        """An empty `emoji` removes the reaction."""
        return await self._send_to(to, "reaction", {"message_id": message_id, "emoji": emoji},
                                   phone_number_id=phone_number_id)

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
            "POST", f"{self._phone(phone_number_id)}/{edge}", json=payload, timeout=timeout,
        )

    async def mark_message_read(self, wamid: str, *, typing: bool = False,
                                phone_number_id: str | None = None) -> dict:
        """`typing` also shows a typing indicator until you reply (max 25 seconds)."""
        payload: dict = {"messaging_product": "whatsapp", "status": "read", "message_id": wamid}
        if typing:
            payload["typing_indicator"] = {"type": "text"}
        return await self.request("POST", f"{self._phone(phone_number_id)}/messages", json=payload)

    # Media

    async def upload_message_media(
        self, *, file_name: str, file_type: str, content: bytes, phone_number_id: str | None = None
    ) -> str:
        """Upload send-time media and return its ID (templates use upload_template_sample)."""
        response = await self.request(
            "POST", f"{self._phone(phone_number_id)}/media",
            data={"messaging_product": "whatsapp", "type": file_type},
            files={"file": (file_name, content, file_type)},
        )
        media_id = response.get("id")
        if not media_id:
            raise _error("Meta returned no media ID")
        return str(media_id)

    async def get_media(self, media_id: str, *, phone_number_id: str | None = None) -> dict:
        """{url, mime_type, sha256, file_size, id}; the url expires after 5 minutes."""
        return await self.request("GET", media_id, params=_query(phone_number_id=phone_number_id))

    async def download_media(self, media_id: str, *, phone_number_id: str | None = None) -> bytes:
        url = (await self.get_media(media_id, phone_number_id=phone_number_id)).get("url")
        if not url:
            raise _error("Meta returned no media URL")
        response = await self._send("GET", url, timeout=httpx.Timeout(120.0))
        if response.status_code >= 400:
            _parse(response)
        return response.content

    async def delete_media(self, media_id: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request("DELETE", media_id, params=_query(phone_number_id=phone_number_id))

    # Templates

    async def create_message_template(self, *, name: str, language: str, category: str,
                                      components: list[dict] | None = None,
                                      waba_id: str | None = None, **extra) -> dict:
        """Submit a template for review. `extra`: parameter_format, sub_category,
        message_send_ttl_seconds, allow_category_change, library_template_name, ... ."""
        payload = _clean({"name": name, "language": language, "category": category,
                          "components": components, **extra})
        return await self.request("POST", f"{self._waba(waba_id)}/message_templates", json=payload)

    async def update_message_template(self, meta_template_id: str, *,
                                      components: list[dict] | None = None, **extra) -> dict:
        """Name/language are immutable. The prior approved version sends while the edit is
        reviewed."""
        return await self.request("POST", str(meta_template_id),
                                  json=_clean({"components": components, **extra}))

    async def get_message_template(
        self, meta_template_id: str, timeout: httpx.Timeout | float | None = None,
        fields: str = TEMPLATE_FIELDS,
    ) -> dict:
        return await self.request("GET", str(meta_template_id), timeout=timeout,
                                  params={"fields": fields})

    async def list_message_templates(self, limit: int = 100, after: str | None = None, *,
                                     fields: str = TEMPLATE_FIELDS, waba_id: str | None = None,
                                     **filters) -> dict:
        """`filters`: name, status, category, language, content, quality_score, before."""
        return await self.request("GET", f"{self._waba(waba_id)}/message_templates",
                                  params=_page(fields, limit, after, **filters))

    async def delete_message_template(self, name: str | None = None,
                                      meta_template_id: str | None = None, *,
                                      hsm_ids: list[str] | None = None,
                                      waba_id: str | None = None) -> dict:
        # Without hsm_id Meta deletes every language variant sharing the name.
        params = _query(name=name, hsm_id=meta_template_id and str(meta_template_id), hsm_ids=hsm_ids)
        return await self.request("DELETE", f"{self._waba(waba_id)}/message_templates", params=params)

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
                                    timeout=httpx.Timeout(120.0))
        handle = _parse(response).get("h")
        if not handle:
            raise _error("Meta returned no media handle")
        return handle

    # Flows

    async def list_flows(self, *, fields: str | None = None, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/flows", params=_query(fields=fields))

    async def create_flow(self, *, name: str, categories: list[str], flow_json: str | None = None,
                          publish: bool | None = None, clone_flow_id: str | None = None,
                          endpoint_uri: str | None = None, waba_id: str | None = None) -> dict:
        payload = _clean({"name": name, "categories": categories, "flow_json": flow_json,
                          "publish": publish, "clone_flow_id": clone_flow_id,
                          "endpoint_uri": endpoint_uri})
        return await self.request("POST", f"{self._waba(waba_id)}/flows", json=payload)

    async def get_flow(self, flow_id: str, fields: str | None = None) -> dict:
        """Metrics and previews are fields too, e.g. `preview.invalidate(true)` or
        `metric.name(ENDPOINT_REQUEST_COUNT).granularity(DAY).since(2026-01-01)`."""
        return await self.request("GET", flow_id, params=_query(fields=fields))

    async def update_flow(self, flow_id: str, **metadata) -> dict:
        """`metadata`: name, categories, endpoint_uri, application_id."""
        return await self.request("POST", flow_id, json=_clean(metadata))

    async def delete_flow(self, flow_id: str) -> dict:
        """Only DRAFT flows can be deleted."""
        return await self.request("DELETE", flow_id)

    async def upload_flow_json(self, flow_id: str, flow_json: str | bytes) -> dict:
        content = flow_json.encode() if isinstance(flow_json, str) else flow_json
        return await self.request(
            "POST", f"{flow_id}/assets",
            data={"name": "flow.json", "asset_type": "FLOW_JSON"},
            files={"file": ("flow.json", content, "application/json")},
        )

    async def list_flow_assets(self, flow_id: str) -> dict:
        return await self.request("GET", f"{flow_id}/assets")

    async def publish_flow(self, flow_id: str) -> dict:
        return await self.request("POST", f"{flow_id}/publish")

    async def deprecate_flow(self, flow_id: str) -> dict:
        return await self.request("POST", f"{flow_id}/deprecate")

    async def migrate_flows(self, source_waba_id: str, *, source_flow_names: list[str] | None = None,
                            waba_id: str | None = None) -> dict:
        return await self.request(
            "POST", f"{self._waba(waba_id)}/migrate_flows",
            params=_query(source_waba_id=source_waba_id, source_flow_names=source_flow_names),
        )

    # Phone numbers

    async def list_phone_numbers(self, *, fields: str | None = None, waba_id: str | None = None,
                                 **filters) -> dict:
        """`filters`: filtering, sort, limit, after, before."""
        return await self.request("GET", f"{self._waba(waba_id)}/phone_numbers",
                                  params=_query(fields=fields, **filters))

    async def create_phone_number(self, *, cc: str, phone_number: str, verified_name: str,
                                  waba_id: str | None = None, **extra) -> dict:
        payload = _clean({"cc": cc, "phone_number": phone_number, "verified_name": verified_name, **extra})
        return await self.request("POST", f"{self._waba(waba_id)}/phone_numbers", json=payload)

    async def get_phone_number(self, phone_number_id: str | None = None, *,
                               fields: str | None = None) -> dict:
        return await self.request("GET", self._phone(phone_number_id), params=_query(fields=fields))

    async def update_phone_number(self, phone_number_id: str | None = None, **body) -> dict:
        """`body`: pin (two-step verification), new_display_name, search_visibility,
        webhook_configuration, username, ... ."""
        return await self.request("POST", self._phone(phone_number_id), json=_clean(body))

    async def set_two_step_pin(self, pin: str, *, phone_number_id: str | None = None) -> dict:
        """Disabling two-step verification is only possible in WhatsApp Manager."""
        return await self.update_phone_number(phone_number_id, pin=pin)

    async def register_phone_number(self, pin: str, *, data_localization_region: str | None = None,
                                    phone_number_id: str | None = None) -> dict:
        """Limited to 10 calls per number per 72 hours."""
        payload = _clean({"messaging_product": "whatsapp", "pin": pin,
                          "data_localization_region": data_localization_region})
        return await self.request("POST", f"{self._phone(phone_number_id)}/register", json=payload)

    async def deregister_phone_number(self, *, phone_number_id: str | None = None) -> dict:
        return await self.request("POST", f"{self._phone(phone_number_id)}/deregister")

    async def request_verification_code(self, code_method: str = "SMS", language: str = "en_US", *,
                                        phone_number_id: str | None = None) -> dict:
        """`code_method`: SMS or VOICE."""
        return await self.request("POST", f"{self._phone(phone_number_id)}/request_code",
                                  json={"code_method": code_method, "language": language})

    async def verify_code(self, code: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request("POST", f"{self._phone(phone_number_id)}/verify_code",
                                  json={"code": code})

    async def get_sending_limits(self, phone_number_id: str | None = None) -> dict:
        """Throughput, coexistence, and messaging limit as Meta reports them; absent fields are
        None."""
        payload = await self.request(
            "GET", self._phone(phone_number_id),
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

    async def get_phone_settings(self, *, include_sip_credentials: bool | None = None,
                                 phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/settings",
                                  params=_query(include_sip_credentials=include_sip_credentials))

    async def update_phone_settings(self, phone_number_id: str | None = None, **settings) -> dict:
        """`settings`: calling, storage_configuration, user_identity_change, payload_encryption."""
        return await self.request("POST", f"{self._phone(phone_number_id)}/settings",
                                  json=_clean(settings))

    async def get_business_profile(self, *, fields: str = "about,address,description,email,"
                                   "profile_picture_url,websites,vertical",
                                   phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/whatsapp_business_profile",
                                  params={"fields": fields})

    async def update_business_profile(self, phone_number_id: str | None = None, **profile) -> dict:
        """`profile`: about, address, description, email, vertical, websites,
        profile_picture_handle (from upload_template_sample)."""
        return await self.request("POST", f"{self._phone(phone_number_id)}/whatsapp_business_profile",
                                  json={"messaging_product": "whatsapp", **_clean(profile)})

    async def get_commerce_settings(self, *, phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/whatsapp_commerce_settings")

    async def update_commerce_settings(self, *, is_cart_enabled: bool | None = None,
                                       is_catalog_visible: bool | None = None,
                                       phone_number_id: str | None = None) -> dict:
        return await self.request(
            "POST", f"{self._phone(phone_number_id)}/whatsapp_commerce_settings",
            params=_query(is_cart_enabled=is_cart_enabled, is_catalog_visible=is_catalog_visible),
        )

    async def get_encryption_key(self, *, phone_number_id: str | None = None) -> dict:
        """The Flows endpoint public key and its signature status."""
        return await self.request("GET", f"{self._phone(phone_number_id)}/whatsapp_business_encryption")

    async def set_encryption_key(self, public_key_pem: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request("POST", f"{self._phone(phone_number_id)}/whatsapp_business_encryption",
                                  data={"business_public_key": public_key_pem})

    async def get_compliance_info(self, *, phone_number_id: str | None = None) -> dict:
        """India-based businesses: the grievance officer and entity details Meta requires."""
        return await self.request("GET", f"{self._phone(phone_number_id)}/business_compliance_info")

    async def update_compliance_info(self, phone_number_id: str | None = None, **info) -> dict:
        return await self.request("POST", f"{self._phone(phone_number_id)}/business_compliance_info",
                                  json={"messaging_product": "whatsapp", **_clean(info)})

    async def get_official_business_account(self, *, phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/official_business_account")

    async def request_official_business_account(self, phone_number_id: str | None = None,
                                                **application) -> dict:
        """Apply for the green badge; `application` is Meta's OBA request body."""
        return await self.request("POST", f"{self._phone(phone_number_id)}/official_business_account",
                                  json=_clean(application))

    async def set_conversational_automation(self, *, enable_welcome_message: bool | None = None,
                                            prompts: list[str] | None = None,
                                            commands: list[dict] | None = None,
                                            phone_number_id: str | None = None) -> dict:
        """Welcome message, ice breakers (`prompts`), and `/` commands
        ({command_name, command_description})."""
        payload = _clean({"enable_welcome_message": enable_welcome_message,
                          "prompts": prompts, "commands": commands})
        return await self.request("POST", f"{self._phone(phone_number_id)}/conversational_automation",
                                  json=payload)

    # QR codes

    async def list_qr_codes(self, *, code: str | None = None, fields: str | None = None,
                            phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/message_qrdls",
                                  params=_query(code=code, fields=fields))

    async def get_qr_code(self, qr_code_id: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/message_qrdls/{qr_code_id}")

    async def create_qr_code(self, prefilled_message: str, *, image_format: str | None = "PNG",
                             code: str | None = None, phone_number_id: str | None = None) -> dict:
        """Pass `code` to update an existing QR code's message. `image_format`: PNG or SVG."""
        payload = _clean({"prefilled_message": prefilled_message, "generate_qr_image": image_format,
                          "code": code})
        return await self.request("POST", f"{self._phone(phone_number_id)}/message_qrdls", json=payload)

    async def delete_qr_code(self, qr_code_id: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request("DELETE", f"{self._phone(phone_number_id)}/message_qrdls/{qr_code_id}")

    # Blocking

    async def list_blocked_users(self, *, limit: int | None = None, after: str | None = None,
                                 phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/block_users",
                                  params=_page(limit=limit, after=after))

    async def block_users(self, users: list[str], *, phone_number_id: str | None = None) -> dict:
        """Only users who messaged you in the last 24 hours can be blocked."""
        return await self._block("POST", users, phone_number_id)

    async def unblock_users(self, users: list[str], *, phone_number_id: str | None = None) -> dict:
        return await self._block("DELETE", users, phone_number_id)

    async def _block(self, method: str, users: list[str], phone_number_id: str | None) -> dict:
        return await self.request(method, f"{self._phone(phone_number_id)}/block_users", json={
            "messaging_product": "whatsapp", "block_users": [{"user": u} for u in users]})

    # Calling

    async def call(self, action: str, *, call_id: str | None = None, to: str | None = None,
                   session: dict | None = None, callback_data: str | None = None,
                   phone_number_id: str | None = None) -> dict:
        """`action`: connect (start a call `to` a user), pre_accept, accept, reject, terminate,
        media_update.
        `session` is {sdp_type, sdp} for WebRTC negotiation."""
        payload = _clean({"messaging_product": "whatsapp", "action": action, "call_id": call_id,
                          "to": to, "session": session, "biz_opaque_callback_data": callback_data})
        return await self.request("POST", f"{self._phone(phone_number_id)}/calls", json=payload)

    async def get_call_permissions(self, user_wa_id: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/call_permissions",
                                  params={"user_wa_id": user_wa_id})

    # Groups

    async def create_group(self, subject: str, *, description: str | None = None,
                           join_approval_mode: str | None = None,
                           phone_number_id: str | None = None) -> dict:
        payload = _clean({"messaging_product": "whatsapp", "subject": subject,
                          "description": description, "join_approval_mode": join_approval_mode})
        return await self.request("POST", f"{self._phone(phone_number_id)}/groups", json=payload)

    async def list_groups(self, *, limit: int | None = None, after: str | None = None,
                          phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/groups",
                                  params=_page(limit=limit, after=after))

    async def get_group(self, group_id: str, *, fields: str | None = None) -> dict:
        return await self.request("GET", group_id, params=_query(fields=fields))

    async def update_group(self, group_id: str, *, subject: str | None = None,
                           description: str | None = None) -> dict:
        return await self.request("POST", group_id, json=_clean(
            {"messaging_product": "whatsapp", "subject": subject, "description": description}))

    async def delete_group(self, group_id: str) -> dict:
        return await self.request("DELETE", group_id)

    async def create_group_invite_link(self, group_id: str) -> dict:
        return await self.request("POST", f"{group_id}/invite_link",
                                  json={"messaging_product": "whatsapp"})

    async def delete_group_invite_link(self, group_id: str) -> dict:
        return await self.request("DELETE", f"{group_id}/invite_link",
                                  json={"messaging_product": "whatsapp"})

    async def list_group_join_requests(self, group_id: str) -> dict:
        return await self.request("GET", f"{group_id}/join_requests")

    async def approve_group_join_requests(self, group_id: str, join_requests: list[str]) -> dict:
        return await self.request("POST", f"{group_id}/join_requests", json={
            "messaging_product": "whatsapp", "join_requests": join_requests})

    async def reject_group_join_requests(self, group_id: str, join_requests: list[str]) -> dict:
        return await self.request("DELETE", f"{group_id}/join_requests", json={
            "messaging_product": "whatsapp", "join_requests": join_requests})

    async def add_group_participants(self, group_id: str, participants: list[str]) -> dict:
        return await self._participants("POST", group_id, participants)

    async def remove_group_participants(self, group_id: str, participants: list[str]) -> dict:
        return await self._participants("DELETE", group_id, participants)

    async def _participants(self, method: str, group_id: str, participants: list[str]) -> dict:
        return await self.request(method, f"{group_id}/participants", json={
            "messaging_product": "whatsapp", "participants": [{"user": p} for p in participants]})

    # WhatsApp Business Account

    async def get_business_account(self, *, fields: str | None = None,
                                   waba_id: str | None = None) -> dict:
        return await self.request("GET", self._waba(waba_id), params=_query(fields=fields))

    async def update_business_account(self, *, name: str | None = None, timezone_id: str | None = None,
                                      waba_id: str | None = None) -> dict:
        return await self.request("POST", self._waba(waba_id),
                                  json=_clean({"name": name, "timezone_id": timezone_id}))

    async def get_analytics(self, metric: str, *, start: int, end: int, granularity: str,
                            waba_id: str | None = None, **filters) -> dict:
        """`metric`: analytics, conversation_analytics, pricing_analytics, template_analytics,
        template_group_analytics. `start`/`end` are UNIX seconds; `filters` (phone_numbers,
        country_codes, metric_types, template_ids, dimensions, ...) follow Meta's names."""
        field = f"{metric}.start({start}).end({end}).granularity({granularity})"
        field += "".join(f".{k}({json.dumps(v)})" for k, v in _clean(filters).items())
        return await self.get_business_account(fields=field, waba_id=waba_id)

    async def list_subscribed_apps(self, *, waba_id: str | None = None) -> dict:
        """Apps currently receiving webhooks for this WABA."""
        return await self.request("GET", f"{self._waba(waba_id)}/subscribed_apps")

    async def subscribe_app_to_waba(self, *, override_callback_uri: str | None = None,
                                    verify_token: str | None = None,
                                    waba_id: str | None = None) -> dict:
        """Subscribe the token's app to WABA webhooks; dashboard setup alone doesn't deliver.
        `override_callback_uri` sends this WABA's webhooks to a different URL."""
        body = _clean({"override_callback_uri": override_callback_uri, "verify_token": verify_token})
        return await self.request("POST", f"{self._waba(waba_id)}/subscribed_apps", json=body or None)

    async def unsubscribe_app_from_waba(self, *, waba_id: str | None = None) -> dict:
        return await self.request("DELETE", f"{self._waba(waba_id)}/subscribed_apps")

    async def list_assigned_users(self, business_id: str, *, fields: str | None = None,
                                  waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/assigned_users",
                                  params=_query(business=business_id, fields=fields))

    async def assign_user(self, user_id: str, tasks: list[str], *, waba_id: str | None = None) -> dict:
        """`tasks`: MANAGE, DEVELOP, MANAGE_TEMPLATES, MANAGE_PHONE, VIEW_COST, ... ."""
        return await self.request("POST", f"{self._waba(waba_id)}/assigned_users",
                                  json={"user": user_id, "tasks": tasks})

    async def remove_assigned_user(self, user_id: str, *, waba_id: str | None = None) -> dict:
        return await self.request("DELETE", f"{self._waba(waba_id)}/assigned_users",
                                  json={"user": user_id})

    async def list_schedules(self, *, fields: str | None = None, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/schedules", params=_query(fields=fields))

    async def create_schedule(self, waba_id: str | None = None, **schedule) -> dict:
        """`schedule`: name, hsm_id (template), audience_id, delivery_time, description."""
        return await self.request("POST", f"{self._waba(waba_id)}/schedules", json=_clean(schedule))

    async def list_activities(self, *, fields: str | None = None, limit: int | None = None,
                              after: str | None = None, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/activities",
                                  params=_page(fields, limit, after))

    async def list_waba_solutions(self, *, fields: str | None = None, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/solutions", params=_query(fields=fields))

    async def app_id(self) -> str:
        """The Meta app the access token belongs to."""
        payload = await self.request("GET", "debug_token", params={"input_token": self.access_token})
        app_id = (payload.get("data") or {}).get("app_id")
        if not app_id:
            raise _error("Could not determine the Meta app for this token")
        return str(app_id)

    # Business portfolio (tech providers and partners)

    async def get_business(self, business_id: str, *, fields: str | None = None) -> dict:
        return await self.request("GET", business_id, params=_query(fields=fields))

    async def list_owned_business_accounts(self, business_id: str, **filters) -> dict:
        return await self.request("GET", f"{business_id}/owned_whatsapp_business_accounts",
                                  params=_query(**filters))

    async def list_client_business_accounts(self, business_id: str, **filters) -> dict:
        return await self.request("GET", f"{business_id}/client_whatsapp_business_accounts",
                                  params=_query(**filters))

    async def list_business_accounts(self, business_id: str, **filters) -> dict:
        return await self.request("GET", f"{business_id}/whatsapp_business_accounts",
                                  params=_query(**filters))

    async def create_business_account(self, business_id: str, **account) -> dict:
        return await self.request("POST", f"{business_id}/whatsapp_business_accounts",
                                  json=_clean(account))

    async def add_business_phone_numbers(self, business_id: str, **body) -> dict:
        return await self.request("POST", f"{business_id}/add_phone_numbers", json=_clean(body))

    async def list_extended_credits(self, business_id: str, *, fields: str | None = None) -> dict:
        return await self.request("GET", f"{business_id}/extendedcredits", params=_query(fields=fields))

    async def onboard_partners_to_mm_lite(self, business_id: str, *, solution_id: str | None = None,
                                          **body) -> dict:
        return await self.request("POST", f"{business_id}/onboard_partners_to_mm_lite",
                                  params=_query(solution_id=solution_id), json=_clean(body) or None)

    async def list_user_business_accounts(self, user_id: str, **filters) -> dict:
        """WABAs assigned to a (system) user."""
        return await self.request("GET", f"{user_id}/assigned_whatsapp_business_accounts",
                                  params=_query(**filters))

    async def list_message_history_events(self, message_history_id: str, **filters) -> dict:
        return await self.request("GET", f"{message_history_id}/events", params=_query(**filters))

    async def get_node(self, node_id: str, *, fields: str | None = None) -> dict:
        """Any node by ID: account number, migration intent, bot, business profile, ... ."""
        return await self.request("GET", node_id, params=_query(fields=fields))

    async def update_node(self, node_id: str, **body) -> dict:
        return await self.request("POST", node_id, json=_clean(body))

    # Pre-verified phone numbers

    async def list_preverified_numbers(self, business_id: str, **filters) -> dict:
        return await self.request("GET", f"{business_id}/preverified_numbers", params=_query(**filters))

    async def share_preverified_numbers(self, business_id: str, **body) -> dict:
        return await self.request("POST", f"{business_id}/share_preverified_numbers", json=_clean(body))

    async def delete_preverified_number(self, preverified_id: str) -> dict:
        return await self.request("DELETE", preverified_id)

    async def list_preverified_number_partners(self, preverified_id: str, **filters) -> dict:
        return await self.request("GET", f"{preverified_id}/partners", params=_query(**filters))

    async def request_preverified_code(self, preverified_id: str, code_method: str = "SMS",
                                       language: str = "en_US") -> dict:
        return await self.request("POST", f"{preverified_id}/request_code",
                                  json={"code_method": code_method, "language": language})

    async def verify_preverified_code(self, preverified_id: str, code: str) -> dict:
        return await self.request("POST", f"{preverified_id}/verify_code", json={"code": code})

    # Multi-Partner Solutions

    async def list_app_solutions(self, app_id: str, **filters) -> dict:
        return await self.request("GET", f"{app_id}/whatsapp_business_solutions", params=_query(**filters))

    async def create_solution(self, app_id: str, **solution) -> dict:
        return await self.request("POST", f"{app_id}/whatsapp_business_solution", json=_clean(solution))

    async def list_connected_client_businesses(self, app_id: str, **filters) -> dict:
        return await self.request("GET", f"{app_id}/connected_client_businesses", params=_query(**filters))

    async def get_solution_access_token(self, solution_id: str, business_id: str) -> dict:
        return await self.request("GET", f"{solution_id}/access_token", params={"business_id": business_id})

    async def solution_action(self, solution_id: str, action: str, **body) -> dict:
        """`action`: accept, reject, send_deactivation_request, accept_deactivation_request,
        reject_deactivation_request."""
        return await self.request("POST", f"{solution_id}/{action}", json=_clean(body) or None)
