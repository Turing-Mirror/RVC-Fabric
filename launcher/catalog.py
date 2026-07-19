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
        if pth is None:
            continue
        side = _read_sidecar(folder)
        name = str(side.get("name") or folder.name)
        tag = str(side.get("tag") or guess_tag(name))
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
        out.append(
            {
                "name": name,
                "path": str(pth.resolve()),
                "file": pth.name,
                "dir": str(folder.resolve()),
                "cover": cover,
                "index": index,
                "tag": tag,
                "source": "user_data",
                "pitch": side.get("pitch"),
                "formant": side.get("formant"),
            }
        )
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


def import_model_to_catalog(
    src_pth: Path,
    models_root: Path,
    *,
    display_name: Optional[str] = None,
    cover_src: Optional[Path] = None,
    index_src: Optional[Path] = None,
) -> dict[str, Any]:
    """Copy a .pth into User_Data/models/<name>/ and write config.json."""
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
    (dest_dir / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
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
