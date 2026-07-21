# -*- coding: utf-8 -*-
"""
RVC 整合包风格启动器（B 站 / 官方一键包同款体验）

目标：双击 → 选功能 → 实际仍是 WebUI / 实时 GUI
不改算法，只做「解压即用」入口。
"""

from __future__ import annotations

import os
import sys
import threading
import subprocess
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

# 仓库根目录（launcher 的上一级）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORT = 7897
WEB_URL = f"http://127.0.0.1:{PORT}"
HF_PACK_NVIDIA = (
    "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/RVC1006Nvidia.7z"
)
HF_PACK_AMD = (
    "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/RVC1006AMD_Intel.7z"
)
HF_SPACE = "https://huggingface.co/lj1995/VoiceConversionWebUI/tree/main/"
GITHUB = "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI"

# 关键风格：接近常见整合包深色控制台感，避免花哨渐变
BG = "#1e1e1e"
FG = "#e8e8e8"
ACCENT = "#3d8bfd"
BTN_BG = "#2d2d2d"
OK = "#3dd68c"
WARN = "#f0c14b"
ERR = "#f07178"


def find_python() -> tuple[str, str]:
    """返回 (python 可执行文件, 来源说明)。优先整合包 runtime。"""
    runtime = ROOT / "runtime" / "python.exe"
    if runtime.is_file():
        return str(runtime), "整合包 runtime"
    # 当前解释器
    if sys.executable:
        return sys.executable, "当前 Python"
    for name in ("python", "py"):
        return name, f"PATH:{name}"
    return "python", "默认"


def check_assets() -> list[tuple[str, bool, str]]:
    """检查推理必需文件。"""
    items = [
        ("Hubert", ROOT / "assets" / "hubert" / "hubert_base.pt", "推理必需"),
        ("RMVPE", ROOT / "assets" / "rmvpe" / "rmvpe.pt", "音高提取推荐"),
        ("预训练 v2 G40k", ROOT / "assets" / "pretrained_v2" / "f0G40k.pth", "训练推荐"),
        ("音色目录", ROOT / "assets" / "weights", "放 .pth 模型"),
    ]
    out = []
    for name, path, note in items:
        ok = path.is_file() if path.suffix else path.is_dir()
        out.append((name, ok, note))
    return out


def count_voice_models() -> int:
    w = ROOT / "assets" / "weights"
    if not w.is_dir():
        return 0
    return sum(1 for p in w.iterdir() if p.suffix.lower() == ".pth")


class LauncherApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("RVC Fabric")
        self.root.geometry("720x560")
        self.root.minsize(640, 480)
        self.root.configure(bg=BG)
        self.proc: subprocess.Popen | None = None
        self.py, self.py_src = find_python()

        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        title = tk.Label(
            self.root,
            text="RVC 检索式变声 · 整合包启动器",
            font=("Microsoft YaHei UI", 16, "bold"),
            bg=BG,
            fg=FG,
        )
        title.pack(anchor="w", **pad)

        sub = tk.Label(
            self.root,
            text="和 B 站 / 官方教程一样：启动后仍是浏览器 WebUI（训练·推理·分离）或实时变声窗口",
            font=("Microsoft YaHei UI", 9),
            bg=BG,
            fg="#aaaaaa",
            wraplength=680,
            justify="left",
        )
        sub.pack(anchor="w", padx=12)

        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Consolas", 9),
            bg=BG,
            fg=OK,
            justify="left",
            anchor="w",
        )
        self.status_lbl.pack(fill="x", padx=12, pady=8)

        # 主按钮区
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="x", padx=12, pady=4)

        self._btn(
            frame,
            "① 启动 WebUI（训练 / 推理 / 伴奏分离）",
            self.start_webui,
            primary=True,
        ).pack(fill="x", pady=4)
        self._btn(
            frame,
            "② 启动实时变声 GUI（游戏 / 语音）",
            self.start_realtime,
        ).pack(fill="x", pady=4)

        row = tk.Frame(frame, bg=BG)
        row.pack(fill="x", pady=4)
        self._btn(row, "下载预训练模型", self.download_models, width=18).pack(
            side="left", padx=(0, 6)
        )
        self._btn(row, "打开音色文件夹", self.open_weights, width=16).pack(
            side="left", padx=6
        )
        self._btn(row, "打开浏览器界面", self.open_browser, width=16).pack(
            side="left", padx=6
        )
        self._btn(row, "停止 WebUI", self.stop_process, width=12).pack(
            side="left", padx=6
        )

        row2 = tk.Frame(frame, bg=BG)
        row2.pack(fill="x", pady=4)
        self._btn(row2, "使用说明", self.open_readme, width=12).pack(
            side="left", padx=(0, 6)
        )
        self._btn(row2, "官方完整整合包下载", self.open_hf_packs, width=20).pack(
            side="left", padx=6
        )
        self._btn(row2, "GitHub 源码", self.open_github, width=12).pack(
            side="left", padx=6
        )
        self._btn(row2, "刷新状态", self.refresh_status, width=10).pack(
            side="left", padx=6
        )

        # 日志
        tk.Label(
            self.root,
            text="运行日志",
            font=("Microsoft YaHei UI", 10),
            bg=BG,
            fg=FG,
        ).pack(anchor="w", padx=12, pady=(10, 0))

        self.log = scrolledtext.ScrolledText(
            self.root,
            height=14,
            bg="#121212",
            fg=FG,
            insertbackground=FG,
            font=("Consolas", 9),
            relief="flat",
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=8)

        self._log(
            "提示：首次使用请先「下载预训练模型」。音色 .pth 放进 assets\\weights 后点刷新音色。"
        )
        self._log(f"工作目录: {ROOT}")
        self._log(f"Python: {self.py} ({self.py_src})")

    def _btn(self, parent, text, cmd, primary=False, width=None):
        kw = {
            "text": text,
            "command": cmd,
            "font": ("Microsoft YaHei UI", 10, "bold" if primary else "normal"),
            "bg": ACCENT if primary else BTN_BG,
            "fg": "#ffffff" if primary else FG,
            "activebackground": "#5aa0ff" if primary else "#3a3a3a",
            "activeforeground": "#ffffff",
            "relief": "flat",
            "cursor": "hand2",
            "padx": 10,
            "pady": 8 if primary else 6,
        }
        if width:
            kw["width"] = width
        return tk.Button(parent, **kw)

    def _log(self, msg: str) -> None:
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    def refresh_status(self) -> None:
        self.py, self.py_src = find_python()
        lines = [f"Python: {self.py_src} | 端口: {PORT} | 音色模型: {count_voice_models()} 个"]
        missing = []
        for name, ok, note in check_assets():
            mark = "OK" if ok else "缺"
            lines.append(f"  [{mark}] {name} — {note}")
            if not ok and name in ("Hubert", "RMVPE"):
                missing.append(name)
        color = OK if not missing else WARN
        self.status_lbl.configure(fg=color)
        self.status_var.set("\n".join(lines))
        if missing:
            self._log(f"缺少: {', '.join(missing)} — 请点「下载预训练模型」")

    def _env(self) -> dict:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        # 避免系统代理导致 Gradio Connection Error（FAQ 常见问题）
        env.setdefault("no_proxy", "localhost,127.0.0.1,::1")
        env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
        return env

    def _spawn(self, args: list[str], title: str) -> None:
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno(
                "已有进程",
                "当前似乎已有 RVC 进程在运行。仍要再启动一个吗？",
            ):
                return
        self._log(f"启动 {title}: {' '.join(args)}")
        try:
            # Windows 下新开控制台窗口，方便看训练日志（和 go-web.bat 一致）
            creation = 0
            if sys.platform == "win32":
                creation = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
            self.proc = subprocess.Popen(
                args,
                cwd=str(ROOT),
                env=self._env(),
                creationflags=creation,
            )
            self._log(f"已启动 PID={self.proc.pid}。浏览器稍后打开 {WEB_URL}")
        except Exception as e:
            self._log(f"启动失败: {e}")
            messagebox.showerror("启动失败", str(e))

    def start_webui(self) -> None:
        self.refresh_status()
        py = self.py
        script = ROOT / "infer-web.py"
        if not script.is_file():
            messagebox.showerror("错误", f"找不到 {script}")
            return
        # 与官方 go-web.bat 一致：runtime python + port 7897
        args = [py, str(script), "--pycmd", py, "--port", str(PORT)]
        self._spawn(args, "WebUI")
        # 延迟打开浏览器
        def later():
            import time

            time.sleep(3)
            try:
                webbrowser.open(WEB_URL)
            except Exception:
                pass

        threading.Thread(target=later, daemon=True).start()

    def start_realtime(self) -> None:
        script = ROOT / "gui_v1.py"
        if not script.is_file():
            messagebox.showerror("错误", f"找不到 {script}")
            return
        self._spawn([self.py, str(script)], "实时变声")

    def download_models(self) -> None:
        script = ROOT / "tools" / "download_models.py"
        if not script.is_file():
            messagebox.showerror("错误", "找不到 tools/download_models.py")
            return

        def run():
            self._log("开始下载预训练模型（体积较大，请耐心等待）...")
            try:
                p = subprocess.run(
                    [self.py, str(script)],
                    cwd=str(ROOT),
                    env=self._env(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if p.stdout:
                    self._log(p.stdout[-2000:] if len(p.stdout) > 2000 else p.stdout)
                if p.stderr:
                    self._log(p.stderr[-1000:] if len(p.stderr) > 1000 else p.stderr)
                if p.returncode == 0:
                    self._log("下载完成。")
                    messagebox.showinfo("完成", "预训练模型下载完成（或已存在已跳过）。")
                else:
                    self._log(f"下载退出码 {p.returncode}")
                    messagebox.showwarning(
                        "未完全成功",
                        "下载可能失败。可改用「官方完整整合包」或配置网络后重试。",
                    )
            except Exception as e:
                self._log(f"下载异常: {e}")
                messagebox.showerror("下载失败", str(e))
            finally:
                self.refresh_status()

        threading.Thread(target=run, daemon=True).start()

    def open_weights(self) -> None:
        path = ROOT / "assets" / "weights"
        path.mkdir(parents=True, exist_ok=True)
        self._log(f"打开: {path}")
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def open_browser(self) -> None:
        webbrowser.open(WEB_URL)
        self._log(f"打开 {WEB_URL}")

    def stop_process(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self._log("已发送停止信号。若控制台仍在，可手动关闭黑色窗口。")
        else:
            self._log("没有由本启动器拉起的活动进程。")

    def open_readme(self) -> None:
        doc = ROOT / "docs" / "整合包使用说明.md"
        if doc.is_file():
            if sys.platform == "win32":
                os.startfile(str(doc))  # type: ignore[attr-defined]
            else:
                webbrowser.open(doc.as_uri())
        else:
            messagebox.showinfo("说明", "请阅读 docs/整合包使用说明.md")

    def open_hf_packs(self) -> None:
        webbrowser.open(HF_SPACE)
        self._log("已打开 HuggingFace 官方资源页（含 RVC1006Nvidia.7z 等完整整合包）")
        self._log(f"N 卡完整包: {HF_PACK_NVIDIA}")
        self._log(f"A/I 卡完整包: {HF_PACK_AMD}")

    def open_github(self) -> None:
        webbrowser.open(GITHUB)

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        # 不强制杀 WebUI，方便后台继续训练
        self.root.destroy()


def main() -> None:
    os.chdir(ROOT)
    app = LauncherApp()
    app.run()


if __name__ == "__main__":
    main()
