//! Adapts approved Community ZIP releases to the existing voice store.
use std::{
    collections::HashSet,
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

use reqwest::{blocking::Client, Url};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use trm_app_protocol::{ApiError, ApiResult};

pub(crate) const PRODUCT_ID: &str = "com.turingmirror.rvcfabric";
pub(crate) const FAMILY: &str = "rvc";
const COMMUNITY_API: &str = "https://api.turingmirror.com/v1/community";

fn is_loopback(url: &Url) -> bool {
    matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"))
}

fn public_url(value: &str, allow_local: bool) -> Result<Url, String> {
    let url = Url::parse(value).map_err(|e| e.to_string())?;
    if (url.scheme() != "https" && !(allow_local && url.scheme() == "http" && is_loopback(&url)))
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("Invalid public URL".into());
    }
    Ok(url)
}

pub(crate) fn configured_base(variable: &str, default: &str) -> Result<Url, String> {
    if cfg!(debug_assertions) {
        if let Ok(value) = std::env::var(variable) {
            let url = public_url(value.trim(), true)?;
            if url.query().is_none()
                && url.fragment().is_none()
                && (is_loopback(&url)
                    || url.as_str().trim_end_matches('/') == default.trim_end_matches('/'))
            {
                return Ok(url);
            }
            return Err("Invalid service address".into());
        }
    }
    public_url(default, false)
}

fn api_base() -> Result<Url, String> {
    configured_base("TRM_COMMUNITY_API_URL", COMMUNITY_API)
}

pub(crate) fn endpoint(api: &Url, segments: &[&str]) -> Url {
    let mut url = api.clone();
    url.set_query(None);
    url.set_fragment(None);
    let mut path = url.path_segments_mut().expect("HTTP URL");
    path.pop_if_empty();
    path.extend(segments.iter().copied());
    drop(path);
    url
}

pub(crate) fn links() -> Value {
    let account = crate::community_account::account_base().ok();
    json!({
        "enabled": publication_base().is_ok(),
        "accountUrl": account.as_ref().map(Url::as_str),
    })
}

pub(crate) fn publication_base() -> ApiResult<Url> {
    let base = api_base().map_err(ApiError::invalid)?;
    let account = crate::community_account::account_base()?;
    if is_loopback(&base) != is_loopback(&account) {
        return Err(ApiError::new("unavailable", "Publishing is unavailable."));
    }
    Ok(base)
}

fn client() -> Result<Client, String> {
    Client::builder()
        .timeout(Duration::from_secs(8))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|e| e.to_string())
}

fn request(client: &Client, url: Url) -> Result<Value, String> {
    let response = client.get(url).send().map_err(|e| e.to_string())?;
    if !response.status().is_success() {
        return Err(format!("Community returned HTTP {}", response.status()));
    }
    let body = response.text().map_err(|e| e.to_string())?;
    serde_json::from_str(&body).map_err(|e| e.to_string())
}

fn field<'a>(value: &'a Value, key: &str) -> &'a str {
    value[key].as_str().unwrap_or_default()
}

pub(crate) fn is_zip(path: &str) -> bool {
    Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| extension.eq_ignore_ascii_case("zip"))
}

fn valid_id(id: &str) -> bool {
    !id.is_empty() && !matches!(id, "." | "..") && !id.contains(['/', '\\'])
}

pub(crate) struct Package<'a> {
    pub asset_id: &'a str,
    pub version_id: &'a str,
    file_id: &'a str,
    path: &'a str,
    sha256: &'a str,
    pub size: u64,
    legacy_id: &'a str,
}

impl<'a> Package<'a> {
    pub(crate) fn from_entry(entry: &'a Value) -> Result<Option<Self>, String> {
        if entry.get("community_file_id").is_none() {
            return Ok(None);
        }
        let package = Self {
            asset_id: field(entry, "id"),
            version_id: field(entry, "community_version_id"),
            file_id: field(entry, "community_file_id"),
            path: field(entry, "community_package_path"),
            sha256: field(entry, "sha256"),
            size: entry["size_bytes"].as_u64().unwrap_or_default(),
            legacy_id: field(entry, "legacy_catalog_id"),
        };
        if [package.asset_id, package.version_id, package.file_id]
            .iter()
            .any(|id| !valid_id(id))
            || !is_zip(package.path)
            || package.sha256.len() != 64
            || !package.sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
            || package.size == 0
        {
            return Err(refresh_required());
        }
        Ok(Some(package))
    }

    pub(crate) fn staging_id(&self) -> String {
        path_id(&format!("{}/{}", self.asset_id, self.version_id))
    }

    pub(crate) fn model_id(&self) -> String {
        path_id(self.asset_id)
    }

    pub(crate) fn installed<'v>(
        &self,
        installed: &'v [InstalledVoice],
    ) -> Option<&'v InstalledVoice> {
        installed
            .iter()
            .filter(|voice| voice.config_text("community_asset_id") == self.asset_id)
            .max_by_key(|voice| voice.config_text("community_version_id") == self.version_id)
            .or_else(|| {
                if self.legacy_id.is_empty() {
                    return None;
                }
                let legacy_dir = crate::voices::safe_model_dir_name(self.legacy_id).ok()?;
                installed.iter().find(|voice| {
                    let online_id = voice.config_text("online_id");
                    voice.config_text("community_asset_id").is_empty()
                        && (online_id == self.legacy_id
                            || voice.id == legacy_dir && online_id == legacy_dir)
                })
            })
    }

    pub(crate) fn download_url(&self) -> Result<String, String> {
        let api = api_base()?;
        let descriptor = request(
            &client()?,
            endpoint(&api, &["files", self.file_id, "download"]),
        )?;
        self.verified_url(&descriptor, &api)
    }

    fn verified_url(&self, descriptor: &Value, api: &Url) -> Result<String, String> {
        let origin = &descriptor["origin"];
        if field(origin, "assetId") != self.asset_id
            || field(origin, "versionId") != self.version_id
            || field(descriptor, "path") != self.path
            || descriptor["sizeBytes"].as_u64() != Some(self.size)
            || !field(descriptor, "sha256").eq_ignore_ascii_case(self.sha256)
        {
            return Err(refresh_required());
        }
        public_url(field(descriptor, "url"), is_loopback(api)).map(|url| url.to_string())
    }

    pub(crate) fn verify_size(&self, path: &Path) -> Result<(), String> {
        if path.metadata().ok().map(|meta| meta.len()) != Some(self.size) {
            return Err(refresh_required());
        }
        Ok(())
    }

    pub(crate) fn verify_file(&self, path: &Path) -> Result<(), String> {
        self.verify_size(path)?;
        crate::download::verify_sha256(path, self.sha256)
    }
}

fn path_id(identity: &str) -> String {
    let hash = format!("{:x}", Sha256::digest(identity));
    format!("community-{}", &hash[..24])
}

pub(crate) fn refresh_required() -> String {
    crate::i18n::t("community.refreshBeforeDownload")
}

pub(crate) struct InstalledVoice {
    pub id: String,
    pub pth: PathBuf,
    pub config: Map<String, Value>,
}

impl InstalledVoice {
    pub(crate) fn config_text(&self, key: &str) -> &str {
        self.config
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
    }
}

pub(crate) fn installed_voices(root: &Path) -> Vec<InstalledVoice> {
    fs::read_dir(crate::paths::models_dir(root))
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().is_ok_and(|kind| kind.is_dir()))
        .filter_map(|entry| {
            let id = entry.file_name().into_string().ok()?;
            if id.starts_with('.') {
                return None;
            }
            let dir = entry.path();
            Some(InstalledVoice {
                id,
                pth: crate::voices::find_pth(&dir).filter(|path| path.is_file())?,
                config: crate::voices::read_sidecar(&dir),
            })
        })
        .collect()
}

fn entry(asset: &Value, api: &Url) -> Option<Value> {
    let version = &asset["compatibleVersion"];
    package_entry(asset, version, &version["package"], api)
}

fn package_entry(asset: &Value, version: &Value, package: &Value, api: &Url) -> Option<Value> {
    if asset["state"] != "published"
        || asset["kind"] != "model"
        || asset["metadata"]["family"] != FAMILY
    {
        return None;
    }
    let id = field(asset, "id");
    let meta = &asset["metadata"];
    let cover = if let Some(upload) = asset["coverUploadId"].as_str().filter(|id| !id.is_empty()) {
        let mut url = endpoint(api, &["assets", id, "cover"]);
        url.query_pairs_mut().append_pair("v", upload);
        url.to_string()
    } else if field(asset, "previewMimeType").starts_with("image/") {
        asset["previewFileId"]
            .as_str()
            .filter(|id| !id.is_empty())
            .map(|file| endpoint(api, &["files", file, "content"]).to_string())
            .unwrap_or_default()
    } else {
        String::new()
    };
    let mut entry = json!({
        "id": id,
        "name": field(asset, "title"),
        "version": field(version, "label"),
        "community_version_id": field(version, "id"),
        "community_file_id": field(package, "id"),
        "community_package_path": field(package, "path"),
        "legacy_catalog_id": field(meta, "fabricModelId"),
        "size_bytes": package["sizeBytes"],
        "sha256": package["sha256"],
        "cover_url": cover,
        "description": field(asset, "description"),
        "author": field(asset, "originalAuthor"),
        "community_author_id": field(asset, "communityAuthorId"),
        "author_url": public_url(field(asset, "authorUrl"), false).ok().map(|url| url.to_string()),
        "series": field(meta, "series"),
        "group": field(meta, "group"),
        "date": version["createdAt"].as_str().filter(|date| !date.is_empty()).unwrap_or(field(asset, "createdAt")),
        "source_url": public_url(field(asset, "upstreamUrl"), false).ok().map(|url| url.to_string()),
        "license": asset["license"],
        "origin": "community",
        "official": false,
    });
    let staging_id = Package::from_entry(&entry).ok()??.staging_id();
    entry["community_staging_id"] = json!(staging_id);
    for (from, to) in [
        ("nameI18n", "name_i18n"),
        ("seriesI18n", "series_i18n"),
        ("groupI18n", "group_i18n"),
        ("authorI18n", "author_i18n"),
        ("descriptionI18n", "description_i18n"),
    ] {
        if meta[from].is_object() {
            entry[to] = meta[from].clone();
        }
    }
    Some(entry)
}

fn published_release_entry(
    release: &Value,
    asset_id: &str,
    version_id: &str,
    file_id: &str,
    api: &Url,
) -> Option<Value> {
    let asset = &release["asset"];
    let version = &release["version"];
    if asset["id"] != asset_id
        || version["id"] != version_id
        || version["assetId"] != asset_id
        || version["reviewState"] != "published"
    {
        return None;
    }
    let package = version["files"]
        .as_array()?
        .iter()
        .find(|file| file["id"] == file_id && file["role"] == "package")?;
    package_entry(asset, version, package, api)
}

pub(crate) fn release_entry(
    asset_id: &str,
    version_id: &str,
    file_id: &str,
) -> Result<Value, String> {
    if ![asset_id, version_id, file_id].into_iter().all(valid_id) {
        return Err("Select a published RVC ZIP from Community.".into());
    }
    let api = api_base()?;
    let release = request(
        &client()?,
        endpoint(&api, &["assets", asset_id, "versions", version_id]),
    )
    .map_err(|error| {
        crate::logging::shell_log!(format!(
            "community release {asset_id}/{version_id}: {error}"
        ));
        "Could not load this Community release.".to_owned()
    })?;
    published_release_entry(&release, asset_id, version_id, file_id, &api)
        .ok_or_else(|| "Select a published RVC ZIP from Community.".to_owned())
}

fn load_entries(api: &Url) -> Result<Vec<Value>, String> {
    let client = client()?;
    let mut entries = Vec::new();
    let mut cursors = HashSet::new();
    let mut url = endpoint(api, &["assets"]);
    url.query_pairs_mut()
        .append_pair("productId", PRODUCT_ID)
        .append_pair("limit", "100");
    let mut page_url = url.clone();
    loop {
        let page = request(&client, page_url)?;
        let items = page["items"]
            .as_array()
            .ok_or("Invalid Community catalog")?;
        entries.extend(items.iter().filter_map(|asset| entry(asset, api)));
        let next = field(&page, "nextCursor");
        if next.is_empty() {
            return Ok(entries);
        }
        if !cursors.insert(next.to_owned()) {
            return Err("Invalid Community catalog cursor".into());
        }
        page_url = url.clone();
        page_url.query_pairs_mut().append_pair("cursor", next);
    }
}

pub(crate) fn entries(root: &Path, prefer_remote: bool) -> Vec<Value> {
    let Ok(api) = api_base() else {
        return Vec::new();
    };
    let cache = crate::paths::user_data(root).join("community_catalog_cache.json");
    if prefer_remote {
        match load_entries(&api) {
            Ok(entries) => {
                let _ = trm_app_protocol::discovery::write_json(
                    &cache,
                    &json!({ "url": api.as_str(), "entries": entries }),
                );
                return entries;
            }
            Err(error) => crate::logging::shell_log!(format!("community catalog: {error}")),
        }
    }
    fs::read_to_string(&cache)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .filter(|data| field(data, "url") == api.as_str())
        .and_then(|data| data["entries"].as_array().cloned())
        .unwrap_or_default()
}

pub(crate) fn annotate_installed(root: &Path, entries: &mut Vec<Value>) {
    if entries.is_empty() {
        return;
    }
    let installed = installed_voices(root);
    entries.retain_mut(|entry| {
        let Ok(Some(package)) = Package::from_entry(entry) else {
            return false;
        };
        let matching = package.installed(&installed);
        let update = matching
            .is_some_and(|voice| voice.config_text("community_version_id") != package.version_id);
        entry["installed"] = json!(matching.is_some());
        if let Some(voice) = matching {
            entry["installed_voice_id"] = json!(voice.id);
            entry["update_available"] = json!(update);
        }
        true
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn asset() -> Value {
        json!({
            "id": "asset-1",
            "kind": "model",
            "state": "published",
            "metadata": { "family": "rvc", "fabricModelId": "older-model" },
            "compatibleVersion": {
                "id": "release-1",
                "package": {
                    "id": "file-1", "path": "models/pack.ZIP",
                    "sizeBytes": 32, "sha256": "a".repeat(64)
                }
            }
        })
    }

    #[test]
    fn catalog_requires_an_approved_rvc_zip_with_integrity_fields() {
        let base = Url::parse(COMMUNITY_API).unwrap();
        let original = asset();
        assert!(entry(&original, &base).is_some());
        for (pointer, value) in [
            ("/kind", json!("workflow")),
            ("/state", json!("pending")),
            ("/metadata/family", json!("gpt-sovits")),
            ("/compatibleVersion/package/path", json!("weights.pth")),
            ("/compatibleVersion/package/id", json!("")),
            ("/compatibleVersion/package/sizeBytes", json!(0)),
            ("/compatibleVersion/package/sha256", json!("z".repeat(64))),
        ] {
            let mut invalid = original.clone();
            *invalid.pointer_mut(pointer).unwrap() = value;
            assert!(entry(&invalid, &base).is_none(), "{pointer}");
        }
    }

    #[test]
    fn install_uses_the_exact_published_rvc_package() {
        let base = Url::parse(COMMUNITY_API).unwrap();
        let asset = asset();
        let mut package = asset["compatibleVersion"]["package"].clone();
        package["role"] = json!("package");
        let release = json!({
            "asset": asset,
            "version": {
                "id": "release-1",
                "assetId": "asset-1",
                "label": "v1",
                "reviewState": "published",
                "files": [
                    {"id": "other-zip", "role": "config", "path": "other.zip"},
                    package
                ],
            }
        });
        let install_entry =
            |value: &Value| published_release_entry(value, "asset-1", "release-1", "file-1", &base);
        let entry = install_entry(&release).unwrap();
        assert_eq!(entry["community_version_id"], "release-1");
        assert_eq!(entry["community_file_id"], "file-1");
        assert_eq!(entry["legacy_catalog_id"], "older-model");
        assert!(
            published_release_entry(&release, "asset-1", "release-1", "other-zip", &base).is_none()
        );
        for (pointer, value) in [
            ("/asset/state", json!("withdrawn")),
            ("/asset/metadata/family", json!("gpt-sovits")),
            ("/version/id", json!("release-2")),
            ("/version/assetId", json!("asset-2")),
            ("/version/reviewState", json!("pending")),
            ("/version/files/1/id", json!("file-2")),
            ("/version/files/1/role", json!("config")),
            ("/version/files/1/path", json!("weights.pth")),
        ] {
            let mut mismatched = release.clone();
            *mismatched.pointer_mut(pointer).unwrap() = value;
            assert!(install_entry(&mismatched).is_none(), "{pointer}");
        }
    }

    #[test]
    fn catalog_requests_the_rvc_product_anonymously() {
        use std::io::{BufRead, BufReader, Write};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = Url::parse(&format!(
            "http://{}/v1/community",
            listener.local_addr().unwrap()
        ))
        .unwrap();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let request: Vec<_> = BufReader::new(&stream)
                .lines()
                .map(Result::unwrap)
                .take_while(|line| !line.is_empty())
                .collect();
            assert!(request[0].starts_with("GET /v1/community/assets?"));
            assert!(request[0].contains("productId=com.turingmirror.rvcfabric"));
            assert!(request
                .iter()
                .all(|line| !line.to_ascii_lowercase().starts_with("authorization:")));
            let body = json!({ "items": [asset()] }).to_string();
            write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len(),
            )
            .unwrap();
        });
        let rows = load_entries(&base).unwrap();
        assert_eq!(rows[0]["community_file_id"], "file-1");
        assert_eq!(rows[0]["community_package_path"], "models/pack.ZIP");
        server.join().unwrap();
    }

    #[test]
    fn download_descriptor_must_match_the_reviewed_file() {
        let base = Url::parse(COMMUNITY_API).unwrap();
        let entry = entry(&asset(), &base).unwrap();
        let package = Package::from_entry(&entry).unwrap().unwrap();
        let descriptor = json!({
            "url": "https://example.org/pack.ZIP",
            "origin": {"assetId":"asset-1", "versionId":"release-1"},
            "path": "models/pack.ZIP",
            "sha256": "A".repeat(64),
            "sizeBytes": 32
        });
        assert!(package.verified_url(&descriptor, &base).is_ok());
        for (pointer, value) in [
            ("/origin/assetId", json!("different")),
            ("/origin/versionId", json!("release-2")),
            ("/path", json!("other/pack.ZIP")),
            ("/sha256", json!("b".repeat(64))),
            ("/sizeBytes", json!(33)),
            ("/url", json!("http://127.0.0.1/pack.ZIP")),
        ] {
            let mut mismatched = descriptor.clone();
            *mismatched.pointer_mut(pointer).unwrap() = value;
            assert!(
                package.verified_url(&mismatched, &base).is_err(),
                "{pointer}"
            );
        }
    }

    #[test]
    fn shared_releases_recognize_legacy_identity_and_keep_a_stable_model_id() {
        let base = Url::parse(COMMUNITY_API).unwrap();
        let asset = asset();
        let release = entry(&asset, &base).unwrap();
        let first = Package::from_entry(&release).unwrap().unwrap();
        let mut newer = release.clone();
        newer["community_version_id"] = json!("release-2");
        let second = Package::from_entry(&newer).unwrap().unwrap();
        let installed = [InstalledVoice {
            id: "older-model".into(),
            pth: PathBuf::from("older-model/original.pth"),
            config: Map::from_iter([("online_id".into(), json!("older-model"))]),
        }];
        assert_eq!(second.installed(&installed).unwrap().pth, installed[0].pth);
        assert_eq!(first.model_id(), second.model_id());
        assert_ne!(first.staging_id(), second.staging_id());
    }
}
