# -*- coding: utf-8 -*-
"""
One-click release packer for RVC Fabric.

Builds a RVCMAX-style tree::

    dist/TuringMirror_Voice/   # pack folder name (legacy script id)
      启动器.exe          first-run helper (exe)
      变声器.exe          daily app (UI title: RVC Fabric)
      Runtime/            embedded Python (required)
      User_Data/models/   bundled voice models
      VBCABLE/            VB-Cable installers
      assets/ … infer/    engine (from this repo)
      使用说明.txt

Usage (from repo root)::

    python scripts/build_release.py
    python scripts/build_release.py --runtime "D:\\path\\Runtime" --models "D:\\models"
    python scripts/build_release.py --skip-exe          # layout only
    python scripts/build_release.py --skip-runtime      # dev dry-run without copy

Default Runtime/models/VBCABLE sources try the local RVCMAX reference pack if present.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "dist" / "TuringMirror_Voice"
REF = REPO / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan"
RVCMAX_ROOT = REPO / "RVCMAX"

# Official-style multi-pack: each variant = full tree + its own Runtime
# prefer_dir = local RVCMAX folder name (exact). name_keys = fallback scan.
# exclude_keys = directory names that must NOT match (nvidia vs nvidia50).
VARIANTS: dict[str, dict] = {
    "nvidia": {
        "out_name": "TuringMirror_Voice_Nvidia",
        "accel_default": "cuda",
        "label": "NVIDIA CUDA",
        "name_keys": ("nvidia", "n卡", "cuda"),
        "prefer_dir": "RVCMAX_Nvidia_xiaoyuan",
        "exclude_keys": ("50", "5xxx", "50x0", "blackwell"),
    },
    "amd": {
        "out_name": "TuringMirror_Voice_AMD",
        "accel_default": "dml",
        "label": "AMD/Intel DirectML",
        "name_keys": ("amd", "dml", "a卡", "intel", "directml"),
        "prefer_dir": "RVCMAX_AMD_xiaoyuan",
        "exclude_keys": (),
    },
    "nvidia50": {
        "out_name": "TuringMirror_Voice_Nvidia50",
        "accel_default": "cuda",
        "label": "NVIDIA 50-series CUDA",
        "name_keys": ("50", "5xxx", "rtx50", "50x0", "blackwell"),
        "prefer_dir": "RVCMAX_Nvidia50x0_xiaoyuan",
        "exclude_keys": (),
    },
}

# Substrings that mark a 50-series pack (shared helper for tests)
SERIES50_KEYS = ("50", "5xxx", "50x0", "rtx50", "blackwell")

# Engine files/dirs to ship (lean but runnable).
# docs/ is NOT shipped whole (dev paths / session notes); legal only via strip step.
# launcher/ 已退役（Tk 壳删除）；引擎只依赖 tools/ + gui_v1 + infer。
ENGINE_DIRS = (
    "assets",
    "configs",
    "i18n",
    "infer",
    "tools",
)
ENGINE_FILES = (
    "infer-web.py",
    "gui_v1.py",
    "LICENSE",
    "README.md",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def copy_tree(src: Path, dst: Path, *, ignore=None) -> None:
    if not src.is_dir():
        raise FileNotFoundError(f"missing source dir: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    log(f"  copy dir: {src} -> {dst}")
    shutil.copytree(
        src,
        dst,
        ignore=ignore,
        dirs_exist_ok=False,
    )


def robocopy(src: Path, dst: Path) -> None:
    """Fast Windows copy for large Runtime trees."""
    dst.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        # /MIR mirror; /NFL /NDL quieter; /R:2 retries
        cmd = [
            "robocopy",
            str(src),
            str(dst),
            "/E",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
            "/nc",
            "/ns",
            "/np",
            "/R:2",
            "/W:2",
        ]
        log(f"  robocopy: {src} -> {dst}")
        rc = subprocess.call(cmd)
        # robocopy 0-7 = success-ish
        if rc >= 8:
            raise RuntimeError(f"robocopy failed code {rc}")
    else:
        copy_tree(src, dst)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a command; on Windows resolve npm/npx to *.cmd (CreateProcess cannot run bare npm)."""
    args = list(cmd)
    if sys.platform == "win32" and args:
        head = args[0]
        if head in ("npm", "npx", "cargo", "tauri"):
            which = shutil.which(head) or shutil.which(f"{head}.cmd")
            if which:
                args[0] = which
            elif head == "npm":
                # Common install layout when PATH only has the extensionless shim
                for cand in (
                    Path(r"K:\nodejs\npm.cmd"),
                    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                    / "nodejs"
                    / "npm.cmd",
                    Path(os.environ.get("APPDATA", "")) / "npm" / "npm.cmd",
                ):
                    if cand.is_file():
                        args[0] = str(cand)
                        break
    log("  $ " + " ".join(args))
    subprocess.check_call(args, cwd=str(cwd or REPO))


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "-U", "pyinstaller"])


def ensure_shell_download_deps() -> None:
    """打包机安装壳层联网/封面依赖，打进 启动器.exe / 变声器.exe。

    用户机无需系统 Python。缺 requests → 补全 Runtime 失败；缺 Pillow → 社区封面空白。
    """
    need: list[str] = []
    try:
        import requests  # noqa: F401
        import certifi  # noqa: F401
    except ImportError:
        need.extend(["requests", "certifi"])
    try:
        import PIL  # noqa: F401
    except ImportError:
        need.append("Pillow")
    try:
        import pystray  # noqa: F401
    except ImportError:
        # 系统托盘常驻（缺失时软件仍可用，但托盘/最小化到托盘不可用）
        need.append("pystray")
    if need:
        log(f"[deps] pip install {' '.join(need)} (for frozen shell exes)")
        run([sys.executable, "-m", "pip", "install", "-U", *need])
    else:
        log("[deps] requests/certifi/Pillow/pystray ok (will bundle into shell exes)")


def ensure_shell_ui_deps() -> None:
    """壳层 GUI 依赖 Tcl/Tk。精简/嵌入式 Python（如部分 IDE agent 自带解释器）常无 tkinter。

    若用无 tkinter 的解释器打 onefile，PyInstaller 只会在 warn 里写
    ``missing module named tkinter`` 却仍产出 exe；用户机一点启动器/主界面就：
    ``ModuleNotFoundError: No module named 'tkinter'``。
    """
    exe = Path(sys.executable).resolve()
    log(f"[deps] shell build interpreter: {exe} ({sys.version.split()[0]})")
    bad_markers = (
        "ModularData\\ai-agent\\vm\\tools\\python",
        "ModularData/ai-agent/vm/tools/python",
        "TRAE SOLO",
    )
    exe_s = str(exe)
    for m in bad_markers:
        if m.lower() in exe_s.lower():
            raise RuntimeError(
                "当前 Python 是 IDE/agent 内嵌精简解释器，通常不含 tkinter，"
                "不能用来打包 启动器.exe / 变声器.exe。\n"
                f"  当前: {exe}\n"
                "  请改用完整安装的 CPython（安装时勾选 tcl/tk），例如:\n"
                "  py -3.13 scripts\\build_setup.py\n"
                "  或: C:\\Users\\...\\Python313\\python.exe scripts\\build_setup.py"
            )
    try:
        import tkinter  # noqa: F401
        import _tkinter  # noqa: F401
        from tkinter import messagebox, filedialog, ttk  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "打包机 Python 缺少 tkinter / _tkinter（Tcl/Tk）。\n"
            f"  interpreter: {exe}\n"
            f"  error: {e}\n"
            "  官方 Windows 安装包请勾选 tcl/tk；不要用 embeddable 或 IDE 自带精简 Python 打包。"
        ) from e
    # Touch Tk once so broken installs fail here, not on the user's PC.
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
    except Exception as e:
        raise RuntimeError(
            f"tkinter 可 import 但无法创建 Tk 窗口（Tcl/Tk 数据缺失）: {e}\n"
            f"  interpreter: {exe}"
        ) from e
    log(f"[deps] tkinter OK (Tk {tkinter.TkVersion})")


def shell_hidden_imports() -> list[str]:
    """启动器 / 变声器 onefile 必须打进的模块（下载栈 + GUI + 封面）。"""
    return [
        "requests",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
        "launcher.online.downloader",
        "launcher.online.multipart",
        "launcher.online.safe_zip",
        "launcher.provision_progress",
        "launcher.runtime_provision",
        "launcher.engine_core",
        "launcher.cnb_sources",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "PIL.ImageDraw",
        "pystray",  # 托盘常驻（tray.py 运行时探测，缺了不崩但托盘失效）
        # GUI：必须显式列出；精简 stdlib 缺模块时由 ensure_shell_ui_deps 硬失败
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
        "tkinter.simpledialog",
        "tkinter.scrolledtext",
        "tkinter.font",
        "tkinter.commondialog",
        "tkinter.constants",
        "tkinter.colorchooser",
        "_tkinter",
        # 诊断包 env.json 读注册表取 CPU 名；collect_diagnostics.py 是磁盘加载,
        # PyInstaller 静态分析看不到它,显式点名以免精简 stdlib 缺失时静默降级
        "winreg",
    ]


def _app_version_text() -> str:
    """launcher/version.py 里的 APP_VERSION（文本解析，不 import 避免副作用）。"""
    import re

    text = (REPO / "launcher" / "version.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION[^"\']*["\']([^"\']+)["\']', text)
    return m.group(1) if m else "0.0.0"


def write_shell_version_file(out_dir: Path, exe_name: str) -> Path:
    """生成 PyInstaller --version-file 版本资源。

    无签名 + 无版本资源是杀软启发引擎（360 QVM 等）的典型恶意样本画像；
    补齐 CompanyName/ProductName/FileDescription 可显著降低误报分。
    """
    import re

    ver = _app_version_text()
    nums = [int(x) for x in re.findall(r"\d+", ver)][:4]
    while len(nums) < 4:
        nums.append(0)
    filevers = tuple(nums)
    desc = {
        "TM_Setup": "RVC Fabric 启动器（环境补全与首次配置）",
        "TM_Voice": "RVC Fabric 实时变声主界面",
    }.get(exe_name, "RVC Fabric")
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers!r},
    prodvers={filevers!r},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable('080404b0', [
        StringStruct('CompanyName', 'Turing-Mirror'),
        StringStruct('FileDescription', {desc!r}),
        StringStruct('FileVersion', {ver!r}),
        StringStruct('InternalName', {exe_name!r}),
        StringStruct('LegalCopyright', 'Copyright (C) Turing-Mirror. MIT Licensed.'),
        StringStruct('OriginalFilename', {(exe_name + '.exe')!r}),
        StringStruct('ProductName', 'RVC Fabric'),
        StringStruct('ProductVersion', {ver!r}),
      ]),
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])]),
  ],
)
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"version_{exe_name}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def shell_pyinstaller_args(
    *,
    name: str,
    script: Path,
    distpath: Path,
    workpath: Path,
    specpath: Path,
) -> list[str]:
    """Shared PyInstaller CLI for 启动器 / 变声器 shells."""
    args: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--noupx",  # UPX 压 pythonXY.dll 易导致 LoadLibrary / 文件占用失败
        "--name",
        name,
        "--distpath",
        str(distpath),
        "--workpath",
        str(workpath),
        "--specpath",
        str(specpath),
        "--paths",
        str(REPO),
    ]
    # Product icon (taskbar / title bar / shortcut default)
    ico = REPO / "assets" / "brand" / "app.ico"
    if ico.is_file():
        args.extend(["--icon", str(ico)])
    for mod in shell_hidden_imports():
        args.extend(["--hidden-import", mod])
    # 入口是 stub（runpy 动态启动 launcher.*），静态分析不到 launcher 依赖树，
    # 必须整包收集作为 frozen 兜底；磁盘 launcher/ 存在时优先磁盘（_disk_first）
    args.extend(["--collect-submodules", "launcher"])
    # 版本资源：降低无签名 exe 的杀软启发误报（360 QVM 曾误报 HEUR/QVM05.1）
    args.extend(["--version-file", str(write_shell_version_file(specpath, name))])
    args.extend(["--collect-all", "certifi", str(script)])
    return args


def assert_pyinstaller_collected_tkinter(work_name_dir: Path, exe_name: str) -> None:
    """Fail the build if Analysis still reports tkinter missing (do not ship broken shells)."""
    warn = work_name_dir / f"warn-{exe_name}.txt"
    if not warn.is_file():
        # Older layout: warn-TM_Setup.txt next to Analysis
        cands = list(work_name_dir.rglob("warn-*.txt"))
        warn = cands[0] if cands else warn
    if warn.is_file():
        text = warn.read_text(encoding="utf-8", errors="replace")
        if (
            "missing module named tkinter" in text
            or "missing module named _tkinter" in text
        ):
            raise RuntimeError(
                f"PyInstaller 未打进 tkinter（见 {warn}）。\n"
                "不要用无 Tcl/Tk 的精简 Python 打包。请换完整 CPython 后重打。"
            )
    # Binary smoke: onefile 里应能搜到 tkinter / _tkinter 字样（压缩后仍常保留）
    # 真正保证靠上面的 warn + 打包前 ensure_shell_ui_deps。


APP_DIR = REPO / "app"
TAURI_EXE_NAME = "RVC Fabric.exe"


def build_tauri_shell(out: Path) -> None:
    """Build the Tauri shell into ``out``.

    Replaces the old PyInstaller pair. The launcher is now the app's own
    first-run gate, so there is exactly one executable.

    ``frontend/`` is copied **next to the exe** on purpose: that directory is
    what a UI-only update replaces (OTA strategy A). Leaving it only embedded
    in the binary would make界面热更失效.

    Shared by build_release.py (full offline pack) and build_setup.py (thin
    universal Setup) so the two can never drift apart again.
    """
    if not APP_DIR.is_dir():
        raise FileNotFoundError(f"missing Tauri app dir: {APP_DIR}")

    log("[app] npm install")
    run(["npm", "install", "--no-audit", "--no-fund"], cwd=APP_DIR)
    log("[app] npm run build (vite -> app/frontend)")
    run(["npm", "run", "build"], cwd=APP_DIR)
    # Signed updater artifacts (strategy B) need a private key. Without one
    # `tauri build` fails outright, so only ask for them when the key is set.
    signed = bool(
        os.environ.get("TAURI_SIGNING_PRIVATE_KEY")
        or os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PATH")
    )
    cmd = ["npm", "run", "tauri", "--", "build"]
    if signed:
        cmd += ["--config", '{"bundle":{"createUpdaterArtifacts":true}}']
        log("[app] cargo tauri build (signed updater artifacts)")
    else:
        log("[app] cargo tauri build (no TAURI_SIGNING_PRIVATE_KEY — 不产更新签名包)")
    run(cmd, cwd=APP_DIR)

    release = APP_DIR / "src-tauri" / "target" / "release"
    exe = release / TAURI_EXE_NAME
    if not exe.is_file():
        alt = release / "rvc-fabric.exe"
        if not alt.is_file():
            raise FileNotFoundError(
                f"expected {exe} or {alt} — did `cargo tauri build` fail?"
            )
        exe = alt
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, out / TAURI_EXE_NAME)
    log(f"  exe: {TAURI_EXE_NAME} ({exe.stat().st_size // 1024} KB)")

    fe_src = APP_DIR / "frontend"
    if not (fe_src / "index.html").is_file():
        raise FileNotFoundError(f"missing built frontend: {fe_src}")
    fe_dst = out / "frontend"
    shutil.rmtree(fe_dst, ignore_errors=True)
    shutil.copytree(fe_src, fe_dst)
    n = sum(1 for f in fe_dst.rglob("*") if f.is_file())
    log(f"  frontend/: {n} files (swappable — do not embed only)")

    # Strategy B artifacts (signed installer + .sig) live next to the exe in
    # the bundle dir; build_setup does not ship them, they go to CNB alongside
    # updater.json.
    for extra in ("WebView2Loader.dll",):
        src = release / extra
        if src.is_file():
            shutil.copy2(src, out / extra)
            log(f"  extra: {extra}")


def build_exes(out: Path) -> None:
    """Back-compat alias — the shell is the Tauri app now."""
    build_tauri_shell(out)


def copy_engine(out: Path) -> None:
    log("[engine] copy core from repo")

    def _ignore(directory: str, names: list[str]) -> set[str]:
        skip = set()
        base = Path(directory).name
        for n in names:
            if n in (
                "__pycache__",
                ".git",
                ".pytest_cache",
                "build",
                "dist",
                "RVCMAX",
                "TEMP",
                ".venv",
            ):
                skip.add(n)
            if n.endswith(".pyc"):
                skip.add(n)
        # skip huge optional training logs under logs except mute fixtures
        return skip

    for d in ENGINE_DIRS:
        src = REPO / d
        if src.is_dir():
            copy_tree(
                src,
                out / d,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    ".git",
                ),
            )
    for f in ENGINE_FILES:
        src = REPO / f
        if src.is_file():
            shutil.copy2(src, out / f)
            log(f"  file: {f}")

    # Keep only docs/legal (MIT) — never ship full internal docs tree (review #20)
    legal_src = REPO / "docs" / "legal"
    legal_dst = out / "legal"
    if legal_src.is_dir():
        if legal_dst.exists():
            shutil.rmtree(legal_dst, ignore_errors=True)
        copy_tree(legal_src, legal_dst)
        log("  keep: docs/legal -> legal/ (MIT)")
    # Drop any docs/ that might have been pulled in by mistake
    docs_out = out / "docs"
    if docs_out.is_dir():
        shutil.rmtree(docs_out, ignore_errors=True)
        log("  strip: docs/ (internal handoff/session notes)")

    # scripts/dev 不进包。
    #
    # 这里原来写着「dev launchers (not for end-users)」，然后把它整个拷进了
    # 用户装的目录 —— 注释和动作正好相反。里面剩下的是 Windows 上的调试
    # 批处理和测试清单，用户拿到既不会用也用不上，而且它引用的那套老
    # Python 启动器早就不存在了。

    # logs/ 整个不进包（那是用户的训练实验目录），但 logs/mute 必须进：
    # 训练的 filelist 末尾要补两条静音样本，缺了训练在最后一步才会炸。
    # 1.4 MB，只有这一个子目录。
    mute_src = REPO / "logs" / "mute"
    if mute_src.is_dir():
        copy_tree(mute_src, out / "logs" / "mute")
        log("  keep: logs/mute (训练用静音样本)")

    # Merge critical weights/ffmpeg from RVCMAX if repo placeholders are empty
    merge_rvcmax_engine_bits(out)

    # Never ship developer absolute paths in configs/inuse
    try:
        sys.path.insert(0, str(REPO))
        from inuse_template import write_clean_inuse

        write_clean_inuse(out)
        log("[engine] sanitized configs/inuse/config.json")
    except Exception as e:
        log(f"[engine] inuse sanitize skip: {e}")


def _rvc_core_candidates() -> list[Path]:
    """Prefer N-card core, then AMD / 50-series cores for hubert/rmvpe/ffmpeg."""
    cores: list[Path] = []
    for name in (
        "RVCMAX_Nvidia_xiaoyuan",
        "RVCMAX_AMD_xiaoyuan",
        "RVCMAX_Nvidia50x0_xiaoyuan",
    ):
        p = RVCMAX_ROOT / name / "RVC_Core"
        if p.is_dir():
            cores.append(p)
    return cores


def merge_rvcmax_engine_bits(out: Path) -> None:
    """Fill hubert/rmvpe/ffmpeg from local RVCMAX packs (no network).

    Always try to ship both rmvpe.pt and rmvpe.onnx (AMD/DML needs onnx for F0).
    """
    cores = _rvc_core_candidates()
    if not cores:
        log("[merge] no RVCMAX RVC_Core — ensure hubert/rmvpe already in out/assets")
        return
    log("[merge] hubert / rmvpe / ffmpeg from RVCMAX (multi-core fallback)")

    def _cf_first(rel: str, dst: Path) -> None:
        for core in cores:
            src = core / rel
            if not src.is_file():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_file() and dst.stat().st_size == src.stat().st_size:
                log(f"  skip: {dst.relative_to(out)}")
                return
            shutil.copy2(src, dst)
            log(
                f"  + {dst.relative_to(out)} ({src.stat().st_size // 1024 // 1024} MB) from {core.parent.name}"
            )
            return
        log(f"  missing: {rel}")

    _cf_first(
        "assets/hubert/hubert_base.pt", out / "assets" / "hubert" / "hubert_base.pt"
    )
    for n in ("rmvpe.pt", "rmvpe.onnx"):
        _cf_first(f"assets/rmvpe/{n}", out / "assets" / "rmvpe" / n)
    for n in ("ffmpeg.exe", "ffprobe.exe"):
        _cf_first(n, out / n)


def copy_runtime(out: Path, runtime_src: Path | None) -> None:
    dst = out / "Runtime"
    if runtime_src is None:
        # Keep an existing complete Runtime (incremental rebuild / --skip-runtime)
        if (dst / "python.exe").is_file():
            log(f"[runtime] SKIP — keep existing {dst}")
            # Remove stale placeholder if a real Runtime is present
            ph = dst / "README_PLACE_RUNTIME_HERE.txt"
            if ph.is_file():
                try:
                    ph.unlink()
                except Exception:
                    pass
            return
        log("[runtime] SKIP (--skip-runtime or no source) — writing placeholder")
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "README_PLACE_RUNTIME_HERE.txt").write_text(
            "Put embedded Python Runtime here (python.exe + site-packages).\n"
            "Or re-run: python scripts/build_release.py --runtime <path>\n",
            encoding="utf-8",
        )
        return
    if not runtime_src.is_dir():
        raise FileNotFoundError(f"Runtime source not found: {runtime_src}")
    log(f"[runtime] from {runtime_src}")
    if dst.exists():
        shutil.rmtree(dst)
    robocopy(runtime_src, dst)
    py = dst / "python.exe"
    if not py.is_file():
        raise FileNotFoundError(f"Runtime incomplete: no python.exe in {dst}")


def copy_vbcable(out: Path, src: Path | None) -> None:
    dst = out / "VBCABLE"
    if src is None or not src.is_dir():
        log("[vbcable] using repo VBCABLE + placeholder")
        repo_v = REPO / "VBCABLE"
        if repo_v.is_dir():
            copy_tree(repo_v, dst)
        else:
            dst.mkdir(parents=True, exist_ok=True)
        return
    log(f"[vbcable] from {src}")
    copy_tree(src, dst)


def copy_models(out: Path, models_src: Path | None) -> None:
    dst = out / "User_Data" / "models"
    dst.mkdir(parents=True, exist_ok=True)
    (out / "User_Data" / "logs").mkdir(parents=True, exist_ok=True)
    if models_src and models_src.is_dir():
        log(f"[models] from {models_src}")
        # if models_src is already models/ with numbered folders
        if any(models_src.glob("*/**/*.pth")) or any(models_src.glob("*/*.pth")):
            for child in models_src.iterdir():
                if child.is_dir():
                    target = dst / child.name
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(child, target)
                elif child.suffix.lower() == ".pth":
                    name = child.stem
                    folder = dst / name
                    folder.mkdir(exist_ok=True)
                    shutil.copy2(child, folder / child.name)
        elif any(models_src.glob("*.pth")):
            for pth in models_src.glob("*.pth"):
                folder = dst / pth.stem
                folder.mkdir(exist_ok=True)
                shutil.copy2(pth, folder / pth.name)
        else:
            # copy tree as-is
            for child in models_src.iterdir():
                if child.is_dir():
                    shutil.copytree(child, dst / child.name, dirs_exist_ok=True)
    else:
        log("[models] no source — empty catalog (import in UI later)")
    # also pull any existing User_Data/models from repo
    repo_m = REPO / "User_Data" / "models"
    if repo_m.is_dir():
        for child in repo_m.iterdir():
            if child.is_dir() and any(child.glob("*.pth")):
                t = dst / child.name
                if not t.exists():
                    shutil.copytree(child, t)
                    log(f"  + repo model {child.name}")


def write_readme(
    out: Path, *, variant: str = "nvidia", label: str = "NVIDIA CUDA"
) -> None:
    accel_line = {
        "nvidia": "本包为 NVIDIA CUDA（对齐官方 N 卡整合包）。",
        "amd": (
            "本包为 AMD/Intel DirectML（对齐官方 A/I 卡整合包 + --dml）。\n"
            "请勿与 N 卡 Runtime 混用。默认走 DirectML，勿强行改 cuda。"
        ),
        "nvidia50": "本包为 NVIDIA 50 系适配 CUDA Runtime（参考 RVCMAX 50 系包）。",
    }.get(variant, f"加速变体：{label}")
    text = f"""RVC Fabric — 发行版（{label}）
================================

【用户只需要】
1. 解压到英文路径（推荐 D:\\RVC_Fabric\\）
2. 双击「启动器.exe」（或 TM_Setup.exe）
3. 点「发送快捷方式」「安装虚拟声卡」
4. 之后双击桌面图标或主界面「变声器.exe」（界面标题为 RVC Fabric）

【显卡说明 — 与官方 RVC 一致】
{accel_line}
官方 Windows：
  · N 卡 = 单独 CUDA 环境（requirements / Nvidia 7z）
  · A/I 卡 = 单独 DirectML 环境（requirements-dml / AMD_Intel 7z）+ 启动 --dml
不是「同一个 Runtime 只加一个参数」；参数只在正确环境里切换设备。

【已内置】
- Runtime\\     本变体专用绿色 Python（无需自装 Python）
- package_meta.json  标记本包变体与默认加速
- User_Data\\models\\  预置音色（若打包时带了）
- VBCABLE\\     虚拟声卡安装包
- 引擎与界面（含 rmvpe.pt / rmvpe.onnx）

【不要用】
- tools\\dev\\ 下的 .bat 仅供开发调试
- 不要把 N 卡包 Runtime 拷进 A 卡包混用

打包时间: {time.strftime("%Y-%m-%d %H:%M:%S")}
变体: {variant}
"""
    (out / "使用说明.txt").write_text(text, encoding="utf-8")
    log("[doc] 使用说明.txt")


def pack_dir_matches(
    dir_name: str,
    *,
    name_keys: tuple[str, ...],
    exclude_keys: tuple[str, ...] = (),
) -> bool:
    """Return True if folder name matches include keys and none of exclude keys."""
    name = (dir_name or "").lower()
    if not name:
        return False
    keys = tuple(k.lower() for k in name_keys if k)
    excludes = tuple(k.lower() for k in exclude_keys if k)
    if excludes and any(ex in name for ex in excludes):
        return False
    if not keys:
        return False
    return any(k in name for k in keys)


def find_rvcmax_pack_dir(
    name_keys: tuple[str, ...],
    prefer_dir: str = "",
    *,
    exclude_keys: tuple[str, ...] = (),
    rvcmax_root: Path | None = None,
) -> Path | None:
    """Find RVCMAX/<pack>/ that matches keywords and has Runtime/python.exe.

    Order: prefer_dir (exact) → scan by name_keys with exclude_keys filter.
    ``rvcmax_root`` is injectable for unit tests.
    """
    root = rvcmax_root if rvcmax_root is not None else RVCMAX_ROOT
    if prefer_dir:
        p = root / prefer_dir
        if (p / "Runtime" / "python.exe").is_file():
            return p
    if not root.is_dir():
        return None
    for child in sorted(root.iterdir(), key=lambda x: x.name.lower()):
        if not child.is_dir():
            continue
        if not pack_dir_matches(
            child.name, name_keys=name_keys, exclude_keys=exclude_keys
        ):
            continue
        if (child / "Runtime" / "python.exe").is_file():
            return child
    return None


def find_pack_for_variant(
    variant: str, *, rvcmax_root: Path | None = None
) -> Path | None:
    """Resolve RVCMAX pack directory for a shipping variant."""
    info = VARIANTS.get(variant, VARIANTS["nvidia"])
    return find_rvcmax_pack_dir(
        tuple(info.get("name_keys") or ()),
        str(info.get("prefer_dir") or ""),
        exclude_keys=tuple(info.get("exclude_keys") or ()),
        rvcmax_root=rvcmax_root,
    )


def default_runtime(variant: str = "nvidia") -> Path | None:
    env = os.environ.get("TM_RUNTIME_SRC", "")
    if env and (Path(env) / "python.exe").is_file():
        return Path(env)
    pack = find_pack_for_variant(variant)
    if pack and (pack / "Runtime" / "python.exe").is_file():
        return pack / "Runtime"
    # Do NOT fall back to REPO/Runtime: dev trees often junction AMD/50 Runtime there.
    # Only accept the canonical prefer_dir pack or REF for nvidia.
    if variant == "nvidia":
        ref_rt = REF / "Runtime"
        if (ref_rt / "python.exe").is_file():
            return ref_rt
    return None


def default_models(variant: str = "nvidia") -> Path | None:
    env = os.environ.get("TM_MODELS_SRC", "")
    if env and Path(env).is_dir():
        return Path(env)
    pack = find_pack_for_variant(variant)
    if pack and (pack / "User_Data" / "models").is_dir():
        return pack / "User_Data" / "models"
    for p in (REF / "User_Data" / "models", REPO / "User_Data" / "models"):
        if p.is_dir():
            return p
    return None


def default_vbcable(variant: str = "nvidia") -> Path | None:
    pack = find_pack_for_variant(variant)
    if pack and (pack / "VBCABLE").is_dir() and any((pack / "VBCABLE").glob("*.exe")):
        return pack / "VBCABLE"
    for p in (REF / "VBCABLE", REPO / "VBCABLE"):
        if p.is_dir() and any(p.glob("*.exe")):
            return p
    return REPO / "VBCABLE" if (REPO / "VBCABLE").is_dir() else None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build Turing Mirror Voice release pack (official multi-pack ready)"
    )
    p.add_argument(
        "--variant",
        choices=list(VARIANTS.keys()),
        default="nvidia",
        help="nvidia | amd | nvidia50 — full separate packs like official RVC",
    )
    p.add_argument("--out", type=Path, default=None, help="output directory")
    p.add_argument("--runtime", type=Path, default=None, help="Runtime source dir")
    p.add_argument("--models", type=Path, default=None, help="models source dir")
    p.add_argument("--vbcable", type=Path, default=None, help="VBCABLE source dir")
    p.add_argument("--skip-exe", action="store_true", help="do not run PyInstaller")
    p.add_argument("--skip-runtime", action="store_true", help="do not copy Runtime")
    p.add_argument("--clean", action="store_true", help="wipe out dir first")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    variant = str(args.variant or "nvidia")
    vinfo = VARIANTS[variant]
    if args.out is None:
        out = (REPO / "dist" / vinfo["out_name"]).resolve()
    else:
        out = args.out.resolve()
    log(f"=== build release variant={variant} -> {out} ===")
    log(f"    label={vinfo['label']} accel_default={vinfo['accel_default']}")

    if args.clean and out.exists():
        log("[clean] remove old out")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # 1) engine
    copy_engine(out)

    # 2) runtime (full pack must ship correct green env — not flag-only)
    if args.skip_runtime:
        copy_runtime(out, None)
    else:
        rt = args.runtime or default_runtime(variant)
        if rt is None:
            log(
                f"[runtime] WARNING: no Runtime for variant={variant}. "
                "Put RVCMAX pack under RVCMAX/ or pass --runtime PATH."
            )
            if variant != "nvidia":
                log(
                    "[runtime] AMD/50-series pack CANNOT be faked by only setting --dml. "
                    "Need the matching Runtime (official AMD_Intel / RVCMAX A-card pack)."
                )
            copy_runtime(out, None)
        else:
            copy_runtime(out, rt)

    # 3) models
    copy_models(out, args.models or default_models(variant))

    # 4) vbcable
    copy_vbcable(out, args.vbcable or default_vbcable(variant))

    # 5) package identity (official multi-pack)
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from package_meta import write_package_meta

        write_package_meta(
            out,
            variant,
            label=vinfo["label"],
            accel_default=vinfo["accel_default"],
            use_dml=bool(vinfo["accel_default"] == "dml"),
        )
        log(f"[meta] package_meta.json variant={variant}")
    except Exception as e:
        # Fallback: write meta without importing launcher (path issues)
        log(f"[meta] import write_package_meta failed ({e}); writing JSON fallback")
        meta = {
            "variant": variant,
            "label": vinfo["label"],
            "accel_default": vinfo["accel_default"],
            "use_dml": bool(vinfo["accel_default"] == "dml"),
            "tagged": True,
        }
        (out / "package_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"[meta] package_meta.json variant={variant} (fallback)")

    # Seed default app config accel for first launch
    try:
        ud = out / "User_Data"
        ud.mkdir(parents=True, exist_ok=True)
        cfg_path = ud / "app_config.json"
        if not cfg_path.is_file():
            seed = {
                "accel_backend": vinfo["accel_default"],
                "pitch": 0,
                "f0method": "fcpe",
            }
            cfg_path.write_text(
                json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log(f"[meta] seed User_Data/app_config.json accel={vinfo['accel_default']}")
    except Exception as e:
        log(f"[meta] seed config skip: {e}")

    # 6) exes into out root
    if not args.skip_exe:
        try:
            build_exes(out)
        except Exception as e:
            log(f"[exe] FAILED: {e}")
            log("  You can re-run without --skip-exe after fixing PyInstaller.")
            return 1
    else:
        log("[exe] skipped")

    write_readme(out, variant=variant, label=str(vinfo["label"]))

    # summary
    log("=== done ===")
    log(f"Output: {out}")
    for name in (
        "TM_Setup.exe",
        "TM_Voice.exe",
        "启动器.exe",
        "变声器.exe",
        "Runtime",
        "User_Data",
        "VBCABLE",
        "package_meta.json",
    ):
        p = out / name
        mark = "OK" if (p.is_file() or p.is_dir()) else "MISSING"
        log(f"  [{mark}] {name}")
    if not (out / "Runtime" / "python.exe").is_file():
        log("[WARN] Runtime incomplete — do not ship this folder to users yet.")
    log("User path: unzip -> double-click 启动器.exe or TM_Setup.exe (no bat).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
