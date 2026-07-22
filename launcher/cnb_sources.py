# -*- coding: utf-8 -*-
"""CNB release catalog helpers for Setup / Runtime provision.

Product downloads use public HTTPS only (no cnb CLI on end-user PCs).

- **Runtime**：优先 CNB **Release 附件**（``…/-/releases/download/<tag>/<file>``）
- **音色 / 其它大文件**：CNB **Git LFS**（``…/-/lfs/<sha256>``）
- **小文本清单**：``…/-/git/raw/main/…``

官方仓：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases
运维 CLI 见 ``CNB-GIT-RELEASE/SYNC_COMMANDS.txt`` / cnb skill（本机打包用）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CNB_HOST = "https://cnb.cool"
CNB_API = "https://api.cnb.cool"
CNB_ORG_REPO = "Turing-Mirror/RVC-Fabric-Releases"
CNB_REPO_URL = f"{CNB_HOST}/{CNB_ORG_REPO}"
CNB_RAW_MAIN = f"{CNB_HOST}/{CNB_ORG_REPO}/-/git/raw/main"
CNB_LFS_BASE = f"{CNB_HOST}/{CNB_ORG_REPO}/-/lfs"

# Release tag used for green Runtime tarballs (see cnb releases list-releases)
DEFAULT_RUNTIME_RELEASE_TAG = "RVC-runtime"

MANIFEST_URLS = (
    f"{CNB_RAW_MAIN}/catalog/online_catalog.snippet.json",
    f"{CNB_RAW_MAIN}/manifest.json",
)

# Embedded fallback when network catalog is unreachable (sha256 from packed artifacts)
_FALLBACK_RUNTIMES: dict[str, dict[str, Any]] = {
    "nvidia": {
        "variant": "nvidia",
        "label": "NVIDIA CUDA",
        "version": "2026.07.21",
        "format": "tar",
        "size_bytes": 6077133824,
        "extract_root": "Runtime",
        "release_tag": DEFAULT_RUNTIME_RELEASE_TAG,
        "parts": [
            {
                "name": "runtime-nvidia-2026.07.21.tar",
                "size_bytes": 6077133824,
                "sha256": "d76ac4e8140490bda1abac8df2718bfec95f8a696c8a5ba730a5e7e901421d9b",
            }
        ],
    },
    "amd": {
        "variant": "amd",
        "label": "AMD/Intel DirectML",
        "version": "2026.07.21",
        "format": "tar",
        "size_bytes": 1801268224,
        "extract_root": "Runtime",
        "release_tag": DEFAULT_RUNTIME_RELEASE_TAG,
        "parts": [
            {
                "name": "runtime-amd-2026.07.21.tar",
                "size_bytes": 1801268224,
                "sha256": "5d5e4437c70ac1cf368232829381170d5a88f457eed20d14d35b1ef155dd0274",
            }
        ],
    },
    "nvidia50": {
        "variant": "nvidia50",
        "label": "NVIDIA 50 系 CUDA",
        "version": "2026.07.21",
        "format": "tar",
        "size_bytes": 6698774016,
        "extract_root": "Runtime",
        "release_tag": DEFAULT_RUNTIME_RELEASE_TAG,
        "parts": [
            {
                "name": "runtime-nvidia50-2026.07.21.tar",
                "size_bytes": 6698774016,
                "sha256": "a828e13e23589447f25b16b9314b6d730a1a7701e973613bc97d80a026102489",
            }
        ],
    },
}

VARIANT_LABELS = {
    "nvidia": "NVIDIA（推荐大多数 N 卡）",
    "amd": "AMD / Intel（DirectML）",
    "nvidia50": "NVIDIA 50 系（RTX 50xx）",
}


def cnb_lfs_url(sha256: str) -> str:
    oid = re.sub(r"[^0-9a-fA-F]", "", (sha256 or "").strip()).lower()
    if len(oid) != 64:
        raise ValueError("sha256 必须是 64 位 hex")
    return f"{CNB_LFS_BASE}/{oid}"


def cnb_release_download_url(tag: str, filename: str) -> str:
    """Browser download URL for a CNB Release asset."""
    tag = (tag or DEFAULT_RUNTIME_RELEASE_TAG).strip().lstrip("/")
    name = (filename or "").strip().lstrip("/")
    if not name:
        raise ValueError("empty release asset name")
    return f"{CNB_HOST}/{CNB_ORG_REPO}/-/releases/download/{tag}/{name}"


def cnb_release_api_url(tag: str, filename: str) -> str:
    tag = (tag or DEFAULT_RUNTIME_RELEASE_TAG).strip().lstrip("/")
    name = (filename or "").strip().lstrip("/")
    return f"{CNB_API}/{CNB_ORG_REPO}/-/releases/download/{tag}/{name}"


def http_get_text(url: str, *, timeout: float = 30.0) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "RVCFabric-Setup/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def http_get_json(url: str, *, timeout: float = 30.0) -> Any:
    return json.loads(http_get_text(url, timeout=timeout))


def fetch_remote_catalog(*, timeout: float = 30.0) -> dict[str, Any]:
    """Fetch online catalog snippet or manifest; first success wins."""
    errors: list[str] = []
    for url in MANIFEST_URLS:
        try:
            data = http_get_json(url, timeout=timeout)
            if isinstance(data, dict):
                data["_source_url"] = url
                return data
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            errors.append(f"{url}: {e}")
    raise RuntimeError("无法拉取 CNB 清单：\n" + "\n".join(errors[:4]))


def load_bundled_runtime_catalog() -> dict[str, Any]:
    """Prefer product ``configs/online_catalog.json`` runtimes if present."""
    try:
        from launcher.paths import ROOT

        for rel in (
            "configs/online_catalog.json",
            "configs/inuse/online_catalog.json",
        ):
            p = ROOT / rel
            if not p.is_file():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("runtimes"):
                return data
    except Exception:
        pass
    return {"runtimes": dict(_FALLBACK_RUNTIMES), "schema": 1, "_source": "embedded"}


@dataclass
class RuntimePart:
    name: str
    sha256: str
    size_bytes: int = 0
    urls: list[str] = field(default_factory=list)


@dataclass
class RuntimeSpec:
    variant: str
    label: str
    version: str
    format: str
    size_bytes: int
    extract_root: str
    parts: list[RuntimePart]
    release_tag: str = DEFAULT_RUNTIME_RELEASE_TAG

    @property
    def primary(self) -> RuntimePart:
        if not self.parts:
            raise ValueError(f"Runtime {self.variant} 无下载部件")
        return self.parts[0]


def _normalize_part(
    part: dict[str, Any],
    *,
    release_tag: str,
) -> RuntimePart:
    name = str(part.get("name") or part.get("file") or "").strip()
    sha = re.sub(r"[^0-9a-fA-F]", "", str(part.get("sha256") or "")).lower()
    size = int(part.get("size_bytes") or 0)
    urls: list[str] = []
    # 1) explicit urls from catalog
    raw_urls = part.get("urls") or part.get("url")
    if isinstance(raw_urls, str) and raw_urls.strip():
        urls.append(raw_urls.strip())
    elif isinstance(raw_urls, list):
        for u in raw_urls:
            if isinstance(u, str) and u.strip():
                urls.append(u.strip())
    # 2) Release (preferred for Runtime)
    if name:
        rel = cnb_release_download_url(release_tag, name)
        if rel not in urls:
            urls.insert(0, rel)
    # 3) LFS fallback
    if len(sha) == 64:
        lfs = cnb_lfs_url(sha)
        if lfs not in urls:
            urls.append(lfs)
    return RuntimePart(name=name or f"runtime-{sha[:12]}.tar", sha256=sha, size_bytes=size, urls=urls)


def parse_runtime_spec(variant: str, data: dict[str, Any] | None = None) -> RuntimeSpec:
    var = (variant or "nvidia").strip().lower()
    if var not in ("nvidia", "amd", "nvidia50"):
        var = "nvidia"
    blob: dict[str, Any] = {}
    if data and isinstance(data.get("runtimes"), dict):
        blob = dict(data["runtimes"].get(var) or {})
    if not blob:
        blob = dict(_FALLBACK_RUNTIMES.get(var) or _FALLBACK_RUNTIMES["nvidia"])
    release_tag = str(
        blob.get("release_tag")
        or (data.get("runtime_release_tag") if data else "")
        or DEFAULT_RUNTIME_RELEASE_TAG
    ).strip() or DEFAULT_RUNTIME_RELEASE_TAG
    parts_raw = blob.get("parts") or []
    parts: list[RuntimePart] = []
    if isinstance(parts_raw, list):
        for p in parts_raw:
            if isinstance(p, dict):
                parts.append(_normalize_part(p, release_tag=release_tag))
    if not parts and blob.get("sha256"):
        parts.append(
            _normalize_part(
                {
                    "name": str(blob.get("name") or f"runtime-{var}.tar"),
                    "sha256": blob["sha256"],
                    "size_bytes": blob.get("size_bytes") or 0,
                },
                release_tag=release_tag,
            )
        )
    if not parts:
        fb = _FALLBACK_RUNTIMES[var]
        parts = [_normalize_part(fb["parts"][0], release_tag=release_tag)]
        blob = dict(fb)
    return RuntimeSpec(
        variant=var,
        label=str(blob.get("label") or VARIANT_LABELS.get(var, var)),
        version=str(blob.get("version") or ""),
        format=str(blob.get("format") or "tar"),
        size_bytes=int(blob.get("size_bytes") or parts[0].size_bytes or 0),
        extract_root=str(blob.get("extract_root") or "Runtime"),
        parts=parts,
        release_tag=release_tag,
    )


def resolve_runtime_spec(
    variant: str,
    *,
    prefer_remote: bool = True,
    timeout: float = 20.0,
) -> RuntimeSpec:
    """Build RuntimeSpec: remote catalog → bundled → embedded fallback."""
    data: Optional[dict[str, Any]] = None
    if prefer_remote:
        try:
            data = fetch_remote_catalog(timeout=timeout)
        except Exception:
            data = None
    if data is None:
        data = load_bundled_runtime_catalog()
    return parse_runtime_spec(variant, data)


def format_size(n: int) -> str:
    if n <= 0:
        return "未知大小"
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f} GB"
    if n >= 1_000_000:
        return f"{n / 1e6:.0f} MB"
    return f"{n / 1e3:.0f} KB"
