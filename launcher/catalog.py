# -*- coding: utf-8 -*-
"""Voice model catalog under User_Data (RVCMAX job split; not engine assets).

Canonical on-disk layout (after import / community install)::

    User_Data/models/<name>/
        *.pth            # required — model weight (one primary file)
        *.index          # optional — FAISS retrieval, **same folder as .pth**
        cover.png|jpg    # optional — card art
        config.json      # sidecar: name/tag/params + index binding + active_profile
        profiles/*.tmvp  # optional — named config profiles

Import entry points accept ``.pth`` / ``.index`` / (via UI) ``.zip`` voice packs.
``.index`` never lives in a global dump folder by default: it is copied next to
its ``.pth`` so a voice folder is portable.

Legacy fallback: flat ``assets/weights/*.pth`` still listed, tagged as legacy.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional, Sequence, Union

# Safe folder name for catalog entries
_SAFE = re.compile(r"[^\w\u4e00-\u9fff\-]+", re.UNICODE)


def safe_model_dir_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        raise ValueError("model name is empty")
    n = _SAFE.sub("_", n).strip("._")
    if not n or n in (".", ".."):
        raise ValueError(f"invalid model name: {name!r}")
    return n[:80]


def guess_tag(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("女", "girl", "loli", "萝莉", "少女")):
        return "少女音"
    if any(k in n for k in ("男", "boy", "男声", "青年")):
        return "男声"
    if "御姐" in n:
        return "御姐音"
    return "音色"


def _find_pth(folder: Path) -> Optional[Path]:
    pths = sorted(folder.glob("*.pth"))
    return pths[0] if pths else None


# A real RVC .pth is many MB. A few-hundred-byte "model" is not usable —
# an interrupted copy, a truncated/placeholder file, etc. Flag it so the app
# tells the user instead of pretending it's a working voice.
_MIN_MODEL_BYTES = 200 * 1024


def _model_is_broken(pth: Optional[Path]) -> bool:
    """True when the .pth is missing or too small to be a real model."""
    if pth is None or not pth.is_file():
        return True
    try:
        return pth.stat().st_size < _MIN_MODEL_BYTES
    except Exception:
        return False


def _looks_like_voice_folder(folder: Path) -> bool:
    """A folder the user thinks is a voice (has config or a cover) even if the
    .pth is missing — so we can show it as 缺失 instead of hiding it silently."""
    if (folder / "config.json").is_file():
        return True
    return _find_cover(folder) is not None


def _find_cover(folder: Path) -> Optional[str]:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        for p in folder.glob(f"*{ext}"):
            return str(p.resolve())
        c = folder / f"cover{ext}"
        if c.is_file():
            return str(c.resolve())
    return None


def _find_index(name: str, search_roots: list[Path]) -> str:
    """Find an .index whose *name or parent folder* matches ``name``.

    Scans search roots but never returns a hit from another model folder
    just because the path string loosely overlaps — parent folder name or
    filename must contain the model name (case-insensitive).
    """
    key = (name or "").strip()
    if not key:
        return ""
    key_l = key.lower()
    for root in search_roots:
        if not root.is_dir():
            continue
        for ip in root.rglob("*.index"):
            if "trained" in ip.name.lower():
                continue
            try:
                parent_l = ip.parent.name.lower()
                name_l = ip.name.lower()
            except Exception:
                continue
            if key_l in name_l or key_l in parent_l:
                return str(ip.resolve())
    return ""


def _pick_local_index(
    folder: Path, *, name: str = "", pth_stem: str = ""
) -> str:
    """Choose the best .index inside ``folder``.

    Prefer a file whose name matches the model name / pth stem. Never pick
    alphabetically-first when a name-matched candidate exists — that used to
    make Soyo auto-select a leftover rana-cloud.index from another voice.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return ""
    local = sorted(folder.glob("*.index"))
    if not local:
        return ""
    keys = [k for k in (name, pth_stem, folder.name) if k]
    for key in keys:
        key_l = str(key).lower()
        for ip in local:
            if "trained" in ip.name.lower():
                continue
            if key_l in ip.name.lower():
                return str(ip.resolve())
    for ip in local:
        if "trained" not in ip.name.lower():
            return str(ip.resolve())
    return str(local[0].resolve())


def resolve_model_active_index(
    model_dir: Path,
    side: Optional[dict[str, Any]] = None,
    *,
    name: str = "",
    pth_stem: str = "",
    search_roots: Optional[list[Path]] = None,
) -> str:
    """Resolve which .index this model should use (disk is source of truth).

    Order:
    1. If ``config.json`` has an ``index`` key:
       - ``""`` means the user chose「不用检索库」— do **not** auto-pick.
       - non-empty path: use it when the file exists. If it points *outside*
         the model folder but the same filename sits inside, prefer the local
         copy (heals sticky absolute paths from another install / model dir).
       - non-empty but missing file: fall through to auto-discover.
    2. No ``index`` key yet: best local ``*.index`` (name-matched preferred).
    3. Optional scan of ``search_roots`` by model name / pth stem.
    """
    model_dir = Path(model_dir)
    if side is None:
        side = _read_sidecar(model_dir)
    display = str(name or side.get("name") or model_dir.name)
    stem = str(pth_stem or "")
    if not stem:
        pth = _find_pth(model_dir)
        if pth is not None:
            stem = pth.stem

    if "index" in side:
        configured = str(side.get("index") or "").strip()
        if not configured:
            # Explicit none — user clicked「不用检索库」or cleared binding.
            return ""
        try:
            cfg_path = Path(configured)
            if cfg_path.is_file():
                local_same = model_dir / cfg_path.name
                try:
                    outside = (
                        model_dir.is_dir()
                        and cfg_path.parent.resolve() != model_dir.resolve()
                    )
                except Exception:
                    outside = True
                if outside and local_same.is_file():
                    return str(local_same.resolve())
                return str(cfg_path.resolve())
        except Exception:
            pass
        # Configured path missing on disk → fall through to discover.

    local = _pick_local_index(model_dir, name=display, pth_stem=stem)
    if local:
        return local

    roots = search_roots or []
    return _find_index(display, roots) or _find_index(stem, roots) or ""


def get_model_active_index(model_dir: Path) -> str:
    """Active .index path for a model folder ("" = none / missing file)."""
    return resolve_model_active_index(Path(model_dir))


def _read_sidecar(folder: Path) -> dict[str, Any]:
    cfg = folder / "config.json"
    if not cfg.is_file():
        return {}
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def list_models_in_user_data(
    models_root: Path,
    *,
    index_search_roots: Optional[list[Path]] = None,
) -> list[dict[str, Any]]:
    """List catalog entries under User_Data/models."""
    models_root = Path(models_root)
    out: list[dict[str, Any]] = []
    if not models_root.is_dir():
        return out
    roots = index_search_roots or []
    for folder in sorted(models_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        pth = _find_pth(folder)
        side = _read_sidecar(folder)
        name = str(side.get("name") or folder.name)
        tag = str(side.get("tag") or guess_tag(name))
        broken = _model_is_broken(pth)
        if pth is None:
            # No .pth at all: surface it as 缺失 only if it looks like a voice
            # folder (config/cover); otherwise it's just some other directory.
            if not _looks_like_voice_folder(folder):
                continue
            out.append({
                "name": name,
                "path": "",
                "file": "",
                "dir": str(folder.resolve()),
                "cover": _find_cover(folder),
                "index": "",
                "tag": tag,
                "source": "user_data",
                "missing": True,
                "pitch": None, "formant": None, "index_rate": None,
                "rms_mix_rate": None, "threhold": None, "f0method": None,
            })
            continue
        index = resolve_model_active_index(
            folder,
            side,
            name=name,
            pth_stem=pth.stem,
            search_roots=roots,
        )
        cover = side.get("cover")
        if cover:
            cp = Path(str(cover))
            if not cp.is_file():
                cover = _find_cover(folder)
            else:
                cover = str(cp.resolve())
        else:
            cover = _find_cover(folder)
        entry = {
            "name": name,
            "path": str(pth.resolve()),
            "file": pth.name,
            "dir": str(folder.resolve()),
            "cover": cover,
            "index": index,
            "tag": tag,
            "source": "user_data",
            "missing": broken,
            "pitch": None,
            "formant": None,
            "index_rate": None,
            "rms_mix_rate": None,
            "threhold": None,
            "f0method": None,
        }
        entry.update(voice_params_from_side(side))
        out.append(entry)
    return out


def list_models_legacy_weights(
    weights_dir: Path,
    *,
    index_search_roots: Optional[list[Path]] = None,
) -> list[dict[str, Any]]:
    """Legacy flat assets/weights/*.pth."""
    weights_dir = Path(weights_dir)
    out: list[dict[str, Any]] = []
    if not weights_dir.is_dir():
        return out
    roots = index_search_roots or []
    for p in sorted(weights_dir.glob("*.pth")):
        name = p.stem
        cover = None
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            c = p.with_suffix(ext)
            if c.is_file():
                cover = str(c.resolve())
                break
        out.append(
            {
                "name": name,
                "path": str(p.resolve()),
                "file": p.name,
                "dir": str(weights_dir.resolve()),
                "cover": cover,
                "index": _find_index(name, roots),
                "tag": guess_tag(name),
                "source": "legacy_weights",
                "missing": _model_is_broken(p),
                "pitch": None,
                "formant": None,
            }
        )
    return out


def list_voice_catalog(
    models_root: Path,
    legacy_weights: Optional[Path] = None,
    *,
    index_search_roots: Optional[list[Path]] = None,
) -> list[dict[str, Any]]:
    """Prefer User_Data catalog; append legacy weights not already present."""
    primary = list_models_in_user_data(
        models_root, index_search_roots=index_search_roots
    )
    seen_paths = {Path(m["path"]).resolve() for m in primary}
    # Prefer catalog entry over legacy same stem (avoid duplicate kikiV1 cards)
    seen_stems = {(m.get("file") or Path(m["path"]).name).lower() for m in primary}
    if legacy_weights is not None:
        for m in list_models_legacy_weights(
            legacy_weights, index_search_roots=index_search_roots
        ):
            rp = Path(m["path"]).resolve()
            stem = (m.get("file") or rp.name).lower()
            if rp in seen_paths or stem in seen_stems:
                continue
            primary.append(m)
            seen_paths.add(rp)
            seen_stems.add(stem)
    return primary


MODEL_SORT_KEYS: tuple[str, ...] = ("default", "name", "index")


def filter_sort_models(
    models: list[dict[str, Any]],
    query: str = "",
    *,
    sort: str = "default",
) -> list[dict[str, Any]]:
    """Filter the catalog by substring and sort it — UI-independent.

    * ``query``: case-insensitive substring matched against name / tag / file.
    * ``sort``: ``default`` keeps catalog order; ``name`` sorts A→Z;
      ``index`` puts models that have an ``.index`` first, then by name.

    Never mutates the input list.
    """
    q = (query or "").strip().lower()
    if q:
        def _hit(m: dict[str, Any]) -> bool:
            return any(
                q in str(m.get(k) or "").lower() for k in ("name", "tag", "file")
            )

        out = [m for m in models if _hit(m)]
    else:
        out = list(models)

    if sort == "name":
        out.sort(key=lambda m: str(m.get("name") or "").lower())
    elif sort == "index":
        out.sort(
            key=lambda m: (
                0 if (m.get("index") or "") else 1,
                str(m.get("name") or "").lower(),
            )
        )
    return out


_COVER_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_IMPORT_EXTS = frozenset({".pth", ".index", ".zip", ".png", ".jpg", ".jpeg", ".webp"})


def model_folder_layout_help() -> str:
    """User-facing placement rules (import dialog / help page)."""
    return (
        "音色装好后的固定位置：\n"
        "  User_Data/models/<名称>/\n"
        "    *.pth        模型权重（必需）\n"
        "    *.index      特征检索库（可选，与 .pth 放同一文件夹）\n"
        "    cover.jpg    封面（可选）\n"
        "    config.json  参数与绑定（软件维护）\n"
        "    profiles/    配置档案（可选）\n"
        "\n"
        "导入时可选：\n"
        "  · .pth — 装成一个音色；同目录同名 .index 会自动带上\n"
        "  · .pth + .index — 一起放进同一文件夹并绑定（推荐）\n"
        "  · 仅 .index — 复制进当前选中音色的文件夹并绑定\n"
        "  · .zip — 与社区/CNB 音色包相同，整包安装\n"
    )


def classify_import_paths(
    paths: Sequence[Union[str, Path]],
) -> dict[str, list[Path]]:
    """Split user-selected paths into zips / pths / indices / covers."""
    out: dict[str, list[Path]] = {
        "zip": [],
        "pth": [],
        "index": [],
        "cover": [],
        "other": [],
    }
    seen: set[str] = set()
    for raw in paths:
        p = Path(raw)
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if not p.is_file():
            out["other"].append(p)
            continue
        suf = p.suffix.lower()
        if suf == ".zip":
            out["zip"].append(p)
        elif suf == ".pth":
            out["pth"].append(p)
        elif suf == ".index":
            out["index"].append(p)
        elif suf in _COVER_EXTS:
            out["cover"].append(p)
        else:
            out["other"].append(p)
    return out


def match_index_for_pth(
    pth: Path, indices: Sequence[Path]
) -> Optional[Path]:
    """Pick the best .index for a .pth from a multi-select list (or siblings)."""
    pth = Path(pth)
    inds = [Path(i) for i in indices if Path(i).is_file()]
    if not inds:
        return None
    stem = pth.stem.lower()
    for ip in inds:
        if ip.stem.lower() == stem:
            return ip
    for ip in inds:
        n = ip.stem.lower()
        if stem in n or n in stem:
            return ip
    try:
        parent = pth.parent.resolve()
        same_dir = [ip for ip in inds if ip.parent.resolve() == parent]
    except Exception:
        same_dir = []
    if len(same_dir) == 1:
        return same_dir[0]
    if len(inds) == 1:
        return inds[0]
    return None


def match_cover_for_pth(pth: Path, covers: Sequence[Path]) -> Optional[Path]:
    pth = Path(pth)
    covs = [Path(c) for c in covers if Path(c).is_file()]
    if not covs:
        return None
    stem = pth.stem.lower()
    for c in covs:
        if c.stem.lower() in (stem, "cover"):
            return c
    try:
        parent = pth.parent.resolve()
        same = [c for c in covs if c.parent.resolve() == parent]
    except Exception:
        same = []
    if len(same) == 1:
        return same[0]
    if len(covs) == 1:
        return covs[0]
    return None


def import_model_to_catalog(
    src_pth: Path,
    models_root: Path,
    *,
    display_name: Optional[str] = None,
    cover_src: Optional[Path] = None,
    index_src: Optional[Path] = None,
    move: bool = False,
) -> dict[str, Any]:
    """Copy (or move) a .pth into User_Data/models/<name>/ + write config.json.

    The .index is **copied into the model folder** (not left as a loose shared
    path) so placement is always: models/<name>/*.pth + models/<name>/*.index.

    ``move=True`` removes the source files after a successful import — the
    user chose 「移动」 so the software folder becomes the single home.
    """
    src_pth = Path(src_pth)
    if not src_pth.is_file() or src_pth.suffix.lower() != ".pth":
        raise ValueError(f"not a .pth file: {src_pth}")
    name = safe_model_dir_name(display_name or src_pth.stem)
    dest_dir = Path(models_root) / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_pth = dest_dir / src_pth.name
    if dest_pth.resolve() != src_pth.resolve():
        shutil.copy2(src_pth, dest_pth)
    if cover_src and Path(cover_src).is_file():
        ext = Path(cover_src).suffix.lower() or ".png"
        if ext == ".jpeg":
            ext = ".jpg"
        shutil.copy2(cover_src, dest_dir / f"cover{ext}")
    # Auto-pick sibling .index next to the pth if not provided
    if index_src is None:
        sib = src_pth.with_suffix(".index")
        if sib.is_file():
            index_src = sib
        else:
            # same folder, any .index containing stem
            for ip in src_pth.parent.glob("*.index"):
                if src_pth.stem in ip.stem or name in ip.stem:
                    index_src = ip
                    break
    index_path = ""
    if index_src and Path(index_src).is_file():
        # Always copy into the model folder (portable pack rule)
        index_path = bind_index_to_model_dir(
            dest_dir,
            Path(index_src),
            display_name=name,
            copy_into_folder=True,
        )
        # bind_index_to_model_dir already wrote config; re-read and keep
        side = _read_sidecar(dest_dir)
        side["name"] = name
        side["tag"] = side.get("tag") or guess_tag(name)
        side["file"] = dest_pth.name
        side["source"] = "import"
        side["index"] = index_path
        files = [str(p) for p in (side.get("index_files") or [])]
        if index_path not in files:
            files.append(index_path)
        side["index_files"] = files
        _write_sidecar(dest_dir, side)
    else:
        cfg = {
            "name": name,
            "tag": guess_tag(name),
            "file": dest_pth.name,
            "source": "import",
        }
        # Preserve any pre-existing index keys if re-importing over same folder
        old = _read_sidecar(dest_dir)
        for k in ("index", "index_files", "pitch", "formant", "index_rate",
                  "rms_mix_rate", "threhold", "f0method", "active_profile"):
            if k in old and k not in cfg:
                cfg[k] = old[k]
        (dest_dir / "config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if move:
        # Source files have a safe copy inside dest_dir — remove the originals
        try:
            if dest_pth.is_file() and dest_pth.resolve() != src_pth.resolve():
                src_pth.unlink()
        except Exception:
            pass
        try:
            if (
                index_src
                and Path(index_src).is_file()
                and index_path
                and Path(index_path).resolve() != Path(index_src).resolve()
            ):
                Path(index_src).unlink()
        except Exception:
            pass
        try:
            if (
                cover_src
                and Path(cover_src).is_file()
                and Path(cover_src).resolve().parent.resolve()
                != dest_dir.resolve()
            ):
                Path(cover_src).unlink()
        except Exception:
            pass
    side = _read_sidecar(dest_dir)
    index_path = str(side.get("index") or index_path or "")
    return {
        "name": str(side.get("name") or name),
        "path": str(dest_pth.resolve()),
        "file": dest_pth.name,
        "dir": str(dest_dir.resolve()),
        "cover": _find_cover(dest_dir),
        "index": index_path,
        "tag": str(side.get("tag") or guess_tag(name)),
        "source": "user_data",
    }


def import_index_for_model(
    model_dir: Path,
    index_src: Path,
    *,
    move: bool = False,
    activate: bool = True,
) -> str:
    """Copy a standalone .index into an existing model folder and bind it.

    Placement rule: always ends up as ``model_dir / <filename>.index``.
    """
    model_dir = Path(model_dir)
    index_src = Path(index_src)
    if not model_dir.is_dir():
        raise ValueError(f"音色文件夹不存在：{model_dir}")
    if not index_src.is_file() or index_src.suffix.lower() != ".index":
        raise ValueError(f"不是 .index 文件：{index_src}")
    path = add_index_binding(
        model_dir, index_src, copy_into_folder=True, move_into_folder=move
    )
    if activate:
        set_active_index(model_dir, path)
    return path


def import_user_files(
    paths: Sequence[Union[str, Path]],
    models_root: Path,
    *,
    move: bool = False,
    current_model_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Import a multi-select of .pth / .index / covers (not zips).

    Returns a summary dict::

        {
          "models": [import_model_to_catalog results…],
          "indices": [{"path": …, "model_dir": …}, …],
          "errors": [{"path": str, "error": str}, …],
          "skipped_other": [str, …],
        }

    Zip files are listed under ``skipped_other`` — the UI should route them
    to ``install_voice_pack_zip`` separately.
    """
    groups = classify_import_paths(paths)
    summary: dict[str, Any] = {
        "models": [],
        "indices": [],
        "errors": [],
        "skipped_other": [str(p) for p in groups["other"]],
        "zips": [str(p) for p in groups["zip"]],
    }
    models_root = Path(models_root)
    pths = list(groups["pth"])
    indices = list(groups["index"])
    covers = list(groups["cover"])
    used_indices: set[str] = set()
    used_covers: set[str] = set()

    for pth in pths:
        try:
            idx = match_index_for_pth(pth, indices)
            cov = match_cover_for_pth(pth, covers)
            info = import_model_to_catalog(
                pth,
                models_root,
                cover_src=cov,
                index_src=idx,
                move=move,
            )
            summary["models"].append(info)
            if idx is not None:
                try:
                    used_indices.add(str(idx.resolve()))
                except Exception:
                    used_indices.add(str(idx))
            if cov is not None:
                try:
                    used_covers.add(str(cov.resolve()))
                except Exception:
                    used_covers.add(str(cov))
        except Exception as e:
            summary["errors"].append({"path": str(pth), "error": str(e)})

    leftover_idx = []
    for ip in indices:
        try:
            key = str(ip.resolve())
        except Exception:
            key = str(ip)
        if key not in used_indices:
            leftover_idx.append(ip)

    target_dir: Optional[Path] = None
    if leftover_idx:
        if current_model_dir and Path(current_model_dir).is_dir():
            target_dir = Path(current_model_dir)
        elif summary["models"]:
            # bind extras to the last imported model in this batch
            target_dir = Path(summary["models"][-1]["dir"])
        else:
            summary["errors"].append(
                {
                    "path": str(leftover_idx[0]),
                    "error": (
                        "只选了 .index 时，请先在音色目录里选中一个音色，"
                        "或同时选中配套的 .pth。"
                    ),
                }
            )
            leftover_idx = []

    for ip in leftover_idx:
        if target_dir is None:
            break
        try:
            bound = import_index_for_model(
                target_dir, ip, move=move, activate=True
            )
            summary["indices"].append(
                {"path": bound, "model_dir": str(target_dir.resolve())}
            )
        except Exception as e:
            summary["errors"].append({"path": str(ip), "error": str(e)})

    return summary


def discover_index_files(search_roots: list[Path]) -> list[str]:
    """Return sorted absolute paths of *.index under roots (skip *trained*)."""
    found: set[str] = set()
    for root in search_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        try:
            for ip in root.rglob("*.index"):
                if "trained" in ip.name.lower():
                    continue
                if ip.is_file():
                    found.add(str(ip.resolve()))
        except Exception:
            continue
    return sorted(found)


def bind_index_to_model_dir(
    model_dir: Path,
    index_src: Path,
    *,
    display_name: Optional[str] = None,
    copy_into_folder: bool = True,
) -> str:
    """Attach a .index file to a catalog model folder (write config.json).

    Prefer copying the index next to the .pth so the voice pack is portable.
    Returns absolute path of the index that should be used.
    """
    model_dir = Path(model_dir)
    index_src = Path(index_src)
    if not index_src.is_file() or index_src.suffix.lower() != ".index":
        raise ValueError(f"not a .index file: {index_src}")
    model_dir.mkdir(parents=True, exist_ok=True)
    if copy_into_folder:
        dest = model_dir / index_src.name
        try:
            if dest.resolve() != index_src.resolve():
                shutil.copy2(index_src, dest)
            index_path = str(dest.resolve())
        except Exception:
            index_path = str(index_src.resolve())
    else:
        index_path = str(index_src.resolve())

    side = _read_sidecar(model_dir)
    if display_name:
        side.setdefault("name", display_name)
    side["index"] = index_path
    pth = _find_pth(model_dir)
    if pth is not None:
        side.setdefault("file", pth.name)
    side.setdefault("tag", guess_tag(str(side.get("name") or model_dir.name)))
    (model_dir / "config.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return index_path


def clear_model_index(model_dir: Path) -> None:
    """Remove index binding from model config.json (does not delete files)."""
    model_dir = Path(model_dir)
    side = _read_sidecar(model_dir)
    if not side and not model_dir.is_dir():
        return
    side.pop("index", None)
    if "name" not in side:
        side["name"] = model_dir.name
    (model_dir / "config.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Index bindings: candidates live in the model folder by default.
# config.json keeps ``index`` (active) + ``index_files`` (list). Stale absolute
# paths from other installs (e.g. Grok_test\...) are sanitized away when the
# same filename already exists next to the .pth — that was the fake
# 「共享位置」 row users saw.
# --------------------------------------------------------------------------


def _write_sidecar(model_dir: Path, side: dict) -> None:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    if "name" not in side:
        side["name"] = model_dir.name
    (model_dir / "config.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _path_inside_dir(path: Path, folder: Path) -> bool:
    try:
        return path.resolve().parent.resolve() == folder.resolve()
    except Exception:
        return False


def ensure_index_in_model_dir(model_dir: Path, index_src: Path) -> str:
    """Guarantee ``index_src`` is available as a file inside ``model_dir``.

    Copies when the source is outside the model folder. Returns the local
    absolute path (always under model_dir when copy succeeds).
    """
    model_dir = Path(model_dir)
    index_src = Path(index_src)
    if not index_src.is_file() or index_src.suffix.lower() != ".index":
        raise ValueError(f"not a .index file: {index_src}")
    model_dir.mkdir(parents=True, exist_ok=True)
    if _path_inside_dir(index_src, model_dir):
        return str(index_src.resolve())
    dest = model_dir / index_src.name
    try:
        if not dest.is_file() or dest.resolve() != index_src.resolve():
            shutil.copy2(index_src, dest)
        return str(dest.resolve())
    except Exception:
        # last resort: keep original path if copy fails
        return str(index_src.resolve())


def sanitize_index_bindings(model_dir: Path) -> list[str]:
    """Dedupe + prefer files inside the model folder; rewrite config.json.

    Rules:
    - Local ``*.index`` in the model folder always win.
    - External paths with the **same filename** as a local file are dropped
      (they were the misleading 「共享位置」 duplicates from old absolute paths).
    - External paths that still exist and have no local twin are **copied in**
      so everything ends up under the model folder.
    - Missing paths are removed. Active ``index`` is healed to a local file.
    """
    model_dir = Path(model_dir)
    side = _read_sidecar(model_dir)
    candidates: list[str] = []
    if model_dir.is_dir():
        for ip in sorted(model_dir.glob("*.index")):
            candidates.append(str(ip))
    if side.get("index"):
        candidates.append(str(side.get("index")))
    for p in side.get("index_files") or []:
        candidates.append(str(p))

    # basename -> preferred absolute path (local first)
    by_name: dict[str, str] = {}
    order: list[str] = []

    def _prefer(path_str: str) -> None:
        try:
            p = Path(path_str)
            if not p.is_file():
                return
            name = p.name
            rp = str(p.resolve())
        except Exception:
            return
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = rp
            order.append(name)
            return
        # Prefer path inside model_dir
        try:
            ex = Path(existing)
            if _path_inside_dir(p, model_dir) and not _path_inside_dir(ex, model_dir):
                by_name[name] = rp
            # else keep existing (already local or first seen)
        except Exception:
            pass

    for c in candidates:
        _prefer(c)

    # Copy any remaining external-only entries into the model folder
    cleaned: list[str] = []
    for name in order:
        rp = by_name[name]
        p = Path(rp)
        if _path_inside_dir(p, model_dir):
            cleaned.append(rp)
            continue
        try:
            local = ensure_index_in_model_dir(model_dir, p)
            cleaned.append(local)
        except Exception:
            cleaned.append(rp)

    # Dedup cleaned by resolve
    seen: set[str] = set()
    final: list[str] = []
    for p in cleaned:
        try:
            r = str(Path(p).resolve())
        except Exception:
            continue
        if r in seen or not Path(r).is_file():
            continue
        seen.add(r)
        final.append(r)

    # Heal active pointer
    active_raw = str(side.get("index") or "").strip()
    active = ""
    if active_raw:
        try:
            ap = Path(active_raw)
            if ap.is_file():
                local_same = model_dir / ap.name
                if local_same.is_file():
                    active = str(local_same.resolve())
                elif _path_inside_dir(ap, model_dir):
                    active = str(ap.resolve())
                else:
                    try:
                        active = ensure_index_in_model_dir(model_dir, ap)
                    except Exception:
                        active = str(ap.resolve())
        except Exception:
            active = ""
    if active and active not in final:
        # active might already be in final under same resolve
        try:
            ar = str(Path(active).resolve())
            if ar not in {str(Path(x).resolve()) for x in final}:
                final.insert(0, ar)
            active = ar
        except Exception:
            pass
    if not active and final:
        # keep empty if user explicitly cleared; only when key missing use first
        if "index" not in side:
            active = final[0]
        elif str(side.get("index") or "").strip():
            # had a broken path — pick best local name match or first
            active = final[0]
        else:
            active = ""

    side["index_files"] = final
    side["index"] = active
    _write_sidecar(model_dir, side)
    return final


def list_index_bindings(model_dir: Path) -> list[str]:
    """All .index files for this model (sanitized, model-folder preferred).

    Side effect: rewrites config.json when stale external duplicates exist so
    the UI never shows a fake 「共享位置」 twin of a local file.
    """
    return sanitize_index_bindings(Path(model_dir))


def add_index_binding(
    model_dir: Path,
    index_src: Path,
    *,
    copy_into_folder: bool = True,
    move_into_folder: bool = False,
) -> str:
    """Bind one more .index to the model; returns the recorded path.

    Default **copies into the model folder** (portable). ``move_into_folder``
    moves instead. ``copy_into_folder=False`` only records an external path
    (discouraged; UI no longer offers this).
    Becomes the active index only when the model had none.
    """
    model_dir = Path(model_dir)
    index_src = Path(index_src)
    if not index_src.is_file() or index_src.suffix.lower() != ".index":
        raise ValueError(f"not a .index file: {index_src}")
    model_dir.mkdir(parents=True, exist_ok=True)
    if copy_into_folder or move_into_folder:
        dest = model_dir / index_src.name
        if dest.resolve() != index_src.resolve():
            if move_into_folder:
                shutil.move(str(index_src), str(dest))
            else:
                shutil.copy2(index_src, dest)
        path = str(dest.resolve())
    else:
        path = str(index_src.resolve())
    side = _read_sidecar(model_dir)
    files = [str(p) for p in (side.get("index_files") or [])]
    if path not in files:
        files.append(path)
    side["index_files"] = files
    if not str(side.get("index") or ""):
        side["index"] = path
    _write_sidecar(model_dir, side)
    return path


def remove_index_binding(model_dir: Path, index_path: str) -> None:
    """Unbind (never deletes the .index file itself)."""
    model_dir = Path(model_dir)
    side = _read_sidecar(model_dir)
    try:
        target = str(Path(index_path).resolve())
    except Exception:
        target = str(index_path)

    def _same(p: str) -> bool:
        try:
            return str(Path(p).resolve()) == target
        except Exception:
            return p == target

    side["index_files"] = [
        p for p in (side.get("index_files") or []) if not _same(str(p))
    ]
    if _same(str(side.get("index") or "")):
        side["index"] = ""
    _write_sidecar(model_dir, side)


def rename_model_display(model_dir: Path, new_name: str) -> str:
    """Change the display name shown in the app (folder/files untouched)."""
    new_name = str(new_name or "").strip()
    if not new_name:
        raise ValueError("名称不能为空")
    model_dir = Path(model_dir)
    side = _read_sidecar(model_dir)
    side["name"] = new_name
    _write_sidecar(model_dir, side)
    return new_name


def delete_model_dir(model_dir: Path, models_root: Path) -> None:
    """Delete a voice folder (model + sidecar + profiles). Guarded to the
    catalog root so a bad path can never wipe anything else."""
    md = Path(model_dir).resolve()
    root = Path(models_root).resolve()
    if root not in md.parents:
        raise ValueError(f"refuse to delete outside models root: {md}")
    shutil.rmtree(md)


def set_active_index(model_dir: Path, index_path: str) -> None:
    """Choose which bound .index the engine uses ("" = use none).

    Non-empty paths are always copied into the model folder first, so the
    active pointer never stays on a foreign absolute path (other install /
    other model). That makes「使用」actually stick in the UI.
    """
    model_dir = Path(model_dir)
    path = str(index_path or "").strip()
    if not path:
        side = _read_sidecar(model_dir)
        side["index"] = ""
        _write_sidecar(model_dir, side)
        return
    local = ensure_index_in_model_dir(model_dir, Path(path))
    side = _read_sidecar(model_dir)
    files = [str(p) for p in (side.get("index_files") or [])]
    if local not in files:
        files.append(local)
    side["index_files"] = files
    side["index"] = local
    _write_sidecar(model_dir, side)
    # Drop stale external twins with the same filename
    sanitize_index_bindings(model_dir)
    side = _read_sidecar(model_dir)
    side["index"] = local
    _write_sidecar(model_dir, side)


# Per-voice hot params stored in User_Data/models/<name>/config.json
VOICE_PARAM_KEYS: tuple[str, ...] = (
    "pitch",
    "formant",
    "index_rate",
    "rms_mix_rate",
    "threhold",
    "f0method",
)


def voice_params_from_side(side: dict[str, Any]) -> dict[str, Any]:
    """Return only keys that are explicitly set (not null/empty) on a sidecar."""
    out: dict[str, Any] = {}
    if not isinstance(side, dict):
        return out
    for k in VOICE_PARAM_KEYS:
        if k not in side:
            continue
        v = side.get(k)
        if v is None or v == "":
            continue
        out[k] = v
    return out


def get_model_voice_params(model_dir: Path) -> dict[str, Any]:
    """Read per-model voice params from config.json (missing keys omitted)."""
    return voice_params_from_side(_read_sidecar(Path(model_dir)))


def save_model_voice_params(
    model_dir: Path,
    params: dict[str, Any],
    *,
    display_name: Optional[str] = None,
) -> dict[str, Any]:
    """Merge voice params into model folder config.json. Returns full sidecar."""
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        raise ValueError(f"model dir missing: {model_dir}")
    side = _read_sidecar(model_dir)
    if display_name:
        side["name"] = str(display_name)
    elif "name" not in side:
        side["name"] = model_dir.name
    pth = _find_pth(model_dir)
    if pth is not None:
        side.setdefault("file", pth.name)
    side.setdefault("tag", guess_tag(str(side.get("name") or model_dir.name)))

    for k in VOICE_PARAM_KEYS:
        if k not in params:
            continue
        v = params.get(k)
        if v is None or v == "":
            # explicit clear
            side[k] = None
            continue
        if k == "pitch":
            side[k] = int(round(float(v)))
        elif k == "threhold":
            side[k] = int(round(float(v)))
        elif k == "f0method":
            side[k] = str(v)
        else:
            side[k] = float(v)

    cfg_path = model_dir / "config.json"
    cfg_path.write_text(
        json.dumps(side, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return side
