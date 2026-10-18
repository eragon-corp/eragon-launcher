import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class LauncherTests(unittest.TestCase):
    def run_launcher(self, models, **options):
        request = dict(script=(ROOT / "eragon.sh").read_text(),
                       models=models if isinstance(models, str) else json.dumps(models), **options)
        result = subprocess.run([sys.executable, str(ROOT / "tests/pty_runner.py")],
                                input=json.dumps(request), text=True, capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        self.assertNotIn("fixture-secret", reply["output"])
        return reply

    def test_syntax(self):
        subprocess.run(["bash", "-n", str(ROOT / "eragon.sh")], check=True)

    def test_selection_and_no_persistence(self):
        reply = self.run_launcher({"data": [{"id": "claude-sonnet-5"}, {"id": "claude-opus-5"},
                                                 {"id": "gpt-6"}, {"id": "claude-$(touch injected)"}]}, choices=["2"])
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"model": "claude-sonnet-5"', reply["output"])
        self.assertNotIn("gpt-6", reply["output"])
        self.assertNotIn("touch injected", reply["output"])

    def test_invalid_input_then_default(self):
        reply = self.run_launcher({"data": [{"id": "claude-sonnet-5"}]}, choices=["$(touch injected)", ""])
        self.assertEqual(reply["exit"], 0)
        self.assertIn("Enter one of the model numbers", reply["output"])

    def test_unusable_catalogue(self):
        for models in ["invalid json", {"data": []}, {"data": [{"id": "gpt-6"}]}]:
            with self.subTest(models=models):
                reply = self.run_launcher(models)
                self.assertNotEqual(reply["exit"], 0)
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_model_line_breaks(self):
        for model in ["claude-sonnet-5\n", "\nclaude-sonnet-5", "claude-sonnet-5\r", "claude-\nsonnet-5"]:
            with self.subTest(model=model):
                reply = self.run_launcher({"data": [{"id": model}]})
                self.assertNotEqual(reply["exit"], 0)
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_cancel_restores_terminal(self):
        reply = self.run_launcher({"data": []}, interrupt=True)
        self.assertEqual(reply["exit"], 130)
        self.assertNotIn("LAUNCHED", reply["output"])

    def test_network_failure(self):
        reply = self.run_launcher({"data": [{"id": "claude-sonnet-5"}]}, curlFail=1)
        self.assertNotEqual(reply["exit"], 0)
        self.assertIn("Could not load models", reply["output"])
        self.assertNotIn("LAUNCHED", reply["output"])

if __name__ == "__main__":
    unittest.main()
