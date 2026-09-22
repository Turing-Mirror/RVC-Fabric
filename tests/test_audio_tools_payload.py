"""Audio tools share the product root; no Runtime is copied or required."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_setup

class AudioToolsPayload(unittest.TestCase):
    def test_tools_are_listed_once_at_shared_root(self):
        config = json.loads((ROOT / "app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        for tool in ("ffmpeg.exe", "ffprobe.exe"):
            self.assertEqual(resources[f"engine-payload/{tool}"], tool)
            self.assertEqual(list(resources.values()).count(tool), 1)

    def test_complete_pair_is_required_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, dest = root / "source", root / "dest"
            source.mkdir()
            dest.mkdir()
            (source / "ffmpeg.exe").write_bytes(b"x" * 1_000_000)
            with patch.object(build_setup, "REPO", source):
                with self.assertRaises(FileNotFoundError):
                    build_setup.copy_audio_tools(dest)
                self.assertEqual(list(dest.iterdir()), [])
                (source / "ffprobe.exe").write_bytes(b"y" * 1_000_000)
                build_setup.copy_audio_tools(dest)
            self.assertEqual(sorted(p.name for p in dest.iterdir()), ["ffmpeg.exe", "ffprobe.exe"])
            self.assertEqual((dest / "ffmpeg.exe").read_bytes(), (source / "ffmpeg.exe").read_bytes())

    def test_strip_preserves_audio_tools_but_removes_weights(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for tool in ("ffmpeg.exe", "ffprobe.exe"):
                (root / tool).write_bytes(b"fixture")
            weight = root / "assets/hubert/hubert_base.pt"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"weight")
            build_setup.strip_heavy_from_payload(root)
            self.assertFalse(weight.exists())
            for tool in ("ffmpeg.exe", "ffprobe.exe"):
                self.assertEqual((root / tool).read_bytes(), b"fixture")

    def test_tools_are_not_forbidden_in_prepared_payload(self):
        spec = importlib.util.spec_from_file_location("audio_payload_test", ROOT / "scripts/prepare_engine_payload.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for tool in ("ffmpeg.exe", "ffprobe.exe"):
            self.assertNotIn(tool, module.FORBIDDEN)
        self.assertIn("Runtime", module.FORBIDDEN)
        self.assertIn("assets/hubert/hubert_base.pt", module.FORBIDDEN)

if __name__ == "__main__":
    unittest.main()
