# -*- coding: utf-8 -*-
"""In-app usage guide content (product-specific wording).

Synthesized from common RVC realtime pitfalls (cable routing, pitch, latency,
index) and this app's actual page/button names — not a paste of third-party tutorials.
"""

from __future__ import annotations

# Sections: (eyebrow, title, body markdown-ish plain text)
HELP_SECTIONS: list[tuple[str, str, str]] = [
    (
        "START HERE",
        "这是什么软件",
        "Turing Mirror 变声器是给游戏 / QQ / Discord 等场景用的**本地实时变声**工具。\n"
        "你对着麦克风说话，软件把声音换成所选「音色」，再通过虚拟声卡送进游戏或语音软件。\n"
        "\n"
        "日常只需要：\n"
        "1. 启动器（首次：快捷方式、虚拟声卡、环境）\n"
        "2. 变声器主界面：选音色 → 设设备 → 点「开启变声」\n"
        "\n"
        "训练自己的音色、翻唱歌曲属于进阶，在「其他」里打开训练/翻唱 WebUI，**不是每次开黑都要开**。",
    ),
    (
        "FIRST RUN",
        "第一次怎么开",
        "1. 解压到**尽量是英文路径**的文件夹（路径里少用生僻字，可减少运行库报错）。\n"
        "2. 双击 **启动器**（启动器.exe / 首次设置）。\n"
        "3. 点「发送快捷方式」——以后从桌面进主界面，一般没有黑框。\n"
        "4. 点「安装虚拟声卡」——装 **VB-Cable**（开黑必备）。\n"
        "5. 点「检测与部署」——确认日常变声需要的文件齐全（训练资源可选，不必全下）。\n"
        "6. 点「打开变声器」进入主界面。\n"
        "\n"
        "说明：第一次检测时若短暂弹出黑色命令行，多半是绿色 Runtime 在加载，**不是病毒**，窗口会自己关。",
    ),
    (
        "CABLE",
        "声卡怎么接（最重要）",
        "请记住三条线：\n"
        "\n"
        "【在本软件「设置」里】\n"
        "· **输入设备** = 你的真实麦克风（不要选 CABLE）\n"
        "· **输出设备** = **CABLE Input**（有的列表写成 VB-Audio Virtual Cable）\n"
        "· **监听设备**（可选）= 你的耳机 / 音箱，用来「变声时监听自己」\n"
        "\n"
        "【在游戏 / QQ / Discord 里】\n"
        "· 麦克风 / 输入 = **CABLE Output**\n"
        "  这样对面听到的是变声后的声音\n"
        "\n"
        "【Windows 系统】\n"
        "· 默认播放设备 = 耳机（不要设成 CABLE，否则容易啸叫或听不到系统声音）\n"
        "\n"
        "可用启动器「系统快捷 → 声音设备」，或设置页「声卡接线说明」对照。\n"
        "装完 VB-Cable 后若列表没有设备：点设置里的「重载设备列表」，或重启一次软件。",
    ),
    (
        "DAILY",
        "日常开黑五步",
        "1. **首页**或**模型**页选好音色（首页可左右切换；底栏也会显示当前音色）。\n"
        "2. **设置**里确认输入/输出设备（见上一节）。需要听自己时勾选「变声时监听自己」。\n"
        "3. 点底栏 **「开启变声」**。首次加载约 20～40 秒，右下角会显示「变声中」。\n"
        "4. 游戏麦克风选 CABLE Output，正常说话即可。\n"
        "5. 结束时再点一次（变为停止），或「其他 → 强制结束变声引擎」。\n"
        "\n"
        "底栏还有 **输出变声 / 原声旁路**：\n"
        "· 输出变声 = 正常换音色\n"
        "· 原声旁路 = 不换音色，只走线路（测麦、测接线）\n"
        "运行中可切换。音高 / 共鸣 / 阈值可在底栏快速拧，并会按当前音色记住。",
    ),
    (
        "PAGES",
        "每个页面做什么",
        "· **首页**：选音色、看当前音色、开启变声（主舞台）。\n"
        "· **模型**：导入 .pth、刷新列表、打开音色文件夹 User_Data/models。\n"
        "· **设置**：设备、变声参数、性能、声音效果、快捷键、加速后端。\n"
        "· **更新**：在线音色库、GUI 增量更新；有新版本时导航可能显示「更新·新」。完整大包请走 SharePoint / QQ 群。\n"
        "· **说明**：你现在看的使用教程。\n"
        "· **其他**：训练 WebUI、启动器、强制结束引擎、打开目录等。",
    ),
    (
        "VOICE",
        "音色从哪来",
        "· 把别人做好的 **.pth** 用「模型 → 导入模型」装进软件。\n"
        "· 或在「更新」页从在线音色库下载（zip 或直链）。\n"
        "· 可选的 **.index** 是特征检索文件，不是训练底模；没有也能变声，有时更像训练时的音色。\n"
        "· 每个音色可以单独记住音高、共鸣等（存在该音色目录的 config.json）。\n"
        "\n"
        "自己训练：用「其他 → 训练/翻唱 WebUI」。需要较干净的人声素材；训练完用导出的小模型做实时，"
        "不要把训练中途的大文件当成品。",
    ),
    (
        "SETTINGS",
        "设置项一句话（详细见设置页旁注释）",
        "【设备】\n"
        "· 加速后端：auto / cuda / dml / cpu——按你下载的发行包来，别混 N 卡与 A 卡 Runtime。\n"
        "· 设备类型：多数情况用 MME 最省事。\n"
        "· 输入 / 输出 / 监听：见「声卡怎么接」。\n"
        "· WASAPI 独占：容易抢设备，一般不要勾。\n"
        "\n"
        "【变声参数 · 运行中多半可热更新】\n"
        "· 响应阈值：越小越容易触发变声；环境吵可调高（更不敏感）。\n"
        "· 音高 Pitch：半音。男变女常试 +8～+12，女变男试 −8～−12，再微调。\n"
        "· 共鸣 Formant：音色明暗/腔体感，轻微拧即可。\n"
        "· Index Rate：有 .index 时才有意义；越高越「贴」训练特征，也可能更死板或更吃性能。\n"
        "· 响度因子：输出响度与原声包络的混合程度。\n"
        "· 音高算法：fcpe 较均衡；rmvpe 常更稳；卡顿可换轻量算法试。\n"
        "\n"
        "【性能 · 改后需重新开启变声】\n"
        "· 延迟预设：低延迟 / 均衡 / 稳定——一键设好采样长度等，不必逐项试。\n"
        "· 采样长度：越大越稳、延迟越高；卡顿可略加大。\n"
        "· 淡入淡出 / 额外推理时长：影响平滑度与延迟，先保持默认再动。\n"
        "· 输入/输出降噪：更干净但更吃显卡，小显卡可先关。\n"
        "\n"
        "【声音效果】\n"
        "· 在变声之后的噪声门 / 压缩 / EQ，默认关。开黑可试压缩 + 轻 EQ。",
    ),
    (
        "FAQ",
        "常见问题",
        "Q：对面听不到 / 没变声？\n"
        "A：检查游戏麦是否为 CABLE Output；本软件输出是否为 CABLE Input；是否已「开启变声」且模式为「输出变声」。\n"
        "\n"
        "Q：有变声但自己听不到？\n"
        "A：勾选「变声时监听自己」，监听设备选真实耳机，不要选 CABLE。\n"
        "\n"
        "Q：声音一卡一卡、延迟很大？\n"
        "A：略增大「采样长度」；关掉一项降噪；换 fcpe；关无关占麦软件；确认用的是对应显卡发行包。\n"
        "\n"
        "Q：音高飘、不像目标音色？\n"
        "A：先调 Pitch；有 index 时 Index Rate 试 0.3～0.75；换 rmvpe 再比。\n"
        "\n"
        "Q：停不干净、声卡一直被占？\n"
        "A：「其他 → 强制结束变声引擎」，再重开软件。\n"
        "\n"
        "Q：第一次很慢？\n"
        "A：正常，模型与 Runtime 冷启动需要时间。\n"
        "\n"
        "Q：完整大更新 / 换显卡包？\n"
        "A：用「更新」页的 SharePoint / QQ 群下全量包，解压到新目录使用；不要指望软件内覆盖 Runtime。\n"
        "\n"
        "Q：中文路径报错？\n"
        "A：尽量把整个软件放到英文路径再试。",
    ),
    (
        "HOTKEYS",
        "快捷键（可在设置里改）",
        "默认常见键位（以你「设置 → 快捷键」里显示的为准）：\n"
        "· 左右方向键：切换音色\n"
        "· F5：开启 / 停止变声\n"
        "· Ctrl+↑ / Ctrl+↓：音高加减\n"
        "· 模式切换、全局快捷键等见设置页说明\n"
        "· F1：打开快捷键说明（若已启用）\n"
        "\n"
        "游戏里也要用快捷键时，在设置中打开**全局快捷键**，并尽量用带 Ctrl 的组合键，减少误触。",
    ),
    (
        "SAFETY",
        "使用注意",
        "· 请遵守游戏与平台规则，勿用于诈骗或骚扰。\n"
        "· 本软件在本地运行，变声质量取决于音色模型与设备性能。\n"
        "· 完整包与模型请从你信任的渠道获取（官方分发 / 你配置的 SharePoint 与群）。",
    ),
]


def strip_md_emphasis(text: str) -> str:
    """Remove lightweight Markdown markers used in help bodies (**bold**).

    In-app display either strips these or renders bold; never show raw asterisks.
    """
    import re

    if not text:
        return ""
    # **bold** → bold (content only)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    # leftover single ** pairs / orphan *
    out = out.replace("**", "")
    return out


def iter_md_segments(text: str) -> list[tuple[str, str]]:
    """Split into (kind, text) where kind is 'normal' | 'bold' for **...** only."""
    import re

    if not text:
        return []
    parts: list[tuple[str, str]] = []
    pos = 0
    for m in re.finditer(r"\*\*(.+?)\*\*", text, flags=re.DOTALL):
        if m.start() > pos:
            parts.append(("normal", text[pos : m.start()]))
        parts.append(("bold", m.group(1)))
        pos = m.end()
    if pos < len(text):
        parts.append(("normal", text[pos:]))
    return parts or [("normal", text)]


def help_plain_text() -> str:
    """Flatten for dialog / copy (no raw markdown asterisks)."""
    parts: list[str] = ["Turing Mirror 变声器 · 使用说明", ""]
    for _eye, title, body in HELP_SECTIONS:
        parts.append(f"【{title}】")
        parts.append(strip_md_emphasis(body))
        parts.append("")
    return "\n".join(parts).strip() + "\n"


# Tips for settings page: key -> short tip (shown under control + HoverTip)
SETTING_TIPS: dict[str, str] = {
    "accel": (
        "按发行包选加速方式：N 卡包用 cuda，A/I 卡包用 dml。"
        "auto 会自动选。改完需停变声再开，勿混用不同显卡的 Runtime。"
    ),
    "hostapi": (
        "音频驱动类型。Windows 上多数人用 MME 最省事；"
        "若设备异常可换其他类型后点「重载设备列表」。"
    ),
    "input": "真实麦克风。不要选 CABLE Output/Input。",
    "output": (
        "变声结果送出的设备。开黑请选 CABLE Input，"
        "游戏里再把麦克风设为 CABLE Output。"
    ),
    "monitor_on": (
        "一边变声一边用耳机听自己。输出仍给 CABLE；"
        "监听请选真实耳机，不要选 CABLE。"
    ),
    "monitor": "仅用于「听自己」的耳机/音箱，不是给对面听的线路。",
    "wasapi": "独占模式可能抢走别的软件声卡。一般保持不勾选。",
    "sr_type": (
        "sr_model=按模型采样率；sr_device=按声卡采样率。"
        "多数情况保持默认即可。"
    ),
    "threhold": (
        "多小声才开始变声。数值越低（如 -60）越灵敏；"
        "环境杂音多时可调高，减少乱触发。"
    ),
    "pitch": (
        "音高偏移（半音）。男声变女声常试 +8～+12；"
        "女声变男声试 −8～−12。可运行中调节，并按音色保存。"
    ),
    "formant": (
        "共鸣/音色明暗。略调可改变「腔体」感；"
        "拧太狠会不自然，建议小幅调整。"
    ),
    "index_rate": (
        "特征检索强度。需要已绑定 .index。"
        "0=几乎不用索引；升高更贴训练音色，也可能更耗性能或发闷。无 index 时自动当 0。"
    ),
    "rms": (
        "响度混合：越靠近 1 越跟随你原来的音量起伏；"
        "越靠近 0 输出更「平」。按听感微调。"
    ),
    "f0": (
        "音高检测算法。fcpe 较均衡；rmvpe 常更稳；"
        "卡顿可试更轻的算法。运行中可切换。"
    ),
    "function": (
        "输出变声=正常换音色；输入监听=原声旁路，只测麦和接线。"
    ),
    "index": (
        "可选的 .index 检索库，绑定到当前音色。"
        "改路径后需重新「开启变声」。不是训练用的底模。"
    ),
    "block": (
        "每次处理的音频块长度（秒）。越大越稳、延迟越高；"
        "卡顿可略加大。也可用上方「延迟预设」一键设置。改后需重新开启变声。"
    ),
    "crossfade": (
        "块与块之间的交叉淡化，减少爆音。"
        "过小可能「啪啪」响，过大略增延迟。改后需重开变声。"
    ),
    "extra": (
        "额外送进模型的上下文长度，影响稳定度与延迟。"
        "默认一般够用。改后需重开变声。"
    ),
    "n_cpu": (
        "部分算法（如 harvest）使用的 CPU 进程数。"
        "仅当音高算法用到时有效；不是越大越好。"
    ),
    "i_nr": "进模型前降噪。更干净，但更吃性能；小显卡可关。",
    "o_nr": "变声结果后再降噪。同样更吃性能，可与输入降噪二选一试。",
    "use_pv": "相位声码器，部分场景更平滑，也可能略改音色。按听感开关。",
    "fx_en": "总开关：变声之后的噪声门/压缩/EQ。默认关，不影响原听感。",
    "fx_gate": "小声时压低底噪。门限过低可能吃字，过高仍有噪音。",
    "fx_comp": "压动态，让小声更大、大声不爆，开黑时声音更稳。",
    "fx_eq": "分段均衡。可用预设「人声前倾/温暖」等，再微调各频段。",
    "fx_out": "效果链最后的音量加减。过大易破音。",
}
