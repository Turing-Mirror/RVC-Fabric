# -*- coding: utf-8 -*-
"""launcher/catalog.filter_sort_models — models-page search/sort logic."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.catalog import MODEL_SORT_KEYS, filter_sort_models

MODELS = [
    {"name": "Kiki", "tag": "少女音", "file": "kikiV1.pth", "index": ""},
    {"name": "Miku", "tag": "少女音", "file": "Miku.pth", "index": "/x/Miku.index"},
    {"name": "青年男声", "tag": "男声", "file": "aoto.pth", "index": ""},
    {"name": "Aria", "tag": "御姐音", "file": "aria.pth", "index": "/x/aria.index"},
]


def test_empty_query_returns_all_in_order():
    out = filter_sort_models(MODELS)
    assert [m["name"] for m in out] == ["Kiki", "Miku", "青年男声", "Aria"]


def test_does_not_mutate_input():
    before = [dict(m) for m in MODELS]
    filter_sort_models(MODELS, "m", sort="name")
    assert MODELS == before


def test_query_matches_name_case_insensitive():
    out = filter_sort_models(MODELS, "miku")
    assert [m["name"] for m in out] == ["Miku"]


def test_query_matches_tag():
    out = filter_sort_models(MODELS, "少女")
    assert {m["name"] for m in out} == {"Kiki", "Miku"}


def test_query_matches_file():
    out = filter_sort_models(MODELS, "aoto")
    assert [m["name"] for m in out] == ["青年男声"]


def test_query_matches_cjk_name():
    out = filter_sort_models(MODELS, "青年")
    assert [m["name"] for m in out] == ["青年男声"]


def test_no_match_returns_empty():
    assert filter_sort_models(MODELS, "zzz nothing") == []


def test_sort_name_alpha():
    out = filter_sort_models(MODELS, sort="name")
    # ascii sorts before CJK by codepoint; just assert ascii ordering holds
    names = [m["name"] for m in out]
    assert names.index("Aria") < names.index("Kiki") < names.index("Miku")


def test_sort_index_first():
    out = filter_sort_models(MODELS, sort="index")
    # models with an index come first, then alphabetical
    assert [m["name"] for m in out[:2]] == ["Aria", "Miku"]
    assert {m["name"] for m in out[2:]} == {"Kiki", "青年男声"}


def test_sort_keys_constant_exposed():
    assert MODEL_SORT_KEYS == ("default", "name", "index")


def test_query_and_sort_combined():
    out = filter_sort_models(MODELS, "少女", sort="index")
    # only the two 少女音 models, index-holder first
    assert [m["name"] for m in out] == ["Miku", "Kiki"]
