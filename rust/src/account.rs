//! Phone numbers, profile and settings, QR codes, blocking, calling, and groups.

use std::time::Duration;

use serde_json::{Value, json};

use crate::{Body, Method, Result, WhatsApp, body};

impl WhatsApp {
    // Phone numbers

    /// `params`: fields, filtering, sort, limit, after, before.
    pub async fn list_phone_numbers(&self, params: Value) -> Result<Value> {
        self.get(&format!("{}/phone_numbers", self.waba_id()), params).await
    }

    pub async fn create_phone_number(&self, cc: &str, phone_number: &str, verified_name: &str, extra: Value) -> Result<Value> {
        let payload = body(json!({"cc": cc, "phone_number": phone_number, "verified_name": verified_name}), extra);
        self.post(&format!("{}/phone_numbers", self.waba_id()), payload).await
    }

    pub async fn get_phone_number(&self, fields: Option<&str>) -> Result<Value> {
        self.get(self.phone(), json!({"fields": fields})).await
    }

    /// `fields`: pin (two-step verification), new_display_name, search_visibility,
    /// webhook_configuration, username, ... .
    pub async fn update_phone_number(&self, fields: Value) -> Result<Value> {
        self.post(self.phone(), body(fields, Value::Null)).await
    }

    /// Disabling two-step verification is only possible in WhatsApp Manager.
    pub async fn set_two_step_pin(&self, pin: &str) -> Result<Value> {
        self.update_phone_number(json!({"pin": pin})).await
    }

    /// Limited to 10 calls per number per 72 hours.
    pub async fn register_phone_number(&self, pin: &str, data_localization_region: Option<&str>) -> Result<Value> {
        let payload = body(json!({"messaging_product": "whatsapp", "pin": pin, "data_localization_region": data_localization_region}), Value::Null);
        self.post(&format!("{}/register", self.phone()), payload).await
    }

    pub async fn deregister_phone_number(&self) -> Result<Value> {
        self.post_empty(&format!("{}/deregister", self.phone()), Value::Null).await
    }

    /// `code_method`: SMS or VOICE.
    pub async fn request_verification_code(&self, code_method: &str, language: &str) -> Result<Value> {
        self.post(&format!("{}/request_code", self.phone()), json!({"code_method": code_method, "language": language})).await
    }

    pub async fn verify_code(&self, code: &str) -> Result<Value> {
        self.post(&format!("{}/verify_code", self.phone()), json!({"code": code})).await
    }

    /// Throughput, coexistence, and messaging limit as Meta reports them; absent fields are Null.
    pub async fn get_sending_limits(&self) -> Result<Value> {
        let fields = json!({"fields": "throughput,is_on_biz_app,whatsapp_business_manager_messaging_limit"});
        let payload = self.call_graph(Method::GET, self.phone(), fields, Body::None, Some(Duration::from_secs(10))).await?;
        let level = payload.pointer("/throughput/level").filter(|v| !v.is_null() && *v != "");
        Ok(json!({
            "throughput": level.map(|v| v.as_str().map_or_else(|| v.to_string(), str::to_owned)),
            "is_on_biz_app": payload.get("is_on_biz_app") == Some(&Value::Bool(true)),
            "messaging_limit": payload.get("whatsapp_business_manager_messaging_limit").cloned().unwrap_or(Value::Null),
        }))
    }

    pub async fn get_phone_settings(&self, include_sip_credentials: Option<bool>) -> Result<Value> {
        self.get(&format!("{}/settings", self.phone()), json!({"include_sip_credentials": include_sip_credentials})).await
    }

    /// `settings`: calling, storage_configuration, user_identity_change, payload_encryption.
    pub async fn update_phone_settings(&self, settings: Value) -> Result<Value> {
        self.post(&format!("{}/settings", self.phone()), body(settings, Value::Null)).await
    }

    // Profile and settings

    pub async fn get_business_profile(&self, fields: Option<&str>) -> Result<Value> {
        let fields = fields.unwrap_or("about,address,description,email,profile_picture_url,websites,vertical");
        self.get(&format!("{}/whatsapp_business_profile", self.phone()), json!({"fields": fields})).await
    }

    /// `profile`: about, address, description, email, vertical, websites,
    /// profile_picture_handle (from upload_template_sample).
    pub async fn update_business_profile(&self, profile: Value) -> Result<Value> {
        let payload = body(json!({"messaging_product": "whatsapp"}), profile);
        self.post(&format!("{}/whatsapp_business_profile", self.phone()), payload).await
    }

    pub async fn get_commerce_settings(&self) -> Result<Value> {
        self.get(&format!("{}/whatsapp_commerce_settings", self.phone()), Value::Null).await
    }

    pub async fn update_commerce_settings(&self, is_cart_enabled: Option<bool>, is_catalog_visible: Option<bool>) -> Result<Value> {
        let params = json!({"is_cart_enabled": is_cart_enabled, "is_catalog_visible": is_catalog_visible});
        self.post_empty(&format!("{}/whatsapp_commerce_settings", self.phone()), params).await
    }

    /// The Flows endpoint public key and its signature status.
    pub async fn get_encryption_key(&self) -> Result<Value> {
        self.get(&format!("{}/whatsapp_business_encryption", self.phone()), Value::Null).await
    }

    pub async fn set_encryption_key(&self, public_key_pem: &str) -> Result<Value> {
        self.post_form(&format!("{}/whatsapp_business_encryption", self.phone()), json!({"business_public_key": public_key_pem})).await
    }

    /// India-based businesses: the grievance officer and entity details Meta requires.
    pub async fn get_compliance_info(&self) -> Result<Value> {
        self.get(&format!("{}/business_compliance_info", self.phone()), Value::Null).await
    }

    pub async fn update_compliance_info(&self, info: Value) -> Result<Value> {
        let payload = body(json!({"messaging_product": "whatsapp"}), info);
        self.post(&format!("{}/business_compliance_info", self.phone()), payload).await
    }

    pub async fn get_official_business_account(&self) -> Result<Value> {
        self.get(&format!("{}/official_business_account", self.phone()), Value::Null).await
    }

    /// Apply for the green badge; `application` is Meta's OBA request body.
    pub async fn request_official_business_account(&self, application: Value) -> Result<Value> {
        self.post(&format!("{}/official_business_account", self.phone()), body(application, Value::Null)).await
    }

    /// Welcome message, ice breakers (`prompts`), and `/` commands ({command_name,
    /// command_description}).
    pub async fn set_conversational_automation(&self, enable_welcome_message: Option<bool>, prompts: Option<&[&str]>, commands: Value) -> Result<Value> {
        let payload = body(json!({"enable_welcome_message": enable_welcome_message, "prompts": prompts, "commands": commands}), Value::Null);
        self.post(&format!("{}/conversational_automation", self.phone()), payload).await
    }

    /// {username, status}; status is approved, reserved, ... .
    pub async fn get_username(&self) -> Result<Value> {
        self.get(&format!("{}/username", self.phone()), Value::Null).await
    }

    pub async fn set_username(&self, username: &str, transfer_action: Option<&str>) -> Result<Value> {
        let payload = body(json!({"username": username, "transfer_action": transfer_action}), Value::Null);
        self.post(&format!("{}/username", self.phone()), payload).await
    }

    pub async fn get_username_suggestions(&self) -> Result<Value> {
        self.get(&format!("{}/username_suggestions", self.phone()), Value::Null).await
    }

    /// The contact book entry for a business-scoped user ID.
    pub async fn get_contact(&self, bsuid: &str) -> Result<Value> {
        self.get(&format!("{}/contact_book", self.phone()), json!({"messaging_product": "whatsapp", "bsuid": bsuid})).await
    }

    pub async fn delete_contact(&self, bsuid: &str) -> Result<Value> {
        self.delete(&format!("{}/contact_book", self.phone()), json!({"messaging_product": "whatsapp", "bsuid": bsuid})).await
    }

    /// Coexistence numbers: replay the WhatsApp Business app's contacts (smb_app_state_sync) or
    /// chat history (history) as webhooks. Allowed once.
    pub async fn sync_business_app_data(&self, sync_type: &str) -> Result<Value> {
        self.post(&format!("{}/smb_app_data", self.phone()), json!({"messaging_product": "whatsapp", "sync_type": sync_type})).await
    }

    // QR codes

    pub async fn list_qr_codes(&self, code: Option<&str>, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/message_qrdls", self.phone()), json!({"code": code, "fields": fields})).await
    }

    pub async fn get_qr_code(&self, qr_code_id: &str) -> Result<Value> {
        self.get(&format!("{}/message_qrdls/{qr_code_id}", self.phone()), Value::Null).await
    }

    /// Pass `code` to update an existing QR code's message. `image_format`: PNG or SVG.
    pub async fn create_qr_code(&self, prefilled_message: &str, image_format: Option<&str>, code: Option<&str>) -> Result<Value> {
        let payload = body(json!({"prefilled_message": prefilled_message, "generate_qr_image": image_format, "code": code}), Value::Null);
        self.post(&format!("{}/message_qrdls", self.phone()), payload).await
    }

    pub async fn delete_qr_code(&self, qr_code_id: &str) -> Result<Value> {
        self.delete(&format!("{}/message_qrdls/{qr_code_id}", self.phone()), Value::Null).await
    }

    // Blocking

    /// `params`: limit, after.
    pub async fn list_blocked_users(&self, params: Value) -> Result<Value> {
        self.get(&format!("{}/block_users", self.phone()), params).await
    }

    /// Only users who messaged you in the last 24 hours can be blocked.
    pub async fn block_users(&self, users: &[&str]) -> Result<Value> {
        self.post(&format!("{}/block_users", self.phone()), block_body(users)).await
    }

    pub async fn unblock_users(&self, users: &[&str]) -> Result<Value> {
        self.delete_json(&format!("{}/block_users", self.phone()), block_body(users)).await
    }

    // Calling

    /// `action`: connect (start a call `to` a user), pre_accept, accept, reject, terminate,
    /// media_update. `session` is {sdp_type, sdp} for WebRTC negotiation.
    pub async fn call(&self, action: &str, call_id: Option<&str>, to: Option<&str>, session: Value, callback_data: Option<&str>) -> Result<Value> {
        let payload = body(json!({"messaging_product": "whatsapp", "action": action, "call_id": call_id, "to": to,
                                  "session": session, "biz_opaque_callback_data": callback_data}), Value::Null);
        self.post(&format!("{}/calls", self.phone()), payload).await
    }

    pub async fn get_call_permissions(&self, user_wa_id: &str) -> Result<Value> {
        self.get(&format!("{}/call_permissions", self.phone()), json!({"user_wa_id": user_wa_id})).await
    }

    // Groups

    pub async fn create_group(&self, subject: &str, description: Option<&str>, join_approval_mode: Option<&str>) -> Result<Value> {
        let payload = body(json!({"messaging_product": "whatsapp", "subject": subject, "description": description,
                                  "join_approval_mode": join_approval_mode}), Value::Null);
        self.post(&format!("{}/groups", self.phone()), payload).await
    }

    /// `params`: limit, after.
    pub async fn list_groups(&self, params: Value) -> Result<Value> {
        self.get(&format!("{}/groups", self.phone()), params).await
    }

    pub async fn get_group(&self, group_id: &str, fields: Option<&str>) -> Result<Value> {
        self.get(group_id, json!({"fields": fields})).await
    }

    pub async fn update_group(&self, group_id: &str, subject: Option<&str>, description: Option<&str>) -> Result<Value> {
        self.post(group_id, body(json!({"messaging_product": "whatsapp", "subject": subject, "description": description}), Value::Null)).await
    }

    pub async fn delete_group(&self, group_id: &str) -> Result<Value> {
        self.delete(group_id, Value::Null).await
    }

    pub async fn get_group_invite_link(&self, group_id: &str) -> Result<Value> {
        self.get(&format!("{group_id}/invite_link"), Value::Null).await
    }

    /// Creates the link, or resets it (old link stops working).
    pub async fn create_group_invite_link(&self, group_id: &str) -> Result<Value> {
        self.post(&format!("{group_id}/invite_link"), json!({"messaging_product": "whatsapp"})).await
    }

    pub async fn delete_group_invite_link(&self, group_id: &str) -> Result<Value> {
        self.delete_json(&format!("{group_id}/invite_link"), json!({"messaging_product": "whatsapp"})).await
    }

    pub async fn list_group_join_requests(&self, group_id: &str) -> Result<Value> {
        self.get(&format!("{group_id}/join_requests"), Value::Null).await
    }

    pub async fn approve_group_join_requests(&self, group_id: &str, join_requests: &[&str]) -> Result<Value> {
        self.post(&format!("{group_id}/join_requests"), json!({"messaging_product": "whatsapp", "join_requests": join_requests})).await
    }

    pub async fn reject_group_join_requests(&self, group_id: &str, join_requests: &[&str]) -> Result<Value> {
        self.delete_json(&format!("{group_id}/join_requests"), json!({"messaging_product": "whatsapp", "join_requests": join_requests})).await
    }

    pub async fn add_group_participants(&self, group_id: &str, participants: &[&str]) -> Result<Value> {
        self.post(&format!("{group_id}/participants"), participants_body(participants)).await
    }

    pub async fn remove_group_participants(&self, group_id: &str, participants: &[&str]) -> Result<Value> {
        self.delete_json(&format!("{group_id}/participants"), participants_body(participants)).await
    }
}

fn block_body(users: &[&str]) -> Value {
    json!({"messaging_product": "whatsapp", "block_users": users.iter().map(|u| json!({"user": u})).collect::<Vec<_>>()})
}

fn participants_body(participants: &[&str]) -> Value {
    json!({"messaging_product": "whatsapp", "participants": participants.iter().map(|p| json!({"user": p})).collect::<Vec<_>>()})
}
