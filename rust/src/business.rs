//! WhatsApp Business Account, payments, partners, credit lines, pre-verified numbers, and
//! Multi-Partner Solutions.

use reqwest::multipart::Form;
use serde_json::{Value, json};

use crate::{Result, WhatsApp, body, fail, file_part, str_field};

/// Analytics served by their own WABA edge rather than as a field on the WABA.
const ANALYTICS_EDGES: [&str; 3] = ["template_analytics", "template_group_analytics", "group_analytics"];

impl WhatsApp {
    // WhatsApp Business Account

    pub async fn get_business_account(&self, fields: Option<&str>) -> Result<Value> {
        self.get(self.waba_id(), json!({"fields": fields})).await
    }

    pub async fn update_business_account(&self, name: Option<&str>, timezone_id: Option<&str>) -> Result<Value> {
        self.post(self.waba_id(), body(json!({"name": name, "timezone_id": timezone_id}), Value::Null)).await
    }

    /// `metric`: analytics, conversation_analytics, pricing_analytics, call_analytics,
    /// template_analytics, template_group_analytics, group_analytics. `start`/`end` are UNIX
    /// seconds; `filters` (phone_numbers, country_codes, metric_types, template_ids, group_ids,
    /// dimensions, ...) follow Meta's names.
    pub async fn get_analytics(&self, metric: &str, start: i64, end: i64, granularity: &str, filters: Value) -> Result<Value> {
        if ANALYTICS_EDGES.contains(&metric) {
            let params = body(json!({"start": start, "end": end, "granularity": granularity}), filters);
            return self.get(&format!("{}/{metric}", self.waba_id()), params).await;
        }
        let mut field = format!("{metric}.start({start}).end({end}).granularity({granularity})");
        if let Value::Object(map) = body(filters, Value::Null) {
            for (key, value) in map {
                field.push_str(&format!(".{key}({value})"));
            }
        }
        self.get_business_account(Some(&field)).await
    }

    /// The catalog connected to the WABA, e.g. fields = "id,name,product_count".
    pub async fn get_product_catalogs(&self, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/product_catalogs", self.waba_id()), json!({"fields": fields})).await
    }

    /// `params`: fields, limit, after, filter (e.g. {"name": {"i_contains": "shoe"}}).
    pub async fn list_catalog_products(&self, catalog_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{catalog_id}/products"), params).await
    }

    pub async fn connect_product_catalog(&self, catalog_id: &str) -> Result<Value> {
        self.post(&format!("{}/product_catalogs", self.waba_id()), json!({"catalog_id": catalog_id})).await
    }

    /// Click-to-WhatsApp ad welcome messages.
    pub async fn list_welcome_sequences(&self, sequence_id: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/welcome_message_sequences", self.waba_id()), json!({"sequence_id": sequence_id})).await
    }

    /// Create, or update when `sequence_id` is given. `sequence`: {text, autofill_message,
    /// ice_breakers}.
    pub async fn save_welcome_sequence(&self, name: &str, sequence: Value, sequence_id: Option<&str>) -> Result<Value> {
        let form = json!({"name": name, "welcome_message_sequence": sequence, "sequence_id": sequence_id});
        self.post_form(&format!("{}/welcome_message_sequences", self.waba_id()), form).await
    }

    pub async fn delete_welcome_sequence(&self, sequence_id: &str) -> Result<Value> {
        self.delete(&format!("{}/welcome_message_sequences", self.waba_id()), json!({"sequence_id": sequence_id})).await
    }

    /// In-App Signup deep link: signup_message, confirmation_message, privacy_policy_url,
    /// website_url, promo_code, display_name, policy.
    pub async fn create_signup(&self, signup: Value) -> Result<Value> {
        self.post(&format!("{}/signups", self.waba_id()), body(signup, Value::Null)).await
    }

    pub async fn list_signups(&self) -> Result<Value> {
        self.get(&format!("{}/signups", self.waba_id()), Value::Null).await
    }

    pub async fn get_signup(&self, signup_id: &str) -> Result<Value> {
        self.get(&format!("signups/{signup_id}"), Value::Null).await
    }

    pub async fn update_signup(&self, signup_id: &str, signup: Value) -> Result<Value> {
        self.post(&format!("signups/{signup_id}"), body(signup, Value::Null)).await
    }

    pub async fn get_default_customer_base(&self) -> Result<Value> {
        self.get(&format!("{}/default_messaging_customer_base", self.waba_id()), Value::Null).await
    }

    pub async fn set_default_customer_base(&self, customer_base_id: &str) -> Result<Value> {
        self.post(&format!("{}/default_messaging_customer_base", self.waba_id()),
                  json!({"messaging_customer_base_id": customer_base_id})).await
    }

    /// Marketing messages audience size, e.g. {"geo_locations": {"countries": ["IN"]}}.
    pub async fn get_reach_estimate(&self, targeting_spec: Value, date_interval: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/reachestimate", self.waba_id()), json!({"targeting_spec": targeting_spec, "date_interval": date_interval})).await
    }

    pub async fn list_system_users(&self) -> Result<Value> {
        self.get(&format!("{}/system_users", self.waba_id()), Value::Null).await
    }

    /// Tag the WABA for migration to another Multi-Partner Solution.
    pub async fn set_solution_migration_intent(&self, solution_id: &str) -> Result<Value> {
        self.post(&format!("{}/set_solution_migration_intent", self.waba_id()), json!({"solution_id": solution_id})).await
    }

    /// Change the WABA's billing currency or credit line; then `resume_migration`.
    pub async fn set_payment_method_migration_intent(&self, currency: Option<&str>, extended_credit_id: Option<&str>) -> Result<Value> {
        let payload = body(json!({"currency": currency, "extended_credit_id": extended_credit_id}), Value::Null);
        self.post(&format!("{}/set_payment_method_migration_intent", self.waba_id()), payload).await
    }

    pub async fn resume_migration(&self, migration_id: &str) -> Result<Value> {
        self.post_empty(&format!("{migration_id}/resume_migration"), Value::Null).await
    }

    pub async fn list_subscribed_apps(&self) -> Result<Value> {
        self.get(&format!("{}/subscribed_apps", self.waba_id()), Value::Null).await
    }

    /// Subscribe the token's app to WABA webhooks; dashboard setup alone doesn't deliver.
    /// `override_callback_uri` sends this WABA's webhooks to a different URL.
    pub async fn subscribe_app_to_waba(&self, override_callback_uri: Option<&str>, verify_token: Option<&str>) -> Result<Value> {
        let path = format!("{}/subscribed_apps", self.waba_id());
        match override_callback_uri {
            Some(uri) => self.post(&path, body(json!({"override_callback_uri": uri, "verify_token": verify_token}), Value::Null)).await,
            None => self.post_empty(&path, Value::Null).await,
        }
    }

    pub async fn unsubscribe_app_from_waba(&self) -> Result<Value> {
        self.delete(&format!("{}/subscribed_apps", self.waba_id()), Value::Null).await
    }

    pub async fn list_assigned_users(&self, business_id: &str, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/assigned_users", self.waba_id()), json!({"business": business_id, "fields": fields})).await
    }

    /// `tasks`: MANAGE, DEVELOP, MANAGE_TEMPLATES, MANAGE_PHONE, VIEW_COST, ... .
    pub async fn assign_user(&self, user_id: &str, tasks: &[&str]) -> Result<Value> {
        self.post(&format!("{}/assigned_users", self.waba_id()), json!({"user": user_id, "tasks": tasks})).await
    }

    pub async fn remove_assigned_user(&self, user_id: &str) -> Result<Value> {
        self.delete_json(&format!("{}/assigned_users", self.waba_id()), json!({"user": user_id})).await
    }

    pub async fn list_schedules(&self, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/schedules", self.waba_id()), json!({"fields": fields})).await
    }

    /// `schedule`: name, hsm_id (template), audience_id, delivery_time, description.
    pub async fn create_schedule(&self, schedule: Value) -> Result<Value> {
        self.post(&format!("{}/schedules", self.waba_id()), body(schedule, Value::Null)).await
    }

    /// `params`: fields, limit, after.
    pub async fn list_activities(&self, params: Value) -> Result<Value> {
        self.get(&format!("{}/activities", self.waba_id()), params).await
    }

    pub async fn list_waba_solutions(&self, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{}/solutions", self.waba_id()), json!({"fields": fields})).await
    }

    // Payments (India: UPI and payment gateways)

    pub async fn list_payment_configurations(&self) -> Result<Value> {
        self.get(&format!("{}/payment_configurations", self.waba_id()), Value::Null).await
    }

    pub async fn get_payment_configuration(&self, name: &str) -> Result<Value> {
        self.get(&format!("{}/payment_configuration/{name}", self.waba_id()), Value::Null).await
    }

    /// `provider_name`: razorpay, payu, zaakpay, upi_vpa, ...; `extra`: redirect_url (gateways)
    /// or merchant_vpa (UPI). Gateways answer with an OAuth link to finish.
    pub async fn create_payment_configuration(&self, name: &str, purpose_code: &str, merchant_category_code: &str, provider_name: &str, extra: Value) -> Result<Value> {
        let payload = body(json!({"configuration_name": name, "purpose_code": purpose_code,
                                  "merchant_category_code": merchant_category_code, "provider_name": provider_name}), extra);
        self.post(&format!("{}/payment_configuration", self.waba_id()), payload).await
    }

    /// `fields`: data_endpoint_url, ... .
    pub async fn update_payment_configuration(&self, name: &str, fields: Value) -> Result<Value> {
        self.post(&format!("{}/payment_configuration/{name}", self.waba_id()), body(fields, Value::Null)).await
    }

    pub async fn delete_payment_configuration(&self, name: &str) -> Result<Value> {
        self.delete_json(&format!("{}/payment_configuration", self.waba_id()), json!({"configuration_name": name})).await
    }

    pub async fn regenerate_payment_oauth_link(&self, name: &str, redirect_url: &str) -> Result<Value> {
        self.post(&format!("{}/generate_payment_configuration_oauth_link", self.waba_id()),
                  json!({"configuration_name": name, "redirect_url": redirect_url})).await
    }

    /// Status of an order_details payment: pending or captured, plus transactions.
    pub async fn get_payment(&self, configuration_name: &str, reference_id: &str) -> Result<Value> {
        self.get(&format!("{}/payments/{configuration_name}/{reference_id}", self.phone()), Value::Null).await
    }

    /// `amount`: {currency, value, offset}; `speed`: instant or normal.
    pub async fn refund_payment(&self, reference_id: &str, payment_config_id: &str, amount: Value, speed: Option<&str>) -> Result<Value> {
        let payload = body(json!({"reference_id": reference_id, "payment_config_id": payment_config_id,
                                  "amount": amount, "speed": speed}), Value::Null);
        self.post(&format!("{}/payments_refund", self.phone()), payload).await
    }

    // Business portfolio (tech providers and partners)

    pub async fn get_business(&self, business_id: &str, fields: Option<&str>) -> Result<Value> {
        self.get(business_id, json!({"fields": fields})).await
    }

    pub async fn list_owned_business_accounts(&self, business_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{business_id}/owned_whatsapp_business_accounts"), params).await
    }

    pub async fn list_client_business_accounts(&self, business_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{business_id}/client_whatsapp_business_accounts"), params).await
    }

    pub async fn list_business_accounts(&self, business_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{business_id}/whatsapp_business_accounts"), params).await
    }

    pub async fn create_business_account(&self, business_id: &str, account: Value) -> Result<Value> {
        self.post(&format!("{business_id}/whatsapp_business_accounts"), body(account, Value::Null)).await
    }

    pub async fn add_business_phone_numbers(&self, business_id: &str, fields: Value) -> Result<Value> {
        self.post(&format!("{business_id}/add_phone_numbers"), body(fields, Value::Null)).await
    }

    pub async fn list_extended_credits(&self, business_id: &str, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{business_id}/extendedcredits"), json!({"fields": fields})).await
    }

    pub async fn onboard_partners_to_mm_lite(&self, business_id: &str, solution_id: Option<&str>) -> Result<Value> {
        self.post_empty(&format!("{business_id}/onboard_partners_to_mm_lite"), json!({"solution_id": solution_id})).await
    }

    /// WABAs assigned to a (system) user.
    pub async fn list_user_business_accounts(&self, user_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{user_id}/assigned_whatsapp_business_accounts"), params).await
    }

    pub async fn list_message_history_events(&self, message_history_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{message_history_id}/events"), params).await
    }

    /// Any node by ID: account number, migration intent, bot, business profile, template group,
    /// credit allocation, ... .
    pub async fn get_node(&self, node_id: &str, fields: Option<&str>) -> Result<Value> {
        self.get(node_id, json!({"fields": fields})).await
    }

    pub async fn update_node(&self, node_id: &str, fields: Value) -> Result<Value> {
        self.post(node_id, body(fields, Value::Null)).await
    }

    /// E.g. a template group, or a credit allocation (revokes a shared credit line).
    pub async fn delete_node(&self, node_id: &str) -> Result<Value> {
        self.delete(node_id, Value::Null).await
    }

    /// Embedded Signup: the customer's business token, read with your system token. Requires
    /// `app_secret` on the client.
    pub async fn get_system_user_token(&self, business_id: &str) -> Result<String> {
        let payload = self.post_form(&format!("{business_id}/system_user_access_tokens"), json!({"fetch_only": "true"})).await?;
        str_field(&payload, "access_token").ok_or_else(|| fail("Meta returned no business token"))
    }

    pub async fn list_business_users(&self, business_id: &str, fields: Option<&str>) -> Result<Value> {
        self.get(&format!("{business_id}/business_users"), json!({"fields": fields})).await
    }

    /// Apps a Tech Provider picked in the Multi-Partner Solution flow.
    pub async fn list_app_details(&self) -> Result<Value> {
        self.get("me/application_details", Value::Null).await
    }

    pub async fn create_customer_base(&self, business_id: &str, name: &str) -> Result<Value> {
        self.post(&format!("{business_id}/messaging_customer_base"), json!({"messaging_customer_base_name": name})).await
    }

    pub async fn list_customer_bases(&self, business_id: &str) -> Result<Value> {
        self.get(&format!("{business_id}/messaging_customer_base"), Value::Null).await
    }

    pub async fn sign_max_price_agreement(&self, business_id: &str, signer_name: &str, signer_email: &str) -> Result<Value> {
        self.post(&format!("{business_id}/max_price_agreements"), json!({"signer_name": signer_name, "signer_email": signer_email})).await
    }

    /// Partner-led verification; `documents` are (file_name, content, mime_type).
    pub async fn submit_business_verification(&self, business_id: &str, end_business_id: &str, documents: Vec<(String, Vec<u8>, String)>) -> Result<Value> {
        let mut form = Form::new().text("end_business_id", end_business_id.to_owned());
        for (name, content, mime) in documents {
            form = form.part("business_documents[]", file_part(&name, &mime, content)?);
        }
        self.post_multipart(&format!("{business_id}/self_certify_whatsapp_business"), form, None).await
    }

    pub async fn list_business_verifications(&self, business_id: &str, end_business_id: Option<&str>) -> Result<Value> {
        self.get(&format!("{business_id}/self_certified_whatsapp_business_submissions"), json!({"end_business_id": end_business_id})).await
    }

    // Credit lines

    pub async fn share_credit_line(&self, credit_line_id: &str, receiving_business_id: &str) -> Result<Value> {
        self.post_empty(&format!("{credit_line_id}/whatsapp_credit_sharing"), json!({"receiving_business_id": receiving_business_id})).await
    }

    /// `share` also shares the line with the WABA's business in the same call.
    pub async fn attach_credit_line(&self, credit_line_id: &str, waba_id: &str, waba_currency: &str, share: bool) -> Result<Value> {
        let edge = if share { "whatsapp_credit_sharing_and_attach" } else { "whatsapp_credit_attach" };
        self.post_empty(&format!("{credit_line_id}/{edge}"), json!({"waba_id": waba_id, "waba_currency": waba_currency})).await
    }

    /// Revoke a share with delete_node(allocation_id).
    pub async fn list_credit_allocations(&self, credit_line_id: &str, receiving_business_id: &str) -> Result<Value> {
        self.get(&format!("{credit_line_id}/owning_credit_allocation_configs"),
                 json!({"receiving_business_id": receiving_business_id, "fields": "id,receiving_business,request_status"})).await
    }

    // Pre-verified phone numbers

    pub async fn list_preverified_numbers(&self, business_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{business_id}/preverified_numbers"), params).await
    }

    pub async fn share_preverified_numbers(&self, business_id: &str, fields: Value) -> Result<Value> {
        self.post(&format!("{business_id}/share_preverified_numbers"), body(fields, Value::Null)).await
    }

    pub async fn unshare_preverified_number(&self, business_id: &str, preverified_id: &str, partner_business_id: &str) -> Result<Value> {
        self.delete(&format!("{business_id}/share_preverified_numbers"),
                    json!({"partner_business_id": partner_business_id, "preverified_id": preverified_id})).await
    }

    pub async fn delete_preverified_number(&self, preverified_id: &str) -> Result<Value> {
        self.delete(preverified_id, Value::Null).await
    }

    pub async fn list_preverified_number_partners(&self, preverified_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{preverified_id}/partners"), params).await
    }

    pub async fn request_preverified_code(&self, preverified_id: &str, code_method: &str, language: &str) -> Result<Value> {
        self.post(&format!("{preverified_id}/request_code"), json!({"code_method": code_method, "language": language})).await
    }

    pub async fn verify_preverified_code(&self, preverified_id: &str, code: &str) -> Result<Value> {
        self.post(&format!("{preverified_id}/verify_code"), json!({"code": code})).await
    }

    // Multi-Partner Solutions

    pub async fn list_app_solutions(&self, app_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{app_id}/whatsapp_business_solutions"), params).await
    }

    pub async fn create_solution(&self, app_id: &str, solution: Value) -> Result<Value> {
        self.post(&format!("{app_id}/whatsapp_business_solution"), body(solution, Value::Null)).await
    }

    pub async fn list_connected_client_businesses(&self, app_id: &str, params: Value) -> Result<Value> {
        self.get(&format!("{app_id}/connected_client_businesses"), params).await
    }

    pub async fn get_solution_access_token(&self, solution_id: &str, business_id: &str) -> Result<Value> {
        self.get(&format!("{solution_id}/access_token"), json!({"business_id": business_id})).await
    }

    /// `action`: accept, reject, send_deactivation_request, accept_deactivation_request,
    /// reject_deactivation_request.
    pub async fn solution_action(&self, solution_id: &str, action: &str) -> Result<Value> {
        self.post_empty(&format!("{solution_id}/{action}"), Value::Null).await
    }
}
