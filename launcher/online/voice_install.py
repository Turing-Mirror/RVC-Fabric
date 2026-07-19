# -*- coding: utf-8 -*-
"""Install a voice model from catalog entry into User_Data/models."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, Optional

from launcher.catalog import guess_tag, safe_model_dir_name
from launcher.online.catalog import VoiceEntry
from launcher.online.downloader import DownloadError, download_file
from launcher.paths import MODELS_DIR, USER_DATA

ProgressCb = Callable[[str, int, int], None]  # phase, done, total


def install_voice_from_entry(
    entry: VoiceEntry,
    *,
    models_root: Optional[Path] = None,
    progress: Optional[ProgressCb] = None,
) -> dict:
    """Download pth/index/cover into User_Data/models/<id>/."""
    models_root = Path(models_root or MODELS_DIR)
    if not entry.pth_url:
        raise DownloadError("该音色没有 pth 下载地址")
    vid = safe_model_dir_name(entry.id or entry.name)
    dest_dir = models_root / vid
    dest_dir.mkdir(parents=True, exist_ok=True)
    cache = USER_DATA / "update_cache" / "voices" / vid
    cache.mkdir(parents=True, exist_ok=True)

    def _prog(phase: str):
        def inner(done: int, total: int) -> None:
            if progress:
                progress(phase, done, total)

        return inner

    pth_name = f"{vid}.pth"
    pth_tmp = cache / pth_name
    download_file(
        entry.pth_url,
        pth_tmp,
        progress=_prog("pth"),
        expected_sha256=entry.sha256 or "",
    )
    # size sanity
    if pth_tmp.stat().st_size < 50_000:
        raise DownloadError("下载的模型文件过小，可能不是有效 .pth")

    dest_pth = dest_dir / pth_name
    shutil.copy2(pth_tmp, dest_pth)

    index_path = ""
    if entry.index_url:
        idx_tmp = cache / f"{vid}.index"
        try:
            download_file(entry.index_url, idx_tmp, progress=_prog("index"))
            if idx_tmp.stat().st_size > 1000:
                dest_idx = dest_dir / f"{vid}.index"
                shutil.copy2(idx_tmp, dest_idx)
                index_path = str(dest_idx.resolve())
        except Exception:
            pass

    cover_path = ""
    if entry.cover_url:
        ext = ".jpg"
        low = entry.cover_url.lower()
        for e in (".png", ".jpg", ".jpeg", ".webp"):
            if e in low:
                ext = e if e != ".jpeg" else ".jpg"
                break
        cov_tmp = cache / f"cover{ext}"
        try:
            download_file(entry.cover_url, cov_tmp, progress=_prog("cover"))
            if cov_tmp.stat().st_size > 500:
                dest_cov = dest_dir / f"cover{ext}"
                shutil.copy2(cov_tmp, dest_cov)
                cover_path = str(dest_cov.resolve())
        except Exception:
            pass

    cfg = {
        "name": entry.name or vid,
        "tag": entry.tag or guess_tag(entry.name or vid),
        "file": dest_pth.name,
        "version": entry.version,
        "source": "online",
        "online_id": entry.id,
    }
    if index_path:
        cfg["index"] = index_path
    if cover_path:
        cfg["cover"] = cover_path
    (dest_dir / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "name": cfg["name"],
        "path": str(dest_pth.resolve()),
        "dir": str(dest_dir.resolve()),
        "index": index_path,
        "cover": cover_path or None,
        "id": vid,
    }
