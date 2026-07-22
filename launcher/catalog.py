# -*- coding: utf-8 -*-
"""Voice model catalog under User_Data (RVCMAX job split; not engine assets).

Preferred layout (product story)::

    User_Data/models/<name>/
        *.pth
        cover.png|jpg   (optional)
        config.json     (optional: pitch, formant, tag, index)

Legacy fallback: flat ``assets/weights/*.pth`` still listed, tagged as legacy.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional

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
    for root in search_roots:
        if not root.is_dir():
            continue
        for ip in root.rglob("*.index"):
            if "trained" in ip.name:
                continue
            if name in ip.name or name in str(ip):
                return str(ip.resolve())
    return ""


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
        index = str(side.get("index") or "")
        if index and not Path(index).is_file():
            index = ""
        if not index:
            # Prefer .index sitting next to the .pth in this folder
            local_idx = sorted(folder.glob("*.index"))
            if local_idx:
                index = str(local_idx[0].resolve())
        if not index:
            index = _find_index(name, roots) or _find_index(pth.stem, roots)
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
    shutil.copy2(src_pth, dest_pth)
    if cover_src and Path(cover_src).is_file():
        ext = Path(cover_src).suffix.lower() or ".png"
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
        index_path = bind_index_to_model_dir(dest_dir, Path(index_src), display_name=name)
    cfg = {
        "name": name,
        "tag": guess_tag(name),
        "file": dest_pth.name,
    }
    if index_path:
        cfg["index"] = index_path
        cfg["index_files"] = [index_path]
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
    return {
        "name": name,
        "path": str(dest_pth.resolve()),
        "file": dest_pth.name,
        "dir": str(dest_dir.resolve()),
        "cover": _find_cover(dest_dir),
        "index": index_path,
        "tag": cfg["tag"],
        "source": "user_data",
    }


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
# Index bindings (many-to-many): a model keeps a LIST of candidate .index
# files in its sidecar ("index_files") plus the active one ("index", kept for
# engine compatibility). The same .index path may appear in several models'
# lists — that is what makes the binding many-to-many.
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


def list_index_bindings(model_dir: Path) -> list[str]:
    """All .index files bound to this model (existing files only, deduped).

    Union of: sidecar ``index_files``, the active ``index``, and any .index
    sitting inside the model folder. Order: model-folder files first, then
    the rest in recorded order.
    """
    model_dir = Path(model_dir)
    side = _read_sidecar(model_dir)
    seen: set[str] = set()
    out: list[str] = []

    def _add(p: str) -> None:
        try:
            rp = str(Path(p).resolve())
        except Exception:
            return
        if rp in seen or not Path(rp).is_file():
            return
        seen.add(rp)
        out.append(rp)

    if model_dir.is_dir():
        for ip in sorted(model_dir.glob("*.index")):
            _add(str(ip))
    _add(str(side.get("index") or ""))
    for p in side.get("index_files") or []:
        _add(str(p))
    return out


def add_index_binding(
    model_dir: Path,
    index_src: Path,
    *,
    copy_into_folder: bool = False,
    move_into_folder: bool = False,
) -> str:
    """Bind one more .index to the model; returns the recorded path.

    ``copy_into_folder`` copies the file next to the .pth (portable pack);
    ``move_into_folder`` moves it instead; default records the source path
    (shared index — the same file can stay bound to other models too).
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
    """Choose which bound .index the engine uses ("" = use none)."""
    model_dir = Path(model_dir)
    side = _read_sidecar(model_dir)
    path = str(index_path or "").strip()
    if path:
        path = str(Path(path).resolve())
        files = [str(p) for p in (side.get("index_files") or [])]
        if path not in files:
            files.append(path)
            side["index_files"] = files
    side["index"] = path
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
