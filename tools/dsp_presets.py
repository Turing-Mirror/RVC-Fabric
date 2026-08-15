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


# 内置预设。名字用描述性的通用词（Alien / Robot / Radio 这类谁都能用），
# 不打包任何别人的音频素材，也不宣称跟谁「兼容」。
#
# 顺序就是界面上的顺序：先是几个一眼能听出效果的梗声（流量入口），
# 再是正经能用的男女声互换，最后是场景类。
BUILTIN: List[Dict[str, Any]] = [
    {
        "id": "chipmunk",
        "name": "花栗鼠",
        "desc": "音高拉高，共振峰跟着走 —— 经典的尖细嗓",
        "params": _p(pitch={"semitones": 8.0}),
    },
    {
        "id": "giant",
        "name": "巨人",
        "desc": "音高压低，整个人变大一号",
        "params": _p(pitch={"semitones": -8.0}, reverb={"size": 0.6, "mix": 0.18}),
    },
    {
        "id": "robot",
        "name": "机器人",
        "desc": "环形调制把嗓音打成金属声",
        "params": _p(ring={"freq": 55.0, "mix": 0.85}, drive={"amount": 0.25}),
    },
    {
        "id": "alien",
        "name": "外星人",
        "desc": "高频环调加颤音，谁都听得出不是人",
        "params": _p(
            pitch={"semitones": 4.0},
            ring={"freq": 420.0, "mix": 0.6},
            vibrato={"rate": 7.0, "depth": 18.0},
        ),
    },
    {
        "id": "radio",
        "name": "老收音机",
        "desc": "限带加底噪，像从喇叭里传出来",
        "params": _p(
            radio={"low": 420.0, "high": 2800.0, "mix": 1.0, "noise": 0.12},
            drive={"amount": 0.3},
        ),
    },
    {
        "id": "walkie",
        "name": "对讲机",
        "desc": "更窄的带宽，更狠的过载",
        "params": _p(
            radio={"low": 500.0, "high": 2400.0, "mix": 1.0, "noise": 0.2},
            drive={"amount": 0.55},
            bitcrush={"bits": 10, "downsample": 1},
        ),
    },
    {
        "id": "retro8bit",
        "name": "8-bit",
        "desc": "位深压到底，掉进老游戏机里",
        "params": _p(bitcrush={"bits": 4, "downsample": 8}, drive={"amount": 0.2}),
    },
    {
        "id": "ghost",
        "name": "幽灵",
        "desc": "耳语加长混响，贴着耳朵说话",
        "params": _p(
            whisper={"amount": 0.75},
            pitch={"semitones": -3.0},
            reverb={"size": 0.85, "mix": 0.45},
        ),
    },
    {
        "id": "monster",
        "name": "怪物",
        "desc": "压得很低再过载，胸腔里出来的声音",
        "params": _p(
            pitch={"semitones": -12.0},
            formant={"shift": -3.0},
            drive={"amount": 0.5},
            reverb={"size": 0.5, "mix": 0.2},
        ),
    },
    {
        "id": "helium",
        "name": "氦气",
        "desc": "只搬共振峰不动音高 —— 吸了气球的那种细，但调子没变",
        "params": _p(formant={"shift": 7.0}),
    },
    {
        "id": "male_to_female",
        "name": "男声转女声",
        "desc": "音高与共振峰配平，升调但不发塑料",
        "params": _p(pitch={"semitones": 5.0}, formant={"shift": 2.5}),
    },
    {
        "id": "female_to_male",
        "name": "女声转男声",
        "desc": "降调同时把共振峰压下来，不闷",
        "params": _p(pitch={"semitones": -5.0}, formant={"shift": -2.5}),
    },
    {
        "id": "child",
        "name": "小孩",
        "desc": "音高与共振峰一起上抬，比单纯升调自然",
        "params": _p(pitch={"semitones": 6.0}, formant={"shift": 4.0}),
    },
    {
        "id": "elder",
        "name": "老者",
        "desc": "略降调 + 慢颤音，喉头有点抖",
        "params": _p(
            pitch={"semitones": -2.0},
            formant={"shift": -1.5},
            vibrato={"rate": 4.5, "depth": 9.0},
        ),
    },
    {
        "id": "whisper",
        "name": "耳语",
        "desc": "谐波打散、共振峰保留，气声但听得清",
        "params": _p(whisper={"amount": 0.9}),
    },
    {
        "id": "chorus_crowd",
        "name": "一群人",
        "desc": "三路失谐叠在一起，一个人说成一群",
        "params": _p(chorus={"depth": 0.85, "rate": 0.5, "voices": 3}),
    },
    {
        "id": "cave",
        "name": "山洞",
        "desc": "大混响加长回声",
        "params": _p(
            reverb={"size": 0.95, "mix": 0.5},
            echo={"time_ms": 320.0, "feedback": 0.45, "mix": 0.35},
        ),
    },
    {
        "id": "telephone",
        "name": "电话",
        "desc": "300–3400Hz 的老式话路",
        "params": _p(radio={"low": 300.0, "high": 3400.0, "mix": 1.0, "noise": 0.03}),
    },
    {
        "id": "megaphone",
        "name": "扩音喇叭",
        "desc": "限带加重过载加短回声",
        "params": _p(
            radio={"low": 600.0, "high": 3800.0, "mix": 0.9, "noise": 0.05},
            drive={"amount": 0.75},
            echo={"time_ms": 90.0, "feedback": 0.2, "mix": 0.2},
        ),
    },
    {
        "id": "underwater",
        "name": "水下",
        "desc": "砍掉高频再加慢颤音",
        "params": _p(
            radio={"low": 80.0, "high": 1100.0, "mix": 0.95, "noise": 0.0},
            vibrato={"rate": 2.5, "depth": 12.0},
            reverb={"size": 0.7, "mix": 0.3},
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
