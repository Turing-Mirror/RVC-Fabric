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
    Batch {
        #[serde(rename = "batchId")]
        batch_id: String,
        items: Vec<Value>,
    },
    Author {
        id: String,
        page: Option<u32>,
        cursor: Option<String>,
        query: Option<String>,
        limit: Option<u32>,
    },
    Owned {
        page: Option<u32>,
        cursor: Option<String>,
        query: Option<String>,
        limit: Option<u32>,
    },
    Asset {
        id: String,
    },
    Version {
        id: String,
        #[serde(rename = "versionId")]
        version_id: String,
    },
    CoverPreview {
        id: String,
    },
    Categories {
        parent: Option<String>,
    },
    Mine {
        state: Option<String>,
        page: Option<u32>,
        limit: Option<u32>,
        batch: Option<String>,
    },
    Withdraw {
        id: String,
    },
}

fn unavailable() -> ApiError {
    ApiError::new("unavailable", "Community is temporarily unavailable.")
}

fn catalog_query(url: &mut reqwest::Url, page: Option<u32>, cursor: Option<String>, query: Option<String>, limit: Option<u32>) {
    let mut pairs = url.query_pairs_mut();
    pairs.append_pair("productId", community_catalog::PRODUCT_ID);
    if let Some(page) = page {
        pairs.append_pair("page", &page.to_string());
    } else if let Some(cursor) = cursor {
        pairs.append_pair("cursor", &cursor);
    }
    if let Some(query) = query {
        pairs.append_pair("q", &query);
    }
    if let Some(limit) = limit {
        pairs.append_pair("limit", &limit.to_string());
    }
}

fn attach_cover(value: &mut Value, base: &reqwest::Url) {
    if let (Some(id), Some(cover)) = (value["id"].as_str(), value["coverUploadId"].as_str()) {
        let mut url = community_catalog::endpoint(base, &["assets", id, "cover"]);
        url.query_pairs_mut().append_pair("v", cover);
        value["coverUrl"] = json!(url.as_str());
    }
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
pub async fn community_publication(request: PublicationRequest) -> Result<Value, Value> {
    let result: ApiResult = async {
    let base = community_catalog::publication_base()?;
    let client = Client::builder()
        .timeout(Duration::from_secs(45))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| unavailable())?;
    let endpoint = |path: &[&str]| community_catalog::endpoint(&base, path);
    let public = matches!(&request, PublicationRequest::Author { .. }
        | PublicationRequest::Asset { .. } | PublicationRequest::Version { .. } | PublicationRequest::Categories { .. });
    let preview = matches!(&request, PublicationRequest::CoverPreview { .. });
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
        PublicationRequest::Batch { batch_id, items } => {
            if items.iter().any(|item| item["body"]["asset"]["kind"] != "model"
                || item["body"]["asset"]["metadata"]["family"] != community_catalog::FAMILY) {
                return Err(ApiError::invalid("Choose a voice package."));
            }
            json_body(client.post(endpoint(&["submissions", "batch"])), &json!({ "batchId": batch_id, "items": items }))
        }
        PublicationRequest::Author { id, page, cursor, query, limit } => {
            let mut url = endpoint(&["authors", &id]);
            catalog_query(&mut url, page, cursor, query, limit);
            client.get(url)
        }
        PublicationRequest::Owned { page, cursor, query, limit } => {
            let mut url = endpoint(&["me", "assets"]);
            catalog_query(&mut url, page, cursor, query, limit);
            client.get(url)
        }
        PublicationRequest::Asset { id } => client.get(endpoint(&["assets", &id])),
        PublicationRequest::Version { id, version_id } => client.get(endpoint(&["assets", &id, "versions", &version_id])),
        PublicationRequest::CoverPreview { id } => client.get(endpoint(&["uploads", &id, "content"])),
        PublicationRequest::Categories { parent } => {
            let mut url = endpoint(&["categories"]);
            if let Some(parent) = parent {
                url.query_pairs_mut().append_pair("parent", &parent);
            }
            client.get(url)
        }
        PublicationRequest::Mine { state, page, limit, batch } => {
            let mut url = endpoint(&["me", "submissions"]);
            url.query_pairs_mut()
                .append_pair("family", community_catalog::FAMILY);
            if let Some(state) = state {
                url.query_pairs_mut().append_pair("state", &state);
            }
            if let Some(batch) = batch {
                url.query_pairs_mut().append_pair("batch", &batch);
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
    let request = if public { request } else { request.bearer_auth(community_account::access_token().await?) };
    let response = request.send()
        .await
        .map_err(|_| unavailable())?;
    let status = response.status();
    if preview && status.is_success() {
        let mime = response.headers().get(header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok()).unwrap_or_default().to_owned();
        let size = response.content_length();
        if !matches!(mime.as_str(), "image/jpeg" | "image/png" | "image/webp" | "image/avif" | "image/gif")
            || size.is_none_or(|size| size > 8 * 1024 * 1024) {
            return Err(ApiError::invalid("Invalid Community cover."));
        }
        let bytes = response.bytes().await.map_err(|_| unavailable())?;
        return Ok(json!({ "url": format!("data:{mime};base64,{}", crate::wallpaper::encode_base64(&bytes)) }));
    }
    let body = response.text().await.map_err(|_| unavailable())?;
    let mut value: Value = serde_json::from_str(&body).map_err(|_| unavailable())?;
    if status.is_success() {
        if let Some(items) = value["items"].as_array_mut() {
            for item in items {
                if item.get("asset").is_none() {
                    attach_cover(item, &base);
                } else if item["state"] == "published" {
                    if let (Some(id), Some(cover)) = (item["assetId"].as_str(), item["coverUploadId"].as_str()) {
                        let mut url = endpoint(&["assets", id, "cover"]);
                        url.query_pairs_mut().append_pair("v", cover);
                        item["coverUrl"] = json!(url.as_str());
                    }
                }
            }
        }
        if let Some(asset) = value.get_mut("asset") {
            attach_cover(asset, &base);
        }
        return Ok(value);
    }
    let error = &value["error"];
    let code = error["code"].as_str().unwrap_or("unavailable");
    let mut failure = ApiError::new(
        code,
        error["message"]
            .as_str()
            .unwrap_or("Community request failed."),
    );
    if let Some(seconds) = error["retryAfter"].as_u64() {
        failure.details = json!({ "retryAfter": seconds });
    }
    Err(failure)
    }.await;
    result.map_err(|error| crate::diagnostics::api_error("community_publication", error))
}
