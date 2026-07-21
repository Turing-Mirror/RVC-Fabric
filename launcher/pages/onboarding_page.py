# -*- coding: utf-8 -*-
"""First-run newbie onboarding wizard (split out of main_app).

Uses MainApp state (self.cfg, self.root, self.show_page, …) on the composed
instance. No behavior change vs the pre-split methods.
"""

from __future__ import annotations

import webbrowser

import tkinter as tk
from tkinter import messagebox

from launcher.config_store import save_config
from launcher.theme import (
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_META,
    TM_SURFACE,
    mono_font,
    sans_font,
    title_font,
    tracked,
)
from launcher.ui import GhostButton, PrimaryButton

# ---------------------------------------------------------------------------
# 运营占位：新手引导最后一步「加入 QQ 群」的入口链接。
# TODO(运营): 上线前把下面的 URL 换成你的【B 站视频链接】。
#   视频文案引导：一键三连 + 关注 UP 主后，私信「加群」即可获取 QQ 群号。
# 只需改这一处；引导页与「其他」页的重看入口都会用它。
# ---------------------------------------------------------------------------
COMMUNITY_LINK_URL = "https://www.bilibili.com/"  # ← 改成 B 站视频链接


class OnboardingMixin:
    def _maybe_show_onboarding(self) -> None:
        """Show the guide once on first launch; no-op if already completed."""
        try:
            if bool(self.cfg.get("onboarding_done", False)):
                return
        except Exception:
            return
        self.show_onboarding(first_run=True)

    def _mark_onboarding_done(self) -> None:
        self.cfg["onboarding_done"] = True
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def _open_community_link(self) -> None:
        """Open the community entry (placeholder → 换成 B 站视频链接)."""
        url = (COMMUNITY_LINK_URL or "").strip()
        if url:
            try:
                webbrowser.open(url)
                return
            except Exception:
                pass
        messagebox.showinfo(
            "获取 QQ 群",
            "请打开 UP 主视频：一键三连 + 关注后，私信「加群」即可获取 QQ 群号。",
        )

    def show_onboarding(self, first_run: bool = False) -> None:
        """Simple multi-step guide; ends with community + help call-to-action."""
        steps: list[tuple[str, str, list[str]]] = [
            (
                "WELCOME",
                "欢迎使用 Turing Mirror 变声器",
                [
                    "这是一个本地实时变声工具：对着麦克风说话，声音会被实时换成你选的音色。",
                    "常用于游戏 / QQ / Discord 语音，全部在本机运行，不上传你的声音。",
                    "跟着下面几步走，两分钟就能开黑。",
                ],
            ),
            (
                "STEP 1 · 接线",
                "先把声音接对（最重要）",
                [
                    "① 本软件「设置」→ 输入设备 = 你的真实麦克风",
                    "② 本软件「设置」→ 输出设备 = CABLE Input",
                    "③ 游戏 / QQ 里的麦克风 = CABLE Output",
                    "还没有虚拟声卡？先在启动器点「安装虚拟声卡」。",
                ],
            ),
            (
                "STEP 2 · 开声",
                "三步开始变声",
                [
                    "① 在「首页」或「模型」页选择一个音色",
                    "② 在「设置」页确认输入 / 输出设备",
                    "③ 点底栏「开启变声」（首次加载约 20～40 秒）",
                    "想边变声边听自己：勾选「监听自己」，监听设备选真实耳机。",
                ],
            ),
            (
                "STEP 3 · 调声",
                "调出更像的声音",
                [
                    "· 音高 Pitch：男变女常试 +8～+12，女变男试 −8～−12。",
                    "· 共鸣 Formant：微调音色的明暗与厚度。",
                    "· 底栏可随时快速调节，并会按当前音色自动记住。",
                    "· 更多细调（降噪 / 声音效果）在设置页，每项旁都有「?」说明。",
                ],
            ),
            (
                "DONE · 加入我们",
                "加群 & 看完整说明",
                [
                    "遇到问题、想要更多音色？欢迎加入玩家 QQ 群一起玩。",
                    "获取方式：点下方按钮打开视频 → 一键三连 + 关注 UP 主 →",
                    "再私信 UP 主「加群」，即可拿到最新 QQ 群号。",
                    "完整图文教程见「说明」页，随时可以回看。",
                ],
            ),
        ]

        win = tk.Toplevel(self.root)
        win.title("新手引导")
        win.configure(bg=TM_BG)
        win.geometry("560x470")
        win.minsize(480, 420)
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass

        state = {"i": 0}

        def _close_done():
            self._mark_onboarding_done()
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _close_done)

        eyebrow = tk.Label(win, text="", font=mono_font(9), bg=TM_BG, fg=TM_META)
        eyebrow.pack(anchor="w", padx=24, pady=(20, 0))
        title = tk.Label(
            win,
            text="",
            font=title_font(17, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            justify="left",
            anchor="w",
        )
        title.pack(anchor="w", padx=24, pady=(2, 8))

        body = tk.Frame(
            win, bg=TM_SURFACE, highlightthickness=1, highlightbackground=TM_HAIRLINE
        )
        body.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        body_inner = tk.Frame(body, bg=TM_SURFACE)
        body_inner.pack(fill="both", expand=True, padx=18, pady=16)

        footer = tk.Frame(win, bg=TM_BG)
        footer.pack(fill="x", padx=24, pady=(4, 16))

        def _next():
            if state["i"] < len(steps) - 1:
                state["i"] += 1
                render()

        def _prev():
            if state["i"] > 0:
                state["i"] -= 1
                render()

        def _open_help():
            _close_done()
            self.show_page("help")

        def render():
            i = state["i"]
            eb, ttl, lines = steps[i]
            eyebrow.configure(text=tracked(eb, gap=" "))
            title.configure(text=ttl)
            for w in body_inner.winfo_children():
                w.destroy()
            for ln in lines:
                tk.Label(
                    body_inner,
                    text=ln,
                    font=sans_font(11),
                    bg=TM_SURFACE,
                    fg=TM_INK,
                    justify="left",
                    anchor="w",
                    wraplength=470,
                ).pack(anchor="w", pady=4, fill="x")
            for w in footer.winfo_children():
                w.destroy()
            is_final = i == len(steps) - 1
            tk.Label(
                footer,
                text=f"第 {i + 1} / {len(steps)} 步",
                font=mono_font(9),
                bg=TM_BG,
                fg=TM_META,
            ).pack(side="left")
            GhostButton(
                footer,
                "完成" if is_final else "跳过引导",
                command=_close_done,
                padx=12,
                pady=8,
            ).pack(side="left", padx=(12, 0))
            if is_final:
                PrimaryButton(
                    footer,
                    "打开视频 · 三连关注得 QQ 群",
                    command=self._open_community_link,
                    padx=16,
                    pady=8,
                ).pack(side="right")
                GhostButton(
                    footer, "查看使用说明", command=_open_help, padx=14, pady=8
                ).pack(side="right", padx=(0, 8))
                GhostButton(
                    footer, "上一步", command=_prev, padx=14, pady=8
                ).pack(side="right", padx=(0, 8))
            else:
                PrimaryButton(
                    footer, "下一步", command=_next, padx=22, pady=8
                ).pack(side="right")
                if i > 0:
                    GhostButton(
                        footer, "上一步", command=_prev, padx=14, pady=8
                    ).pack(side="right", padx=(0, 8))

        render()
