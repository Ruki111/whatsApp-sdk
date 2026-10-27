use std::time::Duration;

use hmac::{Hmac, Mac};
use openping_whatsapp::{Error, SendOptions, TemplateOptions, WhatsApp, verify_challenge, verify_signature};
use reqwest::Method;
use serde_json::{Value, json};
use sha2::Sha256;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, Request, ResponseTemplate};

fn sig(key: &str, body: &[u8]) -> String {
    let mut mac = Hmac::<Sha256>::new_from_slice(key.as_bytes()).unwrap();
    mac.update(body);
    mac.finalize().into_bytes().iter().map(|b| format!("{b:02x}")).collect()
}

async fn server(status: u16, body: Value) -> MockServer {
    let server = MockServer::start().await;
    Mock::given(wiremock::matchers::any())
        .respond_with(ResponseTemplate::new(status).set_body_json(body))
        .mount(&server)
        .await;
    server
}

fn client(server: &MockServer) -> WhatsApp {
    WhatsApp::new("tok").waba("w1").phone_number("p1").graph_version("v99.0").graph_url(server.uri())
}

async fn last(server: &MockServer) -> Request {
    server.received_requests().await.unwrap().pop().unwrap()
}

fn json_body(req: &Request) -> Value {
    serde_json::from_slice(&req.body).unwrap()
}

fn param(req: &Request, key: &str) -> Option<String> {
    req.url.query_pairs().find(|(k, _)| k == key).map(|(_, v)| v.into_owned())
}

#[tokio::test]
async fn builds_requests_like_meta_expects() {
    let s = server(200, json!({"success": true, "messages": [{"id": "wamid.1"}]})).await;
    let wa = client(&s);

    let options = TemplateOptions { marketing_messages: true, ..Default::default() };
    wa.send_template_message("1", "hi", "en", Value::Null, options).await.unwrap();
    let req = last(&s).await;
    assert_eq!(req.url.path(), "/v99.0/p1/marketing_messages");
    assert_eq!(req.headers.get("authorization").unwrap(), "Bearer tok");
    assert_eq!(json_body(&req)["product_policy"], "CLOUD_API_FALLBACK");

    wa.clone().phone_number("p2").send_template_message("1", "hi", "en", Value::Null, TemplateOptions::default()).await.unwrap();
    assert_eq!(last(&s).await.url.path(), "/v99.0/p2/messages");

    let reply = SendOptions { reply_to: Some("wamid.0".into()), ..Default::default() };
    wa.send_text("1", "yo", false, reply).await.unwrap();
    let b = json_body(&last(&s).await);
    assert_eq!(b["text"], json!({"body": "yo", "preview_url": false}));
    assert_eq!(b["context"], json!({"message_id": "wamid.0"}));

    wa.send_media("1", "image", json!({"link": "https://x/y.jpg", "caption": null}), SendOptions::default()).await.unwrap();
    assert_eq!(json_body(&last(&s).await)["image"], json!({"link": "https://x/y.jpg"}));

    wa.mark_message_read("wamid.1", true).await.unwrap();
    assert_eq!(json_body(&last(&s).await)["typing_indicator"], json!({"type": "text"}));

    // Graph wants arrays in the query string as JSON, and unset values left out.
    wa.delete_message_template(None, None, Some(&["1", "2"])).await.unwrap();
    let req = last(&s).await;
    assert_eq!(param(&req, "hsm_ids").as_deref(), Some(r#"["1","2"]"#));
    assert_eq!(param(&req, "name"), None);

    wa.block_users(&["15551234567"]).await.unwrap();
    let req = last(&s).await;
    assert_eq!(req.method.as_str(), "POST");
    assert_eq!(json_body(&req)["block_users"], json!([{"user": "15551234567"}]));

    wa.get_analytics("template_analytics", 1, 2, "DAILY", json!({"template_ids": ["t1"]})).await.unwrap();
    let req = last(&s).await;
    assert_eq!(req.url.path(), "/v99.0/w1/template_analytics");
    assert_eq!(param(&req, "template_ids").as_deref(), Some(r#"["t1"]"#));

    wa.get_analytics("pricing_analytics", 1, 2, "DAILY", json!({"dimensions": ["COUNTRY"]})).await.unwrap();
    assert_eq!(param(&last(&s).await, "fields").as_deref(),
               Some(r#"pricing_analytics.start(1).end(2).granularity(DAILY).dimensions(["COUNTRY"])"#));

    // BSUIDs go in `recipient`, groups keep `to` with recipient_type=group.
    wa.send_text("US.13491208655302741918", "hi", false, SendOptions::default()).await.unwrap();
    let b = json_body(&last(&s).await);
    assert_eq!(b["recipient"], "US.13491208655302741918");
    assert!(b.get("to").is_none());
    wa.send("g1", "text", json!({"body": "all"}), SendOptions { group: true, ..Default::default() }).await.unwrap();
    let b = json_body(&last(&s).await);
    assert_eq!((b["to"].as_str(), b["recipient_type"].as_str()), (Some("g1"), Some("group")));

    wa.list_catalog_products("c1", json!({"fields": "name", "limit": 100, "filter": {"name": {"i_contains": "x"}}})).await.unwrap();
    let req = last(&s).await;
    assert_eq!(req.url.path(), "/v99.0/c1/products");
    assert_eq!(serde_json::from_str::<Value>(&param(&req, "filter").unwrap()).unwrap(), json!({"name": {"i_contains": "x"}}));
    assert_eq!(param(&req, "limit").as_deref(), Some("100"));

    wa.subscribe_app_to_waba(None, None).await.unwrap();
    assert!(last(&s).await.body.is_empty());

    let signed = client(&s).app_secret("s3");
    signed.get_phone_number(None).await.unwrap();
    assert_eq!(param(&last(&s).await, "appsecret_proof"), Some(sig("s3", b"tok")));
    wa.get_phone_number(None).await.unwrap();
    assert_eq!(param(&last(&s).await, "appsecret_proof"), None);

    let raw = wa.request(Method::GET, "anything", json!({"a": 1}), None).await.unwrap();
    assert_eq!(raw["success"], true);
}

#[tokio::test]
async fn uploads_template_samples_with_the_oauth_scheme() {
    let s = MockServer::start().await;
    Mock::given(path("/v99.0/debug_token")).respond_with(ResponseTemplate::new(200).set_body_json(json!({"data": {"app_id": "app1"}}))).mount(&s).await;
    Mock::given(path("/v99.0/app1/uploads")).respond_with(ResponseTemplate::new(200).set_body_json(json!({"id": "upload:1"}))).mount(&s).await;
    Mock::given(path("/v99.0/upload:1")).respond_with(ResponseTemplate::new(200).set_body_json(json!({"h": "handle"}))).mount(&s).await;
    let handle = client(&s).upload_template_sample("a.png", "image/png", b"x".to_vec()).await.unwrap();
    assert_eq!(handle, "handle");
    assert_eq!(last(&s).await.headers.get("authorization").unwrap(), "OAuth tok");
}

#[tokio::test]
async fn paginates_until_there_is_no_next_page() {
    let s = MockServer::start().await;
    Mock::given(method("GET"))
        .respond_with(|req: &Request| {
            let page = if req.url.query().unwrap_or("").contains("after=c1") {
                json!({"data": [{"id": 2}], "paging": {"cursors": {"after": "c2"}}})
            } else {
                json!({"data": [{"id": 1}], "paging": {"cursors": {"after": "c1"}, "next": "https://n"}})
            };
            ResponseTemplate::new(200).set_body_json(page)
        })
        .mount(&s)
        .await;
    let wa = client(&s);
    let mut pager = wa.paginate("w1/flows", json!({"limit": 1}));
    let mut ids = Vec::new();
    while let Some(item) = pager.next().await.unwrap() {
        ids.push(item["id"].as_i64().unwrap());
    }
    assert_eq!(ids, [1, 2]);
}

#[tokio::test]
async fn reports_meta_errors() {
    let s = server(400, json!({"error": {"code": 100, "error_user_msg": "Nope"}})).await;
    let err = client(&s).get_phone_number(None).await.unwrap_err();
    assert_eq!((err.status, err.code, err.message.as_str()), (400, Some(100), "Nope"));

    let s = MockServer::start().await;
    Mock::given(wiremock::matchers::any()).respond_with(ResponseTemplate::new(200).set_body_json(json!(["not", "an", "object"]))).mount(&s).await;
    assert_eq!(client(&s).get_phone_number(None).await.unwrap(), json!({}));

    let s = server(200, json!({})).await;
    let err = client(&s).upload_message_media("a.jpg", "image/jpeg", b"x".to_vec()).await.unwrap_err();
    assert_eq!(err.status, 502);
}

async fn error_with(status: u16, error: Value, verb: Method) -> Error {
    let s = server(status, json!({"error": error})).await;
    client(&s).request(verb, "p1/messages", Value::Null, None).await.unwrap_err()
}

#[tokio::test]
async fn classifies_what_is_safe_to_retry() {
    assert!(error_with(429, json!({}), Method::POST).await.retryable);
    assert!(error_with(500, json!({}), Method::POST).await.retryable);
    let gateway = error_with(504, json!({}), Method::POST).await;
    assert!(!gateway.retryable && gateway.maybe_sent);
    assert!(error_with(503, json!({}), Method::GET).await.retryable);
    assert!(error_with(400, json!({"code": 130429}), Method::POST).await.retryable);
    assert!(error_with(400, json!({"code": 100, "is_transient": true}), Method::POST).await.retryable);
    assert!(!error_with(400, json!({"code": 131026}), Method::POST).await.retryable);

    // Nothing listens on port 9 here: the connection is refused, so nothing was sent.
    let refused = WhatsApp::new("tok").graph_url("http://127.0.0.1:9").request(Method::POST, "p1/messages", Value::Null, None).await.unwrap_err();
    assert!(refused.retryable && !refused.maybe_sent);

    let s = MockServer::start().await;
    Mock::given(wiremock::matchers::any()).respond_with(ResponseTemplate::new(200).set_delay(Duration::from_secs(2))).mount(&s).await;
    let slow = client(&s).timeout(Duration::from_millis(200));
    let lost = slow.request(Method::POST, "p1/messages", Value::Null, None).await.unwrap_err();
    assert!(!lost.retryable && lost.maybe_sent);
    assert!(slow.request(Method::GET, "p1", Value::Null, None).await.unwrap_err().retryable);
}

#[tokio::test]
async fn never_sends_the_token_outside_meta_media_hosts() {
    let wa = WhatsApp::new("tok");
    for url in ["https://evil.example/f", "http://lookaside.fbsbx.com/f",
                "https://lookaside.fbsbx.com:8443/f", "https://evilfbsbx.com/f",
                "https://user:pw@lookaside.fbsbx.com/f", "not a url"] {
        let err = wa.iter_media(url, None).await.err().expect(url);
        assert!(err.message.contains("Untrusted"), "{url}");
    }
}

#[test]
fn checks_webhooks() {
    let good = format!("sha256={}", sig("secret", b"{}"));
    assert!(verify_signature("secret", b"{}", Some(&good)));
    assert!(!verify_signature("secret", b"{}", Some("sha256=bad")));
    assert!(!verify_signature("secret", b"{}", None));
    assert!(!verify_signature("secret", b"{}", Some("sha256=\u{e9}")));
    // An empty secret would accept a signature anyone can compute.
    assert!(!verify_signature("", b"{}", Some(&format!("sha256={}", sig("", b"{}")))));

    assert_eq!(verify_challenge(Some("subscribe"), Some("v"), Some("42"), "v").as_deref(), Some("42"));
    assert_eq!(verify_challenge(Some("subscribe"), Some("x"), Some("42"), "v"), None);
    assert_eq!(verify_challenge(Some("subscribe"), Some(""), Some("1"), ""), None);
}
