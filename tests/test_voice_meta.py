# -*- coding: utf-8 -*-
"""Voice pack identity meta: name / author / author_url / date / cover."""

import json
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.online.package_spec import (
    normalize_voice_meta,
    normalize_yymmdd,
    voice_meta_template,
)


def test_normalize_yymmdd():
    assert normalize_yymmdd("260722") == "260722"
    assert normalize_yymmdd("2026-07-22") == "260722"
    assert normalize_yymmdd("20260722") == "260722"
    assert normalize_yymmdd("") == ""


def test_normalize_voice_meta_fields():
    m = normalize_voice_meta(
        {
            "name": "浅夏",
            "author": "作者A",
            "author_url": "https://example.com/a",
            "date": "2026-07-22",
            "cover": "art/cover.png",
            "url": "https://should.not/use",  # pack download — ignore
        }
    )
    assert m["name"] == "浅夏"
    assert m["author"] == "作者A"
    assert m["author_url"] == "https://example.com/a"
    assert m["date"] == "260722"
    assert m["cover"] == "art/cover.png"
    assert "url" not in m


def test_voice_meta_template():
    t = voice_meta_template(
        name="kiki", author="TM", author_url="https://x", date="260101"
    )
    assert t["name"] == "kiki"
    assert t["author"] == "TM"
    assert t["date"] == "260101"
    assert t["cover"] == "cover.jpg"


def test_install_zip_reads_config_identity(tmp_path):
    from launcher.catalog import list_models_in_user_data
    from launcher.online.voice_install import install_voice_pack_zip

    root = tmp_path / "pack"
    root.mkdir()
    # minimal fake pth (> 50k)
    pth = root / "kiki.pth"
    pth.write_bytes(b"x" * 60_000)
    cover = root / "cover.jpg"
    cover.write_bytes(b"\xff\xd8\xff" + b"y" * 600)
    (root / "config.json").write_text(
        json.dumps(
            {
                "name": "浅夏",
                "author": "作者B",
                "author_url": "https://example.com/b",
                "date": "260715",
                "cover": "cover.jpg",
                "tag": "少女音",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    zpath = tmp_path / "kiki.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for f in root.iterdir():
            zf.write(f, f.name)

    models = tmp_path / "models"
    info = install_voice_pack_zip(zpath, voice_id="kiki", models_root=models)
    dest = Path(info["dir"])
    cfg = json.loads((dest / "config.json").read_text(encoding="utf-8"))
    assert cfg["name"] == "浅夏"
    assert cfg["author"] == "作者B"
    assert cfg["author_url"] == "https://example.com/b"
    assert cfg["date"] == "260715"
    assert cfg["cover"] in ("cover.jpg", str(dest / "cover.jpg"))
    assert (dest / "cover.jpg").is_file()

    listed = {m["name"]: m for m in list_models_in_user_data(models)}
    assert listed["浅夏"]["author"] == "作者B"
    assert listed["浅夏"]["author_url"] == "https://example.com/b"
    assert listed["浅夏"]["date"] == "260715"
