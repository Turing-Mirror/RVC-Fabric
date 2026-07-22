# -*- coding: utf-8 -*-
"""RVC Fabric Setup — install shell + launcher, pick GPU, hand off to bootstrap.

User path (product decision)::

    下载 Setup → 安装软件与启动器 → 启动器自动补全 Runtime/环境
    → 主界面 → 新手指引 → 社区下载音色 → 变声 → 调参
    → 免费/付费优化 → 收集资料 → 进群

Runtime comes from CNB **Release** assets; voices use CNB Git LFS.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.cnb_sources import (
    CNB_REPO_URL,
    VARIANT_LABELS,
    format_size,
    resolve_runtime_spec,
)
from launcher.package_meta import write_package_meta
from launcher.paths import APP_TITLE, ensure_dirs
from launcher.runtime_provision import runtime_ready
from launcher.theme import (
    APP_WORDMARK,
    PAD_X,
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    mono_font,
    sans_font,
    title_font,
)
from launcher.ui import GhostButton, PrimaryButton

# Shell tree pieces copied into install dir (no Runtime / no multi-GB weights)
_SHELL_DIRS = (
    "launcher",
    "configs",
    "i18n",
    "infer",
    "tools",
    "docs",
    "assets",
)
_SHELL_FILES = (
    "gui_v1.py",
    "infer-web.py",
    "LICENSE",
    "README.md",
    ".env",
    "OpenApp.vbs",
    "OpenSetup.vbs",
    "package_meta.json",
)
_SHELL_EXES = (
    "启动器.exe",
    "变声器.exe",
    "TM_Setup.exe",
    "TM_Voice.exe",
    "RVC Fabric.exe",
    "RVC Fabric Setup.exe",
    "Setup.exe",
)


def _detect_source_root() -> Path:
    """Directory that holds the product shell to install from."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _default_install_dir() -> Path:
    home = Path.home()
    for base in (
        home / "Documents" / "RVC Fabric",
        Path(os.environ.get("LOCALAPPDATA", str(home))) / "RVC Fabric",
        home / "RVC Fabric",
    ):
        return base
    return home / "RVC Fabric"


def _is_shell_tree(path: Path) -> bool:
    return (path / "launcher").is_dir() and (
        (path / "gui_v1.py").is_file()
        or (path / "变声器.exe").is_file()
        or (path / "TM_Voice.exe").is_file()
    )


def _ignore_copy(directory: str, names: list[str]) -> set[str]:
    skip = {
        "__pycache__",
        ".git",
        ".pytest_cache",
        "RVCMAX",
        "dist",
        "build",
        "TEMP",
        "TEMP_BUILD",
        "CNB-GIT-RELEASE",
        "Runtime",
        "runtime",
        "_local",
        "_sync_backup_20260721",
    }
    out = {n for n in names if n in skip or n.endswith(".pyc")}
    # never copy multi-GB model blobs under assets if present as real weights
    dlow = directory.replace("\\", "/").lower()
    if dlow.endswith("/assets/hubert") or dlow.endswith("/assets/rmvpe"):
        for n in names:
            if n.endswith((".pt", ".onnx", ".pth")) and n not in out:
                # still copy if small placeholder; skip huge
                try:
                    p = Path(directory) / n
                    if p.is_file() and p.stat().st_size > 5_000_000:
                        out.add(n)
                except OSError:
                    pass
    return out


def copy_shell_tree(src: Path, dst: Path, *, log=None) -> None:
    """Copy thin product shell src → dst (no Runtime)."""
    if src.resolve() == dst.resolve():
        if log:
            log("安装目录即当前目录，跳过复制。")
        return
    dst.mkdir(parents=True, exist_ok=True)
    for name in _SHELL_DIRS:
        s = src / name
        if not s.is_dir():
            continue
        d = dst / name
        if log:
            log(f"复制 {name}/ …")
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(s, d, ignore=_ignore_copy)
    for name in _SHELL_FILES:
        s = src / name
        if s.is_file():
            shutil.copy2(s, dst / name)
    for name in _SHELL_EXES:
        s = src / name
        if s.is_file():
            shutil.copy2(s, dst / name)
    # empty user dirs
    for rel in (
        "User_Data/models",
        "User_Data/logs",
        "User_Data/indices",
        "User_Data/shared_profiles",
        "VBCABLE",
    ):
        (dst / rel).mkdir(parents=True, exist_ok=True)
    # optional VBCABLE binaries
    vb = src / "VBCABLE"
    if vb.is_dir():
        for f in vb.iterdir():
            if f.is_file() and f.suffix.lower() in (".exe", ".txt", ".md"):
                shutil.copy2(f, dst / "VBCABLE" / f.name)


def create_shortcuts(install_root: Path) -> list[str]:
    """Desktop shortcuts to 启动器 and main app under install_root."""
    created: list[str] = []
    from launcher.paths import desktop_dir
    from launcher.win_util import CREATE_NO_WINDOW

    desk = desktop_dir()
    desk.mkdir(parents=True, exist_ok=True)

    targets = []
    boot = None
    for n in ("启动器.exe", "TM_Setup.exe"):
        p = install_root / n
        if p.is_file():
            boot = p
            break
    app = None
    for n in ("变声器.exe", "TM_Voice.exe", "RVC Fabric.exe"):
        p = install_root / n
        if p.is_file():
            app = p
            break
    if boot is not None:
        targets.append(("RVC Fabric 启动器.lnk", boot))
    if app is not None:
        targets.append(("RVC Fabric.lnk", app))
    if not targets:
        # Dev: VBS / pythonw
        vbs = install_root / "OpenSetup.vbs"
        if vbs.is_file():
            targets.append(
                (
                    "RVC Fabric 启动器.lnk",
                    Path(r"C:\Windows\System32\wscript.exe"),
                    f'//nologo "{vbs}"',
                )
            )

    import subprocess

    for item in targets:
        if len(item) == 2:
            name, target = item
            arguments = ""
            icon = str(target)
        else:
            name, target, arguments = item
            icon = str(target)
        lnk = desk / name

        def _esc(s: str) -> str:
            return s.replace("'", "''")

        ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{_esc(str(lnk))}')
$sc.TargetPath = '{_esc(str(target))}'
$sc.Arguments = '{_esc(arguments)}'
$sc.WorkingDirectory = '{_esc(str(install_root))}'
$sc.WindowStyle = 1
$sc.Description = 'RVC Fabric'
$sc.IconLocation = '{_esc(icon)},0'
$sc.Save()
"""
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            check=False,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if lnk.is_file():
            created.append(str(lnk))
    return created


def start_bootstrap_at(install_root: Path) -> None:
    env = os.environ.copy()
    env["TM_VOICE_ROOT"] = str(install_root)
    env["PYTHONPATH"] = str(install_root) + os.pathsep + env.get("PYTHONPATH", "")
    for n in ("启动器.exe", "TM_Setup.exe"):
        exe = install_root / n
        if exe.is_file():
            import subprocess

            subprocess.Popen(
                [str(exe)],
                cwd=str(install_root),
                env=env,
                close_fds=True,
            )
            return
    py = install_root / "Runtime" / "pythonw.exe"
    if not py.is_file():
        # host python for first bootstrap (will download Runtime)
        py = Path(sys.executable)
        if py.name.lower() == "python.exe":
            pyw = py.with_name("pythonw.exe")
            if pyw.is_file():
                py = pyw
    script = install_root / "launcher" / "bootstrap.py"
    import subprocess

    subprocess.Popen(
        [str(py), str(script)],
        cwd=str(install_root),
        env=env,
        close_fds=True,
    )


class SetupApp:
    """Multi-step installer UI."""

    STEPS = ("欢迎", "安装位置", "显卡分版", "安装", "完成")

    def __init__(self) -> None:
        self.source = _detect_source_root()
        self.install_dir = (
            self.source if _is_shell_tree(self.source) else _default_install_dir()
        )
        self.variant = tk.StringVar(value="nvidia")
        self._step = 0
        self._busy = False
        self._log_lines: list[str] = []

        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE} · Setup")
        self.root.geometry("640x560")
        self.root.configure(bg=TM_BG)
        self.root.resizable(False, False)

        head = tk.Frame(self.root, bg=TM_SURFACE)
        head.pack(fill="x")
        inner = tk.Frame(head, bg=TM_SURFACE)
        inner.pack(fill="x", padx=PAD_X, pady=(18, 12))
        tk.Label(
            inner,
            text=APP_WORDMARK,
            font=title_font(16, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        self.lbl_step = tk.Label(
            inner,
            text="安装向导",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
        )
        self.lbl_step.pack(anchor="w", pady=(8, 0))
        tk.Frame(self.root, bg=TM_HAIRLINE, height=1).pack(fill="x")

        # step dots
        self.dots = tk.Frame(self.root, bg=TM_BG)
        self.dots.pack(fill="x", padx=PAD_X, pady=(12, 4))
        self._dot_labels: list[tk.Label] = []
        for i, name in enumerate(self.STEPS):
            lb = tk.Label(
                self.dots,
                text=f" {i + 1}.{name} ",
                font=mono_font(8),
                bg=TM_INSET,
                fg=TM_INK_MUTED,
                padx=4,
                pady=3,
            )
            lb.pack(side="left", padx=2)
            self._dot_labels.append(lb)

        self.body = tk.Frame(self.root, bg=TM_BG)
        self.body.pack(fill="both", expand=True, padx=PAD_X, pady=(8, 4))

        self.status = tk.Label(
            self.root,
            text="",
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=560,
            justify="left",
            anchor="w",
        )
        self.status.pack(fill="x", padx=PAD_X, pady=(0, 6))

        nav = tk.Frame(self.root, bg=TM_BG)
        nav.pack(fill="x", padx=PAD_X, pady=(4, 16))
        self.btn_back = GhostButton(nav, "上一步", command=self.on_back, padx=16, pady=8)
        self.btn_back.pack(side="left")
        self.btn_next = PrimaryButton(nav, "下一步", command=self.on_next, padx=28, pady=8)
        self.btn_next.pack(side="right")

        self._pages: dict[int, tk.Frame] = {}
        self._build_pages()
        self._show_step(0)

    def _clear_body(self) -> None:
        for w in self.body.winfo_children():
            w.pack_forget()

    def _build_pages(self) -> None:
        # 0 welcome
        p0 = tk.Frame(self.body, bg=TM_BG)
        tk.Label(
            p0,
            text="欢迎使用 RVC Fabric",
            font=title_font(14, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(8, 8))
        flow = (
            "本向导会：\n"
            "  1. 把软件壳层与启动器装到你选的目录\n"
            "  2. 按显卡选择写入分版信息\n"
            "  3. 创建桌面快捷方式\n"
            "  4. 交给「启动器」自动下载补全 Runtime 与必需文件\n\n"
            "之后在软件里：新手指引 → 社区下载音色（pth/index）→ 变声 → 调参\n"
            "→ 免费/付费优化 → 收集资料 → 进群。\n\n"
            f"制品仓：{CNB_REPO_URL}\n"
            "Runtime 走 CNB Release；音色等走 Git LFS。"
        )
        tk.Label(
            p0,
            text=flow,
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            justify="left",
            anchor="w",
            wraplength=560,
        ).pack(fill="x")
        self._pages[0] = p0

        # 1 install path
        p1 = tk.Frame(self.body, bg=TM_BG)
        tk.Label(
            p1,
            text="选择安装位置",
            font=title_font(14, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(8, 8))
        tk.Label(
            p1,
            text="建议使用纯英文路径、机械盘/固态均可；预留约 8–12 GB（含 Runtime）。",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=560,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))
        row = tk.Frame(p1, bg=TM_BG)
        row.pack(fill="x")
        self.ent_path = tk.Entry(
            row,
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        self.ent_path.pack(side="left", fill="x", expand=True, ipady=6)
        self.ent_path.insert(0, str(self.install_dir))
        GhostButton(row, "浏览…", command=self.on_browse, padx=12, pady=6).pack(
            side="left", padx=(8, 0)
        )
        if _is_shell_tree(self.source):
            tk.Label(
                p1,
                text=f"当前包位置：{self.source}\n可直接装在此处，或复制到其它目录。",
                font=mono_font(8),
                bg=TM_BG,
                fg=TM_INK_MUTED,
                justify="left",
                anchor="w",
                wraplength=560,
            ).pack(fill="x", pady=(12, 0))
        self._pages[1] = p1

        # 2 GPU
        p2 = tk.Frame(self.body, bg=TM_BG)
        tk.Label(
            p2,
            text="选择显卡分版",
            font=title_font(14, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(8, 8))
        tk.Label(
            p2,
            text="启动器会按此分版从 CNB Release 下载对应 Runtime（体积较大，需联网）。",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=560,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, 12))
        self._size_labels: dict[str, tk.Label] = {}
        for key, label in (
            ("nvidia", VARIANT_LABELS["nvidia"]),
            ("amd", VARIANT_LABELS["amd"]),
            ("nvidia50", VARIANT_LABELS["nvidia50"]),
        ):
            fr = tk.Frame(
                p2,
                bg=TM_SURFACE,
                highlightthickness=1,
                highlightbackground=TM_HAIRLINE,
            )
            fr.pack(fill="x", pady=4)
            rb = tk.Radiobutton(
                fr,
                text=label,
                variable=self.variant,
                value=key,
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_INK,
                activebackground=TM_SURFACE,
                selectcolor=TM_SURFACE,
                anchor="w",
                command=self._refresh_variant_hint,
            )
            rb.pack(fill="x", padx=12, pady=(10, 2))
            sz = tk.Label(
                fr,
                text="",
                font=mono_font(8),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                anchor="w",
            )
            sz.pack(fill="x", padx=28, pady=(0, 10))
            self._size_labels[key] = sz
        self._pages[2] = p2

        # 3 install progress
        p3 = tk.Frame(self.body, bg=TM_BG)
        tk.Label(
            p3,
            text="正在安装",
            font=title_font(14, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(8, 8))
        self.lbl_install = tk.Label(
            p3,
            text="准备中…",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
            wraplength=560,
            justify="left",
        )
        self.lbl_install.pack(fill="x")
        self.txt_log = tk.Text(
            p3,
            height=14,
            font=mono_font(8),
            bg=TM_INSET,
            fg=TM_INK,
            relief="flat",
            wrap="word",
        )
        self.txt_log.pack(fill="both", expand=True, pady=(10, 0))
        self.txt_log.configure(state="disabled")
        self._pages[3] = p3

        # 4 done
        p4 = tk.Frame(self.body, bg=TM_BG)
        tk.Label(
            p4,
            text="安装完成",
            font=title_font(14, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(8, 8))
        self.lbl_done = tk.Label(
            p4,
            text="",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            justify="left",
            anchor="w",
            wraplength=560,
        )
        self.lbl_done.pack(fill="x")
        self._pages[4] = p4

    def _show_step(self, i: int) -> None:
        self._step = max(0, min(i, len(self.STEPS) - 1))
        self._clear_body()
        self._pages[self._step].pack(fill="both", expand=True)
        self.lbl_step.configure(text=f"步骤 {self._step + 1}/{len(self.STEPS)} · {self.STEPS[self._step]}")
        for j, lb in enumerate(self._dot_labels):
            if j == self._step:
                lb.configure(bg=TM_ACCENT, fg=TM_ACCENT_INK)
            elif j < self._step:
                lb.configure(bg=TM_OK, fg=TM_ACCENT_INK)
            else:
                lb.configure(bg=TM_INSET, fg=TM_INK_MUTED)
        self.btn_back.configure(state="normal" if self._step > 0 and self._step < 3 else "disabled")
        if self._step == 0:
            self.btn_next.configure(text="下一步")
        elif self._step == 2:
            self.btn_next.configure(text="开始安装")
            self._refresh_variant_hint()
        elif self._step == 3:
            self.btn_next.configure(text="请稍候…")
            self.btn_next.configure(state="disabled")
            self.btn_back.configure(state="disabled")
        elif self._step == 4:
            self.btn_next.configure(text="打开启动器")
            self.btn_next.configure(state="normal")
            self.btn_back.configure(state="disabled")
        else:
            self.btn_next.configure(text="下一步")
            self.btn_next.configure(state="normal")

    def _refresh_variant_hint(self) -> None:
        for key, lb in self._size_labels.items():
            try:
                spec = resolve_runtime_spec(key, prefer_remote=False)
                lb.configure(
                    text=f"Runtime 约 {format_size(spec.size_bytes)} · Release 标签 {spec.release_tag}"
                )
            except Exception:
                lb.configure(text="（体积见 CNB 清单）")

    def on_browse(self) -> None:
        d = filedialog.askdirectory(initialdir=str(self.install_dir))
        if d:
            self.ent_path.delete(0, "end")
            self.ent_path.insert(0, d)

    def on_back(self) -> None:
        if self._busy or self._step <= 0:
            return
        self._show_step(self._step - 1)

    def on_next(self) -> None:
        if self._busy:
            return
        if self._step == 1:
            path = Path(self.ent_path.get().strip().strip('"'))
            if not path.parts:
                messagebox.showwarning("安装位置", "请选择有效目录。")
                return
            self.install_dir = path
        if self._step == 2:
            self._show_step(3)
            self._start_install()
            return
        if self._step == 4:
            try:
                start_bootstrap_at(self.install_dir)
                self.root.after(400, self.root.destroy)
            except Exception as e:
                messagebox.showerror("启动失败", str(e))
            return
        if self._step < 4:
            self._show_step(self._step + 1)

    def _append_log(self, msg: str) -> None:
        self._log_lines.append(msg)
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
        self.lbl_install.configure(text=msg)
        self.status.configure(text=msg, fg=TM_OK)

    def _start_install(self) -> None:
        self._busy = True
        src = self.source
        dst = Path(self.ent_path.get().strip().strip('"') or self.install_dir)
        self.install_dir = dst
        var = self.variant.get().strip().lower() or "nvidia"

        def work() -> None:
            lines: list[str] = []

            def log(m: str) -> None:
                lines.append(m)
                self.root.after(0, lambda t=m: self._append_log(t))

            try:
                if not _is_shell_tree(src):
                    raise RuntimeError(
                        f"当前目录不是有效的软件包：{src}\n"
                        "请从官方 Setup 压缩包解压后运行。"
                    )
                log(f"源：{src}")
                log(f"目标：{dst}")
                log(f"分版：{var}")
                copy_shell_tree(src, dst, log=log)
                write_package_meta(
                    dst,
                    var,
                    install_via="setup",
                    cnb_repo=CNB_REPO_URL,
                )
                log("已写入 package_meta.json")
                # marker for bootstrap auto-provision
                try:
                    ensure_dirs()
                except Exception:
                    pass
                marker = dst / "User_Data"
                marker.mkdir(parents=True, exist_ok=True)
                (marker / "setup_pending.json").write_text(
                    '{"pending_runtime": true, "variant": "%s"}\n' % var,
                    encoding="utf-8",
                )
                log("已标记：启动器将自动补全 Runtime")
                sc = create_shortcuts(dst)
                if sc:
                    log("桌面快捷方式：" + "；".join(Path(s).name for s in sc))
                else:
                    log("快捷方式创建跳过（可在启动器内再创建）")
                if runtime_ready(dst):
                    log("检测到已有 Runtime，无需下载。")
                else:
                    log("Runtime 未安装 — 打开启动器后将自动从 CNB Release 下载。")
                log("安装完成。")
                ok = True
                msg = "完成"
            except Exception as e:
                ok = False
                msg = str(e)
                log(f"失败：{msg}")

            def done() -> None:
                self._busy = False
                if ok:
                    self.lbl_done.configure(
                        text=(
                            f"软件已安装到：\n{dst}\n\n"
                            f"显卡分版：{VARIANT_LABELS.get(var, var)}\n\n"
                            "下一步：打开「启动器」——它会自动下载补全运行环境，"
                            "然后进入主界面完成新手指引与社区音色下载。\n\n"
                            "若下载中断，可再次打开启动器继续补全。"
                        )
                    )
                    self._show_step(4)
                else:
                    messagebox.showerror("安装失败", msg)
                    self._busy = False
                    self.btn_back.configure(state="normal")
                    self.btn_next.configure(state="normal", text="返回重试")

                    def back_retry() -> None:
                        self.btn_next.configure(command=self.on_next)
                        self._show_step(2)

                    self.btn_next.configure(command=back_retry)

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    SetupApp().run()


if __name__ == "__main__":
    main()
