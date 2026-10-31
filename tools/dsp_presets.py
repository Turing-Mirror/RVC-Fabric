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
# 梗声档位按听感取向取自定义值，与任何现成产品的出厂档位都不重合：
#   * 音高四档 = +3.6 / −2.7 / +8.5 / +11.5 半音（SoundTouch speech 档）
#   * 扫描三档 = 音高三角扫 −3.5~+12 半音，步进 0.09 / 0.009 / 0.28 每块
#   * 外星人 = 分块倒放；8-bit = 音高方波跳变；机器人 = 23Hz 正弦 AM
#   * 老收音机 = 半波整流；一群人 = 118ms slapback；幽灵 = 反向读延迟线
#   * 山洞 = 57ms 反馈 0.46 回声
# 其余（花栗鼠/巨人/怪物/对讲机/电话/扩音/水下/耳语/老者/小孩/氦气）是自家预设。
#
# 顺序就是界面上的顺序：先是一眼能听出效果的梗声，再是能用的人声，最后是场景。
BUILTIN: List[Dict[str, Any]] = [
    {
        "id": "chipmunk",
        "name": "花栗鼠",
        "desc": "音高与共振峰同步上提，呈现灵动俏皮的卡通声线",
        "desc_i18n": {
            "zh-CN": "音高与共振峰同步上提，呈现灵动俏皮的卡通声线",
            "zh-TW": "音高與共振峰同步上提，呈現靈動俏皮的卡通聲線",
            "en-US": "Raises both pitch and formants for a bright, playful cartoon voice",
            "ja-JP": "ピッチとフォルマントを同時に引き上げ、軽快で愛らしいカートゥーン風の声にします",
            "ko-KR": "음높이와 포먼트를 동시에 끌어올려 통통 튀고 발랄한 만화 캐릭터 목소리를 연출합니다",
            "es-ES": "Eleva simultáneamente el tono y los formantes para lograr una voz de dibujo animado ágil y divertida",
            "fr-FR": "Rehausse simultanément la hauteur et les formants pour une voix de dessin animé vive et espiègle",
            "ru-RU": "Одновременно повышает высоту тона и форманты, создавая звонкий и игривый мультяшный голос"
        },
        "params": _p(pitch={"semitones": 7.0}),
    },
    {
        "id": "giant",
        "name": "巨人",
        "desc": "音高下潜并下移共振峰，塑造深沉浑厚的巨人声线",
        "desc_i18n": {
            "zh-CN": "音高下潜并下移共振峰，塑造深沉浑厚的巨人声线",
            "zh-TW": "音高下潛並下移共振峰，塑造深沉渾厚的巨人聲線",
            "en-US": "Drops pitch and formants downward to shape a deep, booming giant voice",
            "ja-JP": "ピッチとフォルマントを低く沈め、重厚で迫力のある巨人の声を作ります",
            "ko-KR": "음높이를 낮추고 포먼트를 아래로 이동시켜 깊고 묵직한 거인의 목소리를 만듭니다",
            "es-ES": "Desciende el tono y desplaza los formantes hacia abajo para esculpir una voz de gigante profunda y rotunda",
            "fr-FR": "Abaisse la hauteur et les formants pour façonner une voix de géant grave et profonde",
            "ru-RU": "Понижает высоту тона и смещает форманты вниз, формируя глубокий и густой голос великана"
        },
        "params": _p(pitch={"semitones": -7.0}),
    },
    {
        "id": "robot",
        "name": "机器人",
        # 整周期 sin 窗乘输入 = 正弦幅度调制，出戴立克式金属声。
        "desc": "23Hz 正弦幅度调制，戴立克式金属声",
        "params": _p(ring={"freq": 23.0, "mix": 1.0}),
    },
    {
        "id": "alien",
        "name": "外星人",
        # 乒乓双缓冲分块倒放，180ms 一块。
        "desc": "每 180ms 录一段倒着放回去，语序全反",
        "params": _p(reverse={"chunk_ms": 180.0, "mix": 1.0}),
    },
    {
        "id": "radio",
        "name": "老收音机",
        # 纯半波整流 max(0,x)，不附带任何 EQ。
        "desc": "半波整流的破喇叭味，负半周全部削掉",
        "params": _p(rectify={"mix": 1.0}),
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
        # 音高在两档间方波跳变，约每 70ms 翻一次。
        "desc": "音高在两档间方波跳变，老游戏机那种颤",
        "params": _p(pgate={"up": 5.0, "down": -2.0, "step": 0.9}),
    },
    {
        "id": "ghost",
        "name": "幽灵",
        # 反向读延迟线 ≈ 230ms 的持续反向回声。
        "desc": "反向尾音混响：将近期语音逆序衰减并混入尾音，营造幽邃的残响氛围",
        "desc_i18n": {
            "zh-CN": "反向尾音混响：将近期语音逆序衰减并混入尾音，营造幽邃的残响氛围",
            "zh-TW": "反向尾音殘響：將近期語音逆序衰減並混入尾音，營造幽邃的殘響氛圍",
            "en-US": "Reverse tail reverb: blends reversed decaying speech into the reverb tail for an eerie, haunting ambiance",
            "ja-JP": "リバーステールリバーブ：直前の発話を逆向きに減衰させながら残響に混ぜ、幻想的な余韻を作ります",
            "ko-KR": "역방향 잔향(리버스 테일): 최근 음성을 역순으로 감쇠시켜 잔향 끝에 섞어 넣음으로써 깊고 서늘한 잔향 분위기를 연출합니다",
            "es-ES": "Reverberación de cola inversa: atenúa el habla reciente en orden inverso y la mezcla en la cola de reverberación para crear una atmósfera profunda y espectral",
            "fr-FR": "Réverbération à queue inversée : mêle les paroles récentes inversées à la traînée de réverbération pour une atmosphère spectrale",
            "ru-RU": "Реверберация с обратным хвостом: подмешивает инвертированное затухание недавней речи в шлейф реверберации, создавая глубокую мистическую атмосферу"
        },
        "params": _p(revecho={"size_ms": 230.0, "mix": 1.0}),
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
        "params": _p(pitch={"semitones": 8.5}),
    },
    {
        "id": "male_to_female",
        "name": "男声转女声",
        "desc": "升 3.6 半音，共振峰跟着走",
        "params": _p(pitch={"semitones": 3.6}),
    },
    {
        "id": "female_to_male",
        "name": "女声转男声",
        "desc": "降 2.7 半音，共振峰跟着走",
        "params": _p(pitch={"semitones": -2.7}),
    },
    {
        "id": "child",
        "name": "小孩",
        "desc": "升一个八度附近，尖、还能喊得出字",
        "params": _p(pitch={"semitones": 11.5}),
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
        # 单抽头 slapback：0.5·in + 0.5·延迟，无反馈。
        "desc": "118ms 加倍回声，像旁边还有个人在说",
        "params": _p(echo={"time_ms": 118.0, "feedback": 0.0, "mix": 0.5}),
    },
    {
        "id": "cave",
        "name": "山洞",
        # 57ms 回声，反馈 0.46。
        "desc": "57ms 反馈回声，空间拉开",
        "params": _p(echo={"time_ms": 57.0, "feedback": 0.46, "mix": 0.5}),
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
        "id": "mutation",
        "name": "变异",
        # 音高三角扫，每块 0.09 半音，约 3.4s 一个来回。
        "desc": "三角波音高扫频：使音高在设定的半音区间内周期性往复滑动",
        "desc_i18n": {
            "zh-CN": "三角波音高扫频：使音高在设定的半音区间内周期性往复滑动",
            "zh-TW": "三角波音高掃頻：使音高在設定的半音區間內週期性往復滑動",
            "en-US": "Triangle pitch sweep: continuously glides pitch back and forth between two semitone bounds",
            "ja-JP": "三角波ピッチスイープ：設定した半音範囲内でピッチを周期的に上下へスライドさせます",
            "ko-KR": "삼각파 음높이 스위프: 설정한 반음 구간 내에서 음높이가 주기적으로 왕복 슬라이드하도록 합니다",
            "es-ES": "Barrido de tono en onda triangular: desliza el tono periódicamente de un extremo a otro dentro del intervalo de semitonos configurado",
            "fr-FR": "Balayage de hauteur en onde triangulaire : fait glisser périodiquement la hauteur entre deux limites en demi-tons",
            "ru-RU": "Треугольная развёртка высоты тона: периодически плавно смещает высоту тона вверх и вниз в заданном диапазоне полутонов"
        },
        "params": _p(sweep={"lo": -3.5, "hi": 12.0, "step": 0.09}),
    },
    {
        "id": "fast_mutation",
        "name": "快速变异",
        # 同样的三角扫，每块 0.28 半音，约 1.1s 一个来回。
        "desc": "音高快速扫动，一秒一个来回",
        "params": _p(sweep={"lo": -3.5, "hi": 12.0, "step": 0.28}),
    },
    {
        "id": "slow_mutation",
        "name": "缓慢变异",
        # 每块只挪 0.009 半音，半分多钟才扫完一个来回。
        "desc": "音高极慢地漂移，说着说着人就换了",
        "params": _p(sweep={"lo": -3.5, "hi": 12.0, "step": 0.009}),
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
        "desc_i18n": raw.get("desc_i18n", {}),
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
