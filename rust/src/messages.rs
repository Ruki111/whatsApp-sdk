//! Messages, media, templates, and Flows.

use std::time::Duration;

use reqwest::multipart::Form;
use serde_json::{Value, json};

use crate::{Body, Method, Result, TEMPLATE_FIELDS, WhatsApp, body, fail, file_part, recipient, str_field};

/// Optional parts of a message; `group` sends to a group ID instead of a user.
#[derive(Debug, Clone, Default)]
pub struct SendOptions {
    pub group: bool,
    pub reply_to: Option<String>,
    pub callback_data: Option<String>,
}

/// `marketing_messages` uses MM Lite with Cloud API fallback. `callback_data` is echoed back in
/// delivery webhooks.
#[derive(Debug, Clone, Default)]
pub struct TemplateOptions {
    pub marketing_messages: bool,
    pub callback_data: Option<String>,
    pub timeout: Option<Duration>,
}

impl WhatsApp {
    // Messages

    /// Send any message body (text, media, interactive, ...) as Meta defines it.
    pub async fn send_message(&self, payload: Value) -> Result<Value> {
        let path = format!("{}/messages", self.phone());
        self.call_graph(Method::POST, &path, Value::Null, Body::Json(payload), Some(Duration::from_secs(15))).await
    }

    /// Send any message type: `content` is Meta's object for `kind`. `to` is a phone number, a
    /// business-scoped user ID (BSUID), or a group ID with `group: true`.
    pub async fn send(&self, to: &str, kind: &str, content: Value, options: SendOptions) -> Result<Value> {
        let (key, value) = recipient(to);
        let mut payload = json!({
            "messaging_product": "whatsapp",
            "recipient_type": if options.group { "group" } else { "individual" },
            "type": kind,
        });
        payload[key] = value;
        payload[kind] = content;
        if let Some(reply_to) = options.reply_to {
            payload["context"] = json!({"message_id": reply_to});
        }
        if let Some(data) = options.callback_data {
            payload["biz_opaque_callback_data"] = data.into();
        }
        self.send_message(payload).await
    }

    pub async fn send_text(&self, to: &str, text: &str, preview_url: bool, options: SendOptions) -> Result<Value> {
        self.send(to, "text", json!({"body": text, "preview_url": preview_url}), options).await
    }

    /// `kind` is image, video, audio, document, or sticker; `media` is {"id"} or {"link"},
    /// plus optional caption and filename.
    pub async fn send_media(&self, to: &str, kind: &str, media: Value, options: SendOptions) -> Result<Value> {
        self.send(to, kind, body(media, Value::Null), options).await
    }

    pub async fn send_location(
        &self,
        to: &str,
        latitude: f64,
        longitude: f64,
        name: Option<&str>,
        address: Option<&str>,
        options: SendOptions,
    ) -> Result<Value> {
        let content = body(json!({"latitude": latitude, "longitude": longitude, "name": name, "address": address}), Value::Null);
        self.send(to, "location", content, options).await
    }

    pub async fn send_contacts(&self, to: &str, contacts: Value, options: SendOptions) -> Result<Value> {
        self.send(to, "contacts", contacts, options).await
    }

    /// Buttons, lists, CTA URLs, flows, products, location requests: `interactive` is Meta's
    /// object as-is.
    pub async fn send_interactive(&self, to: &str, interactive: Value, options: SendOptions) -> Result<Value> {
        self.send(to, "interactive", interactive, options).await
    }

    /// An empty `emoji` removes the reaction.
    pub async fn send_reaction(&self, to: &str, message_id: &str, emoji: &str) -> Result<Value> {
        self.send(to, "reaction", json!({"message_id": message_id, "emoji": emoji}), SendOptions::default()).await
    }

    /// Send one template. `components` may be Null.
    pub async fn send_template_message(
        &self,
        to: &str,
        name: &str,
        language: &str,
        components: Value,
        options: TemplateOptions,
    ) -> Result<Value> {
        let mut template = json!({"name": name, "language": {"code": language}});
        if components.as_array().is_some_and(|c| !c.is_empty()) {
            template["components"] = components;
        }
        let (key, value) = recipient(to);
        let mut payload = json!({"messaging_product": "whatsapp", "recipient_type": "individual",
                                 "type": "template", "template": template});
        payload[key] = value;
        if let Some(data) = options.callback_data {
            payload["biz_opaque_callback_data"] = data.into();
        }
        let mut edge = "messages";
        if options.marketing_messages {
            edge = "marketing_messages";
            payload["product_policy"] = "CLOUD_API_FALLBACK".into();
        }
        let path = format!("{}/{edge}", self.phone());
        self.call_graph(Method::POST, &path, Value::Null, Body::Json(payload), options.timeout).await
    }

    /// `typing` also shows a typing indicator until you reply (max 25 seconds).
    pub async fn mark_message_read(&self, wamid: &str, typing: bool) -> Result<Value> {
        let mut payload = json!({"messaging_product": "whatsapp", "status": "read", "message_id": wamid});
        if typing {
            payload["typing_indicator"] = json!({"type": "text"});
        }
        self.post(&format!("{}/messages", self.phone()), payload).await
    }

    // Media

    /// Upload send-time media and return its ID; templates use `upload_template_sample`.
    pub async fn upload_message_media(&self, file_name: &str, file_type: &str, content: Vec<u8>) -> Result<String> {
        let form = Form::new()
            .text("messaging_product", "whatsapp")
            .text("type", file_type.to_owned())
            .part("file", file_part(file_name, file_type, content)?);
        let response = self.post_multipart(&format!("{}/media", self.phone()), form, None).await?;
        str_field(&response, "id").ok_or_else(|| fail("Meta returned no media ID"))
    }

    /// {url, mime_type, sha256, file_size, id}; the url expires after 5 minutes.
    pub async fn get_media(&self, media_id: &str) -> Result<Value> {
        let phone = (!self.phone().is_empty()).then(|| self.phone());
        self.get(media_id, json!({"phone_number_id": phone})).await
    }

    pub async fn delete_media(&self, media_id: &str) -> Result<Value> {
        let phone = (!self.phone().is_empty()).then(|| self.phone());
        self.delete(media_id, json!({"phone_number_id": phone})).await
    }

    // Templates

    /// Submit a template for review. `extra`: parameter_format, sub_category,
    /// message_send_ttl_seconds, allow_category_change, library_template_name, ... .
    pub async fn create_message_template(
        &self,
        name: &str,
        language: &str,
        category: &str,
        components: Value,
        extra: Value,
    ) -> Result<Value> {
        let payload = body(json!({"name": name, "language": language, "category": category, "components": components}), extra);
        self.post(&format!("{}/message_templates", self.waba_id()), payload).await
    }

    /// Name/language are immutable. The prior approved version sends while the edit is reviewed.
    pub async fn update_message_template(&self, template_id: &str, components: Value, extra: Value) -> Result<Value> {
        self.post(template_id, body(json!({"components": components}), extra)).await
    }

    pub async fn get_message_template(&self, template_id: &str, fields: Option<&str>, timeout: Option<Duration>) -> Result<Value> {
        let params = json!({"fields": fields.unwrap_or(TEMPLATE_FIELDS)});
        self.call_graph(Method::GET, template_id, params, Body::None, timeout).await
    }

    /// `filters`: limit, after, before, name, status, category, language, content, quality_score.
    pub async fn list_message_templates(&self, fields: Option<&str>, filters: Value) -> Result<Value> {
        let params = body(json!({"fields": fields.unwrap_or(TEMPLATE_FIELDS), "limit": 100}), filters);
        self.get(&format!("{}/message_templates", self.waba_id()), params).await
    }

    /// Without `template_id` Meta deletes every language variant sharing the name; `hsm_ids`
    /// deletes several at once.
    pub async fn delete_message_template(&self, name: Option<&str>, template_id: Option<&str>, hsm_ids: Option<&[&str]>) -> Result<Value> {
        let params = json!({"name": name, "hsm_id": template_id, "hsm_ids": hsm_ids});
        self.delete(&format!("{}/message_templates", self.waba_id()), params).await
    }

    /// Meta's pre-written templates. `filters`: search, topic, usecase, industry, language, name.
    /// Create one with create_message_template(extra = {"library_template_name": ...}).
    pub async fn list_template_library(&self, filters: Value) -> Result<Value> {
        self.get("message_template_library", filters).await
    }

    /// Sends, block rate, and top block reason of two templates (7/30/60/90-day windows).
    pub async fn compare_templates(&self, template_id: &str, other_template_id: &str, start: i64, end: i64) -> Result<Value> {
        self.get(&format!("{template_id}/compare"), json!({"template_ids": [other_template_id], "start": start, "end": end})).await
    }

    /// `options`: add_security_recommendation, code_expiration_minutes, button_types.
    pub async fn preview_authentication_templates(&self, languages: &[&str], options: Value) -> Result<Value> {
        let languages = (!languages.is_empty()).then(|| languages.join(","));
        let params = body(json!({"category": "AUTHENTICATION", "languages": languages}), options);
        self.get(&format!("{}/message_template_previews", self.waba_id()), params).await
    }

    /// Create or update one authentication template in many languages at once.
    pub async fn upsert_authentication_templates(&self, name: &str, languages: &[&str], components: Value, extra: Value) -> Result<Value> {
        let payload = body(json!({"name": name, "languages": languages, "category": "AUTHENTICATION", "components": components}), extra);
        self.post(&format!("{}/upsert_message_templates", self.waba_id()), payload).await
    }

    /// Copy approved templates from another WABA of the same business into this one.
    pub async fn migrate_message_templates(&self, source_waba_id: &str, page_number: u32, count: Option<u32>, template_ids: Option<&[&str]>) -> Result<Value> {
        let payload = body(json!({"source_waba_id": source_waba_id, "page_number": page_number, "count": count, "template_ids": template_ids}), Value::Null);
        self.post(&format!("{}/migrate_message_templates", self.waba_id()), payload).await
    }

    /// Read, update, or delete a group with get_node / update_node / delete_node.
    pub async fn create_template_group(&self, name: &str, template_ids: &[&str], description: Option<&str>) -> Result<Value> {
        let payload = body(json!({"name": name, "description": description, "whatsapp_business_templates": template_ids}), Value::Null);
        self.post(&format!("{}/template_groups", self.waba_id()), payload).await
    }

    pub async fn list_template_groups(&self, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/template_groups", self.waba_id()), json!({"fields": fields})).await
    }

    // Flows

    /// `params`: fields, limit, after.
    pub async fn list_flows(&self, params: Value) -> Result<Value> {
        self.get(&format!("{}/flows", self.waba_id()), params).await
    }

    /// `extra`: flow_json, publish, clone_flow_id, endpoint_uri.
    pub async fn create_flow(&self, name: &str, categories: &[&str], extra: Value) -> Result<Value> {
        self.post(&format!("{}/flows", self.waba_id()), body(json!({"name": name, "categories": categories}), extra)).await
    }

    /// Metrics and previews are fields too, e.g. `preview.invalidate(true)` or
    /// `metric.name(ENDPOINT_REQUEST_COUNT).granularity(DAY).since(2026-01-01)`.
    pub async fn get_flow(&self, flow_id: &str, fields: Option<&str>) -> Result<Value> {
        self.get(flow_id, json!({"fields": fields})).await
    }

    /// `metadata`: name, categories, endpoint_uri, application_id.
    pub async fn update_flow(&self, flow_id: &str, metadata: Value) -> Result<Value> {
        self.post(flow_id, body(metadata, Value::Null)).await
    }

    /// Only DRAFT flows can be deleted.
    pub async fn delete_flow(&self, flow_id: &str) -> Result<Value> {
        self.delete(flow_id, Value::Null).await
    }

    pub async fn upload_flow_json(&self, flow_id: &str, flow_json: Vec<u8>) -> Result<Value> {
        let form = Form::new()
            .text("name", "flow.json")
            .text("asset_type", "FLOW_JSON")
            .part("file", file_part("flow.json", "application/json", flow_json)?);
        self.post_multipart(&format!("{flow_id}/assets"), form, None).await
    }

    pub async fn list_flow_assets(&self, flow_id: &str) -> Result<Value> {
        self.get(&format!("{flow_id}/assets"), Value::Null).await
    }

    pub async fn publish_flow(&self, flow_id: &str) -> Result<Value> {
        self.post_empty(&format!("{flow_id}/publish"), Value::Null).await
    }

    pub async fn deprecate_flow(&self, flow_id: &str) -> Result<Value> {
        self.post_empty(&format!("{flow_id}/deprecate"), Value::Null).await
    }

    pub async fn migrate_flows(&self, source_waba_id: &str, source_flow_names: Option<&[&str]>) -> Result<Value> {
        let params = json!({"source_waba_id": source_waba_id, "source_flow_names": source_flow_names});
        self.post_empty(&format!("{}/migrate_flows", self.waba_id()), params).await
    }
}
