# -*- coding: utf-8 -*-
"""消息码表的守卫。

这张表是「worker 说的话」和「界面显示的话」之间唯一的契约，两边各在一个
语言里（Python / Rust），编译器管不着。所以规则写成测试。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import msg_codes as mc  # noqa: E402

LOCALES = ["zh-CN", "zh-TW", "en-US", "ja-JP", "ko-KR", "ru-RU", "es-ES", "fr-FR"]
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _pack(loc: str) -> dict:
    p = ROOT / "app" / "i18n" / "locales" / f"{loc}.json"
    return json.loads(p.read_text(encoding="utf-8"))["msg"]


def _lookup(pack: dict, code: str):
    group, key = code.split(".", 1)
    return pack.get(group, {}).get(key)


def test_every_code_exists_in_every_locale():
    # 缺一条，那个语言的用户就会在面板上看到中文兜底。
    for loc in LOCALES:
        pack = _pack(loc)
        missing = [c for c in mc._FALLBACK_ZH if _lookup(pack, c) is None]
        assert not missing, f"{loc} 少了：{missing}"


def test_placeholders_match_across_locales():
    # 译文漏掉一个 {name}，用户看到的就是一句缺了主语的话；多一个没人填的
    # 占位符，屏幕上会直接出现 "{path}" 这种东西。
    for code, zh in mc._FALLBACK_ZH.items():
        want = set(PLACEHOLDER.findall(zh))
        for loc in LOCALES:
            got = set(PLACEHOLDER.findall(_lookup(_pack(loc), code)))
            assert got == want, f"{loc} {code}: 期望 {want}，实际 {got}"


def test_zh_cn_pack_matches_the_python_fallback():
    # 两份中文必须一字不差 —— 否则「壳翻译过的」和「worker 兜底的」会是
    # 两句话，用户切个语言再切回来，同一件事的措辞就变了。
    pack = _pack("zh-CN")
    for code, zh in mc._FALLBACK_ZH.items():
        assert _lookup(pack, code) == zh, code


def test_params_survive_json_even_when_they_are_not_json_types():
    # 调用点传的常是异常对象、Path、numpy 整数。以前它们被 f-string 拼掉了，
    # 现在要自己走一趟 json.dumps。
    nasty = [FileNotFoundError(2, "no such file"), pathlib.Path("/a/b.log"),
             ValueError("boom"), 42, "plain"]
    for i, (code, zh) in enumerate(mc._FALLBACK_ZH.items()):
        names = PLACEHOLDER.findall(zh)
        params = {n: nasty[(i + j) % len(nasty)] for j, n in enumerate(names)} or None
        json.dumps(mc.msg_fields(code, params), ensure_ascii=False)


def test_fallback_message_fills_placeholders():
    assert mc.fallback_message(mc.TRAIN_EPOCH, {"epoch": 3, "total": 20}) == "第 3 / 20 轮"
