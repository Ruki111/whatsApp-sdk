# openping-whatsapp (Rust)

Async Rust client for the WhatsApp Business Platform (Meta Graph API, default `v26.0`).
Same endpoints and behaviour as the Python package. Not published yet.

```toml
[dependencies]
openping-whatsapp = { git = "https://github.com/Ruki111/whatsApp-sdk" }
```

```rust
use openping_whatsapp::{SendOptions, TemplateOptions, WhatsApp, verify_signature};
use serde_json::Value;

let wa = WhatsApp::new("ACCESS_TOKEN").waba("WABA_ID").phone_number("PHONE_NUMBER_ID");

wa.send_text("15551234567", "Hi", false, SendOptions::default()).await?;
wa.send_template_message("15551234567", "hello_world", "en_US", Value::Null, TemplateOptions::default()).await?;

// Another number with the same client and connection pool:
wa.clone().phone_number("OTHER_ID").send_text("15551234567", "Hi", false, SendOptions::default()).await?;

match wa.list_message_templates(None, Value::Null).await {
    Err(e) if e.retryable => { /* safe to send again */ }
    Err(e) if e.maybe_sent => { /* went out, no answer: don't resend blindly */ }
    other => { other?; }
}

verify_signature(APP_SECRET, &raw_body, signature_header);
```

Request bodies and optional fields are `serde_json::Value` objects named as Meta names them
(Null skips them). Setters: `.waba()`, `.phone_number()`, `.graph_version()`, `.timeout()`,
`.client()` (shared `reqwest::Client`), `.app_secret()` (signs calls with `appsecret_proof`).
Anything not wrapped: `wa.request(Method::GET, "<path>", params, body)`.

Test (from `rust/`): `cargo test`
