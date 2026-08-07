# -*- coding: utf-8 -*-
"""批量收编 + 验证第三方音色（可落地扩库用）。

用法::

    # 只生成 YAML（不下载验证）
    python scripts/batch_thirdparty_expand.py --add-only

    # 用 Runtime 的 torch 验证并写回（默认）
    L:\\My project\\Grok\\Runtime\\python.exe scripts/batch_thirdparty_expand.py --verify

    # 只验证已有 YAML 且缺 pth_struct_ok 的
    Runtime\\python.exe scripts/batch_thirdparty_expand.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
CNB = ROOT / "CNB-GIT-RELEASE"
TP_DIR = CNB / "catalog-src" / "thirdparty"
ENDPOINT = "https://hf-mirror.com"
UA = "Turing-Mirror/RVC-Fabric"

# 勿与官方 MyGO 五色撞车
MYGO_SKIP = {"anon", "tomori", "soyo", "taki", "rana"}

# ── 候选：id, name, series, tag, hf, pack|pth, kind ─────────────────────────
# kind: pack | files
CANDIDATES: list[dict[str, str]] = [
    # 调研首批差集
    {
        "id": "tp-atri",
        "name": "ATRI",
        "series": "ATRI",
        "tag": "女声",
        "hf": "AppleAndA/ATRI_RVC_Models",
        "pth": "ATRI_e500_s206500.pth",
        "kind": "files",
    },
    {
        "id": "tp-changli",
        "name": "长离",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/ChangliJP_e310_s31620_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-jinhsi",
        "name": "今汐",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/JinhsiJP_e200_s6400_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-shorekeeper",
        "name": "守岸人",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/ShorekeeperJP_e240_s8880_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-shiroko",
        "name": "砂狼白子",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "SunaokamiShiroko.zip",
        "kind": "pack",
    },
    {
        "id": "tp-hoshino",
        "name": "小鸟游星野",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "TakanashiHoshino.zip",
        "kind": "pack",
    },
    {
        "id": "tp-alice",
        "name": "天童爱丽丝",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "TendouAlice.zip",
        "kind": "pack",
    },
    {
        "id": "tp-arona",
        "name": "阿罗娜",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "Arona.zip",
        "kind": "pack",
    },
    {
        "id": "tp-yuuka",
        "name": "早濑优香",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "HayaseYuuka.zip",
        "kind": "pack",
    },
    {
        "id": "tp-hina-ba",
        "name": "空崎日奈",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "SorasakiHina.zip",
        "kind": "pack",
    },
    {
        "id": "tp-wakamo",
        "name": "狐坂若藻",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "KosakaWakamo.zip",
        "kind": "pack",
    },
    {
        "id": "tp-momoi",
        "name": "才羽桃井",
        "series": "蔚蓝档案",
        "tag": "女声",
        "hf": "LordDavis778/BlueArchivevoicemodels",
        "pack": "SaibaMomoi.zip",
        "kind": "pack",
    },
    {
        "id": "tp-kafka",
        "name": "卡芙卡",
        "series": "崩坏：星穹铁道",
        "tag": "女声",
        "hf": "tesune0316/KafkaRVC",
        "pack": "KafkaJP_Mangio_v2_e305.zip",
        "kind": "pack",
    },
    {
        "id": "tp-firefly",
        "name": "流萤",
        "series": "崩坏：星穹铁道",
        "tag": "女声",
        "hf": "kohaku12/RVC-MODELS",
        "pack": "Firefly _ Honkai_ Star Rail - Weights.gg Model.zip",
        "kind": "pack",
    },
    {
        "id": "tp-miyabi",
        "name": "星见雅",
        "series": "绝区零",
        "tag": "女声",
        "hf": "kohaku12/RVC-MODELS",
        "pack": "hoshimi miyabi (Zenless Zone Zero)JP - Weights Model.zip",
        "kind": "pack",
    },
    {
        "id": "tp-jane",
        "name": "简·杜",
        "series": "绝区零",
        "tag": "女声",
        "hf": "Coolwowsocoolwow/Jane_Doe_Zenless_Zone_Zero",
        "pack": "Jane_Doe_Zenless_Zone_Zero_v2.zip",
        "kind": "pack",
    },
    {
        "id": "tp-amiya",
        "name": "阿米娅",
        "series": "明日方舟",
        "tag": "女声",
        "hf": "zhuguang0dust/Arknights_RVC_Model",
        "pack": "RVC_JP_Amiya【bilibili：@逐光之尘_3Z】.zip",
        "kind": "pack",
    },
    {
        "id": "tp-uika",
        "name": "三角初华",
        "series": "Ave Mujica",
        "tag": "女声",
        "hf": "GanbareShamiko/Shamikos_RVC_Depot",
        "pack": "UikaMisumiE430.zip",
        "kind": "pack",
    },
    {
        "id": "tp-nina",
        "name": "井芹仁菜",
        "series": "Girls Band Cry",
        "tag": "女声",
        "hf": "GanbareShamiko/Shamikos_RVC_Depot",
        "pack": "NinaIseriE840.zip",
        "kind": "pack",
    },
    {
        "id": "tp-chihaya",
        "name": "如月千早",
        "series": "偶像大师",
        "tag": "女声",
        "hf": "ronao/IdolmasterRVCV2",
        "pth": "Chihaya_Kisaragi_300e_7200s.pth",
        "kind": "files",
    },
    # 原神第二批
    {
        "id": "tp-hutao",
        "name": "胡桃",
        "series": "原神",
        "tag": "女声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v1/hutao-jp 100 epochs 40k.zip",
        "kind": "pack",
    },
    {
        "id": "tp-venti",
        "name": "温迪",
        "series": "原神",
        "tag": "男声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v2/venti-jp 100 epochs 48k v2.zip",
        "kind": "pack",
    },
    {
        "id": "tp-paimon",
        "name": "派蒙",
        "series": "原神",
        "tag": "女声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v2/paimon-jp 105 epochs 48k v2.zip",
        "kind": "pack",
    },
    {
        "id": "tp-ayaka",
        "name": "神里绫华",
        "series": "原神",
        "tag": "女声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v2/ayaka-jp 101 epochs 48k v2.zip",
        "kind": "pack",
    },
    {
        "id": "tp-kazuha",
        "name": "枫原万叶",
        "series": "原神",
        "tag": "男声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v2/kazuha-jp 100 epochs 48k v2.zip",
        "kind": "pack",
    },
    {
        "id": "tp-neuvillette",
        "name": "那维莱特",
        "series": "原神",
        "tag": "男声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v2/neuvillette-jp 105 epochs 48k v2.zip",
        "kind": "pack",
    },
    {
        "id": "tp-yelan",
        "name": "夜兰",
        "series": "原神",
        "tag": "女声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v1/yelan-jp 100 epochs 40k.zip",
        "kind": "pack",
    },
    {
        "id": "tp-ganyu",
        "name": "甘雨",
        "series": "原神",
        "tag": "女声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v1/ganyu-jp 100 epochs 40k.zip",
        "kind": "pack",
    },
    {
        "id": "tp-yaemiko",
        "name": "八重神子",
        "series": "原神",
        "tag": "女声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v1/yaemiko-jp 100 epochs 40k.zip",
        "kind": "pack",
    },
    {
        "id": "tp-keqing",
        "name": "刻晴",
        "series": "原神",
        "tag": "女声",
        "hf": "ArkanDash/rvc-genshin-impact",
        "pack": "prezipped/v1/keqing-jp 100 epochs 40k.zip",
        "kind": "pack",
    },
    # 鸣潮第二批
    {
        "id": "tp-yinlin",
        "name": "吟霖",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/YinlinJP_e360_s7920_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-camellya",
        "name": "椿",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/CamellyaJP_e210_s6720_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-carlotta",
        "name": "珂莱塔",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/CarlottaJP_e250_s10000_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-zhezhi",
        "name": "折枝",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/ZhezhiJP_e310_s6820_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-encore",
        "name": "安可",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/EncoreJP_e480_s8640_RVCv@_RMVPE.zip",
        "kind": "pack",
    },
    {
        "id": "tp-rover-f",
        "name": "女漂泊者",
        "series": "鸣潮",
        "tag": "女声",
        "hf": "PGR-RVC/Wuthering_Waves_RVC_v2",
        "pack": "JP/FemaleRoverJP_e270_s10530_RVCv2_RMVPE.zip",
        "kind": "pack",
    },
    # 方舟
    {
        "id": "tp-eyjafjalla",
        "name": "艾雅法拉",
        "series": "明日方舟",
        "tag": "女声",
        "hf": "zhuguang0dust/Arknights_RVC_Model",
        "pack": "RVC_JP_Eyjafjalla【bilibili：@逐光之尘_3Z】.zip",
        "kind": "pack",
    },
    {
        "id": "tp-goldenglow",
        "name": "澄闪",
        "series": "明日方舟",
        "tag": "女声",
        "hf": "zhuguang0dust/Arknights_RVC_Model",
        "pack": "RVC_JP_Goldenglow【bilibili：@逐光之尘_3Z】.zip",
        "kind": "pack",
    },
    {
        "id": "tp-lappland",
        "name": "拉普兰德",
        "series": "明日方舟",
        "tag": "女声",
        "hf": "frem1234cats/Lappland-Arknights-RVC-Model",
        "pack": "lappland.zip",
        "kind": "pack",
    },
    # VOCALOID
    {
        "id": "tp-luka",
        "name": "巡音流歌",
        "series": "VOCALOID",
        "tag": "女声",
        "hf": "aple/MegurineLukaNativeRVC",
        "pack": "luka_native_ai.zip",
        "kind": "pack",
    },
]


def _http_json(url: str) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _tree(repo: str) -> list[dict]:
    data = _http_json(f"{ENDPOINT}/api/models/{repo}/tree/main?recursive=true")
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def resolve_exact_path(repo: str, want: str, tree: Optional[list] = None) -> str:
    """Exact match or fuzzy (case / space) against tree paths."""
    files = tree if tree is not None else _tree(repo)
    paths = [str(x.get("path") or "") for x in files]
    if want in paths:
        return want
    # basename match
    base = want.split("/")[-1].lower()
    hits = [p for p in paths if p.split("/")[-1].lower() == base]
    if len(hits) == 1:
        return hits[0]
    # substring
    hits = [p for p in paths if base in p.lower() or want.lower() in p.lower()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        # prefer zip/pth ending
        for p in hits:
            if p.lower().endswith((".zip", ".pth")):
                return p
        return hits[0]
    return want


def bangdream_extra() -> list[dict[str, str]]:
    """Wanlau/RVC_BanGDream：排除 MyGO 官方重叠角。"""
    repo = "Wanlau/RVC_BanGDream"
    try:
        tree = _tree(repo)
    except Exception as e:
        print(f"[warn] BanGDream tree 失败: {e}", file=sys.stderr)
        return []
    # 角色中文粗映射（常见）
    names = {
        "Kasumi": ("户山香澄", "BanG Dream!"),
        "Arisa": ("市谷有咲", "BanG Dream!"),
        "Tae": ("花园多惠", "BanG Dream!"),
        "Rimi": ("牛込里美", "BanG Dream!"),
        "Saaya": ("山吹沙绫", "BanG Dream!"),
        "Saya": ("山吹沙绫", "BanG Dream!"),
        "Yukina": ("凑友希那", "BanG Dream!"),
        "Sayo": ("冰川纱夜", "BanG Dream!"),
        "Lisa": ("今井丽莎", "BanG Dream!"),
        "Ako": ("宇田川亚子", "BanG Dream!"),
        "Rinko": ("白金燐子", "BanG Dream!"),
        "Kokoro": ("弦卷心", "BanG Dream!"),
        "Kaoru": ("濑田薰", "BanG Dream!"),
        "Hagumi": ("北泽育美", "BanG Dream!"),
        "Kanon": ("松原花音", "BanG Dream!"),
        "Misaki": ("奥泽美咲", "BanG Dream!"),
        "Aya": ("丸山彩", "BanG Dream!"),
        "MaruyamaAya": ("丸山彩", "BanG Dream!"),
        "Hina": ("冰川日菜", "BanG Dream!"),
        "Chisato": ("白鹭千圣", "BanG Dream!"),
        "Maya": ("大和麻弥", "BanG Dream!"),
        "Eve": ("若叶睦", "BanG Dream!"),  # 注意：若是 Ave 睦会标错，此仓 Eve 多为 Hello Happy
        "Ran": ("美竹兰", "BanG Dream!"),
        "Moca": ("青叶摩卡", "BanG Dream!"),
        "Himari": ("上原绯玛丽", "BanG Dream!"),
        "Tomoe": ("宇田川巴", "BanG Dream!"),
        "Tsugumi": ("濑田椿", "BanG Dream!"),
        "Rui": ("若宫伊织", "BanG Dream!"),
        "Lock": ("洛克", "BanG Dream!"),
        "Masking": ("增喜", "BanG Dream!"),
        "Masuki": ("PAREO/MASKING", "BanG Dream!"),
        "LAYER": ("LAYER", "BanG Dream!"),
        "CHU2": ("CHU2", "BanG Dream!"),
        "PAREO": ("PAREO", "BanG Dream!"),
        "Rokka": ("广町七深", "BanG Dream!"),
        "Mashiro": ("仓田真白", "BanG Dream!"),
        "Nanami": ("广町七深", "BanG Dream!"),
        "HiromachiNanami": ("广町七深", "BanG Dream!"),
        "Toko": ("二叶筑紫", "BanG Dream!"),
        "Tsukushi": ("二叶筑紫", "BanG Dream!"),
        "Rui2": ("若宫伊织", "BanG Dream!"),
        "CHU²": ("CHU2", "BanG Dream!"),
        "Reona": ("和奏瑞依", "BanG Dream!"),
        "Chiyu": ("通云千雪", "BanG Dream!"),
        "Rei": ("若叶睦", "BanG Dream!"),
    }
    out: list[dict[str, str]] = []
    seen_roles: set[str] = set()
    for x in tree:
        path = str(x.get("path") or "")
        if not path.lower().endswith(".pth"):
            continue
        # skip training junk
        name = path.split("/")[0] if "/" in path else Path(path).stem
        low = name.lower()
        # MyGO 官方重叠（词首精确匹配；子串匹配曾把 Kanon 误杀：k-a**non** ⊃ "anon"）
        if any(low.startswith(m) for m in MYGO_SKIP):
            continue
        # 只取「主」模型：跳过 chanter / mixte 变体以控数量
        if "chanter" in low or "mixte" in low:
            continue
        role_key = name.split("_")[0]
        if role_key in seen_roles:
            continue
        seen_roles.add(role_key)
        # map name
        display = role_key
        series = "BanG Dream!"
        for k, (cn, ser) in names.items():
            if k.lower() in low or low.startswith(k.lower()):
                display = cn
                series = ser
                break
        slug = role_key.lower().replace(" ", "")
        vid = f"tp-bd-{slug}"[:40]
        out.append(
            {
                "id": vid,
                "name": display,
                "series": series,
                "tag": "女声",
                "hf": repo,
                "pth": path,
                "kind": "files",
            }
        )
    return out


def umamusume_extra() -> list[dict[str, str]]:
    """赛马娘 TLME 热门角（voice_files）。"""
    repo = "TLME/RVC-Umamusume"
    want = [
        ("东海帝皇", "tp-teio"),
        ("特别周", "tp-specialweek"),
        ("无声铃鹿", "tp-suzuka"),
        ("小栗帽", "tp-oguri"),
        ("目白麦昆", "tp-mcqueen"),
        ("黄金船", "tp-goldship"),
        ("米浴", "tp-rice"),
        ("春乌拉拉", "tp-urara"),
    ]
    try:
        tree = _tree(repo)
    except Exception as e:
        print(f"[warn] 赛马娘 tree 失败: {e}", file=sys.stderr)
        return []
    paths = [str(x.get("path") or "") for x in tree if str(x.get("path") or "").endswith(".pth")]
    out = []
    for cn, vid in want:
        hits = [p for p in paths if cn in p and "G_" not in p and "D_" not in p]
        if not hits:
            print(f"[gap] 赛马娘无 pth: {cn}")
            continue
        # prefer v2
        hits.sort(key=lambda p: ("v2" not in p.lower(), len(p)))
        pth = hits[0]
        out.append(
            {
                "id": vid,
                "name": cn,
                "series": "赛马娘",
                "tag": "女声",
                "hf": repo,
                "pth": pth,
                "kind": "files",
            }
        )
    return out


def run_add(c: dict[str, str], py: str) -> int:
    yaml_path = TP_DIR / f"{c['id']}.yaml"
    if yaml_path.is_file():
        print(f"  skip add (exists) {c['id']}")
        return 0
    cmd = [
        py,
        str(ROOT / "scripts" / "add_thirdparty_voice.py"),
        "--hf",
        c["hf"],
        "--id",
        c["id"],
        "--name",
        c["name"],
        "--series",
        c.get("series") or "",
        "--tag",
        c.get("tag") or "二次元",
        "--yes",
        "--endpoint",
        ENDPOINT,
        "--cnb",
        str(CNB),
    ]
    # 封面：批量时 Bangumi 搜中文名；失败也不挡
    if c["kind"] == "pack":
        pack = resolve_exact_path(c["hf"], c["pack"])
        cmd += ["--pack-path", pack]
    else:
        pth = resolve_exact_path(c["hf"], c["pth"])
        cmd += ["--pth-path", pth]
    print(" ", " ".join(cmd[-12:]))
    r = subprocess.run(cmd, cwd=str(ROOT))
    return r.returncode


def needs_verify(yaml_path: Path) -> bool:
    if not yaml_path.is_file():
        return False
    text = yaml_path.read_text(encoding="utf-8")
    return "pth_struct_ok" not in text


def run_verify(yaml_path: Path, py: str) -> int:
    cmd = [
        py,
        str(ROOT / "scripts" / "verify_voice_pack.py"),
        "--yaml",
        str(yaml_path),
        "--write",
        "--endpoint",
        ENDPOINT,
    ]
    print(f"  verify {yaml_path.name}")
    r = subprocess.run(cmd, cwd=str(ROOT))
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--add-only", action="store_true")
    ap.add_argument("--verify", action="store_true", help="add 后验证")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument(
        "--python",
        default="",
        help="用于 verify 的 python（需 torch）；默认 Runtime\\python.exe",
    )
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 条新候选")
    args = ap.parse_args()

    py_sys = sys.executable
    py_rt = args.python or str(ROOT / "Runtime" / "python.exe")
    if not Path(py_rt).is_file():
        py_rt = py_sys

    cands = list(CANDIDATES)
    cands.extend(bangdream_extra())
    cands.extend(umamusume_extra())

    # 去重 id
    seen: set[str] = set()
    uniq: list[dict[str, str]] = []
    for c in cands:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        uniq.append(c)
    cands = uniq
    if args.limit > 0:
        cands = cands[: args.limit]

    print(f"候选 {len(cands)} 条；TP_DIR={TP_DIR}")

    if not args.verify_only:
        for c in cands:
            print(f"\n== add {c['id']} {c['name']} ==")
            try:
                rc = run_add(c, py_sys)
            except Exception as e:
                print(f"  FAIL add: {e}")
                continue
            if rc != 0:
                print(f"  add exit {rc}")

    if args.add_only:
        return 0

    if args.verify or args.verify_only:
        yamls = sorted(TP_DIR.glob("tp-*.yaml"))
        # 跳过 trump（应已删除）
        yamls = [y for y in yamls if y.stem != "tp-trump"]
        todo = [y for y in yamls if needs_verify(y)]
        print(f"\n待验证 {len(todo)} / 共 {len(yamls)}")
        fail = 0
        for y in todo:
            rc = run_verify(y, py_rt)
            if rc != 0:
                fail += 1
                print(f"  FAIL {y.name}")
        print(f"\n验证结束：失败 {fail}")
        return 1 if fail else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
