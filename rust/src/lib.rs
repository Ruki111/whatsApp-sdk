//! Async client for the WhatsApp Business Platform (Meta Graph API): Cloud API messaging,
//! Business Management, Flows, Groups, Calling, Payments, and Multi-Partner Solutions.
//!
//! The Rust port of the `openping-whatsapp` Python package; same endpoints, same behaviour.
//! Endpoint reference: <https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/llms.txt>
//! Anything not wrapped here: [`WhatsApp::request`].

use std::fmt;
use std::time::Duration;

use hmac::{Hmac, Mac};
use reqwest::{Method, Url, redirect};
use serde_json::{Map, Value, json};
use sha2::Sha256;

pub use bytes::Bytes;
pub use serde_json;

mod account;
mod business;
mod messages;

pub use messages::{SendOptions, TemplateOptions};

pub const GRAPH_URL: &str = "https://graph.facebook.com";
pub const DEFAULT_GRAPH_VERSION: &str = "v26.0";

/// Meta error codes that clear up on their own (outage, rate and throughput limits, template
/// still syncing); see <https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes>.
pub const RETRYABLE_CODES: [i64; 9] = [2, 4, 80007, 130429, 131000, 131016, 131056, 133004, 134101];

/// Media download URLs live on these hosts; the access token is never sent anywhere else.
pub const MEDIA_HOSTS: [&str; 3] = [".fbsbx.com", ".facebook.com", ".whatsapp.net"];

/// Include review details and components so sync can report rejections and detect external edits.
pub const TEMPLATE_FIELDS: &str =
    "id,name,status,category,language,quality_score,rejected_reason,components,parameter_format";

pub type Result<T> = std::result::Result<T, Error>;

/// A non-2xx response, a 200 carrying an `error` object, or no response at all.
///
/// `retryable`: sending the same request again is safe and may succeed (connection never made,
/// 429, 5xx except a write's gateway error, or a transient Meta code). `maybe_sent`: the request
/// went out but no answer came back, so a message may have been delivered; don't resend blindly.
#[derive(Debug, Clone)]
pub struct Error {
    pub status: u16,
    pub payload: Value,
    pub code: Option<i64>,
    pub subcode: Option<i64>,
    pub title: Option<String>,
    pub message: String,
    pub retryable: bool,
    pub maybe_sent: bool,
}

impl Error {
    fn new(status: u16, payload: Value, retryable: Option<bool>, maybe_sent: bool) -> Self {
        let error = payload.get("error").cloned().unwrap_or_default();
        let code = error.get("code").and_then(Value::as_i64);
        let text = |key: &str| error.get(key).and_then(Value::as_str).map(str::to_owned);
        let retryable = retryable.unwrap_or_else(|| {
            status == 429
                || status >= 500
                || error.get("is_transient") == Some(&Value::Bool(true))
                || code.is_some_and(|c| RETRYABLE_CODES.contains(&c))
        });
        Self {
            status,
            code,
            subcode: error.get("error_subcode").and_then(Value::as_i64),
            title: text("error_user_title"),
            // error_user_msg is the human-readable one; `message` is the generic fallback.
            message: text("error_user_msg")
                .or_else(|| text("message"))
                .unwrap_or_else(|| "WhatsApp Cloud API request failed".into()),
            retryable,
            maybe_sent,
            payload,
        }
    }

    pub fn detail(&self) -> Value {
        json!({"message": self.message, "title": self.title, "code": self.code,
               "subcode": self.subcode, "retryable": self.retryable})
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for Error {}

fn fail(message: &str) -> Error {
    Error::new(502, json!({"error": {"message": message}}), Some(false), false)
}

fn unreached(err: reqwest::Error, method: &Method) -> Error {
    let (connect, builder) = (err.is_connect(), err.is_builder());
    // without_url: the query may carry appsecret_proof or client_secret.
    let message = format!("Could not reach the Graph API: {}", err.without_url());
    let payload = json!({"error": {"message": message}});
    if connect || builder {
        return Error::new(502, payload, Some(connect), false);
    }
    // The request may have reached Meta: only reads are safe to repeat.
    let read = method == Method::GET;
    Error::new(502, payload, Some(read), !read)
}

async fn parse(response: reqwest::Response, method: &Method) -> Result<Value> {
    let status = response.status().as_u16();
    let body = response.bytes().await.map_err(|e| unreached(e, method))?;
    // Non-object bodies (e.g. from a proxy) count as empty so they can't escape Error.
    let payload = match serde_json::from_slice::<Value>(&body) {
        Ok(Value::Object(map)) => Value::Object(map),
        _ => json!({}),
    };
    if method != Method::GET && matches!(status, 502..=504) {
        // A gateway error can arrive after Meta already acted on the request.
        return Err(Error::new(status, payload, Some(false), true));
    }
    if status >= 400 || payload.get("error").is_some() {
        return Err(Error::new(status, payload, None, false));
    }
    Ok(payload)
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn hmac_hex(key: &str, data: &[u8]) -> String {
    let mut mac = Hmac::<Sha256>::new_from_slice(key.as_bytes()).expect("HMAC takes any key length");
    mac.update(data);
    hex(&mac.finalize().into_bytes())
}

fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

/// Check a webhook's `X-Hub-Signature-256` header against the raw request body.
pub fn verify_signature(app_secret: &str, body: &[u8], signature_header: Option<&str>) -> bool {
    // An empty secret would accept a signature anyone can compute.
    match signature_header {
        Some(header) if !app_secret.is_empty() => {
            let expected = format!("sha256={}", hmac_hex(app_secret, body));
            constant_time_eq(expected.as_bytes(), header.as_bytes())
        }
        _ => false,
    }
}

/// Webhook setup handshake: the `hub.challenge` to echo back, or None to reject (403).
pub fn verify_challenge(
    mode: Option<&str>,
    token: Option<&str>,
    challenge: Option<&str>,
    verify_token: &str,
) -> Option<String> {
    let ok = !verify_token.is_empty()
        && mode == Some("subscribe")
        && constant_time_eq(token.unwrap_or("").as_bytes(), verify_token.as_bytes());
    ok.then(|| challenge.unwrap_or("").to_owned())
}

/// Embedded Signup: trade the code the popup returned for the customer's business token.
pub async fn exchange_code(code: &str, app_id: &str, app_secret: &str, graph_version: &str) -> Result<String> {
    let response = reqwest::Client::new()
        .get(format!("{GRAPH_URL}/{graph_version}/oauth/access_token"))
        .query(&[("client_id", app_id), ("client_secret", app_secret), ("code", code)])
        .timeout(Duration::from_secs(30))
        .send()
        .await
        .map_err(|e| unreached(e, &Method::GET))?;
    let payload = parse(response, &Method::GET).await?;
    str_field(&payload, "access_token").ok_or_else(|| fail("Meta returned no access token"))
}

fn str_field(payload: &Value, key: &str) -> Option<String> {
    match payload.get(key)? {
        Value::String(s) if !s.is_empty() => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

/// Drop unset values: Meta rejects explicit nulls on several fields. `extra` (an object or
/// Null) is merged on top, for the optional fields Meta keeps adding.
fn body(base: Value, extra: Value) -> Value {
    let mut map = match base {
        Value::Object(map) => map,
        _ => Map::new(),
    };
    if let Value::Object(more) = extra {
        map.extend(more);
    }
    map.retain(|_, v| !v.is_null());
    Value::Object(map)
}

/// Query string from a JSON object; Graph expects arrays and objects in it as JSON.
fn query(values: Value) -> Vec<(String, String)> {
    let Value::Object(map) = values else { return Vec::new() };
    map.into_iter()
        .filter_map(|(k, v)| match v {
            Value::Null => None,
            Value::String(s) => Some((k, s)),
            Value::Array(_) | Value::Object(_) => Some((k, v.to_string())),
            other => Some((k, other.to_string())),
        })
        .collect()
}

enum Body {
    None,
    Json(Value),
    Form(Vec<(String, String)>),
    Multipart(reqwest::multipart::Form),
}

/// One set of credentials. Cheap to clone; clone and set `phone_number` / `waba` to act on a
/// different number or account with the same client.
#[derive(Clone)]
pub struct WhatsApp {
    access_token: String,
    waba_id: String,
    phone_number_id: String,
    graph_url: String,
    graph_version: String,
    timeout: Duration,
    client: reqwest::Client,
    appsecret_proof: Option<String>,
}

impl WhatsApp {
    pub fn new(access_token: impl Into<String>) -> Self {
        Self {
            access_token: access_token.into(),
            waba_id: String::new(),
            phone_number_id: String::new(),
            graph_url: GRAPH_URL.into(),
            graph_version: DEFAULT_GRAPH_VERSION.into(),
            timeout: Duration::from_secs(30),
            client: reqwest::Client::new(),
            appsecret_proof: None,
        }
    }

    /// Default WhatsApp Business Account for methods that act on one.
    pub fn waba(mut self, waba_id: impl Into<String>) -> Self {
        self.waba_id = waba_id.into();
        self
    }

    /// Default business phone number for methods that act on one.
    pub fn phone_number(mut self, phone_number_id: impl Into<String>) -> Self {
        self.phone_number_id = phone_number_id.into();
        self
    }

    pub fn graph_version(mut self, version: impl Into<String>) -> Self {
        self.graph_version = version.into();
        self
    }

    /// Point at a proxy or a test server instead of graph.facebook.com.
    pub fn graph_url(mut self, url: impl Into<String>) -> Self {
        self.graph_url = url.into().trim_end_matches('/').to_owned();
        self
    }

    pub fn timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    /// Share one connection pool across many clients (e.g. a broadcast).
    pub fn client(mut self, client: reqwest::Client) -> Self {
        self.client = client;
        self
    }

    /// Sign every call with `appsecret_proof`, which Meta requires when the app has
    /// "Require app secret" switched on.
    pub fn app_secret(mut self, app_secret: &str) -> Self {
        self.appsecret_proof =
            (!app_secret.is_empty()).then(|| hmac_hex(app_secret, self.access_token.as_bytes()));
        self
    }

    pub fn access_token(&self) -> &str {
        &self.access_token
    }

    fn url(&self, path: &str) -> String {
        format!("{}/{}/{}", self.graph_url, self.graph_version, path)
    }

    fn phone(&self) -> &str {
        &self.phone_number_id
    }

    fn waba_id(&self) -> &str {
        &self.waba_id
    }

    async fn call_graph(
        &self,
        method: Method,
        path: &str,
        params: Value,
        body: Body,
        timeout: Option<Duration>,
    ) -> Result<Value> {
        let mut params = query(params);
        if let Some(proof) = &self.appsecret_proof {
            params.push(("appsecret_proof".into(), proof.clone()));
        }
        let mut req = self
            .client
            .request(method.clone(), self.url(path))
            .bearer_auth(&self.access_token)
            .query(&params)
            .timeout(timeout.unwrap_or(self.timeout));
        req = match body {
            Body::None => req,
            Body::Json(value) => req.json(&value),
            Body::Form(pairs) => req.form(&pairs),
            Body::Multipart(form) => req.multipart(form),
        };
        let response = req.send().await.map_err(|e| unreached(e, &method))?;
        parse(response, &method).await
    }

    /// Call any Graph API path. `params` is a JSON object for the query string (Null for none);
    /// `json` is the request body, if any.
    pub async fn request(&self, method: Method, path: &str, params: Value, json: Option<Value>) -> Result<Value> {
        self.call_graph(method, path, params, json.map_or(Body::None, Body::Json), None).await
    }

    async fn get(&self, path: &str, params: Value) -> Result<Value> {
        self.call_graph(Method::GET, path, params, Body::None, None).await
    }

    async fn post(&self, path: &str, json: Value) -> Result<Value> {
        self.call_graph(Method::POST, path, Value::Null, Body::Json(json), None).await
    }

    async fn post_empty(&self, path: &str, params: Value) -> Result<Value> {
        self.call_graph(Method::POST, path, params, Body::None, None).await
    }

    async fn post_form(&self, path: &str, form: Value) -> Result<Value> {
        self.call_graph(Method::POST, path, Value::Null, Body::Form(query(form)), None).await
    }

    async fn post_multipart(&self, path: &str, form: reqwest::multipart::Form, timeout: Option<Duration>) -> Result<Value> {
        self.call_graph(Method::POST, path, Value::Null, Body::Multipart(form), timeout).await
    }

    async fn delete(&self, path: &str, params: Value) -> Result<Value> {
        self.call_graph(Method::DELETE, path, params, Body::None, None).await
    }

    async fn delete_json(&self, path: &str, json: Value) -> Result<Value> {
        self.call_graph(Method::DELETE, path, Value::Null, Body::Json(json), None).await
    }

    /// Every item of a list endpoint, following `paging.cursors.after`.
    pub fn paginate(&self, path: &str, params: Value) -> Pager<'_> {
        Pager { wa: self, path: path.to_owned(), params, items: Vec::new(), done: false }
    }

    /// App, expiry, scopes, and granular asset access of a token (default: this one).
    pub async fn debug_token(&self, input_token: Option<&str>) -> Result<Value> {
        let payload = self
            .get("debug_token", json!({"input_token": input_token.unwrap_or(&self.access_token)}))
            .await?;
        Ok(payload.get("data").cloned().unwrap_or_else(|| json!({})))
    }

    /// The Meta app the access token belongs to.
    pub async fn app_id(&self) -> Result<String> {
        str_field(&self.debug_token(None).await?, "app_id")
            .ok_or_else(|| fail("Could not determine the Meta app for this token"))
    }

    /// Upload sample media through an app-scoped resumable session; returns the handle a
    /// template's header_handle expects.
    pub async fn upload_template_sample(&self, file_name: &str, file_type: &str, content: Vec<u8>) -> Result<String> {
        let session = self
            .post_empty(
                &format!("{}/uploads", self.app_id().await?),
                json!({"file_name": file_name, "file_length": content.len(), "file_type": file_type}),
            )
            .await?;
        let upload_id = str_field(&session, "id").ok_or_else(|| fail("Upload session was not opened"))?;
        let mut params = Vec::new();
        if let Some(proof) = &self.appsecret_proof {
            params.push(("appsecret_proof", proof.as_str()));
        }
        // The upload edge wants the OAuth scheme, not Bearer.
        let response = self
            .client
            .post(self.url(&upload_id))
            .header("Authorization", format!("OAuth {}", self.access_token))
            .header("file_offset", "0")
            .query(&params)
            .body(content)
            .timeout(Duration::from_secs(120))
            .send()
            .await
            .map_err(|e| unreached(e, &Method::POST))?;
        let payload = parse(response, &Method::POST).await?;
        str_field(&payload, "h").ok_or_else(|| fail("Meta returned no media handle"))
    }

    /// Stream a media URL from `get_media` in chunks. The token is only ever sent to Meta's own
    /// HTTPS hosts, redirects are refused, and `max_bytes` stops oversized files.
    pub async fn iter_media(&self, url: &str, max_bytes: Option<u64>) -> Result<MediaStream> {
        let parsed = Url::parse(url).map_err(|_| fail("Untrusted media URL"))?;
        let trusted = parsed.scheme() == "https"
            && parsed.username().is_empty()
            && parsed.password().is_none()
            && matches!(parsed.port(), None | Some(443))
            && parsed.host_str().is_some_and(|h| MEDIA_HOSTS.iter().any(|s| h.ends_with(s)));
        if !trusted {
            return Err(fail("Untrusted media URL"));
        }
        // A dedicated client: a shared one may follow redirects and carry the token along.
        let client = reqwest::Client::builder()
            .redirect(redirect::Policy::none())
            .connect_timeout(Duration::from_secs(10))
            .build()
            .map_err(|e| unreached(e, &Method::GET))?;
        let response = client
            .get(parsed)
            .bearer_auth(&self.access_token)
            .timeout(Duration::from_secs(120))
            .send()
            .await
            .map_err(|e| unreached(e, &Method::GET))?;
        if response.status().is_redirection() {
            return Err(fail("Media redirects are not followed"));
        }
        if response.status().as_u16() >= 400 {
            return Err(parse(response, &Method::GET).await.err().unwrap_or_else(|| fail("Media download failed")));
        }
        if let (Some(max), Some(length)) = (max_bytes, response.content_length()) {
            if length > max {
                return Err(fail("Media exceeds the size limit"));
            }
        }
        Ok(MediaStream { response, max_bytes, size: 0 })
    }

    /// Whole file in memory; use `get_media` + `iter_media` to stream large files to disk.
    pub async fn download_media(&self, media_id: &str, max_bytes: Option<u64>) -> Result<Vec<u8>> {
        let meta = self.get_media(media_id).await?;
        let url = str_field(&meta, "url").ok_or_else(|| fail("Meta returned no media URL"))?;
        let mut stream = self.iter_media(&url, max_bytes).await?;
        let mut out = Vec::new();
        while let Some(chunk) = stream.chunk().await? {
            out.extend_from_slice(&chunk);
        }
        Ok(out)
    }
}

/// Items of a list endpoint, one at a time; see [`WhatsApp::paginate`].
pub struct Pager<'a> {
    wa: &'a WhatsApp,
    path: String,
    params: Value,
    items: Vec<Value>,
    done: bool,
}

impl Pager<'_> {
    pub async fn next(&mut self) -> Result<Option<Value>> {
        while self.items.is_empty() {
            if self.done {
                return Ok(None);
            }
            let page = self.wa.get(&self.path, self.params.clone()).await?;
            let paging = page.get("paging");
            let after = paging.and_then(|p| p.pointer("/cursors/after")).and_then(Value::as_str);
            match (after, paging.and_then(|p| p.get("next"))) {
                (Some(after), Some(_)) => {
                    if let Value::Object(map) = &mut self.params {
                        map.insert("after".into(), after.into());
                    } else {
                        self.params = json!({"after": after});
                    }
                }
                _ => self.done = true,
            }
            let mut items = page.get("data").and_then(Value::as_array).cloned().unwrap_or_default();
            items.reverse();
            self.items = items;
        }
        Ok(self.items.pop())
    }
}

/// A media download in progress; see [`WhatsApp::iter_media`].
pub struct MediaStream {
    response: reqwest::Response,
    max_bytes: Option<u64>,
    size: u64,
}

impl MediaStream {
    pub async fn chunk(&mut self) -> Result<Option<Bytes>> {
        let chunk = self.response.chunk().await.map_err(|e| unreached(e, &Method::GET))?;
        if let Some(chunk) = &chunk {
            self.size += chunk.len() as u64;
            if self.max_bytes.is_some_and(|max| self.size > max) {
                return Err(fail("Media exceeds the size limit"));
            }
        }
        Ok(chunk)
    }
}

/// Business-scoped user IDs ("US.13491208655302741918") go in `recipient`; phone numbers never
/// contain a dot.
fn recipient(to: &str) -> (&'static str, Value) {
    if to.contains('.') { ("recipient", to.into()) } else { ("to", to.into()) }
}

fn file_part(file_name: &str, file_type: &str, content: Vec<u8>) -> Result<reqwest::multipart::Part> {
    reqwest::multipart::Part::bytes(content)
        .file_name(file_name.to_owned())
        .mime_str(file_type)
        .map_err(|_| fail("Invalid file type"))
}
