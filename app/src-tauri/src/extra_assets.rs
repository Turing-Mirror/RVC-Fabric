//! 按需下载的附加资源：分离模型、训练底模。
//!
//! 和 `engine_assets.rs` 的区别是**规格不写死在客户端里**。engine-core 和
//! VB-Cable 各只有一个版本，sha256 硬编码在二进制里没问题；但分离模型和训练
//! 底模是会加的 —— 每加一个模型就发一版客户端，谁都受不了。
//!
//! 所以规格从线上清单的 `extras` 段读：
//!
//! ```json
//! "extras": {
//!   "pymss_vocals": {
//!     "label": "人声分离模型",
//!     "dest": "assets/pymss",
//!     "files": [{"name": "...ckpt", "sha256": "...", "size_bytes": 1,
//!                "channel": "release", "release_tag": "pymss"}]
//!   }
//! }
//! ```
//!
//! `dest` 是相对安装根目录的路径，**只允许相对路径**：清单是从网上拉的，
//! 让它决定一个绝对路径等于把任意写文件的权限交出去。

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::{catalog, download};

const CNB_REPO: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases";

static BUSY: Mutex<bool> = Mutex::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExtraFile {
    pub name: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub urls: Vec<String>,
}

impl ExtraFile {
    /// Release 附件按平铺文件名寻址（上传时就是按 base name 传的），
    /// 清单里的 `name` 可以是嵌套相对路径（只决定本地摆哪），拼 URL 只用末段。
    pub fn base_name(&self) -> &str {
        self.name.rsplit('/').next().unwrap_or(&self.name)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExtraSpec {
    pub key: String,
    pub label: String,
    pub dest: String,
    /// 客户端分组：`train` 训练音色 / `separate` 人声分离 / `other`。
    pub group: String,
    /// 对应功能的推荐项（列表里排前、标「推荐」）。
    pub recommended: bool,
    /// 组内排序，越小越靠前。
    pub order: i32,
    /// 给用户看的用途说明，不是路径。
    pub notes: String,
    pub files: Vec<ExtraFile>,
}

impl ExtraSpec {
    pub fn total_bytes(&self) -> u64 {
        self.files.iter().map(|f| f.size_bytes).sum()
    }
}

/// 老清单没写 group 时按 key 兜底，避免下载列表又堆成一坨无意义名字。
fn infer_group(key: &str, raw: &str) -> String {
    let g = raw.trim().to_ascii_lowercase();
    if g == "train" || g == "separate" || g == "other" {
        return g;
    }
    if key.starts_with("pretrained") {
        "train".into()
    } else if key.starts_with("pymss") || key.starts_with("uvr") {
        "separate".into()
    } else {
        "other".into()
    }
}

fn group_rank(g: &str) -> u8 {
    match g {
        "train" => 0,
        "separate" => 1,
        _ => 2,
    }
}

/// 清单里的 `dest` 只能是安装目录下的相对路径。
///
/// 这是从网上拉来的字符串。放行 `C:\Windows\System32` 或 `../..` 就等于把
/// 任意写文件的能力交给了任何能改到那份清单的人。
fn safe_dest(root: &Path, dest: &str) -> Option<PathBuf> {
    let d = dest.trim().replace('\\', "/");
    if d.is_empty() {
        return None;
    }
    let p = Path::new(&d);
    if p.is_absolute() || d.starts_with("//") || d.contains(':') {
        return None;
    }
    let mut out = root.to_path_buf();
    for part in p.components() {
        match part {
            std::path::Component::Normal(s) => out.push(s),
            // `.` 无害但没意义；`..` 是要拦的那个。一律拒绝，规则简单好审。
            _ => return None,
        }
    }
    Some(out)
}

/// 清单里的文件名同样是拼进路径的字符串，但允许嵌套相对路径：PyMSS 的模型
/// 要按 `vocal/vocal_extraction/xxx.ckpt` 这种目录摆放才能被引擎解析到。
/// 规则与 `safe_dest` 同源：只放行普通目录段，`.` 与 `..` 一律拒绝。
fn safe_name(name: &str) -> Option<String> {
    let n = name.trim().replace('\\', "/");
    if n.is_empty() || n.contains(':') || n.starts_with('/') {
        return None;
    }
    let mut out: Vec<&str> = Vec::new();
    for part in n.split('/') {
        match part {
            // 空段 = `a//b` 或结尾斜杠，无意义且可能让路径解析出歧义，拒绝。
            "" | "." | ".." => return None,
            s => out.push(s),
        }
    }
    Some(out.join("/"))
}

fn normalize_sha(s: &str) -> String {
    s.chars()
        .filter(|c| c.is_ascii_hexdigit())
        .collect::<String>()
        .to_ascii_lowercase()
}

fn release_url(tag: &str, name: &str) -> String {
    format!("{CNB_REPO}/-/releases/download/{tag}/{name}")
}

fn lfs_url(sha: &str) -> String {
    format!("{CNB_REPO}/-/lfs/{sha}")
}

/// 把清单里的一条 `extras` 解析成规格。任何一个文件不合法就整条丢掉 ——
/// 下一半的模型不如没有。
pub fn parse_spec(key: &str, blob: &Value) -> Option<ExtraSpec> {
    let dest = blob.get("dest").and_then(|v| v.as_str()).unwrap_or("").to_string();
    if dest.trim().is_empty() {
        return None;
    }
    let label = blob
        .get("label")
        .and_then(|v| v.as_str())
        .unwrap_or(key)
        .to_string();
    let notes = blob
        .get("notes")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let group = infer_group(
        key,
        blob.get("group").and_then(|v| v.as_str()).unwrap_or(""),
    );
    let recommended = blob
        .get("recommended")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let order = blob
        .get("order")
        .and_then(|v| v.as_i64())
        .unwrap_or(100) as i32;
    let default_tag = blob
        .get("release_tag")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let arr = blob.get("files")?.as_array()?;
    let mut files = Vec::new();
    for f in arr {
        let name = safe_name(f.get("name").or_else(|| f.get("file"))?.as_str()?)?;
        let sha = normalize_sha(f.get("sha256").and_then(|v| v.as_str()).unwrap_or(""));
        if sha.len() != 64 {
            return None; // 没有可校验的哈希就不下：几百 MB 下错了没人看得出来
        }
        let size = f.get("size_bytes").and_then(|v| v.as_u64()).unwrap_or(0);
        let channel = f
            .get("channel")
            .and_then(|v| v.as_str())
            .unwrap_or("release")
            .to_ascii_lowercase();
        let tag = f
            .get("release_tag")
            .and_then(|v| v.as_str())
            .unwrap_or(&default_tag)
            .to_string();

        let mut urls: Vec<String> = f
            .get("urls")
            .and_then(|v| v.as_array())
            .map(|a| {
                a.iter()
                    .filter_map(|u| u.as_str())
                    .map(str::trim)
                    .filter(|u| u.starts_with("https://"))
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        if urls.is_empty() {
            let base = name.rsplit('/').next().unwrap_or(&name);
            urls.push(if channel == "lfs" {
                lfs_url(&sha)
            } else if tag.trim().is_empty() {
                return None;
            } else {
                release_url(&tag, base)
            });
        }
        files.push(ExtraFile {
            name,
            sha256: sha,
            size_bytes: size,
            urls,
        });
    }
    if files.is_empty() {
        return None;
    }
    Some(ExtraSpec {
        key: key.to_string(),
        label,
        dest,
        group,
        recommended,
        order,
        notes,
        files,
    })
}

fn extras_from(data: &Value) -> Vec<ExtraSpec> {
    let Some(map) = data.get("extras").and_then(|v| v.as_object()) else {
        return Vec::new();
    };
    let mut out: Vec<ExtraSpec> = map
        .iter()
        .filter_map(|(k, v)| parse_spec(k, v))
        .collect();
    // 训练 → 分离 → 其它；组内推荐优先，再按 order / key。
    out.sort_by(|a, b| {
        group_rank(&a.group)
            .cmp(&group_rank(&b.group))
            .then_with(|| b.recommended.cmp(&a.recommended))
            .then_with(|| a.order.cmp(&b.order))
            .then_with(|| a.key.cmp(&b.key))
    });
    out
}

/// 读安装目录里的内置清单 `configs/online_catalog.json`（离线兜底）。
fn local_catalog(root: &Path) -> Value {
    let p = root.join("configs").join("online_catalog.json");
    match std::fs::read_to_string(&p) {
        Ok(s) => serde_json::from_str(&s).unwrap_or_else(|_| json!({})),
        Err(_) => json!({}),
    }
}

fn extras_nonempty(data: &Value) -> bool {
    data.get("extras")
        .and_then(|v| v.as_object())
        .map(|m| !m.is_empty())
        .unwrap_or(false)
}

/// 优先线上，拿不到或 extras 为空时用内置清单顶上。
///
/// 下载 URL 仍指向 CNB，所以「能列清单」≠「能下下来」；但至少用户能看清
/// 训练 / 分离分别该下什么，而不是对着空列表发呆。
fn catalog_for_extras(root: &Path, prefer_remote: bool) -> (Value, bool) {
    if prefer_remote {
        match catalog::fetch_remote_catalog_cached(12) {
            Ok(remote) if extras_nonempty(&remote) => return (remote, true),
            Ok(_remote) => {
                // 线上通了但还没登记 extras（老 index）→ 用内置补。
                let local = local_catalog(root);
                if extras_nonempty(&local) {
                    return (local, true);
                }
                return (local, true);
            }
            Err(_) => return (local_catalog(root), false),
        }
    }
    (local_catalog(root), false)
}

/// 线上清单里的全部附加资源。
///
/// `available` 说的是**清单拿到没有**，不是**清单里有没有东西**。以前这两件
/// 事被合成一个判断（`!specs.is_empty()`），结果清单明明拉下来了、只是里面
/// 一个模型都没登记，界面却报「暂时无法获取下载清单，检查网络后再试」——
/// 让用户去查一个根本没坏的网络。
pub fn list(root: &Path) -> Value {
    let (data, reachable) = catalog_for_extras(root, true);
    let specs = extras_from(&data);
    let items: Vec<Value> = specs
        .iter()
        .map(|s| {
            let dir = safe_dest(root, &s.dest);
            let installed = dir
                .as_ref()
                .map(|d| s.files.iter().all(|f| file_ok(&d.join(&f.name), f)))
                .unwrap_or(false);
            json!({
                "key": s.key,
                "label": s.label,
                "dest": s.dest,
                "group": s.group,
                "recommended": s.recommended,
                "order": s.order,
                "notes": s.notes,
                "size_bytes": s.total_bytes(),
                "files": s.files.iter().map(|f| f.base_name().to_string()).collect::<Vec<_>>(),
                "installed": installed,
            })
        })
        .collect();
    json!({
        "available": reachable,
        "items": items,
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
}

/// 已经在本地且大小对得上。**不在这里重算 sha256** —— 六百 MB 的文件每次开
/// 界面都哈希一遍，用户会以为软件卡死了。哈希在下载完那一刻校验过。
fn file_ok(p: &Path, f: &ExtraFile) -> bool {
    match std::fs::metadata(p) {
        Ok(m) if m.is_file() => {
            if f.size_bytes > 0 {
                m.len() == f.size_bytes
            } else {
                m.len() > 0
            }
        }
        _ => false,
    }
}

/// 下载一条附加资源。阻塞，调用方负责挪到后台线程。
pub fn download(app: &AppHandle, root: &Path, key: &str) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.42b898eb36").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    let r = download_inner(app, root, key);
    *BUSY.lock().unwrap_or_else(|e| e.into_inner()) = false;
    if let Err(ref e) = r {
        let _ = app.emit(
            "extra-progress",
            json!({ "key": key, "phase": "error", "message": e }),
        );
    }
    r
}

fn download_inner(app: &AppHandle, root: &Path, key: &str) -> Result<Value, String> {
    // 下载也允许内置清单：规格里已经带了 sha256 和 CNB URL，不依赖 index 在线。
    let (data, _) = catalog_for_extras(root, true);
    // 用户主动点下载时再硬拉一次线上，避免内置过旧；失败就用刚才那份。
    let data = catalog::fetch_remote_catalog(20).unwrap_or(data);
    let spec = extras_from(&data)
        .into_iter()
        .find(|s| s.key == key)
        .ok_or_else(|| crate::i18n::te("s.ae3f0d2168", &(key)))?;
    let dir = safe_dest(root, &spec.dest)
        .ok_or_else(|| crate::i18n::te("s.341bc35cbf", &(spec.dest)))?;
    std::fs::create_dir_all(&dir).map_err(|e| crate::i18n::te("s.ec982d9c98", &(e)))?;

    let total: u64 = spec.total_bytes();
    let mut before: u64 = 0;
    for f in &spec.files {
        let dest = dir.join(&f.name);
        if file_ok(&dest, f) {
            before += f.size_bytes;
            continue;
        }
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent).map_err(|e| crate::i18n::te("s.ec982d9c98", &(e)))?;
        }
        let app2 = app.clone();
        let key2 = key.to_string();
        let label = f.name.clone();
        let base = before;
        let cb: download::ProgressFn = Arc::new(move |got, _len, stage| {
            let message = download::parse_retry_attempt(stage)
                .map(|n| crate::i18n::te("s.dlReconnect", &n))
                .unwrap_or_else(|| crate::i18n::te("s.407187444b", &(label)));
            let _ = app2.emit(
                "extra-progress",
                json!({
                    "key": key2,
                    "phase": "run",
                    "done": base + got,
                    "total": total.max(1),
                    "message": message,
                }),
            );
        });
        // 先落到临时名，校验通过再改名：中断留下的半截文件如果就叫最终名，
        // 下次开界面会被 file_ok 当成已装好（大小刚好撞上就更糟）。
        let tmp = dir.join(format!("{}.part", f.name));
        download::download_file(&f.urls, &tmp, &f.sha256, cancel_flag(), Some(cb))
            .map_err(|e| crate::i18n::t2("s.0df1f31a67", &f.name, &e))?;
        if dest.exists() {
            let _ = std::fs::remove_file(&dest);
        }
        std::fs::rename(&tmp, &dest).map_err(|e| crate::i18n::t2("s.538ff61331", &f.name, &e))?;
        before += f.size_bytes;
    }

    let _ = app.emit(
        "extra-progress",
        json!({ "key": key, "phase": "done", "done": total.max(1),
                "total": total.max(1), "message": &crate::i18n::t("s.4bbcf94739") }),
    );
    Ok(json!({ "ok": true, "dest": dir.to_string_lossy() }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_hostile_dest_cannot_escape_the_install() {
        // 清单是从网上拉的。放行绝对路径或 .. 等于把任意写文件的权限交出去。
        let root = Path::new("C:\\App");
        for bad in [
            "",
            "   ",
            "/etc/cron.d",
            "C:\\Windows\\System32",
            "../../Windows",
            "assets/../../evil",
            "\\\\server\\share",
        ] {
            assert!(safe_dest(root, bad).is_none(), "should reject {bad:?}");
        }
        assert_eq!(
            safe_dest(root, "assets/pymss"),
            Some(Path::new("C:\\App").join("assets").join("pymss"))
        );
        // 反斜杠写法也要能认，清单里两种都可能出现。
        assert_eq!(
            safe_dest(root, "assets\\pretrained_v2"),
            Some(Path::new("C:\\App").join("assets").join("pretrained_v2"))
        );
    }

    #[test]
    fn a_hostile_filename_cannot_escape_either() {
        for bad in ["", " ", "..", ".", "C:evil", "a/../b", "/abs", "a//b", "a/"] {
            assert!(safe_name(bad).is_none(), "should reject {bad:?}");
        }
        assert_eq!(safe_name(" model.ckpt "), Some("model.ckpt".into()));
    }

    #[test]
    fn nested_relative_paths_are_allowed() {
        // PyMSS 的模型必须按 catalog relpath 的子目录摆放，引擎才解析得到。
        assert_eq!(
            safe_name("vocal/vocal_extraction/x.ckpt"),
            Some("vocal/vocal_extraction/x.ckpt".into())
        );
        // 反斜杠写法归一成 /，与 dest 同规则。
        assert_eq!(
            safe_name("legacy_vr\\vr_hp2\\7_HP2-UVR.pth"),
            Some("legacy_vr/vr_hp2/7_HP2-UVR.pth".into())
        );
        let root = Path::new("C:\\App");
        let d = safe_dest(root, "assets/pymss").unwrap();
        assert_eq!(
            d.join("vocal/vocal_extraction/x.ckpt"),
            root.join("assets/pymss/vocal/vocal_extraction/x.ckpt")
        );
    }

    fn sha(c: char) -> String {
        std::iter::repeat(c).take(64).collect()
    }

    #[test]
    fn a_file_without_a_usable_hash_is_dropped_whole() {
        // 六百 MB 下错了没人看得出来，所以宁可不给下也不给一条没法校验的。
        let blob = json!({
            "dest": "assets/pymss",
            "files": [
                {"name": "a.ckpt", "sha256": sha('a'), "release_tag": "pymss"},
                {"name": "b.yaml", "release_tag": "pymss"}
            ]
        });
        assert!(parse_spec("pymss", &blob).is_none());
    }

    #[test]
    fn urls_default_to_the_release_attachment() {
        let blob = json!({
            "label": &crate::i18n::t("s.f6bccbff47"),
            "dest": "assets/pymss",
            "release_tag": "pymss",
            "files": [{"name": "a.ckpt", "sha256": sha('a'), "size_bytes": 10}]
        });
        let s = parse_spec("pymss", &blob).expect("spec");
        assert_eq!(s.total_bytes(), 10);
        assert_eq!(
            s.files[0].urls,
            vec![format!("{CNB_REPO}/-/releases/download/pymss/a.ckpt")]
        );
    }

    #[test]
    fn nested_names_use_the_flat_base_name_in_urls() {
        // 附件在 CNB 上是平铺的（上传时就是按 base name 传的），目录只决定本地摆哪。
        let blob = json!({
            "dest": "assets/pymss",
            "release_tag": "pymss",
            "files": [{"name": "legacy_vr/vr_hp2/7_HP2-UVR.pth", "sha256": sha('a')}]
        });
        let s = parse_spec("pymss", &blob).expect("spec");
        assert_eq!(s.files[0].base_name(), "7_HP2-UVR.pth");
        assert_eq!(
            s.files[0].urls,
            vec![format!("{CNB_REPO}/-/releases/download/pymss/7_HP2-UVR.pth")]
        );
    }

    #[test]
    fn lfs_channel_addresses_by_hash() {
        let blob = json!({
            "dest": "assets/pymss",
            "files": [{"name": "a.ckpt", "sha256": sha('b'), "channel": "lfs"}]
        });
        let s = parse_spec("pymss", &blob).expect("spec");
        assert!(s.files[0].urls[0].contains("/-/lfs/"));
    }

    #[test]
    fn release_channel_without_a_tag_is_rejected() {
        // 没 tag 拼不出地址；退一个默认值只会让用户下到别的东西。
        let blob = json!({
            "dest": "assets/pymss",
            "files": [{"name": "a.ckpt", "sha256": sha('c')}]
        });
        assert!(parse_spec("pymss", &blob).is_none());
    }

    #[test]
    fn non_https_urls_are_ignored() {
        let blob = json!({
            "dest": "assets/pymss",
            "release_tag": "pymss",
            "files": [{"name": "a.ckpt", "sha256": sha('d'),
                       "urls": ["http://evil.example/a.ckpt"]}]
        });
        let s = parse_spec("pymss", &blob).expect("spec");
        assert_eq!(s.files[0].urls.len(), 1);
        assert!(s.files[0].urls[0].starts_with("https://cnb.cool/"));
    }

    #[test]
    fn a_catalog_without_extras_yields_nothing() {
        assert!(extras_from(&json!({})).is_empty());
        assert!(extras_from(&json!({"extras": []})).is_empty());
    }

    #[test]
    fn size_mismatch_means_not_installed() {
        // 半截下载的文件存在但没用；只判存在会让分离在加载模型时才炸。
        let base = std::env::temp_dir().join("rvcf-extra-fileok");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(&base).unwrap();
        let p = base.join("a.ckpt");
        std::fs::write(&p, b"1234").unwrap();
        let f = ExtraFile {
            name: "a.ckpt".into(),
            sha256: sha('a'),
            size_bytes: 999,
            urls: vec![],
        };
        assert!(!file_ok(&p, &f));
        let f2 = ExtraFile { size_bytes: 4, ..f };
        assert!(file_ok(&p, &f2));
        let _ = std::fs::remove_dir_all(&base);
    }
}
