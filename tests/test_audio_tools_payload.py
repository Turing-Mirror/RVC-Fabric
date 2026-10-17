"""Audio tools are downloaded after install; the Setup payload no longer carries them."""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_setup

TOOLS = ("ffmpeg.exe", "ffprobe.exe")


class AudioToolsPayload(unittest.TestCase):
    def test_tools_are_not_bundled(self):
        config = json.loads((ROOT / "app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        for tool in TOOLS:
            self.assertNotIn(f"engine-payload/{tool}", resources)
            self.assertNotIn(tool, resources.values())

    def test_strip_removes_audio_tools_and_weights(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for tool in TOOLS:
                (root / tool).write_bytes(b"fixture")
            weight = root / "assets/hubert/hubert_base.pt"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"weight")
            build_setup.strip_heavy_from_payload(root)
            self.assertFalse(weight.exists())
            for tool in TOOLS:
                self.assertFalse((root / tool).exists())

    def test_tools_are_forbidden_in_prepared_payload(self):
        spec = importlib.util.spec_from_file_location("audio_payload_test", ROOT / "scripts/prepare_engine_payload.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for tool in TOOLS:
            self.assertIn(tool, module.FORBIDDEN)
        self.assertIn("Runtime", module.FORBIDDEN)

    def test_download_is_offered_not_silent(self):
        app = (ROOT / "app/src/App.tsx").read_text(encoding="utf-8")
        gate = app[app.index("<ProvisionGate"):app.index("<AudioToolsDialog")]
        self.assertIn("promptAudioTools({", gate[gate.index("onDone="):gate.index("onDismiss=")])
        self.assertIn("audioAfterNotice.current = true", gate)
        self.assertIn("promptAudioTools()", gate[gate.index("<FeedbackNoticeGate"):])
        # 只有提示窗里点了下载才会真正下载
        for path in ("app/src/App.tsx", "app/src/pages/AudioPage.tsx"):
            self.assertNotIn("ensureAudioTools(", (ROOT / path).read_text(encoding="utf-8"), path)
        dialog = (ROOT / "app/src/components/AudioToolsDialog.tsx").read_text(encoding="utf-8")
        self.assertIn("ensureAudioTools()", dialog)
        rust = (ROOT / "app/src-tauri/src/lib.rs").read_text(encoding="utf-8")
        self.assertIn("assets_ensure_audio_tools,", rust)

if __name__ == "__main__":
    unittest.main()
