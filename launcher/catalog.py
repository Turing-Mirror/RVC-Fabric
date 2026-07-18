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
        index = str(side.get("index") or "") or _find_index(name, roots)
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
    cfg = {
        "name": name,
        "tag": guess_tag(name),
        "file": dest_pth.name,
    }
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
        "index": "",
        "tag": cfg["tag"],
        "source": "user_data",
    }
