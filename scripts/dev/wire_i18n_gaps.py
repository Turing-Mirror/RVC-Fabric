# -*- coding: utf-8 -*-
"""Wire shell hardcodes to i18n keys. Adds missing keys to all locale packs (zh text).

Does NOT translate. Run after scan_i18n_gaps.py.

  python scripts/dev/wire_i18n_gaps.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "app" / "i18n" / "locales"
CODES = [
    "zh-CN",
    "zh-TW",
    "en-US",
    "ja-JP",
    "ko-KR",
    "es-ES",
    "fr-FR",
    "ru-RU",
]


def key_of(zh: str) -> str:
    return "s." + hashlib.sha1(zh.encode("utf-8")).hexdigest()[:10]


def set_s_key(pack: dict, k: str, v: str) -> None:
    s = pack.setdefault("s", {})
    if not isinstance(s, dict):
        pack["s"] = {}
        s = pack["s"]
    # k is "s.xxx" or just hash
    name = k[2:] if k.startswith("s.") else k
    s[name] = v


def load_packs() -> dict[str, dict]:
    out = {}
    for c in CODES:
        p = LOCALES / f"{c}.json"
        out[c] = json.loads(p.read_text(encoding="utf-8"))
    return out


def save_packs(packs: dict[str, dict]) -> None:
    for c, data in packs.items():
        path = LOCALES / f"{c}.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def reverse_map(zh_pack: dict) -> dict[str, str]:
    rev: dict[str, str] = {}

    def walk(o, prefix=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(o, str) and o not in rev:
            rev[o] = prefix

    walk(zh_pack)
    return rev


# ---------------------------------------------------------------------------
# New strings (normalized template form used as zh-CN value)
# ---------------------------------------------------------------------------
NEW_STRINGS: list[tuple[str, str]] = [
    # key_hint, zh value with {v0} placeholders
    ("upd.alreadyLatest", "已是最新版本 {v0}（{v1} 检查）"),
    ("upd.found", "发现新版本 {v0}，当前 {v1}"),
    ("upd.downloadingApp", "正在下载程序更新 {v0}…"),
    ("upd.downloadingUi", "正在下载界面更新 {v0}…"),
    ("upd.doneRestart", "已更新至 {v0}，重启程序后生效"),
    ("upd.checkFail", "检查更新失败：{v0}"),
    ("upd.fail", "更新失败：{v0}"),
    ("upd.nudgeHint", "更新会在后台下载，不影响变声使用；下载完成后重启软件即可生效。"),
    ("upd.needMin", "当前版本 {v0}，需先更新至 {v1} 才能继续"),
    ("upd.currentVer", "当前版本 {v0}。{v1}"),
    ("time.mmss", "{v0} 分 {v1} 秒"),
    ("time.hhmm", "{v0} 小时 {v1} 分"),
    ("sep.doneFiles", "完成，输出 {v0} 个文件"),
    ("store.downloading", "下载中"),
    ("store.confirmDelete", "确定删除已下载的音色文件吗？\n\n{v0}\n\n删除后如需使用需重新下载。"),
    ("train.done", "训练完成：{v0}"),
    ("tts.needEngine", "引擎资源未补全（缺 {v0}）。请先在主界面完成引擎资源下载。"),
    ("tts.doneFiles", "完成 {v0} 个文件"),
    ("tts.doneFilesTo", "完成 {v0} 个文件 → {v1}"),
    ("tts.synthDone", "合成完成：{v0}"),
    ("more.saveFail", "保存失败：{v0}"),
    ("more.startFail", "启动失败：{v0}"),
    ("more.donePath", "{v0}完成：{v1}{v2}"),
    ("more.fail", "{v0}失败：{v1}"),
    ("more.diagDone", "生成诊断包完成：{v0}{v1}"),
    ("more.diagFail", "生成诊断包失败：{v0}"),
    ("help.devVirtualAudio", "虚拟音频"),
    ("help.devWaveMix", "波输出混合"),
]

# Also register many rust error templates that match existing pack values —
# resolved at apply time via reverse map or NEW.


def ensure_keys(packs: dict[str, dict], pairs: list[tuple[str, str]]) -> dict[str, str]:
    """pairs: (semantic_or_hash_key, zh). Returns map semantic -> s.xxx full key."""
    mapping: dict[str, str] = {}
    rev = reverse_map(packs["zh-CN"])
    for sem, zh in pairs:
        if zh in rev:
            mapping[sem] = rev[zh]
            continue
        k = key_of(zh)
        for pack in packs.values():
            set_s_key(pack, k, zh)
        mapping[sem] = k
        # update rev for duplicates in same run
        rev[zh] = k
    return mapping


def main() -> None:
    packs = load_packs()
    m = ensure_keys(packs, NEW_STRINGS)
    save_packs(packs)
    # write mapping for apply step
    out = ROOT / "docs" / "i18n" / "gaps" / "wire-key-map.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("keys", len(m))
    for k, v in m.items():
        print(f"  {k} -> {v}")


if __name__ == "__main__":
    main()
