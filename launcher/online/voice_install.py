# -*- coding: utf-8 -*-
"""Install voice models: multi-file URLs or voice_pack zip.

See docs/在线更新与音色库.md and package_spec.voice_pack_layout_help().
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

from launcher.catalog import guess_tag, safe_model_dir_name
from launcher.online.catalog import VoiceEntry
from launcher.online.downloader import DownloadError, download_file
from launcher.online.package_spec import (
    PKG_VOICE_FILES,
    PKG_VOICE_PACK,
    TM_PACKAGE_JSON,
    VOICE_CONFIG_NAME,
    VOICE_COVER_NAMES,
    detect_zip_package_type,
    normalize_package_type,
    read_zip_tm_package,
)
from launcher.paths import MODELS_DIR, USER_DATA

ProgressCb = Callable[[str, int, int], None]  # phase, done, total
MIN_PTH_BYTES = 50_000


def install_voice_from_entry(
    entry: VoiceEntry,
    *,
    models_root: Optional[Path] = None,
    progress: Optional[ProgressCb] = None,
) -> dict:
    """Install by package_type: voice_pack (zip) or voice_files (urls)."""
    models_root = Path(models_root or MODELS_DIR)
    pkg = normalize_package_type(
        entry.package_type or "",
        default=PKG_VOICE_PACK if entry.pack_url else PKG_VOICE_FILES,
    )

    if entry.pack_url or pkg == PKG_VOICE_PACK:
        if not entry.pack_url:
            raise DownloadError("voice_pack 类型需要 pack_url（音色 zip 直链）")
        return install_voice_pack_url(
            entry.pack_url,
            voice_id=entry.id,
            display_name=entry.name,
            tag=entry.tag,
            version=entry.version,
            models_root=models_root,
            progress=progress,
            expected_sha256=entry.sha256 or "",
        )

    if not entry.pth_url:
        raise DownloadError(
            "音色未配置下载地址：需要 pth_url（多文件）或 pack_url（zip 包）"
        )
    return install_voice_files(
        entry,
        models_root=models_root,
        progress=progress,
    )


def install_voice_files(
    entry: VoiceEntry,
    *,
    models_root: Path,
    progress: Optional[ProgressCb] = None,
) -> dict:
    """Download separate pth / index / cover into User_Data/models/<id>/."""
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
    if pth_tmp.stat().st_size < MIN_PTH_BYTES:
        raise DownloadError("下载的模型文件过小，可能不是有效 .pth")

    # clear old pths to avoid multiple conflicting weights
    for old in dest_dir.glob("*.pth"):
        try:
            old.unlink()
        except OSError:
            pass
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
                ext = ".jpg" if e == ".jpeg" else e
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

    return _write_voice_config(
        dest_dir,
        dest_pth=dest_pth,
        name=entry.name or vid,
        tag=entry.tag,
        version=entry.version,
        online_id=entry.id,
        index_path=index_path,
        cover_path=cover_path,
        source="online_files",
    )


def install_voice_pack_url(
    pack_url: str,
    *,
    voice_id: str = "",
    display_name: str = "",
    tag: str = "音色",
    version: str = "1",
    models_root: Optional[Path] = None,
    progress: Optional[ProgressCb] = None,
    expected_sha256: str = "",
) -> dict:
    """Download voice zip and install."""
    models_root = Path(models_root or MODELS_DIR)
    cache = USER_DATA / "update_cache" / "voice_packs"
    cache.mkdir(parents=True, exist_ok=True)
    zpath = cache / f"{safe_model_dir_name(voice_id or 'voice')}.zip"

    def _p(done: int, total: int) -> None:
        if progress:
            progress("pack", done, total)

    download_file(
        pack_url, zpath, progress=_p, expected_sha256=expected_sha256
    )
    return install_voice_pack_zip(
        zpath,
        voice_id=voice_id,
        display_name=display_name,
        tag=tag,
        version=version,
        models_root=models_root,
    )


def install_voice_pack_zip(
    zip_path: Path,
    *,
    voice_id: str = "",
    display_name: str = "",
    tag: str = "音色",
    version: str = "1",
    models_root: Optional[Path] = None,
) -> dict:
    """Extract voice_pack zip into User_Data/models/<id>/."""
    models_root = Path(models_root or MODELS_DIR)
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise DownloadError(f"找不到音色包：{zip_path}")

    detected = detect_zip_package_type(zip_path)
    if detected == "full_package":
        raise DownloadError("该 zip 是全量软件包，不是音色包。")
    if detected == "gui_patch":
        # still allow if it contains pth
        pass

    meta = read_zip_tm_package(zip_path)
    vid = safe_model_dir_name(
        voice_id
        or meta.get("voice_id")
        or meta.get("id")
        or display_name
        or zip_path.stem
    )
    name = (
        display_name
        or str(meta.get("name") or "")
        or vid
    )
    tag = tag or str(meta.get("tag") or "音色")
    version = version or str(meta.get("version") or "1")

    dest_dir = models_root / vid
    # clean reinstall of pack contents
    if dest_dir.is_dir():
        for p in dest_dir.iterdir():
            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tm_voice_") as td:
        tmp = Path(td)
        # Safe extract (reject zip-slip ../ members)
        from launcher.online.safe_zip import UnsafeZipError, safe_extract_zip

        try:
            safe_extract_zip(zip_path, tmp)
        except UnsafeZipError as e:
            raise DownloadError(f"音色包路径不安全：{e}") from e
        # Find content root (optional single folder)
        content = _voice_content_root(tmp)
        pth = _find_first(content, "*.pth")
        if pth is None:
            raise DownloadError(
                "音色包内没有 .pth 文件。\n"
                "请按规范打包：zip 内包含至少一个 *.pth，可选 *.index / cover.* / config.json"
            )
        if pth.stat().st_size < MIN_PTH_BYTES:
            raise DownloadError("音色包内 .pth 过小，可能损坏")

        dest_pth = dest_dir / pth.name
        shutil.copy2(pth, dest_pth)

        index_path = ""
        idx = _find_first(content, "*.index")
        if idx is not None and idx.stat().st_size > 1000:
            dest_idx = dest_dir / idx.name
            shutil.copy2(idx, dest_idx)
            index_path = str(dest_idx.resolve())

        cover_path = ""
        for cname in VOICE_COVER_NAMES:
            c = content / cname
            if c.is_file() and c.stat().st_size > 500:
                dest_c = dest_dir / c.name
                shutil.copy2(c, dest_c)
                cover_path = str(dest_c.resolve())
                break
        if not cover_path:
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                found = list(content.glob(f"*{ext}"))
                # skip random huge assets; prefer small images
                for f in found:
                    if f.name.lower() == TM_PACKAGE_JSON:
                        continue
                    if 500 < f.stat().st_size < 8_000_000:
                        dest_c = dest_dir / f"cover{ext if ext != '.jpeg' else '.jpg'}"
                        shutil.copy2(f, dest_c)
                        cover_path = str(dest_c.resolve())
                        break
                if cover_path:
                    break

        # merge optional config.json from pack
        pack_cfg: dict = {}
        cfg_file = content / VOICE_CONFIG_NAME
        if cfg_file.is_file():
            try:
                pack_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                if not isinstance(pack_cfg, dict):
                    pack_cfg = {}
            except Exception:
                pack_cfg = {}

        name = str(pack_cfg.get("name") or name)
        tag = str(pack_cfg.get("tag") or tag or guess_tag(name))

        extra = {
            k: pack_cfg[k]
            for k in ("pitch", "formant", "index_rate", "rms_mix_rate", "threhold", "f0method")
            if k in pack_cfg
        }
        # Prefer pack stamps when present (tm_package / config from CNB pack)
        for k in ("publisher", "fabric_official", "is_rvc_fabric"):
            if k in pack_cfg:
                extra[k] = pack_cfg[k]
        tm_meta_path = content / TM_PACKAGE_JSON
        if tm_meta_path.is_file():
            try:
                tm = json.loads(tm_meta_path.read_text(encoding="utf-8"))
                if isinstance(tm, dict):
                    for k in ("publisher", "fabric_official", "voice_id"):
                        if k in tm and k not in extra:
                            if k == "voice_id" and not vid:
                                vid = str(tm.get("voice_id") or vid)
                            elif k != "voice_id":
                                extra[k] = tm[k]
            except Exception:
                pass
        return _write_voice_config(
            dest_dir,
            dest_pth=dest_pth,
            name=name,
            tag=tag,
            version=str(pack_cfg.get("version") or version),
            online_id=vid,
            index_path=index_path or str(pack_cfg.get("index") or ""),
            cover_path=cover_path,
            source="online_pack",
            extra=extra,
        )


def _voice_content_root(extracted: Path) -> Path:
    """If zip has single top dir, use it; else extracted root."""
    # ignore __MACOSX
    kids = [
        p
        for p in extracted.iterdir()
        if p.name not in ("__MACOSX", ".DS_Store") and not p.name.startswith(".")
    ]
    if len(kids) == 1 and kids[0].is_dir():
        # if that dir has pth or nested
        if list(kids[0].glob("*.pth")) or list(kids[0].rglob("*.pth")):
            # if pth only in nested, still prefer this folder as walk root
            return kids[0]
    return extracted


def _find_first(root: Path, pattern: str) -> Optional[Path]:
    direct = sorted(root.glob(pattern))
    if direct:
        return direct[0]
    nested = sorted(root.rglob(pattern))
    for p in nested:
        if "__macosx" in str(p).lower():
            continue
        return p
    return None


def _write_voice_config(
    dest_dir: Path,
    *,
    dest_pth: Path,
    name: str,
    tag: str,
    version: str,
    online_id: str,
    index_path: str,
    cover_path: str,
    source: str,
    extra: Optional[dict] = None,
) -> dict:
    # Official RVC Fabric library installs always stamp publisher so consult
    # pack / free-vs-paid paths recognize them offline (also matches catalog id).
    cfg = {
        "name": name,
        "tag": tag or guess_tag(name),
        "file": dest_pth.name,
        "version": version,
        "source": source,
        "online_id": online_id,
        "publisher": "rvc_fabric",
        "fabric_official": True,
    }
    if index_path and Path(index_path).is_file():
        cfg["index"] = str(Path(index_path).resolve())
    if cover_path:
        cfg["cover"] = cover_path
    if extra:
        cfg.update(extra)
    # Do not let pack config wipe official stamps unless pack is not fabric
    if source in ("online_pack", "online_files"):
        cfg["publisher"] = "rvc_fabric"
        cfg["fabric_official"] = True
        if online_id:
            cfg["online_id"] = online_id
    (dest_dir / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "name": cfg["name"],
        "path": str(dest_pth.resolve()),
        "dir": str(dest_dir.resolve()),
        "index": cfg.get("index") or "",
        "cover": cover_path or None,
        "id": online_id,
        "package_type": PKG_VOICE_PACK if source == "online_pack" else PKG_VOICE_FILES,
    }
