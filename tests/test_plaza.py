# -*- coding: utf-8 -*-
"""launcher/online/plaza — 广场 feed 解析/过滤/排序/缓存/用户动作测试。

unittest.TestCase style on purpose: this repo's ``unittest discover`` silently
collects zero tests from bare pytest functions (see CLAUDE.md). No network,
no Tk, no launcher.main_app import.
"""

import dataclasses
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.online.catalog import CNB_RAW_MAIN
from launcher.online.plaza import (
    PlazaItem,
    dismiss,
    dismissed_ids,
    feed_stamp,
    image_cache_path,
    mark_seen,
    on_card_clicked,
    parse_feed,
    pick_models_banner,
    seen_ids,
    unread_ids,
    visible_items,
)

# Every visibility call pins these explicitly — tests never depend on the real
# system date or the real APP_VERSION.
APP = "9.9.9"
TODAY = "250601"


def make_item(item_id, **overrides):
    """Build a PlazaItem through the production parser so sanitizers apply."""
    d = {"id": item_id, "title": overrides.pop("title", "t-" + item_id)}
    d.update(overrides)
    parsed = PlazaItem.from_dict(d)
    if parsed is None:
        raise AssertionError(f"fixture unexpectedly rejected: {d}")
    return parsed


def vis(items, placement="plaza", **kw):
    kw.setdefault("app_version", APP)
    kw.setdefault("today", TODAY)
    return visible_items(items, placement, **kw)


def ids_of(items):
    return [it.id for it in items]


class ParseFeedTests(unittest.TestCase):
    def test_entries_missing_id_or_title_are_skipped(self):
        rows = [
            {"title": "no id"},
            {"id": "no-title"},
            {"id": "", "title": "empty id"},
            {"id": "blank-title", "title": "   "},
        ]
        for row in rows:
            with self.subTest(row=row):
                self.assertEqual(parse_feed({"items": [row]}), [])

    def test_duplicate_id_keeps_first(self):
        out = parse_feed(
            [
                {"id": "a", "title": "first"},
                {"id": "a", "title": "second"},
                {"id": "b", "title": "b"},
            ]
        )
        self.assertEqual(ids_of(out), ["a", "b"])
        self.assertEqual(out[0].title, "first")

    def test_non_dict_rows_are_skipped(self):
        out = parse_feed(["junk", 42, None, ["x"], {"id": "ok", "title": "ok"}])
        self.assertEqual(ids_of(out), ["ok"])

    def test_bare_list_accepted(self):
        out = parse_feed([{"id": "a", "title": "a"}])
        self.assertEqual(len(out), 1)

    def test_completely_invalid_input_returns_empty(self):
        for data in (None, 42, "junk", b"junk", 3.14):
            with self.subTest(data=data):
                self.assertEqual(parse_feed(data), [])

    def test_unknown_fields_preserved_in_raw(self):
        out = parse_feed([{"id": "a", "title": "a", "future_field": "hello"}])
        self.assertEqual(out[0].raw.get("future_field"), "hello")


class UnknownTypeTests(unittest.TestCase):
    def test_parse_keeps_unknown_type_forward_compat(self):
        out = parse_feed([{"id": "u", "title": "u", "type": "hologram"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].type, "hologram")

    def test_visible_items_drops_unknown_type(self):
        items = [
            make_item("u", type="hologram"),
            make_item("n", type="news"),
        ]
        self.assertEqual(ids_of(vis(items)), ["n"])


class AdPolicyTests(unittest.TestCase):
    def test_ads_forced_dismissible_and_flagged(self):
        cases = (
            {"type": "ad"},
            {"type": "sponsor"},
            {"type": "news", "sponsor": "Acme"},
        )
        for kw in cases:
            with self.subTest(kw=kw):
                # Feed explicitly says dismissible: false — product overrides.
                it = make_item("x", dismissible=False, **kw)
                self.assertTrue(it.dismissible)
                self.assertTrue(it.is_ad)

    def test_plain_news_defaults_not_ad_not_dismissible(self):
        it = make_item("n", type="news")
        self.assertFalse(it.dismissible)
        self.assertFalse(it.is_ad)


class PlacementTests(unittest.TestCase):
    def test_string_placement_wrapped_into_list(self):
        it = make_item("a", placements="models_page")
        self.assertEqual(it.placements, ["models_page"])

    def test_default_placement_is_plaza(self):
        self.assertEqual(make_item("a").placements, ["plaza"])

    def test_visible_items_filters_by_placement(self):
        p = make_item("p", placements=["plaza"])
        m = make_item("m", placements=["models_page"])
        both = make_item("both", placements=["plaza", "models_page"])
        items = [p, m, both]
        self.assertEqual(set(ids_of(vis(items, "plaza"))), {"p", "both"})
        self.assertEqual(set(ids_of(vis(items, "models_page"))), {"m", "both"})


class ImagePolicyTests(unittest.TestCase):
    def test_relative_path_gets_cnb_raw_prefix(self):
        it = make_item("a", image="covers/a.jpg")
        self.assertEqual(it.image_url, f"{CNB_RAW_MAIN}/covers/a.jpg")

    def test_backslash_and_leading_slash_normalized(self):
        cases = (
            ("covers\\sub\\a.jpg", f"{CNB_RAW_MAIN}/covers/sub/a.jpg"),
            ("/covers/a.jpg", f"{CNB_RAW_MAIN}/covers/a.jpg"),
        )
        for raw, expect in cases:
            with self.subTest(raw=raw):
                self.assertEqual(make_item("a", image=raw).image_url, expect)

    def test_cnb_https_direct_link_kept(self):
        url = "https://cnb.cool/Turing-Mirror/x/-/git/raw/main/y.png"
        self.assertEqual(make_item("a", image=url).image_url, url)

    def test_foreign_host_and_plain_http_dropped(self):
        for url in (
            "https://evil.example/x.png",
            "http://evil.example/x.png",
            "https://cnb.cool.evil.example/x.png",
        ):
            with self.subTest(url=url):
                self.assertEqual(make_item("a", image=url).image_url, "")


class LinkPolicyTests(unittest.TestCase):
    def test_unsafe_schemes_dropped(self):
        for url in ("javascript:alert(1)", "file:///C:/x.exe", "ftp://host/x"):
            with self.subTest(url=url):
                self.assertEqual(make_item("a", url=url).url, "")

    def test_http_and_https_kept(self):
        for url in ("http://example.com/a", "https://example.com/a"):
            with self.subTest(url=url):
                self.assertEqual(make_item("a", url=url).url, url)


class WindowTests(unittest.TestCase):
    def test_start_in_future_hidden(self):
        it = make_item("a", start="250610")
        self.assertEqual(vis([it], today="250601"), [])

    def test_end_in_past_hidden(self):
        it = make_item("a", end="250520")
        self.assertEqual(vis([it], today="250601"), [])

    def test_boundary_days_visible(self):
        it = make_item("a", start="250610", end="250620")
        for day in ("250610", "250620"):
            with self.subTest(today=day):
                self.assertEqual(ids_of(vis([it], today=day)), ["a"])

    def test_empty_window_unrestricted(self):
        it = make_item("a")
        for day in ("000101", "991231"):
            with self.subTest(today=day):
                self.assertEqual(ids_of(vis([it], today=day)), ["a"])


class VersionGateTests(unittest.TestCase):
    def test_min_version_above_current_hidden(self):
        it = make_item("a", min_app_version="1.2.0")
        self.assertEqual(vis([it], app_version="1.1.2"), [])
        self.assertEqual(ids_of(vis([it], app_version="1.2.0")), ["a"])

    def test_max_version_below_current_hidden(self):
        it = make_item("a", max_app_version="1.1.0")
        self.assertEqual(vis([it], app_version="1.1.2"), [])
        self.assertEqual(ids_of(vis([it], app_version="1.1.0")), ["a"])

    def test_partn_prerelease_is_below_release(self):
        it = make_item("a", min_app_version="1.1.2")
        # 1.1.2-part1 is a prerelease of 1.1.2 → gated out; release passes.
        self.assertEqual(vis([it], app_version="1.1.2-part1"), [])
        self.assertEqual(ids_of(vis([it], app_version="1.1.2")), ["a"])


class DismissSemanticsTests(unittest.TestCase):
    def test_dismissed_hides_only_dismissible_items(self):
        ad = make_item("ad1", type="ad")
        closable = make_item("c1", type="news", dismissible=True)
        stubborn = make_item("s1", type="notice")  # not dismissible
        out = vis([ad, closable, stubborn], dismissed=["ad1", "c1", "s1"])
        self.assertEqual(ids_of(out), ["s1"])

    def test_unrelated_dismissed_ids_do_not_hide(self):
        ad = make_item("ad1", type="ad")
        self.assertEqual(ids_of(vis([ad], dismissed=["other"])), ["ad1"])


class SortingTests(unittest.TestCase):
    def test_full_ordering(self):
        items = [
            make_item("e_nodate"),
            make_item("d_old", date="250101"),
            make_item("b_new2", date="250110"),
            make_item("pin_lo", pinned=True),
            make_item("c_hipri", priority=9),
            make_item("a_new1", date="250110"),
            make_item("pin_hi", pinned=True, priority=3),
        ]
        expect = [
            "pin_hi",  # pinned first, higher priority
            "pin_lo",
            "c_hipri",  # then priority desc
            "a_new1",  # then date desc; same date → id asc
            "b_new2",
            "d_old",
            "e_nodate",  # undated sinks last
        ]
        self.assertEqual(ids_of(vis(items)), expect)


class ModelsBannerTests(unittest.TestCase):
    def test_picks_dismissible_from_models_page_only(self):
        plaza_ad = make_item("pa", type="ad", placements=["plaza"])
        # Pinned non-dismissible notice sorts first but has no banner rights.
        notice = make_item("no", type="notice", placements=["models_page"], pinned=True)
        banner = make_item("ba", type="ad", placements=["models_page"])
        got = pick_models_banner(
            [plaza_ad, notice, banner], app_version=APP, today=TODAY
        )
        self.assertIsNotNone(got)
        self.assertEqual(got.id, "ba")

    def test_all_dismissed_returns_none(self):
        banner = make_item("ba", type="ad", placements=["models_page"])
        got = pick_models_banner(
            [banner], app_version=APP, today=TODAY, dismissed=["ba"]
        )
        self.assertIsNone(got)

    def test_no_models_page_items_returns_none(self):
        plaza_only = make_item("p", type="ad", placements=["plaza"])
        got = pick_models_banner([plaza_only], app_version=APP, today=TODAY)
        self.assertIsNone(got)


class UnreadTests(unittest.TestCase):
    def test_seen_filtered_and_plaza_only(self):
        p1 = make_item("p1")
        p2 = make_item("p2")
        m1 = make_item("m1", placements=["models_page"])
        got = unread_ids([p1, p2, m1], ["p1"], app_version=APP, today=TODAY)
        self.assertEqual(got, ["p2"])

    def test_dismissed_items_not_counted_unread(self):
        ad = make_item("ad1", type="ad")
        got = unread_ids([ad], [], app_version=APP, today=TODAY, dismissed=["ad1"])
        self.assertEqual(got, [])


class CfgActionTests(unittest.TestCase):
    def test_mark_seen_merges_then_idempotent(self):
        cfg = {}
        self.assertTrue(mark_seen(cfg, ["a", "b"]))
        self.assertEqual(seen_ids(cfg), ["a", "b"])
        self.assertFalse(mark_seen(cfg, ["a", "b"]))
        self.assertEqual(seen_ids(cfg), ["a", "b"])

    def test_mark_seen_caps_at_200_keeping_newest(self):
        cfg = {}
        ids = [f"i{i:03d}" for i in range(250)]
        self.assertTrue(mark_seen(cfg, ids))
        self.assertEqual(seen_ids(cfg), ids[50:])

    def test_dismiss_idempotent_and_rejects_empty(self):
        cfg = {}
        self.assertTrue(dismiss(cfg, "x"))
        self.assertFalse(dismiss(cfg, "x"))
        self.assertEqual(dismissed_ids(cfg), ["x"])
        self.assertFalse(dismiss(cfg, ""))
        self.assertFalse(dismiss(cfg, "   "))

    def test_dismiss_caps_at_200_keeping_newest(self):
        old = [f"d{i:03d}" for i in range(200)]
        cfg = {"plaza_dismissed": list(old)}
        self.assertTrue(dismiss(cfg, "newest"))
        got = dismissed_ids(cfg)
        self.assertEqual(len(got), 200)
        self.assertNotIn("d000", got)
        self.assertEqual(got[-1], "newest")

    def test_invalid_cfg_values_return_empty(self):
        for bad in (None, "abc"):
            with self.subTest(bad=bad):
                cfg = {"plaza_seen_ids": bad, "plaza_dismissed": bad}
                self.assertEqual(seen_ids(cfg), [])
                self.assertEqual(dismissed_ids(cfg), [])


class FeedStampTests(unittest.TestCase):
    def test_order_insensitive(self):
        a = make_item("a", date="250101", priority=1)
        b = make_item("b", date="250110", priority=2)
        self.assertEqual(feed_stamp([a, b]), feed_stamp([b, a]))

    def test_changes_on_title_date_priority(self):
        a = make_item("a", date="250101", priority=1)
        b = make_item("b", date="250110", priority=2)
        base = feed_stamp([a, b])
        variants = (
            dataclasses.replace(b, title="other"),
            dataclasses.replace(b, date="250111"),
            dataclasses.replace(b, priority=7),
        )
        for changed in variants:
            with self.subTest(changed=changed):
                self.assertNotEqual(feed_stamp([a, changed]), base)

    def test_changes_on_every_render_field(self):
        """同 id 原地改任一渲染字段都必须改变 stamp——否则客户端刷新短路，
        运营改完 body/url 用户整会话看不到（对抗审查确证过的缺陷）。"""
        a = make_item("a", date="250101", priority=1)
        b = make_item(
            "b",
            body="old body",
            url="https://cnb.cool/old",
            image="plaza/old.jpg",
            action_label="旧按钮",
        )
        base = feed_stamp([a, b])
        variants = (
            dataclasses.replace(b, body="new body"),
            dataclasses.replace(b, url="https://cnb.cool/new"),
            dataclasses.replace(b, image_url="https://cnb.cool/x/new.jpg"),
            dataclasses.replace(b, action_label="新按钮"),
            dataclasses.replace(b, type="ad"),
            dataclasses.replace(b, sponsor="某厂"),
            dataclasses.replace(b, dismissible=True),
            dataclasses.replace(b, pinned=True),
            dataclasses.replace(b, placements=["plaza", "models_page"]),
        )
        for changed in variants:
            with self.subTest(changed=changed):
                self.assertNotEqual(feed_stamp([a, changed]), base)


class ImageCachePathTests(unittest.TestCase):
    def test_same_url_stable(self):
        url = "https://cnb.cool/x/a.png"
        self.assertEqual(image_cache_path(url), image_cache_path(url))

    def test_extension_survives_query_string(self):
        p = image_cache_path("https://cnb.cool/x/a.png?v=1&w=2")
        self.assertEqual(p.suffix, ".png")

    def test_unusual_extension_falls_back_to_jpg(self):
        for url in (
            "https://cnb.cool/x/a.bin",
            "https://cnb.cool/x/no-extension",
        ):
            with self.subTest(url=url):
                self.assertEqual(image_cache_path(url).suffix, ".jpg")

    def test_different_urls_get_different_names(self):
        a = image_cache_path("https://cnb.cool/x/a.png")
        b = image_cache_path("https://cnb.cool/x/b.png")
        self.assertNotEqual(a.name, b.name)


class CardClickTests(unittest.TestCase):
    def test_empty_url_returns_false_without_browser(self):
        it = make_item("a")  # no url
        with mock.patch("webbrowser.open") as opened:
            self.assertFalse(on_card_clicked(it))
        opened.assert_not_called()

    def test_bad_scheme_returns_false_without_browser(self):
        # Bypass from_dict on purpose: a hand-built item must still be safe.
        it = PlazaItem(id="x", title="t", url="javascript:alert(1)")
        with mock.patch("webbrowser.open") as opened:
            self.assertFalse(on_card_clicked(it))
        opened.assert_not_called()

    def test_valid_url_opens_browser_once(self):
        it = make_item("a", url="https://example.com/page")
        with mock.patch("webbrowser.open") as opened:
            self.assertTrue(on_card_clicked(it))
        opened.assert_called_once_with("https://example.com/page")


if __name__ == "__main__":
    unittest.main()
