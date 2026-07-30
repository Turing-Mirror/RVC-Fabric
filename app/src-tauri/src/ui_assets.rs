//! Swappable frontend assets (OTA strategy A).
//!
//! The UI is served through the custom `fabric://` scheme instead of Tauri's
//! embedded asset handler, so that a `frontend/` directory sitting next to the
//! executable can replace the shipped UI without rebuilding the exe. That is
//! what makes a `gui_patch`-style UI-only update possible.
//!
//! Resolution order per request:
//!   1. `<exe_dir>/frontend/<path>` on disk — the swappable copy
//!   2. the copy embedded in the binary at build time — first-install fallback
//!
//! Rust-side changes still require replacing the exe (update strategy B).

use std::path::{Path, PathBuf};

use tauri::http::{Request, Response, StatusCode};
use tauri::AppHandle;

/// Scheme the main window is loaded from.
pub const SCHEME: &str = "fabric";

/// Entry document served for `/` and for unknown non-asset paths.
const INDEX: &str = "index.html";

/// Locate the external, swappable frontend directory.
///
/// Release layout is `<install>/frontend/`, next to the exe. The cwd variants
/// keep `cargo run` from src-tauri working against a local `npm run build`.
/// Resolved once — the directory does not move while the app runs, and this is
/// on the path of every single asset request.
static EXTERNAL_DIR: std::sync::OnceLock<Option<PathBuf>> = std::sync::OnceLock::new();

pub fn external_dir() -> Option<PathBuf> {
    EXTERNAL_DIR.get_or_init(resolve_external_dir).clone()
}

fn resolve_external_dir() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(mut exe) = std::env::current_exe() {
        exe.pop();
        candidates.push(exe.join("frontend"));
    }
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("frontend"));
        candidates.push(cwd.join("..").join("frontend"));
    }
    candidates
        .into_iter()
        .find(|p| p.join(INDEX).is_file())
}

/// Very small extension → MIME map. Enough for a Vite build output.
fn mime_for(rel: &str) -> &'static str {
    let ext = Path::new(rel)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match ext.as_str() {
        "html" => "text/html; charset=utf-8",
        "js" | "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "ico" => "image/x-icon",
        "woff2" => "font/woff2",
        "woff" => "font/woff",
        "ttf" => "font/ttf",
        "map" => "application/json; charset=utf-8",
        "wasm" => "application/wasm",
        _ => "application/octet-stream",
    }
}

fn ok(mime: &str, bytes: Vec<u8>) -> Response<Vec<u8>> {
    Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", mime)
        // The swappable copy changes without the URL changing, so never cache.
        .header("Cache-Control", "no-store")
        .body(bytes)
        .unwrap_or_else(|_| not_found())
}

fn not_found() -> Response<Vec<u8>> {
    Response::builder()
        .status(StatusCode::NOT_FOUND)
        .header("Content-Type", "text/plain; charset=utf-8")
        .body(b"not found".to_vec())
        .expect("static 404 response")
}

/// True when `rel` stays inside the frontend dir.
fn safe_rel(rel: &str) -> bool {
    !rel.is_empty()
        && !rel.starts_with('/')
        && !rel.contains("..")
        && !rel.contains('\\')
        && !rel.contains(':')
}

/// Normalize a request path into a relative frontend path.
///
/// Handles: leading slashes, query/hash, Windows `http://fabric.localhost/`
/// rewrites, and accidental host segments.
fn path_to_rel(uri_path: &str) -> String {
    let mut rel = uri_path.trim().to_string();
    if let Some((p, _)) = rel.split_once('?') {
        rel = p.to_string();
    }
    if let Some((p, _)) = rel.split_once('#') {
        rel = p.to_string();
    }
    // percent-decode common cases (%20 etc.) without pulling in a full crate
    rel = rel.replace("%20", " ");
    while rel.starts_with('/') {
        rel = rel[1..].to_string();
    }
    // Some stacks pass "localhost/index.html" or "fabric.localhost/assets/…"
    for prefix in ["localhost/", "fabric.localhost/"] {
        if let Some(rest) = rel.strip_prefix(prefix) {
            rel = rest.to_string();
            break;
        }
    }
    if rel.is_empty() || rel.ends_with('/') {
        rel = INDEX.to_string();
    }
    rel
}

/// Serve one `fabric://` (or `http://fabric.localhost/`) request.
pub fn serve(app: &AppHandle, req: Request<Vec<u8>>) -> Response<Vec<u8>> {
    let rel = path_to_rel(req.uri().path());
    if !safe_rel(&rel) {
        eprintln!("[rvc-fabric] ui 404 unsafe path: {:?}", req.uri());
        return not_found();
    }

    // 1) swappable copy on disk
    if let Some(dir) = external_dir() {
        let path = dir.join(&rel);
        if path.is_file() {
            if let Ok(bytes) = std::fs::read(&path) {
                return ok(mime_for(&rel), bytes);
            }
        }
    }

    // 2) copy embedded at build time (several path shapes Tauri has used)
    for key in [
        format!("/{rel}"),
        format!("/frontend/{rel}"),
        rel.clone(),
    ] {
        if let Some(asset) = app.asset_resolver().get(key) {
            return ok(mime_for(&rel), asset.bytes);
        }
    }

    eprintln!(
        "[rvc-fabric] ui 404 rel={rel:?} uri={:?} external={:?}",
        req.uri(),
        external_dir()
    );
    not_found()
}

/// Where the UI is being served from — surfaced in the 「其他」page so a
/// misapplied UI patch is diagnosable instead of invisible.
pub fn source_label() -> String {
    match external_dir() {
        Some(dir) => format!("外部目录 {}", dir.to_string_lossy()),
        None => "内置（随程序打包）".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_traversal_and_absolute() {
        assert!(!safe_rel(""));
        assert!(!safe_rel("/etc/passwd"));
        assert!(!safe_rel("../../secret"));
        assert!(!safe_rel("assets/..\\win"));
        assert!(!safe_rel("C:windows"));
        assert!(safe_rel("index.html"));
        assert!(safe_rel("assets/index-Bs5dQX0_.js"));
    }

    #[test]
    fn mime_covers_vite_output() {
        assert_eq!(mime_for("index.html"), "text/html; charset=utf-8");
        assert_eq!(mime_for("assets/a.js"), "text/javascript; charset=utf-8");
        assert_eq!(mime_for("assets/a.css"), "text/css; charset=utf-8");
        assert_eq!(mime_for("x.woff2"), "font/woff2");
        assert_eq!(mime_for("noext"), "application/octet-stream");
    }

    #[test]
    fn path_to_rel_strips_query_and_host() {
        assert_eq!(path_to_rel("/"), "index.html");
        assert_eq!(path_to_rel("/index.html"), "index.html");
        assert_eq!(path_to_rel("/assets/a.js"), "assets/a.js");
        assert_eq!(path_to_rel("/assets/a.js?v=1"), "assets/a.js");
        assert_eq!(path_to_rel("/localhost/assets/a.js"), "assets/a.js");
        assert_eq!(path_to_rel("/fabric.localhost/index.html"), "index.html");
    }

    #[test]
    fn finds_the_swappable_dir_when_built() {
        // Repo has app/frontend/ after `npm run build`; tests run from src-tauri.
        if std::path::Path::new("../frontend/index.html").is_file() {
            assert!(external_dir().is_some(), "external frontend should be found");
        }
    }
}
