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
    normalize_voice_meta,
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
        info = install_voice_pack_url(
            entry.pack_url,
            voice_id=entry.id,
            display_name=entry.name,
            tag=entry.tag,
            version=entry.version,
            models_root=models_root,
            progress=progress,
            expected_sha256=entry.sha256 or "",
        )
        # Catalog author/date fill gaps when pack config omitted them
        _merge_entry_identity_into_installed(info, entry)
        return info

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
    cover_cfg = ""
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
                from launcher.catalog import install_cover_to_ch_banner

                abs_c, rel_c = install_cover_to_ch_banner(
                    cov_tmp, vid, also_model_dir=dest_dir
                )
                cover_path = abs_c or str((dest_dir / f"cover{ext}").resolve())
                cover_cfg = rel_c or f"cover{ext}"
                if not abs_c:
                    dest_cov = dest_dir / f"cover{ext}"
                    shutil.copy2(cov_tmp, dest_cov)
                    cover_path = str(dest_cov.resolve())
        except Exception:
            pass

    extra = _entry_identity_extra(entry)
    if cover_cfg:
        extra["cover"] = cover_cfg
    return _write_voice_config(
        dest_dir,
        dest_pth=dest_pth,
        name=entry.name or vid,
        tag=entry.tag,
        version=entry.version,
        online_id=entry.id,
        index_path=index_path,
        cover_path=cover_path,
        cover_cfg=cover_cfg,
        source="online_files",
        extra=extra or None,
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


def _entry_identity_extra(entry: VoiceEntry) -> dict:
    """Catalog-level identity fallbacks when the zip has no config.json fields."""
    extra: dict = {}
    if entry.author:
        extra["author"] = entry.author
    if entry.author_url:
        extra["author_url"] = entry.author_url
    if entry.date:
        extra["date"] = entry.date
    return extra


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

        # merge optional config.json from pack (identity + params)
        pack_cfg: dict = {}
        cfg_file = content / VOICE_CONFIG_NAME
        if cfg_file.is_file():
            try:
                pack_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                if not isinstance(pack_cfg, dict):
                    pack_cfg = {}
            except Exception:
                pack_cfg = {}

        tm_meta: dict = {}
        tm_meta_path = content / TM_PACKAGE_JSON
        if tm_meta_path.is_file():
            try:
                tm_meta = json.loads(tm_meta_path.read_text(encoding="utf-8"))
                if not isinstance(tm_meta, dict):
                    tm_meta = {}
            except Exception:
                tm_meta = {}

        # Identity: config.json wins, then tm_package.json
        identity = normalize_voice_meta(tm_meta)
        identity.update(normalize_voice_meta(pack_cfg))

        # Cover: config.cover relative path first, then conventional names
        cover_path = ""
        cover_rel = identity.get("cover") or ""
        if cover_rel:
            c = content / cover_rel
            if c.is_file() and c.stat().st_size > 500:
                dest_name = Path(cover_rel).name
                dest_c = dest_dir / dest_name
                shutil.copy2(c, dest_c)
                cover_path = str(dest_c.resolve())
        if not cover_path:
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
                for f in found:
                    if f.name.lower() in (TM_PACKAGE_JSON, VOICE_CONFIG_NAME):
                        continue
                    if 500 < f.stat().st_size < 8_000_000:
                        dest_c = dest_dir / f"cover{ext if ext != '.jpeg' else '.jpg'}"
                        shutil.copy2(f, dest_c)
                        cover_path = str(dest_c.resolve())
                        break
                if cover_path:
                    break

        name = str(identity.get("name") or pack_cfg.get("name") or name)
        tag = str(pack_cfg.get("tag") or tag or guess_tag(name))

        extra = {
            k: pack_cfg[k]
            for k in ("pitch", "formant", "index_rate", "rms_mix_rate", "threhold", "f0method")
            if k in pack_cfg
        }
        for k in ("publisher", "fabric_official", "is_rvc_fabric"):
            if k in pack_cfg:
                extra[k] = pack_cfg[k]
            elif k in tm_meta and k not in extra:
                extra[k] = tm_meta[k]
        if tm_meta.get("voice_id") and not vid:
            vid = str(tm_meta.get("voice_id") or vid)
        # Persist identity fields into installed config.json
        for k in ("author", "author_url", "date"):
            if identity.get(k):
                extra[k] = identity[k]
        # Cover → User_Data/ch-banner/<id>.ext + model folder; config stores ch-banner path
        cover_cfg = ""
        if cover_path and Path(cover_path).is_file():
            try:
                from launcher.catalog import install_cover_to_ch_banner

                abs_c, rel_c = install_cover_to_ch_banner(
                    Path(cover_path), vid, also_model_dir=dest_dir
                )
                if abs_c:
                    cover_path = abs_c
                    cover_cfg = rel_c
            except Exception:
                cover_cfg = Path(cover_path).name
        if cover_cfg:
            extra["cover"] = cover_cfg

        return _write_voice_config(
            dest_dir,
            dest_pth=dest_pth,
            name=name,
            tag=tag,
            version=str(pack_cfg.get("version") or version),
            online_id=vid,
            index_path=index_path or str(pack_cfg.get("index") or ""),
            cover_path=cover_path,
            cover_cfg=cover_cfg,
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


def _merge_entry_identity_into_installed(info: dict, entry: VoiceEntry) -> None:
    """If installed config lacks author/date, copy from catalog entry."""
    d = Path(info.get("dir") or "")
    if not d.is_dir():
        return
    cfg_path = d / VOICE_CONFIG_NAME
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    changed = False
    for k, v in _entry_identity_extra(entry).items():
        if v and not cfg.get(k):
            cfg[k] = v
            changed = True
    if changed:
        cfg_path.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _portable_cover_rel(cover: str, dest_dir: Path) -> str:
    """Normalize cover for config.json — never store drive-absolute paths."""
    s = (cover or "").strip().replace("\\", "/")
    if not s:
        return ""
    if s.lower().startswith(("http://", "https://")):
        return s  # remote catalog only; not used as local install path
    # Already portable
    if s.startswith("ch-banner/"):
        return s
    p = Path(cover)
    try:
        if p.is_file():
            # under model dir → cover.jpg
            if p.parent.resolve() == Path(dest_dir).resolve():
                return p.name
            # under User_Data/ch-banner → ch-banner/name
            from launcher.paths import CH_BANNER_DIR, ROOT

            for base, prefix in (
                (CH_BANNER_DIR, "ch-banner/"),
                (ROOT / "ch-banner", "ch-banner/"),
            ):
                try:
                    if p.resolve().is_relative_to(base.resolve()):
                        return prefix + p.name
                except Exception:
                    try:
                        rel = p.resolve().relative_to(base.resolve())
                        return prefix + str(rel).replace("\\", "/")
                    except Exception:
                        pass
            # fallback: just filename (resolve via ch-banner by id later)
            return p.name
    except Exception:
        pass
    # strip accidental Windows abs like L:\...\ch-banner\x.jpg
    low = s.lower()
    idx = low.find("ch-banner/")
    if idx >= 0:
        return s[idx:]
    return Path(s).name


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
    cover_cfg: str = "",
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
    # cover 只写相对路径，禁止绝对盘符路径（换盘/搬家可移植）
    # 规范：ch-banner/<id>.jpg  或  音色目录内 cover.jpg
    if cover_cfg:
        cfg["cover"] = _portable_cover_rel(cover_cfg, dest_dir)
    elif cover_path:
        cfg["cover"] = _portable_cover_rel(cover_path, dest_dir)
    if extra:
        cfg.update(extra)
        if cfg.get("cover"):
            cfg["cover"] = _portable_cover_rel(str(cfg["cover"]), dest_dir)
        elif cover_cfg:
            cfg["cover"] = _portable_cover_rel(cover_cfg, dest_dir)
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
