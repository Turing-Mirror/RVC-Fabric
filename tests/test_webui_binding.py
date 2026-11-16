"""Check WebUI exposure without importing Gradio or opening a server."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class WebUiBindingTests(unittest.TestCase):
    def launch(self, iscolab):
        source = Path(__file__).resolve().parents[1] / "infer-web.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        branch = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Attribute)
            and isinstance(node.test.value, ast.Name)
            and node.test.value.id == "config" and node.test.attr == "iscolab"
        )
        app = Mock()
        config = SimpleNamespace(iscolab=iscolab, noautoopen=True, listen_port=7865)
        exec(compile(ast.Module(body=[branch], type_ignores=[]), str(source), "exec"),
             {"app": app, "config": config})
        return app.queue.return_value.launch.call_args.kwargs

    def test_desktop_webui_only_listens_on_loopback(self):
        launch = self.launch(False)
        self.assertEqual(launch["server_name"], "127.0.0.1")
        self.assertEqual(launch["server_port"], 7865)
        self.assertFalse(launch["inbrowser"])

    def test_explicit_colab_share_is_preserved(self):
        self.assertEqual(self.launch(True), {"share": True})
