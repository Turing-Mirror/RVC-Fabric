//! VC++ 运行库的检测与安装。
//!
//! 为什么要管这个：`pythonw.exe` 加载 `vcruntime140.dll`，也就是 torch / numpy
//! 那些扩展模块要它。这个 DLL **不是 Windows 自带的**（UCRT 是，它不是），只随
//! VC++ 运行库安装。缺了它，补全都能跑完，一点变声就炸，报错还是一句英文的
//! 模块加载失败 —— 用户完全不知道是缺运行库。
//!
//! 外壳这边另外做了静态 CRT（`.cargo/config.toml`），那是为了让软件在缺运行库
//! 时**还能打开**，好把下面这套检测和引导显示出来。两件事一起才完整：一个负责
//! 让提示能被看见，一个负责让功能真的能跑。
//!
//! 走的路跟 VB-Cable 完全一样：发布仓下载 → SHA 校验 → 解压 → 用户点了才装。
//! 不偷偷装 —— 装的是系统组件，要提权，不该自作主张。

use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

use crate::download;

/// 微软官方 VC_redist.x64.exe 打成的 zip。
///
/// 2015–2022 是同一个 14.x 系列、向后兼容，一个包覆盖全部，不用按 VS 版本分。
pub const PACK_SHA: &str =
    "8070a3607eef0f8e24de95eef079426456ea7d30bfd25d722c23f77b1c3c6d60";
pub const PACK_NAME: &str = "vcredist-x64.zip";

pub fn pack_dir(root: &Path) -> PathBuf {
    root.join("VCREDIST")
}

/// 解压出来得有安装程序才算准备好。
pub fn pack_ready(root: &Path) -> bool {
    find_setup(&pack_dir(root)).is_some()
}

fn find_setup(dir: &Path) -> Option<PathBuf> {
    let entries = std::fs::read_dir(dir).ok()?;
    for e in entries.flatten() {
        let p = e.path();
        if !p.is_file() {
            continue;
        }
        let name = p.file_name()?.to_string_lossy().to_ascii_lowercase();
        if name.starts_with("vc_redist") && name.ends_with(".exe") {
            return Some(p);
        }
    }
    None
}

/// 安装程序的退出码 → 我们怎么说。
///
/// `1638` 是这里最要紧的一条：它表示「机器上已有更高版本」，是**成功**。装了
/// 新版 Visual Studio 的机器会走这个码，当成失败的话会给一台完全正常的电脑
/// 报错，用户还会照着提示反复重装。
pub fn classify_exit(code: i32) -> Result<&'static str, &'static str> {
    match code {
        0 => Ok("s.vcrDone"),
        1638 => Ok("s.vcrAlready"),
        3010 => Ok("s.vcrDoneReboot"),
        1602 | 1223 => Err("s.vcrCancelled"),
        1618 => Err("s.vcrBusy"),
        _ => Err("s.vcrFailed"),
    }
}

/// 机器上装没装运行库。
///
/// 查注册表是微软文档给的办法，比在 System32 里找文件可靠：文件可能是别的
/// 软件塞进去的一份野版本，注册表项才代表「正经装过」。
///
/// 注册表读不到时兜底查文件 —— 宁可漏报（多问用户一次）也不要误报「已安装」
/// 然后让他继续踩那个英文报错。
#[cfg(target_os = "windows")]
pub fn installed() -> bool {
    use std::process::Command;
    let script = concat!(
        "$k='HKLM:\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x64';",
        "if (Test-Path $k) { $v=(Get-ItemProperty $k).Installed; if ($v -eq 1) { exit 0 } };",
        "exit 1"
    );
    let mut cmd = Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-Command", script]);
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    if let Ok(st) = cmd.status() {
        if st.success() {
            return true;
        }
    }
    dll_present()
}

#[cfg(not(target_os = "windows"))]
pub fn installed() -> bool {
    // 非 Windows 上没有这个概念。当成已装，补全流程整条跳过。
    true
}

fn dll_present() -> bool {
    let Ok(dir) = std::env::var("SystemRoot") else {
        return false;
    };
    Path::new(&dir)
        .join("System32")
        .join("vcruntime140.dll")
        .is_file()
}

/// 下载并解压安装包。装不装是下一步，由用户点。
pub fn ensure_pack(
    root: &Path,
    cancel: Arc<AtomicBool>,
    progress: Option<download::ProgressFn>,
) -> Result<(), String> {
    if pack_ready(root) {
        return Ok(());
    }
    if PACK_SHA.is_empty() {
        return Err(crate::i18n::t("s.vcrPackMissing"));
    }
    crate::engine_assets::fetch_pack(PACK_NAME, PACK_SHA, &pack_dir(root), root, cancel, progress)?;
    if pack_ready(root) {
        Ok(())
    } else {
        Err(crate::i18n::t("s.vcrPackBroken"))
    }
}

/// 静默安装。`/install /quiet /norestart` 是微软官方参数。
///
/// 提权躲不掉：装的是系统组件，UAC 那一下必须用户自己点。跟 VB-Cable 一样，
/// 用户点「否」时 Start-Process 抛异常而不是给退出码，这里归一成 1223。
#[cfg(target_os = "windows")]
pub fn install(root: &Path) -> Result<String, String> {
    use std::process::Command;

    let dir = pack_dir(root);
    let setup = find_setup(&dir).ok_or_else(|| crate::i18n::t("s.vcrNoSetup"))?;
    let script = format!(
        "try {{ $p = Start-Process -FilePath '{}' -ArgumentList '/install','/quiet','/norestart' \
         -Verb RunAs -Wait -PassThru; exit $p.ExitCode }} catch {{ exit 1223 }}",
        setup.to_string_lossy().replace('\'', "''")
    );
    let mut cmd = Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-Command", &script]);
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let st = cmd
        .status()
        .map_err(|e| crate::i18n::te("s.vcrFailed", &e))?;
    let code = st.code().unwrap_or(-1);
    match classify_exit(code) {
        Ok(key) => Ok(crate::i18n::t(key)),
        Err(key) => Err(crate::i18n::te(key, &code)),
    }
}

#[cfg(not(target_os = "windows"))]
pub fn install(_root: &Path) -> Result<String, String> {
    Err(crate::i18n::t("s.vcrWindowsOnly"))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 1638 = 「已有更高版本」。判成失败的话，装了新版 VS 的机器会被告知
    /// 运行库安装失败 —— 一台完全正常的电脑，用户还会照着提示反复重装。
    #[test]
    fn a_newer_runtime_already_present_counts_as_success() {
        assert!(classify_exit(1638).is_ok());
        assert!(classify_exit(0).is_ok());
        assert!(classify_exit(3010).is_ok(), "装好了只是要重启，不是失败");
    }

    /// 用户拒绝 UAC 跟「装失败」必须分开：前者该说「已取消，可稍后重试」，
    /// 后者才该报错。混在一起用户会以为自己的电脑有问题。
    #[test]
    fn a_declined_uac_is_reported_as_cancelled_not_broken() {
        assert_eq!(classify_exit(1223), Err("s.vcrCancelled"));
        assert_eq!(classify_exit(1602), Err("s.vcrCancelled"));
        assert_eq!(classify_exit(-1), Err("s.vcrFailed"));
    }

    #[test]
    fn setup_is_found_by_name_not_by_position() {
        let dir = std::env::temp_dir().join("rvcf-vcr-find");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        // 包里除了安装程序还可能有说明文件，不能随便挑一个 exe。
        std::fs::write(dir.join("readme.txt"), b"x").unwrap();
        assert!(find_setup(&dir).is_none());
        std::fs::write(dir.join("VC_redist.x64.exe"), b"x").unwrap();
        assert!(find_setup(&dir).is_some());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
