# -*- coding: utf-8 -*-
"""launcher/online/catalog — 社区下载 pure helpers: filter / sort / paginate / series."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.online.catalog import (
    VoiceEntry,
    filter_voices,
    group_series_only,
    paginate,
    sort_voices_newest_first,
)


def _v(vid, date="", series="", author="", tag="音色"):
    return VoiceEntry(
        id=vid,
        name=vid,
        tag=tag,
        date=date,
        series=series,
        author=author,
        pack_url="https://example.invalid/x.zip",
    )


VOICES = [
    _v("guanguan", date="260721", series="RVC原版", author="RVC"),
    _v("kiki", date="260721", series="RVC原版", author="RVC"),
    _v("Anon", date="260723", series="MyGO!!!!!", author="望月星逸"),
    _v("Tomori", date="260723", series="MyGO!!!!!", author="望月星逸"),
    _v("solo", date="", series="", author="路人甲", tag="男声"),
]


# ---------------------------------------------------------- sort newest first
def test_sort_newest_first_date_desc():
    out = sort_voices_newest_first(VOICES)
    assert [v.id for v in out] == ["Anon", "Tomori", "guanguan", "kiki", "solo"]


def test_sort_undated_sink_to_end():
    assert sort_voices_newest_first(VOICES)[-1].id == "solo"


def test_sort_same_date_keeps_input_order():
    out = sort_voices_newest_first(VOICES)
    assert [v.id for v in out if v.date == "260721"] == ["guanguan", "kiki"]
    assert [v.id for v in out if v.date == "260723"] == ["Anon", "Tomori"]


def test_sort_does_not_mutate_input():
    before = [v.id for v in VOICES]
    sort_voices_newest_first(VOICES)
    assert [v.id for v in VOICES] == before


# ------------------------------------------------------------------- paginate
def test_paginate_basic_split():
    items = list(range(9))
    page_items, page, total = paginate(items, 1, 5)
    assert (page_items, page, total) == ([0, 1, 2, 3, 4], 1, 2)
    page_items, page, total = paginate(items, 2, 5)
    assert (page_items, page, total) == ([5, 6, 7, 8], 2, 2)


def test_paginate_clamps_overrun_to_last_page():
    page_items, page, total = paginate(list(range(9)), 99, 5)
    assert (page, total) == (2, 2)
    assert page_items == [5, 6, 7, 8]


def test_paginate_clamps_low_to_first_page():
    for bad in (0, -3):
        page_items, page, total = paginate(list(range(9)), bad, 5)
        assert (page, total) == (1, 2)
        assert page_items == [0, 1, 2, 3, 4]


def test_paginate_empty_list():
    assert paginate([], 5, 5) == ([], 1, 1)


def test_paginate_exact_multiple():
    page_items, page, total = paginate(list(range(10)), 2, 5)
    assert (page, total) == (2, 2)
    assert page_items == [5, 6, 7, 8, 9]


# ---------------------------------------------------------- group series only
def test_group_series_only_drops_ungrouped():
    groups = group_series_only(VOICES)
    assert [s for s, _ in groups] == ["RVC原版", "MyGO!!!!!"]
    assert [v.id for v in dict(groups)["MyGO!!!!!"]] == ["Anon", "Tomori"]


def test_group_series_only_all_ungrouped_is_empty():
    assert group_series_only([_v("a"), _v("b")]) == []


# -------------------------------------------------------------- filter voices
def test_filter_matches_series_case_insensitive():
    out = filter_voices(VOICES, "mygo")
    assert {v.id for v in out} == {"Anon", "Tomori"}


def test_filter_matches_series_cjk():
    out = filter_voices(VOICES, "RVC原版")
    assert {v.id for v in out} == {"guanguan", "kiki"}


def test_filter_matches_author_and_tag():
    assert {v.id for v in filter_voices(VOICES, "望月")} == {"Anon", "Tomori"}
    assert {v.id for v in filter_voices(VOICES, "男声")} == {"solo"}


def test_filter_empty_query_returns_copy_of_all():
    out = filter_voices(VOICES, "")
    assert out == VOICES
    assert out is not VOICES


def test_filter_no_match():
    assert filter_voices(VOICES, "不存在的关键词") == []
