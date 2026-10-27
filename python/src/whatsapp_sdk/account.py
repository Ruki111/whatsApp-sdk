"""Phone numbers, profile and settings, QR codes, blocking, calling, and groups."""


from ._base import _Base, _clean, _page, _query


class AccountAPI(_Base):
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

    async def get_username(self, *, phone_number_id: str | None = None) -> dict:
        """{username, status}; status is approved, reserved, ... ."""
        return await self.request("GET", f"{self._phone(phone_number_id)}/username")

    async def set_username(self, username: str, *, transfer_action: str | None = None,
                           phone_number_id: str | None = None) -> dict:
        return await self.request("POST", f"{self._phone(phone_number_id)}/username",
                                  json=_clean({"username": username, "transfer_action": transfer_action}))

    async def get_username_suggestions(self, *, phone_number_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._phone(phone_number_id)}/username_suggestions")

    async def get_contact(self, bsuid: str, *, phone_number_id: str | None = None) -> dict:
        """The contact book entry for a business-scoped user ID."""
        return await self.request("GET", f"{self._phone(phone_number_id)}/contact_book",
                                  params={"messaging_product": "whatsapp", "bsuid": bsuid})

    async def delete_contact(self, bsuid: str, *, phone_number_id: str | None = None) -> dict:
        return await self.request("DELETE", f"{self._phone(phone_number_id)}/contact_book",
                                  params={"messaging_product": "whatsapp", "bsuid": bsuid})

    async def sync_business_app_data(self, sync_type: str = "smb_app_state_sync", *,
                                     phone_number_id: str | None = None) -> dict:
        """Coexistence numbers: replay the WhatsApp Business app's contacts
        (smb_app_state_sync) or chat history (history) as webhooks. Allowed once."""
        return await self.request("POST", f"{self._phone(phone_number_id)}/smb_app_data",
                                  json={"messaging_product": "whatsapp", "sync_type": sync_type})

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

    async def get_group_invite_link(self, group_id: str) -> dict:
        return await self.request("GET", f"{group_id}/invite_link")

    async def create_group_invite_link(self, group_id: str) -> dict:
        """Creates the link, or resets it (old link stops working)."""
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
