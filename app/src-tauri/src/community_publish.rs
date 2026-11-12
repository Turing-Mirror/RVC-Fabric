//! The desktop Community form uses the native Account session.
use reqwest::{header, Client, RequestBuilder};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::time::Duration;
use trm_app_protocol::{ApiError, ApiResult};

use crate::{community_account, community_catalog};

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case")]
pub enum PublicationRequest {
    Resolve {
        url: String,
        revision: Option<String>,
    },
    Cover {
        bytes: Vec<u8>,
    },
    Submit {
        body: Value,
        key: String,
    },
    Mine {
        state: Option<String>,
        page: Option<u32>,
        limit: Option<u32>,
    },
    Withdraw {
        id: String,
    },
}

fn unavailable() -> ApiError {
    ApiError::new("unavailable", "Community is temporarily unavailable.")
}

fn json_body(request: RequestBuilder, body: &Value) -> RequestBuilder {
    request
        .header(header::CONTENT_TYPE, "application/json")
        .body(body.to_string())
}

fn cover_body(request: RequestBuilder, bytes: &[u8]) -> ApiResult<RequestBuilder> {
    if bytes.len() > 2 * 1024 * 1024 || !bytes.starts_with(&[0xff, 0xd8, 0xff]) {
        return Err(ApiError::new("invalid_cover", "Choose a JPEG cover."));
    }
    let boundary = format!("Fabric{:x}", Sha256::digest(bytes));
    let mut body = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\npreview\r\n\
         --{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cover.jpg\"\r\n\
         Content-Type: image/jpeg\r\n\r\n"
    )
    .into_bytes();
    body.extend_from_slice(bytes);
    body.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());
    Ok(request
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={boundary}"),
        )
        .body(body))
}

#[tauri::command]
pub async fn community_publication(request: PublicationRequest) -> ApiResult {
    let base = community_catalog::publication_base()?;
    let client = Client::builder()
        .timeout(Duration::from_secs(45))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| unavailable())?;
    let endpoint = |path: &[&str]| community_catalog::endpoint(&base, path);
    let request = match request {
        PublicationRequest::Resolve { url, revision } => json_body(
            client.post(endpoint(&["sources", "resolve"])),
            &json!({ "url": url, "revision": revision }),
        ),
        PublicationRequest::Cover { bytes } => {
            cover_body(client.post(endpoint(&["uploads"])), &bytes)?
        }
        PublicationRequest::Submit { body, key } => {
            if body["asset"]["kind"] != "model"
                || body["asset"]["metadata"]["family"] != community_catalog::FAMILY
            {
                return Err(ApiError::invalid("Choose an RVC voice package."));
            }
            json_body(
                client
                    .post(endpoint(&["submissions"]))
                    .header("Idempotency-Key", key),
                &body,
            )
        }
        PublicationRequest::Mine { state, page, limit } => {
            let mut url = endpoint(&["me", "submissions"]);
            url.query_pairs_mut()
                .append_pair("family", community_catalog::FAMILY);
            if let Some(state) = state {
                url.query_pairs_mut().append_pair("state", &state);
            }
            if let Some(page) = page {
                url.query_pairs_mut().append_pair("page", &page.to_string());
            }
            if let Some(limit) = limit {
                url.query_pairs_mut()
                    .append_pair("limit", &limit.to_string());
            }
            client.get(url)
        }
        PublicationRequest::Withdraw { id } => {
            client.post(endpoint(&["submissions", &id, "withdraw"]))
        }
    };
    let token = community_account::access_token().await?;
    let response = request
        .bearer_auth(token)
        .send()
        .await
        .map_err(|_| unavailable())?;
    let status = response.status();
    let body = response.text().await.map_err(|_| unavailable())?;
    let value: Value = serde_json::from_str(&body).map_err(|_| unavailable())?;
    if status.is_success() {
        return Ok(value);
    }
    let error = &value["error"];
    let code = error["code"].as_str().unwrap_or("unavailable");
    Err(ApiError::new(
        code,
        error["message"]
            .as_str()
            .unwrap_or("Community request failed."),
    ))
}
