# -*- coding: utf-8 -*-
"""内置 DSP 变声预设，以及用户预设的读写。

预设就是一份 `{效果器: {参数: 值}}`，几百字节的 JSON —— 对比 55MB 的 .pth，
广场上点一下就下完了。

内置的放 `configs/dsp_presets/`，用户存的放 `User_Data/dsp_presets/`，
同名时用户的优先（这样用户可以覆盖内置预设而不必改安装目录）。

纯 stdlib，不碰 numpy —— 冻结的主程序壳要拿它列预设画界面。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
BUILTIN_DIR = ROOT / "configs" / "dsp_presets"
USER_DIR = ROOT / "User_Data" / "dsp_presets"

# 预设 id 只允许这些字符：要当文件名用，也要当配置里的键用。
_ID_RE = re.compile(r"^[a-z0-9_]{1,48}$")


def _p(**kw: Any) -> Dict[str, Dict[str, Any]]:
    """把 effect=dict 的关键字参数收成预设 params。"""
    return {k: v for k, v in kw.items()}


# 内置预设。名字用描述性的通用词，不宣称跟谁兼容。
#
# 变调核是 SoundTouch speech 档（共振峰跟着走，和 Clownfish 同一根滑条）。
# 所以：
#   * 花栗鼠 / 巨人 / 小孩 / 氦气 / 男女 = 只动 pitch
#   * 独立 formant 仍留给编辑器，内置档不对着 Clownfish 再叠一层
# 环调 mix 超过 ~0.4 人话就听不清，机器人 / 外星人必须留 intelligibility。
#
# 顺序就是界面上的顺序：先是一眼能听出效果的梗声，再是能用的人声，最后是场景。
BUILTIN: List[Dict[str, Any]] = [
    {
        "id": "chipmunk",
        "name": "花栗鼠",
        "desc": "升调，共振峰跟着走 —— 尖细、能说话",
        "params": _p(pitch={"semitones": 7.0}),
    },
    {
        "id": "giant",
        "name": "巨人",
        "desc": "降调，整个人变大一号，不加混响",
        "params": _p(pitch={"semitones": -7.0}),
    },
    {
        "id": "robot",
        "name": "机器人",
        "desc": "包络去推脉冲载波，金属、还能说话",
        "params": _p(
            robot={"amount": 0.46, "freq": 88.0},
            ring={"freq": 30.0, "mix": 0.1},
            radio={"low": 220.0, "high": 4000.0, "mix": 0.22, "noise": 0.0},
        ),
    },
    {
        "id": "alien",
        "name": "外星人",
        "desc": "略升调，音量和音高一起发颤",
        "params": _p(
            pitch={"semitones": 3.0},
            tremolo={"rate": 7.0, "depth": 0.32},
            ring={"freq": 90.0, "mix": 0.12},
            # 50 音分 = 半个半音。原来写 6，那是 5 音分不到的摆动，人耳听不见，
            # 于是这个预设听着只剩上面那 3 个半音的死升调 —— 用户报的就是这个。
            vibrato={"rate": 6.0, "depth": 50.0},
        ),
    },
    {
        "id": "radio",
        "name": "老收音机",
        "desc": "窄带、底噪、一点点音量晃，像喇叭里传出来",
        "params": _p(
            radio={"low": 400.0, "high": 2600.0, "mix": 1.0, "noise": 0.06},
            # 0.08 只摆 0.72dB，在响度可闻阈（约 1dB）下面 —— 何况前面还压着
            # 限带和过载，那点晃动全被盖掉了。0.12 是 1.11dB：还是「一点点」，
            # 但真的在那儿。
            tremolo={"rate": 7.5, "depth": 0.12},
            drive={"amount": 0.14},
        ),
    },
    {
        "id": "walkie",
        "name": "对讲机",
        "desc": "更窄的带宽，沙沙声和过载都在，人话还在",
        "params": _p(
            radio={"low": 480.0, "high": 2300.0, "mix": 1.0, "noise": 0.13},
            drive={"amount": 0.38},
        ),
    },
    {
        "id": "retro8bit",
        "name": "8-bit",
        "desc": "老游戏机那种碎，不是坏掉的喇叭",
        "params": _p(
            bitcrush={"bits": 6, "downsample": 5},
            radio={"low": 280.0, "high": 3600.0, "mix": 0.32, "noise": 0.0},
            drive={"amount": 0.1},
        ),
    },
    {
        "id": "ghost",
        "name": "幽灵",
        "desc": "半气声、略沉，空间拉开但不糊成一团",
        "params": _p(
            whisper={"amount": 0.42},
            pitch={"semitones": -2.0},
            reverb={"size": 0.72, "mix": 0.26},
        ),
    },
    {
        "id": "monster",
        "name": "怪物",
        "desc": "压低再加一点胸腔过载，还能吼得出字",
        "params": _p(
            pitch={"semitones": -8.0},
            formant={"shift": -2.0},
            drive={"amount": 0.32},
            reverb={"size": 0.32, "mix": 0.12},
        ),
    },
    {
        "id": "helium",
        "name": "氦气",
        "desc": "升得比花栗鼠更高，尖、还能喊得出字",
        "params": _p(pitch={"semitones": 8.0}),
    },
    {
        "id": "male_to_female",
        "name": "男声转女声",
        "desc": "升 4.5 半音，共振峰跟着走",
        "params": _p(pitch={"semitones": 4.5}),
    },
    {
        "id": "female_to_male",
        "name": "女声转男声",
        "desc": "降 4.5 半音，共振峰跟着走",
        "params": _p(pitch={"semitones": -4.5}),
    },
    {
        "id": "child",
        "name": "小孩",
        "desc": "升一个八度，尖、还能喊得出字",
        "params": _p(pitch={"semitones": 12.0}),
    },
    {
        "id": "elder",
        "name": "老者",
        "desc": "略沉、喉头轻抖，亮度还在",
        "params": _p(
            pitch={"semitones": -1.5},
            formant={"shift": 1.0},
            # 「喉头轻抖」要听得出才算数。原来的 6.5 只有 3 音分，等于没写。
            vibrato={"rate": 4.0, "depth": 20.0},
        ),
    },
    {
        "id": "whisper",
        "name": "耳语",
        "desc": "气声，字还能听清",
        "params": _p(whisper={"amount": 0.56}),
    },
    {
        "id": "chorus_crowd",
        "name": "一群人",
        "desc": "自己叠一路，像旁边还有个人在说",
        "params": _p(chorus={"depth": 0.48, "rate": 0.28, "voices": 2}),
    },
    {
        "id": "cave",
        "name": "山洞",
        "desc": "空间拉开，回声不盖住人声",
        "params": _p(
            reverb={"size": 0.8, "mix": 0.28},
            echo={"time_ms": 250.0, "feedback": 0.24, "mix": 0.16},
        ),
    },
    {
        "id": "telephone",
        "name": "电话",
        "desc": "300–3400Hz 老式话路",
        "params": _p(
            radio={"low": 300.0, "high": 3400.0, "mix": 1.0, "noise": 0.025},
            drive={"amount": 0.08},
        ),
    },
    {
        "id": "megaphone",
        "name": "扩音喇叭",
        "desc": "限带、过载、短反射，像手里那只喇叭",
        "params": _p(
            radio={"low": 550.0, "high": 3500.0, "mix": 0.92, "noise": 0.035},
            drive={"amount": 0.46},
            echo={"time_ms": 72.0, "feedback": 0.12, "mix": 0.14},
        ),
    },
    {
        "id": "underwater",
        "name": "水下",
        "desc": "高频闷掉，慢慢晃，远处一点空间",
        "params": _p(
            radio={"low": 70.0, "high": 1000.0, "mix": 0.88, "noise": 0.0},
            # 慢而深地晃。转速只有 1.6Hz，深度不给够就完全察觉不到（原来的 7
            # 折合 1.5 音分）。
            vibrato={"rate": 1.6, "depth": 35.0},
            reverb={"size": 0.62, "mix": 0.2},
        ),
    },
    {
        "id": "fast_mutation",
        "name": "快速变异",
        "desc": "升调加共振峰上移，音高快速抖动 —— 换个人，不是换个怪物",
        "params": _p(
            # 升 5 个半音而不是 7：7 往上就开始像花栗鼠了。5 度左右还留着
            # 说话的质感，是「另一个人」而不是「一只动物」。
            pitch={"semitones": 5.0},
            # 共振峰再往上推一点。只动音高不动共振峰，听感是同一个人捏着嗓子；
            # 共振峰跟上去，声道才像真的变短了，人才换掉。
            formant={"shift": 2.5},
            # 快而浅的音高抖动，是这个预设名字的来处。深度给 17 音分：
            # 再深就成了唱歌的颤音，浅到听不出又白加。
            #
            # 换算式修好之前这里写的是 14，按当时那个漏了 rate 的系数算出来正好
            # 也是 17 音分。改成 17 是为了让这个预设**听感不变** —— 它是唯一一个
            # 之前就抖得出来的，用户拿它当参照。
            vibrato={"rate": 9.5, "depth": 17.0},
            # 一点点过载补回变调损失的密度，不到能听出失真的程度。
            drive={"amount": 0.1},
        ),
    },
]

BUILTIN_IDS = frozenset(p["id"] for p in BUILTIN)


def is_valid_id(pid: str) -> bool:
    return bool(_ID_RE.match(str(pid or "")))


def _sanitize(raw: Dict[str, Any], pid: str, source: str) -> Optional[Dict[str, Any]]:
    """把一份来路不明的预设收成规整形状，收不了就返回 None。

    预设可以手写、可以从广场下载，所以参数一律过 dsp_voice.clamp_params 钳一遍。
    """
    if not isinstance(raw, dict):
        return None
    params = raw.get("params")
    if not isinstance(params, dict):
        return None
    try:
        from tools.dsp_voice import EFFECT_SPECS, clamp_params
    except Exception:
        return None
    clean: Dict[str, Dict[str, Any]] = {}
    for effect, values in params.items():
        if effect not in EFFECT_SPECS or not isinstance(values, dict):
            continue
        got = clamp_params(effect, values)
        # 跟默认值一样的就不存，预设文件干净些
        if got != EFFECT_SPECS[effect]["params"]:
            clean[effect] = got
    return {
        "id": pid,
        "name": str(raw.get("name") or pid),
        "desc": str(raw.get("desc") or ""),
        "params": clean,
        "source": source,
    }


def _read_dir(d: Path, source: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        pid = f.stem
        if not is_valid_id(pid):
            continue
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        got = _sanitize(raw, pid, source)
        if got:
            out[pid] = got
    return out


def list_presets(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """内置 + 广场下载 + 用户自存，同 id 时用户的覆盖内置。"""
    base = root or ROOT
    out: Dict[str, Dict[str, Any]] = {}
    for item in BUILTIN:
        got = _sanitize(item, item["id"], "builtin")
        if got:
            out[item["id"]] = got
    out.update(_read_dir(base / "configs" / "dsp_presets", "builtin"))
    out.update(_read_dir(base / "User_Data" / "dsp_presets", "user"))
    # 内置的按声明顺序在前，用户的按 id 排在后面
    order = {p["id"]: i for i, p in enumerate(BUILTIN)}
    return sorted(out.values(), key=lambda p: (order.get(p["id"], 10_000), p["id"]))


def get_preset(pid: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    for p in list_presets(root):
        if p["id"] == pid:
            return p
    return None


def save_user_preset(
    pid: str, name: str, params: Dict[str, Any], root: Optional[Path] = None
) -> Dict[str, Any]:
    """存一份用户预设。返回规整后的预设，id 非法或参数不合法就抛 ValueError。"""
    if not is_valid_id(pid):
        raise ValueError(f"预设 id 只能是小写字母、数字和下划线：{pid!r}")
    got = _sanitize({"name": name, "params": params}, pid, "user")
    if got is None:
        raise ValueError("预设参数不合法")
    d = (root or ROOT) / "User_Data" / "dsp_presets"
    d.mkdir(parents=True, exist_ok=True)
    body = {"name": got["name"], "desc": got["desc"], "params": got["params"]}
    (d / f"{pid}.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return got


def delete_user_preset(pid: str, root: Optional[Path] = None) -> bool:
    """删用户预设。内置的删不掉（但可以被同 id 的用户预设盖住）。"""
    if not is_valid_id(pid):
        return False
    f = (root or ROOT) / "User_Data" / "dsp_presets" / f"{pid}.json"
    if not f.is_file():
        return False
    f.unlink()
    return True
