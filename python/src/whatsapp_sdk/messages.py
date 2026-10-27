"""Messages, media, templates, and Flows."""

from typing import BinaryIO

import httpx

from ._base import TEMPLATE_FIELDS, _Base, _clean, _page, _query, _recipient
from .errors import _error


class MessagesAPI(_Base):
    # Messages

    async def send_message(self, payload: dict, *, phone_number_id: str | None = None) -> dict:
        """Send any message body (text, media, interactive, ...) as Meta defines it."""
        return await self.request(
            "POST", f"{self._phone(phone_number_id)}/messages",
            json=payload, timeout=httpx.Timeout(15),
        )

    async def send(self, to: str, type_: str, content: dict | list, *,
                   recipient_type: str = "individual", reply_to: str | None = None,
                   callback_data: str | None = None, phone_number_id: str | None = None) -> dict:
        """Send any message type: `content` is Meta's object for `type_`. `to` is a phone
        number, a business-scoped user ID (BSUID), or a group ID with recipient_type="group"."""
        payload = {"messaging_product": "whatsapp", "recipient_type": recipient_type,
                   **_recipient(to), "type": type_, type_: content}
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        if callback_data:
            payload["biz_opaque_callback_data"] = callback_data
        return await self.send_message(payload, phone_number_id=phone_number_id)

    async def send_text(self, to: str, body: str, *, preview_url: bool = False,
                        reply_to: str | None = None, phone_number_id: str | None = None) -> dict:
        return await self.send(to, "text", {"body": body, "preview_url": preview_url},
                               reply_to=reply_to, phone_number_id=phone_number_id)

    async def send_media(self, to: str, kind: str, *, media_id: str | None = None,
                         link: str | None = None, caption: str | None = None,
                         filename: str | None = None, reply_to: str | None = None,
                         phone_number_id: str | None = None) -> dict:
        """`kind` is image, video, audio, document, or sticker; give either `media_id` or `link`."""
        content = _clean({"id": media_id, "link": link, "caption": caption, "filename": filename})
        return await self.send(to, kind, content, reply_to=reply_to,
                               phone_number_id=phone_number_id)

    async def send_location(self, to: str, latitude: float, longitude: float, *,
                            name: str | None = None, address: str | None = None,
                            reply_to: str | None = None, phone_number_id: str | None = None) -> dict:
        content = _clean({"latitude": latitude, "longitude": longitude, "name": name, "address": address})
        return await self.send(to, "location", content, reply_to=reply_to,
                               phone_number_id=phone_number_id)

    async def send_contacts(self, to: str, contacts: list[dict], *, reply_to: str | None = None,
                            phone_number_id: str | None = None) -> dict:
        return await self.send(to, "contacts", contacts, reply_to=reply_to,
                               phone_number_id=phone_number_id)

    async def send_interactive(self, to: str, interactive: dict, *, reply_to: str | None = None,
                               phone_number_id: str | None = None) -> dict:
        """Buttons, lists, CTA URLs, flows, products, location requests: `interactive` is
        Meta's object as-is."""
        return await self.send(to, "interactive", interactive, reply_to=reply_to,
                               phone_number_id=phone_number_id)

    async def send_reaction(self, to: str, message_id: str, emoji: str, *,
                            phone_number_id: str | None = None) -> dict:
        """An empty `emoji` removes the reaction."""
        return await self.send(to, "reaction", {"message_id": message_id, "emoji": emoji},
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
            **_recipient(to),
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
        self, *, file_name: str, file_type: str, content: bytes | BinaryIO,
        phone_number_id: str | None = None,
    ) -> str:
        """Upload send-time media (bytes or an open file) and return its ID; templates use
        upload_template_sample."""
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

    async def list_template_library(self, **filters) -> dict:
        """Meta's pre-written templates. `filters`: search, topic, usecase, industry, language,
        name. Create one with create_message_template(library_template_name=...)."""
        return await self.request("GET", "message_template_library", params=_query(**filters))

    async def compare_templates(self, template_id: str, other_template_id: str, *, start: int,
                                end: int) -> dict:
        """Sends, block rate, and top block reason of two templates (7/30/60/90-day windows)."""
        return await self.request("GET", f"{template_id}/compare", params=_query(
            template_ids=[other_template_id], start=start, end=end))

    async def preview_authentication_templates(self, *, languages: list[str] | None = None,
                                               waba_id: str | None = None, **options) -> dict:
        """`options`: add_security_recommendation, code_expiration_minutes, button_types."""
        params = _query(category="AUTHENTICATION",
                        languages=",".join(languages) if languages else None, **options)
        return await self.request("GET", f"{self._waba(waba_id)}/message_template_previews",
                                  params=params)

    async def upsert_authentication_templates(self, *, name: str, languages: list[str],
                                              components: list[dict],
                                              waba_id: str | None = None, **extra) -> dict:
        """Create or update one authentication template in many languages at once."""
        return await self.request("POST", f"{self._waba(waba_id)}/upsert_message_templates", json=_clean({
            "name": name, "languages": languages, "category": "AUTHENTICATION",
            "components": components, **extra}))

    async def migrate_message_templates(self, source_waba_id: str, *, page_number: int = 0,
                                        count: int | None = None,
                                        template_ids: list[str] | None = None,
                                        waba_id: str | None = None) -> dict:
        """Copy approved templates from another WABA of the same business into this one."""
        return await self.request("POST", f"{self._waba(waba_id)}/migrate_message_templates", json=_clean({
            "source_waba_id": source_waba_id, "page_number": page_number, "count": count,
            "template_ids": template_ids}))

    async def create_template_group(self, name: str, template_ids: list[str], *,
                                    description: str | None = None,
                                    waba_id: str | None = None) -> dict:
        """Read, update, or delete a group with get_node / update_node / delete_node."""
        return await self.request("POST", f"{self._waba(waba_id)}/template_groups", json=_clean({
            "name": name, "description": description,
            "whatsapp_business_templates": template_ids}))

    async def list_template_groups(self, *, fields: str | None = None,
                                   waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/template_groups",
                                  params=_query(fields=fields))

    # Flows

    async def list_flows(self, *, fields: str | None = None, limit: int | None = None,
                         after: str | None = None, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/flows",
                                  params=_page(fields, limit, after))

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
