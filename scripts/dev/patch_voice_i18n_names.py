# -*- coding: utf-8 -*-
"""Patch catalog YAML + online_catalog.json with multilingual voice names."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

NAMES: dict[str, dict[str, str]] = {
    "Anon": {
        "name": "千早爱音",
        "name_ja": "千早愛音",
        "name_en": "Chihaya Anon",
        "name_zh_Hant": "千早愛音",
        "series": "MyGO!!!!!",
    },
    "Tomori": {
        "name": "高松灯",
        "name_ja": "高松燈",
        "name_en": "Takamatsu Tomori",
        "name_zh_Hant": "高松燈",
        "series": "MyGO!!!!!",
    },
    "Rana": {
        "name": "要乐奈",
        "name_ja": "要楽奈",
        "name_en": "Kaname Raana",
        "name_zh_Hant": "要樂奈",
        "series": "MyGO!!!!!",
    },
    "Soyo": {
        "name": "长崎爽世",
        "name_ja": "長崎そよ",
        "name_en": "Nagasaki Soyo",
        "name_zh_Hant": "長崎爽世",
        "series": "MyGO!!!!!",
    },
    "Taki": {
        "name": "椎名立希",
        "name_ja": "椎名立希",
        "name_en": "Shiina Taki",
        "name_zh_Hant": "椎名立希",
        "series": "MyGO!!!!!",
    },
    "tp-nahida": {
        "name": "纳西妲",
        "name_ja": "ナヒーダ",
        "name_en": "Nahida",
        "name_zh_Hant": "納西妲",
        "series": "原神",
        "series_en": "Genshin Impact",
        "series_ja": "原神",
        "series_zh_Hant": "原神",
    },
    "tp-furina": {
        "name": "芙宁娜",
        "name_ja": "フリーナ",
        "name_en": "Furina",
        "name_zh_Hant": "芙寧娜",
        "series": "原神",
        "series_en": "Genshin Impact",
        "series_ja": "原神",
        "series_zh_Hant": "原神",
    },
    "tp-raiden": {
        "name": "雷电将军",
        "name_ja": "雷電将軍",
        "name_en": "Raiden Shogun",
        "name_zh_Hant": "雷電將軍",
        "series": "原神",
        "series_en": "Genshin Impact",
        "series_ja": "原神",
        "series_zh_Hant": "原神",
    },
    "tp-zhongli": {
        "name": "钟离",
        "name_ja": "鍾離",
        "name_en": "Zhongli",
        "name_zh_Hant": "鍾離",
        "series": "原神",
        "series_en": "Genshin Impact",
        "series_ja": "原神",
        "series_zh_Hant": "原神",
    },
    "tp-miku": {
        "name": "初音未来",
        "name_ja": "初音ミク",
        "name_en": "Hatsune Miku",
        "name_zh_Hant": "初音未來",
        "series": "VOCALOID",
    },
    "tp-miku-power": {
        "name": "初音未来（Power）",
        "name_ja": "初音ミク（Power）",
        "name_en": "Hatsune Miku (Power)",
        "name_zh_Hant": "初音未來（Power）",
        "series": "VOCALOID",
    },
    "tp-trump": {
        "name": "唐纳德·特朗普",
        "name_ja": "ドナルド・トランプ",
        "name_en": "Donald Trump",
        "name_zh_Hant": "唐納·川普",
    },
    "guanguan": {
        "name": "guanguanV1",
        "name_en": "guanguanV1",
        "series": "RVC原版",
        "series_en": "RVC Original",
        "series_ja": "RVCオリジナル",
        "series_zh_Hant": "RVC原版",
    },
    "keruan": {
        "name": "keruanV1",
        "name_en": "keruanV1",
        "series": "RVC原版",
        "series_en": "RVC Original",
        "series_ja": "RVCオリジナル",
        "series_zh_Hant": "RVC原版",
    },
    "kiki": {
        "name": "kikiV1",
        "name_en": "kikiV1",
        "series": "RVC原版",
        "series_en": "RVC Original",
        "series_ja": "RVCオリジナル",
        "series_zh_Hant": "RVC原版",
    },
    "youzhanv2-xi": {
        "name": "youzhanv2-xi",
        "name_en": "youzhanv2-xi",
        "series": "RVC原版",
        "series_en": "RVC Original",
        "series_ja": "RVCオリジナル",
        "series_zh_Hant": "RVC原版",
    },
}

EXTRA_KEYS = (
    "name_ja",
    "name_en",
    "name_zh_Hant",
    "series_ja",
    "series_en",
    "series_zh_Hant",
)


def patch_list(arr: list) -> int:
    n = 0
    for v in arr:
        if not isinstance(v, dict):
            continue
        vid = str(v.get("id") or "")
        if vid not in NAMES:
            continue
        for k, val in NAMES[vid].items():
            v[k] = val
        n += 1
    return n


def yaml_quote(val: str) -> str:
    if any(c in val for c in ":#{}[]'\"") or val != val.strip():
        return json.dumps(val, ensure_ascii=False)
    return val


def patch_yaml(path: Path, fields: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    skip = set(EXTRA_KEYS)
    lines = []
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):", line)
        if m and m.group(1) in skip:
            continue
        lines.append(line)
    text = "\n".join(lines)

    if "name" in fields:
        text = re.sub(
            r"^name:\s*.*$",
            f"name: {yaml_quote(fields['name'])}",
            text,
            count=1,
            flags=re.M,
        )
    if "series" in fields:
        if re.search(r"^series:\s*", text, re.M):
            text = re.sub(
                r"^series:\s*.*$",
                f"series: {yaml_quote(fields['series'])}",
                text,
                count=1,
                flags=re.M,
            )
        else:
            text = re.sub(
                r"^(name:\s*.*)$",
                rf"\1\nseries: {yaml_quote(fields['series'])}",
                text,
                count=1,
                flags=re.M,
            )

    extra_lines = []
    for k in EXTRA_KEYS:
        if k in fields:
            extra_lines.append(f"{k}: {yaml_quote(fields[k])}")
    if extra_lines:
        block = "\n".join(extra_lines)
        if re.search(r"^name:\s*", text, re.M):
            text = re.sub(
                r"^(name:\s*.*)$",
                rf"\1\n{block}",
                text,
                count=1,
                flags=re.M,
            )
        else:
            text = block + "\n" + text

    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def main() -> None:
    cat = ROOT / "configs" / "online_catalog.json"
    d = json.loads(cat.read_text(encoding="utf-8"))
    n1 = patch_list(d.get("voices") or [])
    n2 = patch_list(d.get("thirdparty_voices") or [])
    cat.write_text(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"online_catalog: voices={n1} thirdparty={n2}")

    base = ROOT / "CNB-GIT-RELEASE" / "catalog-src"
    for sub in ("voices", "thirdparty"):
        ddir = base / sub
        if not ddir.is_dir():
            print(f"skip missing {ddir}")
            continue
        for y in sorted(ddir.glob("*.yaml")):
            raw = y.read_text(encoding="utf-8")
            m = re.search(r"^id:\s*(\S+)", raw, re.M)
            if not m:
                continue
            vid = m.group(1).strip()
            if vid in NAMES:
                patch_yaml(y, NAMES[vid])
                print(f"yaml {sub}/{y.name}")
    print("done")


if __name__ == "__main__":
    main()
