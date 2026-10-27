# openping-whatsapp

Async Python client for the WhatsApp Business Platform (Meta Graph API, default `v26.0`).
One file, one dependency (`httpx`).

```bash
pip install openping-whatsapp      # or: uv add openping-whatsapp
```

```python
from whatsapp_sdk import WhatsApp, WhatsAppError, verify_challenge, verify_signature

wa = WhatsApp("ACCESS_TOKEN", waba_id="WABA_ID", phone_number_id="PHONE_NUMBER_ID")

await wa.send_text("15551234567", "Hi")
await wa.send_template_message(to="15551234567", name="hello_world", language="en_US")

try:
    await wa.send_text("15551234567", "Hi")
except WhatsAppError as error:
    if error.retryable:      # never reached Meta, 429, 5xx, or a transient Meta code
        ...                  # safe to send again
    elif error.maybe_sent:   # went out, no answer: may have been delivered
        ...                  # don't resend blindly
    print(error.status_code, error.detail)

async for template in wa.paginate("WABA_ID/message_templates", limit=100):
    ...

# Webhooks
verify_challenge(request.query_params, VERIFY_TOKEN)          # setup handshake
verify_signature(APP_SECRET, raw_body, request.headers.get("X-Hub-Signature-256"))
```

`waba_id` / `phone_number_id` are defaults; every method also takes them as arguments.
`to` accepts a phone number or a business-scoped user ID (BSUID); `send(..., recipient_type="group")` messages a group.
For bulk sends, pass one shared `httpx.AsyncClient` (`WhatsApp(..., client=client)`).
Pass `app_secret=` to sign every call with `appsecret_proof`.
Anything not wrapped: `await wa.request("GET", "<path>", params=..., json=...)`.

## Coverage

| Area | Methods |
| --- | --- |
| Messages | `send` (any type, BSUID, groups), `send_message` (raw payload), `send_text`, `send_media`, `send_location`, `send_contacts`, `send_interactive`, `send_reaction`, `send_template_message` (incl. MM Lite), `mark_message_read` (+ typing indicator) |
| Media | `upload_message_media` (bytes or file), `get_media`, `iter_media` (streamed, Meta hosts only, no redirects, `max_bytes`), `download_media`, `delete_media` |
| Templates | create, update, get, list, delete (bulk), `upload_template_sample`, `list_template_library`, `compare_templates`, `preview_authentication_templates`, `upsert_authentication_templates`, `migrate_message_templates`, template groups |
| Flows | `list_flows`, `create_flow`, `get_flow` (+ metrics, preview), `update_flow`, `delete_flow`, `upload_flow_json`, `list_flow_assets`, `publish_flow`, `deprecate_flow`, `migrate_flows` |
| Phone numbers | list, create, get, update, `set_two_step_pin`, register, deregister, request/verify code, `get_sending_limits`, settings, username (+ suggestions), contact book (BSUID), `sync_business_app_data` (coexistence) |
| Profile & settings | business profile, commerce settings, Flows encryption key, compliance info (India), Official Business Account, conversational automation (welcome, ice breakers, commands) |
| QR codes · Blocking | `list/get/create/delete_qr_code(s)` · `list_blocked_users`, `block_users`, `unblock_users` |
| Calling | `call` (connect, pre_accept, accept, reject, terminate, media_update), `get_call_permissions` |
| Groups | create, list, get, update, delete, invite link (get/reset/delete), join requests, participants |
| WABA | get/update, `get_analytics` (messaging, conversation, pricing, call, template, template group, group), subscribed apps (+ callback override), assigned users, system users, schedules, activities, solutions, product catalogs (+ `list_catalog_products`), CTWA welcome sequences, In-App Signup, customer bases, reach estimate, migrations |
| Payments (India) | payment configurations (list/get/create/update/delete, OAuth link), `get_payment`, `refund_payment` |
| Partners | business portfolio, owned/client WABAs, create WABA, add phone numbers, business users, extended credit lines (share/attach/revoke), MM Lite onboarding, max price agreement, partner-led business verification, pre-verified numbers, Multi-Partner Solutions, message history events |
| Auth & tokens | `exchange_code` (Embedded Signup), `get_system_user_token`, `debug_token`, `app_id`, `appsecret_proof` |
| Generic | `request`, `paginate`, `get_node` / `update_node` / `delete_node` |
| Webhooks | `verify_challenge`, `verify_signature` |

Reference: https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/llms.txt

Test: `uv run --no-project --with httpx python test_whatsapp_sdk.py`

## Releasing

1. Bump `version` in `pyproject.toml` and push to `main`.
2. Actions → **Release to PyPI & GitHub** → Run workflow. It tests, builds, publishes to PyPI, tags `vX.Y.Z`, and creates a GitHub release.

## License

Apache-2.0
