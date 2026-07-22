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
    recorded = add_index_binding(md, idx)  # default: copy into model folder
    assert Path(recorded).parent.resolve() == md.resolve()
    assert Path(recorded).name == idx.name
    assert _side(md)["index"] == recorded
    assert list_index_bindings(md) == [recorded]
    assert idx.is_file()  # source kept on copy


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
    assert Path(_side(md)["index"]).resolve() == Path(pb).resolve()
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
    # File still sits in the model folder → still listed; unbind never deletes.
    local = str((md / a.name).resolve())
    assert list_index_bindings(md) == [local]
    assert a.is_file()
    assert Path(local).is_file()


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


def test_same_index_copied_into_two_models(tmp_path):
    """Each model gets its own copy under its folder (not a ghost shared path)."""
    shared = _mk_index(tmp_path, "shared.index")
    m1 = tmp_path / "m" / "A"
    m2 = tmp_path / "m" / "B"
    p1 = add_index_binding(m1, shared)
    p2 = add_index_binding(m2, shared)
    assert Path(p1).parent.resolve() == m1.resolve()
    assert Path(p2).parent.resolve() == m2.resolve()
    assert Path(p1).name == Path(p2).name == "shared.index"
    assert list_index_bindings(m1) == [p1]
    assert list_index_bindings(m2) == [p2]


def test_sanitize_drops_external_twin_of_local_index(tmp_path):
    """Stale absolute path from another install must not appear as「共享」."""
    from launcher.catalog import sanitize_index_bindings, set_active_index

    other = tmp_path / "Grok_test" / "models" / "Tomori"
    local = tmp_path / "models" / "Tomori"
    other.mkdir(parents=True)
    local.mkdir(parents=True)
    name = "added_IVF3156_Flat_nprobe_1_tomori-speak_v2.index"
    ext = other / name
    loc = local / name
    ext.write_bytes(b"external")
    loc.write_bytes(b"local")
    (local / "config.json").write_text(
        json.dumps(
            {
                "name": "Tomori",
                "index": str(ext.resolve()),
                "index_files": [str(ext.resolve()), str(loc.resolve())],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    got = sanitize_index_bindings(local)
    assert len(got) == 1
    assert Path(got[0]).resolve() == loc.resolve()
    side = _side(local)
    assert Path(side["index"]).resolve() == loc.resolve()
    # 「使用」external twin → still lands on local
    set_active_index(local, str(ext))
    assert Path(_side(local)["index"]).resolve() == loc.resolve()
    assert len(list_index_bindings(local)) == 1


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


def test_import_user_files_pth_plus_index_same_folder(tmp_path):
    """Multi-select .pth + .index → both land under models/<name>/."""
    from launcher.catalog import import_user_files, list_index_bindings

    src = tmp_path / "dl"
    src.mkdir()
    pth = src / "MyVoice.pth"
    idx = src / "MyVoice.index"
    pth.write_bytes(b"x" * (300 * 1024))
    idx.write_bytes(b"fake-index-bytes")
    root = tmp_path / "models"
    summary = import_user_files([pth, idx], root, move=False)
    assert len(summary["models"]) == 1
    info = summary["models"][0]
    dest = Path(info["dir"])
    assert (dest / "MyVoice.pth").is_file()
    assert info["index"]
    assert Path(info["index"]).parent.resolve() == dest.resolve()
    assert Path(info["index"]).is_file()
    assert list_index_bindings(dest)


def test_import_index_only_onto_current_model(tmp_path):
    from launcher.catalog import import_model_to_catalog, import_user_files

    root = tmp_path / "models"
    pth = tmp_path / "A.pth"
    pth.write_bytes(b"x" * (300 * 1024))
    info = import_model_to_catalog(pth, root)
    md = Path(info["dir"])
    idx = tmp_path / "extra.index"
    idx.write_bytes(b"idx-data")
    summary = import_user_files(
        [idx], root, move=False, current_model_dir=md
    )
    assert len(summary["indices"]) == 1
    bound = Path(summary["indices"][0]["path"])
    assert bound.parent.resolve() == md.resolve()
    assert bound.is_file()


def test_import_index_only_without_target_errors(tmp_path):
    from launcher.catalog import import_user_files

    idx = tmp_path / "lonely.index"
    idx.write_bytes(b"idx")
    summary = import_user_files([idx], tmp_path / "models", move=False)
    assert summary["models"] == []
    assert summary["indices"] == []
    assert summary["errors"]
