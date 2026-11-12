//! Native external-browser OIDC. Credentials never cross the webview IPC boundary.
use openidconnect::{
    core::{
        CoreAuthenticationFlow, CoreClient, CoreProviderMetadata, CoreTokenResponse,
        CoreUserInfoClaims,
    },
    reqwest, AccessTokenHash, AuthorizationCode, ClientId, CsrfToken, IssuerUrl, Nonce,
    OAuth2TokenResponse, PkceCodeChallenge, RedirectUrl, RefreshToken, Scope, SubjectIdentifier,
    TokenResponse,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    OnceLock,
};
use tauri_plugin_opener::OpenerExt;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use trm_app_protocol::{ApiError, ApiResult};
static BUSY: AtomicBool = AtomicBool::new(false);
static CANCEL: AtomicBool = AtomicBool::new(false);
struct Session {
    profile: Value,
    access: String,
    expires: std::time::Instant,
    checked: std::time::Instant,
}
impl Session {
    fn new(profile: Value, token: &CoreTokenResponse) -> Self {
        let checked = std::time::Instant::now();
        let lifetime = token
            .expires_in()
            .unwrap_or(std::time::Duration::from_secs(60));
        let expires = checked + lifetime.saturating_sub(std::time::Duration::from_secs(10));
        Self {
            profile,
            access: token.access_token().secret().clone(),
            expires,
            checked,
        }
    }
}
static CACHE: OnceLock<tokio::sync::Mutex<Option<Session>>> = OnceLock::new();
#[derive(Serialize, Deserialize)]
struct Saved {
    issuer: String,
    refresh: String,
    profile: Value,
}
const ACCOUNT_URL: &str = "https://account.turingmirror.com";
const DESKTOP_CLIENT_ID: &str = "tm-desktop-v1";
const KEYRING_SERVICE: &str = "TuringMirror.RVCFabric.Account";

pub(crate) fn account_base() -> ApiResult<reqwest::Url> {
    let url = crate::community_catalog::configured_base("TRM_ACCOUNT_URL", ACCOUNT_URL)
        .map_err(ApiError::invalid)?;
    if url.path() != "/" {
        return Err(ApiError::invalid("The TRM Account address is invalid."));
    }
    Ok(url)
}

fn issuer() -> ApiResult<String> {
    Ok(crate::community_catalog::endpoint(&account_base()?, &["api", "auth"]).to_string())
}

fn client_id(issuer: &str) -> String {
    if cfg!(debug_assertions) && !issuer.starts_with(ACCOUNT_URL) {
        if let Ok(id) = std::env::var("TRM_ACCOUNT_CLIENT_ID") {
            return id;
        }
    }
    DESKTOP_CLIENT_ID.into()
}

fn entry(issuer: &str) -> ApiResult<keyring::Entry> {
    keyring::Entry::new(
        KEYRING_SERVICE,
        &format!("{}|{}", issuer, client_id(issuer)),
    )
    .map_err(|_| {
        ApiError::new(
            "credential_store_unavailable",
            "Could not open the system credential store.",
        )
    })
}
fn load(issuer: &str) -> ApiResult<Option<Saved>> {
    match entry(issuer)?.get_password() {
        Ok(value) => serde_json::from_str(&value)
            .map(Some)
            .map_err(|_| ApiError::new("session_invalid", "Sign in to TRM Account again.")),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(_) => Err(ApiError::new(
            "credential_store_unavailable",
            "Could not read the saved sign-in.",
        )),
    }
}
fn save(saved: &Saved) -> ApiResult<()> {
    entry(&saved.issuer)?
        .set_password(&serde_json::to_string(saved).map_err(ApiError::invalid)?)
        .map_err(|_| {
            ApiError::new(
                "credential_store_unavailable",
                "Could not save the sign-in.",
            )
        })
}
fn http() -> ApiResult<reqwest::Client> {
    reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|_| ApiError::new("account_unavailable", "Could not connect to TRM Account."))
}
fn cache() -> &'static tokio::sync::Mutex<Option<Session>> {
    CACHE.get_or_init(|| tokio::sync::Mutex::new(None))
}
async fn cancelable_request<T, E>(
    request: impl std::future::Future<Output = Result<T, E>>,
    cancel: &AtomicBool,
    code: &str,
    message: &str,
) -> ApiResult<T> {
    let canceled = async {
        while !cancel.load(Ordering::Acquire) {
            tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        }
    };
    tokio::select! {
        biased;
        _ = canceled => Err(ApiError::canceled()),
        result = request => result.map_err(|_| ApiError::new(code, message)),
    }
}
async fn sign_in(app: tauri::AppHandle) -> ApiResult {
    if BUSY.swap(true, Ordering::AcqRel) {
        return Err(ApiError::new(
            "login_pending",
            "Complete sign-in in your browser.",
        ));
    }
    struct Reset;
    impl Drop for Reset {
        fn drop(&mut self) {
            BUSY.store(false, Ordering::Release);
        }
    }
    let _reset = Reset;
    CANCEL.store(false, Ordering::Release);
    let issuer = issuer()?;
    let http = http()?;
    let metadata = cancelable_request(
        CoreProviderMetadata::discover_async(
            IssuerUrl::new(issuer.clone()).map_err(ApiError::invalid)?,
            &http,
        ),
        &CANCEL,
        "account_unavailable",
        "Could not connect to TRM Account.",
    )
    .await?;
    let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0)).await?;
    let redirect = format!(
        "http://127.0.0.1:{}/callback",
        listener.local_addr()?.port()
    );
    let client =
        CoreClient::from_provider_metadata(metadata, ClientId::new(client_id(&issuer)), None)
            .set_redirect_uri(RedirectUrl::new(redirect.clone()).map_err(ApiError::invalid)?);
    let (challenge, verifier) = PkceCodeChallenge::new_random_sha256();
    let (authorize, state, nonce) = client
        .authorize_url(
            CoreAuthenticationFlow::AuthorizationCode,
            CsrfToken::new_random,
            Nonce::new_random,
        )
        .add_scope(Scope::new("profile".into()))
        .add_scope(Scope::new("email".into()))
        .add_scope(Scope::new("offline_access".into()))
        .set_pkce_challenge(challenge)
        .url();
    app.opener()
        .open_url(authorize.as_str(), None::<&str>)
        .map_err(|_| ApiError::new("browser_failed", "Could not open your browser."))?;
    let started = std::time::Instant::now();
    let (code, mut connection) = loop {
        if CANCEL.load(Ordering::Acquire) {
            return Err(ApiError::canceled());
        }
        if started.elapsed() > std::time::Duration::from_secs(300) {
            return Err(ApiError::new(
                "login_timeout",
                "Sign-in timed out. Try again.",
            ));
        }
        let incoming =
            tokio::time::timeout(std::time::Duration::from_millis(250), listener.accept()).await;
        let Ok(Ok((mut connection, peer))) = incoming else {
            continue;
        };
        if !peer.ip().is_loopback() {
            continue;
        }
        let mut bytes = vec![0u8; 8192];
        let Ok(Ok(count)) = tokio::time::timeout(
            std::time::Duration::from_secs(3),
            connection.read(&mut bytes),
        )
        .await
        else {
            continue;
        };
        let line = String::from_utf8_lossy(&bytes[..count]);
        let request = line.lines().next().unwrap_or("");
        let Some(target) = request
            .strip_prefix("GET ")
            .and_then(|s| s.split(' ').next())
        else {
            continue;
        };
        let Ok(url) = reqwest::Url::parse(&format!("http://127.0.0.1{target}")) else {
            continue;
        };
        if url.path() != "/callback" {
            let _ = connection
                .write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                .await;
            continue;
        }
        let params = url
            .query_pairs()
            .collect::<std::collections::HashMap<_, _>>();
        if params
            .get("state")
            .is_none_or(|value| CsrfToken::new(value.to_string()) != state)
        {
            let _ = connection
                .write_all(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
                .await;
            continue;
        }
        if params
            .get("iss")
            .is_some_and(|value| value.as_ref() != issuer)
        {
            return Err(ApiError::new(
                "issuer_mismatch",
                "Could not verify the sign-in provider.",
            ));
        }
        if params.contains_key("error") {
            let _ = connection
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
                .await;
            return Err(ApiError::new("login_declined", "Sign-in canceled."));
        }
        let Some(code) = params.get("code").map(|s| s.to_string()) else {
            continue;
        };
        break (code, connection);
    };
    let token_request = client
        .exchange_code(AuthorizationCode::new(code))
        .map_err(|_| ApiError::new("login_failed", "Could not complete sign-in."))?
        .set_pkce_verifier(verifier);
    let token = cancelable_request(
        token_request.request_async(&http),
        &CANCEL,
        "login_failed",
        "Could not complete sign-in.",
    )
    .await?;
    let id_token = token.id_token().ok_or_else(|| {
        ApiError::new(
            "identity_missing",
            "TRM Account did not return your profile.",
        )
    })?;
    let verifier = client.id_token_verifier();
    let claims = id_token
        .claims(&verifier, &nonce)
        .map_err(|_| ApiError::new("identity_invalid", "Could not verify your identity."))?;
    if let Some(expected) = claims.access_token_hash() {
        let actual = AccessTokenHash::from_token(
            token.access_token(),
            id_token.signing_alg().map_err(ApiError::invalid)?,
            id_token.signing_key(&verifier).map_err(ApiError::invalid)?,
        )
        .map_err(ApiError::invalid)?;
        if &actual != expected {
            return Err(ApiError::new(
                "identity_invalid",
                "Could not verify your identity.",
            ));
        }
    }
    let info_request = client
        .user_info(token.access_token().clone(), Some(claims.subject().clone()))
        .map_err(|_| {
            ApiError::new(
                "account_unavailable",
                "Could not read your TRM Account profile.",
            )
        })?;
    let info: CoreUserInfoClaims = cancelable_request(
        info_request.request_async(&http),
        &CANCEL,
        "account_unavailable",
        "Could not read your TRM Account profile.",
    )
    .await?;
    let profile = json!({"id":info.subject().as_str(),"email":info.email().map(|s|s.as_str()),"emailVerified":info.email_verified(),"name":info.name().and_then(|n|n.get(None)).map(|s|s.as_str()).unwrap_or("TRM Account")});
    let refresh = token
        .refresh_token()
        .ok_or_else(|| {
            ApiError::new(
                "refresh_missing",
                "TRM Account did not return a refresh token.",
            )
        })?
        .secret()
        .clone();
    {
        let mut cached = cache().lock().await;
        if CANCEL.load(Ordering::Acquire) {
            return Err(ApiError::canceled());
        }
        save(&Saved {
            issuer,
            refresh,
            profile: profile.clone(),
        })?;
        *cached = Some(Session::new(profile.clone(), &token));
    }
    let html="<!doctype html><meta charset=utf-8><title>TRM Account</title><p>You are signed in. Return to RVC Fabric.</p>";
    let response=format!("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n{html}",html.len());
    let _ = connection.write_all(response.as_bytes()).await;
    Ok(json!({"profile":profile,"offline":false}))
}
// Only transport and temporary service failures use the previously verified profile.
// Invalid credentials, malformed claims and subject mismatches remain errors.
fn profile_after_user_info<E: std::error::Error + 'static>(
    saved_profile: &Value,
    result: Result<CoreUserInfoClaims, openidconnect::UserInfoError<E>>,
) -> ApiResult {
    match result {
        Ok(info) => Ok(json!({"profile": {
            "id": info.subject().as_str(),
            "email": info.email().map(|value| value.as_str()),
            "emailVerified": info.email_verified(),
            "name": info.name().and_then(|value| value.get(None)).map(|value| value.as_str()).unwrap_or("TRM Account")
        }, "offline": false})),
        Err(openidconnect::UserInfoError::Request(_)) => {
            Ok(json!({"profile": saved_profile, "offline": true}))
        }
        Err(openidconnect::UserInfoError::Response(status, _, _))
            if status.is_server_error() || matches!(status.as_u16(), 408 | 429) =>
        {
            Ok(json!({"profile": saved_profile, "offline": true}))
        }
        Err(_) => Err(ApiError::new(
            "account_unavailable",
            "Could not read your TRM Account profile.",
        )),
    }
}
async fn current() -> ApiResult {
    let mut cached = cache().lock().await;
    if let Some(session) = cached.as_ref() {
        if session.checked.elapsed() < std::time::Duration::from_secs(60) {
            return Ok(json!({"profile":session.profile,"offline":false}));
        }
    }
    refresh_session(issuer()?, &mut cached).await
}

pub(crate) async fn access_token() -> ApiResult<String> {
    let mut cached = cache().lock().await;
    if let Some(session) = cached
        .as_ref()
        .filter(|session| session.expires > std::time::Instant::now())
    {
        return Ok(session.access.clone());
    }
    let status = refresh_session(issuer()?, &mut cached).await?;
    if status["offline"] == true {
        return Err(ApiError::new(
            "unavailable",
            "Could not connect to TRM Account.",
        ));
    }
    cached
        .as_ref()
        .filter(|session| session.expires > std::time::Instant::now())
        .map(|session| session.access.clone())
        .ok_or_else(|| ApiError::new("auth_required", "Sign in to TRM Account."))
}

async fn refresh_session(issuer: String, cached: &mut Option<Session>) -> ApiResult {
    let Some(mut saved) = load(&issuer)? else {
        *cached = None;
        return Ok(json!({"profile":null}));
    };
    let http = http()?;
    let metadata = match CoreProviderMetadata::discover_async(
        IssuerUrl::new(issuer.clone()).map_err(ApiError::invalid)?,
        &http,
    )
    .await
    {
        Ok(value) => value,
        Err(_) => return Ok(json!({"profile":saved.profile,"offline":true})),
    };
    let client =
        CoreClient::from_provider_metadata(metadata, ClientId::new(client_id(&issuer)), None);
    let token = match client
        .exchange_refresh_token(&RefreshToken::new(saved.refresh.clone()))
        .map_err(|_| ApiError::new("account_unavailable", "Could not refresh your sign-in."))?
        .request_async(&http)
        .await
    {
        Ok(value) => value,
        Err(openidconnect::RequestTokenError::ServerResponse(error))
            if error.error() == &openidconnect::core::CoreErrorResponseType::InvalidGrant =>
        {
            let _ = entry(&issuer)?.delete_credential();
            *cached = None;
            return Ok(json!({"profile":null}));
        }
        Err(_) => return Ok(json!({"profile":saved.profile,"offline":true})),
    };
    if let Some(refresh) = token.refresh_token() {
        saved.refresh = refresh.secret().clone();
        save(&saved)?;
    }
    let info = client
        .user_info(
            token.access_token().clone(),
            saved.profile["id"]
                .as_str()
                .map(|s| SubjectIdentifier::new(s.into())),
        )
        .map_err(|_| {
            ApiError::new(
                "account_unavailable",
                "Could not read your TRM Account profile.",
            )
        })?
        .request_async(&http)
        .await;
    let current = profile_after_user_info(&saved.profile, info)?;
    if current["offline"] == true {
        return Ok(current);
    }
    saved.profile = current["profile"].clone();
    save(&saved)?;
    *cached = Some(Session::new(saved.profile.clone(), &token));
    Ok(current)
}

// The frontend receives only presentation fields, never native credentials.
fn public_status(current: Value) -> Value {
    let profile = &current["profile"];
    json!({
        "signedIn": profile["id"].as_str().is_some_and(|id| !id.is_empty()),
        "displayName": profile["name"].as_str(),
        "email": profile["email"].as_str(),
        "offline": current["offline"].as_bool().unwrap_or(false)
    })
}

#[tauri::command]
pub async fn community_account_status() -> ApiResult {
    current().await.map(public_status)
}

#[tauri::command]
pub async fn community_account_sign_in(app: tauri::AppHandle) -> ApiResult {
    sign_in(app).await.map(public_status)
}

#[tauri::command]
pub async fn community_account_sign_out() -> ApiResult {
    CANCEL.store(true, Ordering::Release);
    let issuer = issuer()?;
    let mut cached = cache().lock().await;
    match entry(&issuer)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => {}
        Err(_) => {
            return Err(ApiError::new(
                "credential_store_unavailable",
                "Could not remove the saved sign-in.",
            ))
        }
    }
    *cached = None;
    Ok(public_status(json!({"profile": null})))
}

#[cfg(test)]
mod cancellation_tests {
    use super::*;
    #[tokio::test]
    async fn cancellation_drops_a_pending_request() {
        let cancel = AtomicBool::new(false);
        let wait = cancelable_request(
            std::future::pending::<Result<(), ()>>(),
            &cancel,
            "offline",
            "Offline",
        );
        let stop = async {
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            cancel.store(true, Ordering::Release);
        };
        let (result, _) = tokio::time::timeout(std::time::Duration::from_secs(1), async {
            tokio::join!(wait, stop)
        })
        .await
        .unwrap();
        assert_eq!(result.unwrap_err().code, "canceled");
    }
    #[tokio::test]
    async fn canceled_request_does_not_report_a_network_error() {
        let cancel = AtomicBool::new(true);
        let result =
            cancelable_request(async { Err::<(), ()>(()) }, &cancel, "offline", "Offline").await;
        assert_eq!(result.unwrap_err().code, "canceled");
    }
}

#[cfg(test)]
mod restoration_tests {
    use super::*;
    use openidconnect::UserInfoError;
    use std::io;

    #[test]
    fn transient_user_info_failure_keeps_the_verified_profile_offline() {
        let profile = json!({"id": "saved-subject", "name": "Saved account"});
        let disconnected = UserInfoError::Request(io::Error::from(io::ErrorKind::TimedOut));
        let result = profile_after_user_info(&profile, Err(disconnected)).unwrap();
        assert_eq!(result, json!({"profile": profile, "offline": true}));
        for status in [408, 429, 500, 503] {
            let failure = UserInfoError::<io::Error>::Response(
                reqwest::StatusCode::from_u16(status).unwrap(),
                Vec::new(),
                String::new(),
            );
            assert_eq!(
                profile_after_user_info(&profile, Err(failure)).unwrap(),
                result
            );
        }
    }

    #[test]
    fn invalid_user_info_is_not_treated_as_an_offline_session() {
        let profile = json!({"id": "saved-subject"});
        let denied = UserInfoError::<io::Error>::Response(
            reqwest::StatusCode::UNAUTHORIZED,
            Vec::new(),
            String::new(),
        );
        assert!(profile_after_user_info(&profile, Err(denied)).is_err());
        let mismatched = CoreUserInfoClaims::from_json::<io::Error>(
            br#"{"sub":"different-subject"}"#,
            Some(&SubjectIdentifier::new("saved-subject".into())),
        );
        assert!(mismatched.is_err());
        assert!(profile_after_user_info(&profile, mismatched).is_err());
        let malformed = CoreUserInfoClaims::from_json::<io::Error>(b"{}", None);
        assert!(profile_after_user_info(&profile, malformed).is_err());
    }

    #[test]
    fn verified_user_info_replaces_the_offline_profile() {
        let info = CoreUserInfoClaims::from_json::<io::Error>(
            br#"{"sub":"saved-subject","name":"Updated name"}"#,
            Some(&SubjectIdentifier::new("saved-subject".into())),
        );
        let result = profile_after_user_info(&json!({"id": "saved-subject"}), info).unwrap();
        assert_eq!(result["offline"], false);
        assert_eq!(result["profile"]["id"], "saved-subject");
        assert_eq!(result["profile"]["name"], "Updated name");
    }
}

#[cfg(test)]
mod status_tests {
    use super::*;
    #[test]
    fn status_exposes_profile_fields_only() {
        assert_eq!(
            public_status(json!({"profile": null})),
            json!({
                "signedIn": false, "displayName": null, "email": null, "offline": false
            })
        );
        let status = public_status(
            json!({"profile": {"id": "subject", "name": "Test", "email": "test@example.invalid"}, "offline": true, "refresh": "private"}),
        );
        assert_eq!(
            status,
            json!({"signedIn": true, "displayName": "Test", "email": "test@example.invalid", "offline": true})
        );
    }
}
