# whatsapp-sdk

Async client for the WhatsApp Cloud API (Meta Graph API).

```bash
uv add "whatsapp-sdk @ git+https://github.com/Ruki111/whatsApp-sdk"
```

```python
from whatsapp_sdk import WhatsApp, WhatsAppError

wa = WhatsApp("ACCESS_TOKEN", waba_id="WABA_ID", phone_number_id="PHONE_NUMBER_ID")

await wa.send_template_message(to="15551234567", name="hello_world", language="en_US")
await wa.send_message({"messaging_product": "whatsapp", "to": "15551234567",
                       "type": "text", "text": {"body": "Hi"}})

try:
    await wa.list_message_templates()
except WhatsAppError as error:
    print(error.status_code, error.detail)
```

For bulk sends, pass one shared `httpx.AsyncClient` (`WhatsApp(..., client=client)`) to reuse
connections. Anything not wrapped yet: `await wa.request("GET", "<path>", params=...)`.

Test: `uv run --with httpx python test_whatsapp_sdk.py`
