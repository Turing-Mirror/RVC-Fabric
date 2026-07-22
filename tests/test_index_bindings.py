# -*- coding: utf-8 -*-
"""launcher/catalog.py — many-to-many index bindings + import copy/move."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.catalog import (
    add_index_binding,
    import_model_to_catalog,
    list_index_bindings,
    remove_index_binding,
    set_active_index,
)


def _side(model_dir: Path) -> dict:
    p = model_dir / "config.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _mk_index(tmp_path: Path, name: str = "voice.index") -> Path:
    p = tmp_path / name
    p.write_bytes(b"fake-index")
    return p


def test_add_first_binding_becomes_active(tmp_path):
    md = tmp_path / "models" / "Miku"
    idx = _mk_index(tmp_path)
    recorded = add_index_binding(md, idx)
    assert Path(recorded).resolve() == idx.resolve()
    assert _side(md)["index"] == recorded
    assert list_index_bindings(md) == [recorded]
    # shared binding: source file untouched
    assert idx.is_file()


def test_second_binding_listed_but_not_active(tmp_path):
    md = tmp_path / "m" / "kiki"
    a = _mk_index(tmp_path, "a.index")
    b = _mk_index(tmp_path, "b.index")
    pa = add_index_binding(md, a)
    pb = add_index_binding(md, b)
    assert _side(md)["index"] == pa
    assert set(list_index_bindings(md)) == {pa, pb}


def test_set_active_and_clear(tmp_path):
    md = tmp_path / "m" / "kiki"
    a = _mk_index(tmp_path, "a.index")
    b = _mk_index(tmp_path, "b.index")
    pa = add_index_binding(md, a)
    pb = add_index_binding(md, b)
    set_active_index(md, pb)
    assert _side(md)["index"] == pb
    set_active_index(md, "")
    assert _side(md)["index"] == ""
    # both still bound
    assert set(list_index_bindings(md)) == {pa, pb}


def test_remove_binding_clears_active_keeps_file(tmp_path):
    md = tmp_path / "m" / "kiki"
    a = _mk_index(tmp_path, "a.index")
    pa = add_index_binding(md, a)
    remove_index_binding(md, pa)
    assert _side(md)["index"] == ""
    assert list_index_bindings(md) == []
    assert a.is_file()  # unbind never deletes


def test_copy_and_move_into_folder(tmp_path):
    md = tmp_path / "m" / "kiki"
    a = _mk_index(tmp_path, "a.index")
    pa = add_index_binding(md, a, copy_into_folder=True)
    assert Path(pa).parent.resolve() == md.resolve()
    assert a.is_file()  # copy keeps source
    b = _mk_index(tmp_path, "b.index")
    pb = add_index_binding(md, b, move_into_folder=True)
    assert Path(pb).parent.resolve() == md.resolve()
    assert not b.is_file()  # move removes source


def test_same_index_bound_to_two_models(tmp_path):
    shared = _mk_index(tmp_path, "shared.index")
    m1 = tmp_path / "m" / "A"
    m2 = tmp_path / "m" / "B"
    p1 = add_index_binding(m1, shared)
    p2 = add_index_binding(m2, shared)
    assert p1 == p2
    assert list_index_bindings(m1) == [p1]
    assert list_index_bindings(m2) == [p2]


def test_import_copy_keeps_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    pth = src / "Miku.pth"
    pth.write_bytes(b"fake-model")
    idx = src / "Miku.index"
    idx.write_bytes(b"fake-index")
    root = tmp_path / "models_root"
    info = import_model_to_catalog(pth, root)
    assert Path(info["path"]).is_file()
    assert pth.is_file() and idx.is_file()  # copy mode keeps originals
    assert info["index"]  # sibling index auto-bound
    assert _side(Path(info["dir"]))["index_files"] == [info["index"]]


def test_import_move_removes_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    pth = src / "kiki.pth"
    pth.write_bytes(b"fake-model")
    idx = src / "kiki.index"
    idx.write_bytes(b"fake-index")
    root = tmp_path / "models_root"
    info = import_model_to_catalog(pth, root, move=True)
    assert Path(info["path"]).is_file()
    assert Path(info["index"]).is_file()
    assert not pth.is_file()
    assert not idx.is_file()

def test_rename_model_display(tmp_path):
    from launcher.catalog import rename_model_display

    md = tmp_path / "models" / "kiki"
    md.mkdir(parents=True)
    assert rename_model_display(md, " 琪琪 ") == "琪琪"
    assert _side(md)["name"] == "琪琪"
    try:
        rename_model_display(md, "   ")
        assert False, "empty name must raise"
    except ValueError:
        pass


def test_delete_model_dir_guarded(tmp_path):
    from launcher.catalog import delete_model_dir

    root = tmp_path / "models"
    md = root / "kiki"
    md.mkdir(parents=True)
    (md / "kiki.pth").write_bytes(b"x")
    delete_model_dir(md, root)
    assert not md.exists()
    # refuse anything outside the catalog root
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    try:
        delete_model_dir(outside, root)
        assert False, "outside root must raise"
    except ValueError:
        pass
    assert outside.exists()

def test_missing_and_broken_models_flagged(tmp_path):
    from launcher.catalog import list_models_in_user_data

    root = tmp_path / "models"
    # real-ish model: big enough .pth
    real = root / "Miku"
    real.mkdir(parents=True)
    (real / "Miku.pth").write_bytes(b"x" * (300 * 1024))
    (real / "config.json").write_text('{"name": "Miku"}', encoding="utf-8")
    # broken: tiny LFS-pointer-sized .pth
    broken = root / "kiki"
    broken.mkdir()
    (broken / "kiki.pth").write_bytes(b"version https://git-lfs...")
    (broken / "config.json").write_text('{"name": "kiki"}', encoding="utf-8")
    # missing: no .pth but looks like a voice (has config)
    gone = root / "gone"
    gone.mkdir()
    (gone / "config.json").write_text('{"name": "gone"}', encoding="utf-8")
    # not a voice: empty dir → skipped entirely
    (root / "random").mkdir()

    got = {m["name"]: m for m in list_models_in_user_data(root)}
    assert got["Miku"]["missing"] is False
    assert got["kiki"]["missing"] is True   # too small
    assert got["gone"]["missing"] is True    # no .pth at all
    assert got["gone"]["path"] == ""
    assert "random" not in got               # not a voice folder → hidden

def test_promote_legacy_via_import_move(tmp_path):
    # 模拟旧版散装音色 assets/weights/foo.pth + 同名 index，移动进独立文件夹
    from launcher.catalog import import_model_to_catalog, list_index_bindings

    weights = tmp_path / "assets" / "weights"
    weights.mkdir(parents=True)
    pth = weights / "guanguanV1.pth"
    pth.write_bytes(b"x" * (300 * 1024))
    idx = weights / "guanguanV1.index"
    idx.write_bytes(b"fake-index")
    root = tmp_path / "models"

    info = import_model_to_catalog(
        pth, root, display_name="guanguanV1",
        index_src=idx, move=True,
    )
    dest = Path(info["dir"])
    assert dest.parent.resolve() == root.resolve()
    assert Path(info["path"]).is_file()          # pth now in its own folder
    assert info["index"]                          # index bound
    assert list_index_bindings(dest) == [info["index"]]
    assert not pth.is_file()                      # moved out of weights


def test_resolve_prefers_name_matched_local_over_foreign_alpha(tmp_path):
    """Soyo folder with leftover rana-cloud.index must not auto-pick it first."""
    from launcher.catalog import (
        get_model_active_index,
        list_models_in_user_data,
        resolve_model_active_index,
    )

    root = tmp_path / "models"
    soyo = root / "Soyo"
    soyo.mkdir(parents=True)
    (soyo / "Soyo-normal-local.pth").write_bytes(b"x" * (300 * 1024))
    # Alphabetically first is the foreign leftover
    foreign = soyo / "added_IVF1021_Flat_nprobe_1_rana-cloud_v2.index"
    own = soyo / "added_IVF2071_Flat_nprobe_1_Soyo-normal-local_v2.index"
    foreign.write_bytes(b"foreign")
    own.write_bytes(b"own")
    # No index key → auto-discover must prefer name match
    got = resolve_model_active_index(soyo, name="Soyo", pth_stem="Soyo-normal-local")
    assert Path(got).resolve() == own.resolve()

    listed = {m["name"]: m for m in list_models_in_user_data(root)}
    assert Path(listed["Soyo"]["index"]).resolve() == own.resolve()
    assert Path(get_model_active_index(soyo)).resolve() == own.resolve()


def test_resolve_heals_external_path_to_local_same_name(tmp_path):
    """Active index pointing at another model's folder, local copy exists → local."""
    from launcher.catalog import resolve_model_active_index

    root = tmp_path / "models"
    rana = root / "Rana"
    soyo = root / "Soyo"
    rana.mkdir(parents=True)
    soyo.mkdir(parents=True)
    (soyo / "Soyo.pth").write_bytes(b"x" * (300 * 1024))
    name = "added_IVF1021_Flat_nprobe_1_rana-cloud_v2.index"
    external = rana / name
    local = soyo / name
    external.write_bytes(b"ext")
    local.write_bytes(b"loc")
    side = {
        "name": "Soyo",
        "index": str(external.resolve()),
        "index_files": [str(external.resolve()), str(local.resolve())],
    }
    (soyo / "config.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    got = resolve_model_active_index(soyo, side, name="Soyo")
    assert Path(got).resolve() == local.resolve()


def test_resolve_explicit_empty_index_stays_empty(tmp_path):
    """「不用检索库」must not auto-pick a local leftover .index."""
    from launcher.catalog import resolve_model_active_index

    md = tmp_path / "models" / "Soyo"
    md.mkdir(parents=True)
    (md / "Soyo.pth").write_bytes(b"x" * (300 * 1024))
    (md / "Soyo.index").write_bytes(b"idx")
    side = {"name": "Soyo", "index": ""}
    assert resolve_model_active_index(md, side, name="Soyo") == ""
