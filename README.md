# whatsapp-sdk

Async Python client for the WhatsApp Business Platform (Meta Graph API, default `v26.0`).
One file, one dependency (`httpx`).

```bash
uv add "whatsapp-sdk @ git+https://github.com/Ruki111/whatsApp-sdk"
```

```python
from whatsapp_sdk import WhatsApp, WhatsAppError, verify_signature

wa = WhatsApp("ACCESS_TOKEN", waba_id="WABA_ID", phone_number_id="PHONE_NUMBER_ID")

await wa.send_text("15551234567", "Hi")
await wa.send_template_message(to="15551234567", name="hello_world", language="en_US")

try:
    await wa.list_message_templates()
except WhatsAppError as error:
    print(error.status_code, error.detail)

# Webhooks: check the X-Hub-Signature-256 header against the raw body.
verify_signature(APP_SECRET, raw_body, request.headers.get("X-Hub-Signature-256"))
```

`waba_id` / `phone_number_id` are defaults; every method also takes them as arguments.
For bulk sends, pass one shared `httpx.AsyncClient` (`WhatsApp(..., client=client)`).
Anything not wrapped: `await wa.request("GET", "<path>", params=..., json=...)`.

## Coverage

| Area | Methods |
| --- | --- |
| Messages | `send_message` (any payload), `send_text`, `send_media`, `send_location`, `send_contacts`, `send_interactive`, `send_reaction`, `send_template_message` (incl. MM Lite), `mark_message_read` (+ typing indicator) |
| Media | `upload_message_media`, `get_media`, `download_media`, `delete_media` |
| Templates | `create_message_template`, `update_message_template`, `get_message_template`, `list_message_templates`, `delete_message_template`, `upload_template_sample` |
| Flows | `list_flows`, `create_flow`, `get_flow` (+ metrics, preview), `update_flow`, `delete_flow`, `upload_flow_json`, `list_flow_assets`, `publish_flow`, `deprecate_flow`, `migrate_flows` |
| Phone numbers | `list_phone_numbers`, `create_phone_number`, `get_phone_number`, `update_phone_number`, `set_two_step_pin`, `register_phone_number`, `deregister_phone_number`, `request_verification_code`, `verify_code`, `get_sending_limits`, `get_phone_settings`, `update_phone_settings` |
| Profile & settings | `get_business_profile`, `update_business_profile`, `get/update_commerce_settings`, `get/set_encryption_key`, `get/update_compliance_info`, `get/request_official_business_account`, `set_conversational_automation` |
| QR codes | `list_qr_codes`, `get_qr_code`, `create_qr_code`, `delete_qr_code` |
| Blocking | `list_blocked_users`, `block_users`, `unblock_users` |
| Calling | `call` (connect, pre_accept, accept, reject, terminate, media_update), `get_call_permissions` |
| Groups | `create_group`, `list_groups`, `get_group`, `update_group`, `delete_group`, invite links, join requests, participants |
| WABA | `get/update_business_account`, `get_analytics` (messaging, conversation, pricing, template), `list/subscribe/unsubscribe` apps, assigned users, schedules, activities, solutions, `app_id` |
| Partners | business portfolio, owned/client WABAs, create WABA, add phone numbers, extended credits, MM Lite onboarding, pre-verified numbers, Multi-Partner Solutions, message history events, `get_node` / `update_node` |
| Webhooks | `verify_signature` |

Reference: https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/llms.txt

Test: `uv run --no-project --with httpx python test_whatsapp_sdk.py`
