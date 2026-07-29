# -*- coding: utf-8 -*-
"""launcher/profiles.py — voice-config profile data layer (M1)."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import profiles as P


# --- normalization / validation -----------------------------------------

def test_normalize_voice_coerces_and_clamps():
    v = P.normalize_voice(
        {
            "pitch": "3",
            "formant": "1.5",
            "index_rate": 2.0,      # clamp to 1.0
            "rms_mix_rate": -0.5,   # clamp to 0.0
            "threhold": -60.7,
            "f0method": "RMVPE",    # lowercased + whitelisted
            "bogus": 1,             # dropped
        }
    )
    assert v == {
        "pitch": 3,
        "formant": 1.5,
        "index_rate": 1.0,
        "rms_mix_rate": 0.0,
        "threhold": -61,
        "f0method": "rmvpe",
    }


def test_normalize_voice_drops_unset_and_bad_f0():
    v = P.normalize_voice({"pitch": None, "f0method": "nope", "index_rate": ""})
    assert v == {}


def test_normalize_fx_bools_gains_and_floats():
    fx = P.normalize_fx(
        {
            "fx_enabled": 1,
            "fx_gate_threshold_db": "-48",
            "fx_eq_gains": [0, 100, -100, 3, 2],  # clamp to [-24,24]
            "fx_eq_preset": "warm",
            "fx_eq_bad": 5,  # dropped (unknown)
        }
    )
    assert fx["fx_enabled"] is True
    assert fx["fx_gate_threshold_db"] == -48.0
    assert fx["fx_eq_gains"] == [0.0, 24.0, -24.0, 3.0, 2.0]
    assert fx["fx_eq_preset"] == "warm"
    assert "fx_eq_bad" not in fx


def test_normalize_fx_rejects_wrong_length_gains():
    assert "fx_eq_gains" not in P.normalize_fx({"fx_eq_gains": [0.0, 1.0]})


def test_normalize_perf_clamps_to_slider_ranges():
    perf = P.normalize_perf(
        {"block_time": 9.0, "crossfade_length": 0.001, "extra_time": 2.5}
    )
    assert perf == {"block_time": 1.5, "crossfade_length": 0.01, "extra_time": 2.5}


def test_make_profile_shape():
    p = P.make_profile("测试", voice={"pitch": 2}, source="official", score=0.87,
                       for_model="kikiV1")
    assert p["schema_version"] == P.PROFILE_SCHEMA_VERSION
    assert p["name"] == "测试"
    assert p["voice"] == {"pitch": 2}
    assert p["meta"]["source"] == "official"
    assert p["meta"]["score"] == 0.87
    assert p["meta"]["for_model"] == "kikiV1"
    assert len(p["id"]) >= 8


def test_make_profile_invalid_source_falls_back():
    assert P.make_profile("x", source="evil")["meta"]["source"] == "self"


def test_validate_profile_none_for_non_dict():
    assert P.validate_profile("nope") is None
    assert P.validate_profile(None) is None


def test_validate_profile_preserves_id_and_created():
    raw = {
        "name": "外部档案",
        "id": "abc123",
        "voice": {"pitch": -5},
        "meta": {"source": "official", "created": "2020-01-01 00:00:00"},
    }
    p = P.validate_profile(raw)
    assert p["id"] == "abc123"
    assert p["meta"]["created"] == "2020-01-01 00:00:00"
    assert p["meta"]["source"] == "official"
    assert p["voice"] == {"pitch": -5}


def test_is_empty_profile():
    assert P.is_empty_profile(P.make_profile("空"))
    assert not P.is_empty_profile(P.make_profile("有", voice={"pitch": 1}))


# --- on-disk CRUD ---------------------------------------------------------

def test_save_load_roundtrip(tmp_path):
    md = str(tmp_path)
    p = P.make_profile("低延迟清亮", voice={"pitch": 7}, fx={"fx_enabled": True},
                       perf={"block_time": 0.15})
    path = P.save_profile(md, p)
    assert os.path.isfile(path) and path.endswith(P.PROFILE_EXT)
    # atomic write leaves no temp
    assert not any(n.endswith(".tmp") for n in os.listdir(P.profiles_dir(md)))
    loaded = P.load_profile(md, p["id"])
    assert loaded["voice"] == {"pitch": 7}
    assert loaded["perf"] == {"block_time": 0.15}


def test_list_profiles_sorted_and_isolated(tmp_path):
    md = str(tmp_path)
    assert P.list_profiles(md) == []            # missing dir → empty
    a = P.make_profile("A", voice={"pitch": 1}, profile_id="aaaa1111")
    a["meta"]["created"] = "2026-01-01 00:00:00"
    b = P.make_profile("B", voice={"pitch": 2}, profile_id="bbbb2222")
    b["meta"]["created"] = "2026-02-01 00:00:00"
    P.save_profile(md, b)
    P.save_profile(md, a)
    names = [p["name"] for p in P.list_profiles(md)]
    assert names == ["A", "B"]  # sorted by created ascending


def test_list_profiles_skips_corrupt_files(tmp_path):
    md = str(tmp_path)
    P.save_profile(md, P.make_profile("ok", voice={"pitch": 1}))
    # drop a garbage .tmvp
    os.makedirs(P.profiles_dir(md), exist_ok=True)
    with open(os.path.join(P.profiles_dir(md), "broken.tmvp"), "w") as f:
        f.write("{ not json")
    got = P.list_profiles(md)
    assert len(got) == 1 and got[0]["name"] == "ok"


def test_list_profiles_id_follows_filename_stem(tmp_path):
    """Renamed .tmvp: load/delete use filename stem, not JSON id (review #17)."""
    md = str(tmp_path)
    p = P.make_profile("renamed", voice={"pitch": 3}, profile_id="oldid001")
    P.save_profile(md, p)
    src = P.profile_path(md, "oldid001")
    dst = os.path.join(P.profiles_dir(md), "newstem01.tmvp")
    os.replace(src, dst)
    listed = P.list_profiles(md)
    assert len(listed) == 1
    assert listed[0]["id"] == "newstem01"
    assert P.load_profile(md, "newstem01") is not None
    assert P.load_profile(md, "oldid001") is None


def test_delete_profile_and_active_reverts(tmp_path):
    md = str(tmp_path)
    p = P.make_profile("del", voice={"pitch": 1}, profile_id="dead0001")
    P.save_profile(md, p)
    P.set_active_profile_id(md, "dead0001")
    assert P.get_active_profile_id(md) == "dead0001"
    assert P.delete_profile(md, "dead0001") is True
    assert P.load_profile(md, "dead0001") is None
    # active pointer reverted to default
    assert P.get_active_profile_id(md) == ""
    assert P.delete_profile(md, "nope") is False


def test_rename_profile(tmp_path):
    md = str(tmp_path)
    p = P.make_profile("old", voice={"pitch": 1}, profile_id="ren00001")
    P.save_profile(md, p)
    assert P.rename_profile(md, "ren00001", "新名字") is True
    assert P.load_profile(md, "ren00001")["name"] == "新名字"
    assert P.rename_profile(md, "missing", "x") is False


def test_active_pointer_preserves_other_config_keys(tmp_path):
    md = str(tmp_path)
    cfg = os.path.join(md, "config.json")
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"name": "kiki", "pitch": 3, "index": "/x.index"}, f)
    P.set_active_profile_id(md, "prof0001")
    data = json.load(open(cfg, encoding="utf-8"))
    assert data["active_profile"] == "prof0001"
    assert data["pitch"] == 3 and data["index"] == "/x.index"  # untouched
    assert P.resolve_active_profile(md) is None  # points at a missing profile


def test_resolve_active_returns_profile(tmp_path):
    md = str(tmp_path)
    p = P.make_profile("act", voice={"pitch": 9}, profile_id="act00001")
    P.save_profile(md, p)
    P.set_active_profile_id(md, "act00001")
    got = P.resolve_active_profile(md)
    assert got is not None and got["voice"] == {"pitch": 9}


# --- config <-> profile bridge -------------------------------------------

def test_profile_to_config_updates_flattens_groups():
    p = P.make_profile(
        "x",
        voice={"pitch": 5, "f0method": "rmvpe"},
        fx={"fx_enabled": True, "fx_out_gain_db": -2.0},
        perf={"block_time": 0.15},
    )
    upd = P.profile_to_config_updates(p)
    assert upd == {
        "pitch": 5,
        "f0method": "rmvpe",
        "fx_enabled": True,
        "fx_out_gain_db": -2.0,
        "block_time": 0.15,
    }
    assert P.profile_to_config_updates(None) == {}


def test_config_to_profile_snapshots_tunables_only():
    cfg = {
        "pitch": 7,
        "formant": 1.0,
        "index_rate": 0.8,
        "f0method": "fcpe",
        "fx_enabled": True,
        "fx_eq_gains": [1, 2, 3, 4, 5],
        "block_time": 0.22,
        "crossfade_length": 0.05,
        "extra_time": 2.5,
        "sg_output_device": "CABLE Input",  # non-tunable → excluded
        "last_model": "kiki",               # excluded
    }
    prof = P.config_to_profile(cfg, "我的调音", for_model="kiki")
    assert prof["voice"]["pitch"] == 7
    assert prof["voice"]["f0method"] == "fcpe"
    assert prof["fx"]["fx_enabled"] is True
    assert prof["perf"]["block_time"] == 0.22
    # only tunable groups snapshotted
    assert "sg_output_device" not in P.profile_to_config_updates(prof)
    assert "last_model" not in P.profile_to_config_updates(prof)


def test_config_to_profile_round_trips_through_updates():
    cfg = {"pitch": 3, "fx_out_gain_db": -1.5, "extra_time": 1.5}
    prof = P.config_to_profile(cfg, "rt")
    # applying the snapshot back yields the same tunable values
    assert P.profile_to_config_updates(prof) == cfg


def test_config_to_profile_can_skip_perf():
    cfg = {"pitch": 1, "block_time": 0.3}
    prof = P.config_to_profile(cfg, "noperf", include_perf=False)
    assert prof["perf"] == {}
    assert prof["voice"] == {"pitch": 1}
