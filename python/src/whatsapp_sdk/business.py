"""WhatsApp Business Account, payments, partners, credit lines, pre-verified numbers, and
Multi-Partner Solutions."""

import json

from ._base import _Base, _clean, _page, _query
from .errors import _error

# Analytics served by their own WABA edge rather than as a field on the WABA.
_ANALYTICS_EDGES = frozenset({"template_analytics", "template_group_analytics", "group_analytics"})


class BusinessAPI(_Base):
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
        """`metric`: analytics, conversation_analytics, pricing_analytics, call_analytics,
        template_analytics, template_group_analytics, group_analytics. `start`/`end` are UNIX
        seconds; `filters` (phone_numbers, country_codes, metric_types, template_ids,
        group_ids, dimensions, ...) follow Meta's names."""
        if metric in _ANALYTICS_EDGES:
            return await self.request("GET", f"{self._waba(waba_id)}/{metric}", params=_query(
                start=start, end=end, granularity=granularity, **filters))
        field = f"{metric}.start({start}).end({end}).granularity({granularity})"
        field += "".join(f".{k}({json.dumps(v)})" for k, v in _clean(filters).items())
        return await self.get_business_account(fields=field, waba_id=waba_id)

    async def get_product_catalogs(self, *, fields: str | None = None,
                                   waba_id: str | None = None) -> dict:
        """The catalog connected to the WABA, e.g. fields="id,name,product_count"."""
        return await self.request("GET", f"{self._waba(waba_id)}/product_catalogs",
                                  params=_query(fields=fields))

    async def list_catalog_products(self, catalog_id: str, *, fields: str | None = None,
                                    limit: int | None = None, after: str | None = None,
                                    filter: dict | None = None) -> dict:
        """`filter` is Meta's product filter, e.g. {"name": {"i_contains": "shoe"}}."""
        return await self.request("GET", f"{catalog_id}/products",
                                  params=_page(fields, limit, after, filter=filter))

    async def connect_product_catalog(self, catalog_id: str, *, waba_id: str | None = None) -> dict:
        return await self.request("POST", f"{self._waba(waba_id)}/product_catalogs",
                                  json={"catalog_id": catalog_id})

    async def list_welcome_sequences(self, *, sequence_id: str | None = None,
                                     waba_id: str | None = None) -> dict:
        """Click-to-WhatsApp ad welcome messages."""
        return await self.request("GET", f"{self._waba(waba_id)}/welcome_message_sequences",
                                  params=_query(sequence_id=sequence_id))

    async def save_welcome_sequence(self, name: str, sequence: dict, *,
                                    sequence_id: str | None = None,
                                    waba_id: str | None = None) -> dict:
        """Create, or update when `sequence_id` is given. `sequence`: {text, autofill_message,
        ice_breakers}."""
        return await self.request("POST", f"{self._waba(waba_id)}/welcome_message_sequences",
                                  data=_query(name=name, welcome_message_sequence=sequence,
                                              sequence_id=sequence_id))

    async def delete_welcome_sequence(self, sequence_id: str, *, waba_id: str | None = None) -> dict:
        return await self.request("DELETE", f"{self._waba(waba_id)}/welcome_message_sequences",
                                  params={"sequence_id": sequence_id})

    async def create_signup(self, waba_id: str | None = None, **signup) -> dict:
        """In-App Signup deep link: signup_message, confirmation_message, privacy_policy_url,
        website_url, promo_code, display_name, policy."""
        return await self.request("POST", f"{self._waba(waba_id)}/signups", json=_clean(signup))

    async def list_signups(self, *, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/signups")

    async def get_signup(self, signup_id: str) -> dict:
        return await self.request("GET", f"signups/{signup_id}")

    async def update_signup(self, signup_id: str, **signup) -> dict:
        return await self.request("POST", f"signups/{signup_id}", json=_clean(signup))

    async def get_default_customer_base(self, *, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/default_messaging_customer_base")

    async def set_default_customer_base(self, customer_base_id: str, *,
                                        waba_id: str | None = None) -> dict:
        return await self.request("POST", f"{self._waba(waba_id)}/default_messaging_customer_base",
                                  json={"messaging_customer_base_id": customer_base_id})

    async def get_reach_estimate(self, targeting_spec: dict, *, date_interval: str | None = None,
                                 waba_id: str | None = None) -> dict:
        """Marketing messages audience size, e.g. {"geo_locations": {"countries": ["IN"]}}."""
        return await self.request("GET", f"{self._waba(waba_id)}/reachestimate", params=_query(
            targeting_spec=targeting_spec, date_interval=date_interval))

    async def list_system_users(self, *, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/system_users")

    async def set_solution_migration_intent(self, solution_id: str, *,
                                            waba_id: str | None = None) -> dict:
        """Tag the WABA for migration to another Multi-Partner Solution."""
        return await self.request("POST", f"{self._waba(waba_id)}/set_solution_migration_intent",
                                  json={"solution_id": solution_id})

    async def set_payment_method_migration_intent(self, *, currency: str | None = None,
                                                  extended_credit_id: str | None = None,
                                                  waba_id: str | None = None) -> dict:
        """Change the WABA's billing currency or credit line; then `resume_migration`."""
        return await self.request(
            "POST", f"{self._waba(waba_id)}/set_payment_method_migration_intent",
            json=_clean({"currency": currency, "extended_credit_id": extended_credit_id}))

    async def resume_migration(self, migration_id: str) -> dict:
        return await self.request("POST", f"{migration_id}/resume_migration")

    # Payments (India: UPI and payment gateways)

    async def list_payment_configurations(self, *, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/payment_configurations")

    async def get_payment_configuration(self, name: str, *, waba_id: str | None = None) -> dict:
        return await self.request("GET", f"{self._waba(waba_id)}/payment_configuration/{name}")

    async def create_payment_configuration(self, name: str, *, purpose_code: str,
                                           merchant_category_code: str, provider_name: str,
                                           waba_id: str | None = None, **extra) -> dict:
        """`provider_name`: razorpay, payu, zaakpay, upi_vpa, ...; `extra`: redirect_url
        (gateways) or merchant_vpa (UPI). Gateways answer with an OAuth link to finish."""
        return await self.request("POST", f"{self._waba(waba_id)}/payment_configuration", json=_clean({
            "configuration_name": name, "purpose_code": purpose_code,
            "merchant_category_code": merchant_category_code, "provider_name": provider_name,
            **extra}))

    async def update_payment_configuration(self, name: str, *, waba_id: str | None = None,
                                           **fields) -> dict:
        """`fields`: data_endpoint_url, ... ."""
        return await self.request("POST", f"{self._waba(waba_id)}/payment_configuration/{name}",
                                  json=_clean(fields))

    async def delete_payment_configuration(self, name: str, *, waba_id: str | None = None) -> dict:
        return await self.request("DELETE", f"{self._waba(waba_id)}/payment_configuration",
                                  json={"configuration_name": name})

    async def regenerate_payment_oauth_link(self, name: str, redirect_url: str, *,
                                            waba_id: str | None = None) -> dict:
        return await self.request(
            "POST", f"{self._waba(waba_id)}/generate_payment_configuration_oauth_link",
            json={"configuration_name": name, "redirect_url": redirect_url})

    async def get_payment(self, configuration_name: str, reference_id: str, *,
                          phone_number_id: str | None = None) -> dict:
        """Status of an order_details payment: pending or captured, plus transactions."""
        return await self.request(
            "GET", f"{self._phone(phone_number_id)}/payments/{configuration_name}/{reference_id}")

    async def refund_payment(self, *, reference_id: str, payment_config_id: str, amount: dict,
                             speed: str | None = None, phone_number_id: str | None = None) -> dict:
        """`amount`: {currency, value, offset}; `speed`: instant or normal."""
        return await self.request("POST", f"{self._phone(phone_number_id)}/payments_refund", json=_clean({
            "reference_id": reference_id, "payment_config_id": payment_config_id,
            "amount": amount, "speed": speed}))

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
        """Any node by ID: account number, migration intent, bot, business profile, template
        group, credit allocation, ... ."""
        return await self.request("GET", node_id, params=_query(fields=fields))

    async def update_node(self, node_id: str, **body) -> dict:
        return await self.request("POST", node_id, json=_clean(body))

    async def delete_node(self, node_id: str) -> dict:
        """E.g. a template group, or a credit allocation (revokes a shared credit line)."""
        return await self.request("DELETE", node_id)

    async def get_system_user_token(self, business_id: str) -> str:
        """Embedded Signup: the customer's business token, read with your system token.
        Requires `app_secret` on the client."""
        payload = await self.request("POST", f"{business_id}/system_user_access_tokens",
                                     data={"fetch_only": "true"})
        token = payload.get("access_token")
        if not token:
            raise _error("Meta returned no business token")
        return token

    async def list_business_users(self, business_id: str, *, fields: str | None = None) -> dict:
        return await self.request("GET", f"{business_id}/business_users", params=_query(fields=fields))

    async def list_app_details(self) -> dict:
        """Apps a Tech Provider picked in the Multi-Partner Solution flow."""
        return await self.request("GET", "me/application_details")

    async def create_customer_base(self, business_id: str, name: str) -> dict:
        return await self.request("POST", f"{business_id}/messaging_customer_base",
                                  json={"messaging_customer_base_name": name})

    async def list_customer_bases(self, business_id: str) -> dict:
        return await self.request("GET", f"{business_id}/messaging_customer_base")

    async def sign_max_price_agreement(self, business_id: str, *, signer_name: str,
                                       signer_email: str) -> dict:
        return await self.request("POST", f"{business_id}/max_price_agreements",
                                  json={"signer_name": signer_name, "signer_email": signer_email})

    async def submit_business_verification(self, business_id: str, end_business_id: str,
                                           documents: list[tuple[str, bytes, str]]) -> dict:
        """Partner-led verification; `documents` are (file_name, content, mime_type)."""
        return await self.request(
            "POST", f"{business_id}/self_certify_whatsapp_business",
            data={"end_business_id": end_business_id},
            files=[("business_documents[]", doc) for doc in documents])

    async def list_business_verifications(self, business_id: str, *,
                                          end_business_id: str | None = None) -> dict:
        return await self.request(
            "GET", f"{business_id}/self_certified_whatsapp_business_submissions",
            params=_query(end_business_id=end_business_id))

    # Credit lines

    async def share_credit_line(self, credit_line_id: str, receiving_business_id: str) -> dict:
        return await self.request("POST", f"{credit_line_id}/whatsapp_credit_sharing",
                                  params={"receiving_business_id": receiving_business_id})

    async def attach_credit_line(self, credit_line_id: str, waba_id: str, waba_currency: str, *,
                                 share: bool = False) -> dict:
        """`share` also shares the line with the WABA's business in the same call."""
        edge = "whatsapp_credit_sharing_and_attach" if share else "whatsapp_credit_attach"
        return await self.request("POST", f"{credit_line_id}/{edge}",
                                  params={"waba_id": waba_id, "waba_currency": waba_currency})

    async def list_credit_allocations(self, credit_line_id: str, receiving_business_id: str) -> dict:
        """Revoke a share with delete_node(allocation_id)."""
        return await self.request(
            "GET", f"{credit_line_id}/owning_credit_allocation_configs",
            params={"receiving_business_id": receiving_business_id,
                    "fields": "id,receiving_business,request_status"})

    # Pre-verified phone numbers

    async def list_preverified_numbers(self, business_id: str, **filters) -> dict:
        return await self.request("GET", f"{business_id}/preverified_numbers", params=_query(**filters))

    async def share_preverified_numbers(self, business_id: str, **body) -> dict:
        return await self.request("POST", f"{business_id}/share_preverified_numbers", json=_clean(body))

    async def unshare_preverified_number(self, business_id: str, preverified_id: str,
                                         partner_business_id: str) -> dict:
        return await self.request("DELETE", f"{business_id}/share_preverified_numbers", params={
            "partner_business_id": partner_business_id, "preverified_id": preverified_id})

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
