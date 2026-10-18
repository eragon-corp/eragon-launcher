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

    def test_flags_override_environment_and_skip_catalogue(self):
        reply = self.run_launcher("not a catalogue", args=["--endpoint", "https://custom.example:8443/api/", "--model", "team/custom-model"],
                                  environment={"ERAGON_ENDPOINT": "https://ignored.example", "ERAGON_MODEL": "ignored", "ERAGON_API_KEY": "fixture-secret"},
                                  expectedEndpoint="https://custom.example:8443/api", noCatalogue=1, noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"model": "team/custom-model"', reply["output"])
        self.assertNotIn("Personal API Key", reply["output"])
        self.assertNotIn("Choose a model", reply["output"])

    def test_all_environment_configuration(self):
        reply = self.run_launcher({}, environment={"ERAGON_ENDPOINT": "https://other.example/gw", "ERAGON_MODEL": "claude-custom", "ERAGON_API_KEY": "fixture-secret"},
                                  expectedEndpoint="https://other.example/gw", noCatalogue=1, noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"model": "claude-custom"', reply["output"])

    def test_allexport_does_not_export_private_key(self):
        reply = self.run_launcher({}, environment={"ERAGON_API_KEY": "fixture-secret", "ERAGON_MODEL": "model", "eragon_key": "fixture-secret"},
                                  bashOptions=["-x", "-a"], noCatalogue=1, noninteractive=True)
        self.assertEqual(reply["exit"], 0)

    def test_custom_endpoint_with_discovery_and_prompt(self):
        reply = self.run_launcher({"data": [{"id": "claude-sonnet-5"}]}, args=["--endpoint", "https://other.example/gw/"],
                                  expectedEndpoint="https://other.example/gw")
        self.assertEqual(reply["exit"], 0)
        self.assertIn("Personal API Key", reply["output"])

    def test_explicit_model_with_hidden_key(self):
        reply = self.run_launcher({}, args=["--model", "my-model"], noCatalogue=1)
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"model": "my-model"', reply["output"])

    def test_environment_key_with_model_menu(self):
        reply = self.run_launcher({"data": [{"id": "claude-sonnet-5"}]}, environment={"ERAGON_API_KEY": "fixture-secret"})
        self.assertEqual(reply["exit"], 0)
        self.assertNotIn("Personal API Key", reply["output"])

    def test_reject_unsafe_endpoints_before_request(self):
        for endpoint in ["http://other.example", "https://fixture-secret@other.example", "https://other.example?key=fixture-secret", "https://other.example/#fragment", "https://other.example/\n", "https://other.example/\\evil"]:
            with self.subTest(endpoint=endpoint):
                reply = self.run_launcher({}, environment={"ERAGON_ENDPOINT": endpoint, "ERAGON_API_KEY": "fixture-secret", "ERAGON_MODEL": "model"}, noCatalogue=1, noninteractive=True)
                self.assertNotEqual(reply["exit"], 0)
                self.assertIn("Endpoint must be", reply["output"])
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_reject_invalid_configured_model(self):
        for model in ["model\n", "$(touch injected)", "--help"]:
            with self.subTest(model=model):
                reply = self.run_launcher({}, environment={"ERAGON_API_KEY": "fixture-secret", "ERAGON_MODEL": model}, noCatalogue=1, noninteractive=True)
                self.assertNotEqual(reply["exit"], 0)
                self.assertIn("Invalid model ID", reply["output"])
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_reject_header_injection(self):
        reply = self.run_launcher({}, environment={"ERAGON_API_KEY": "fixture-secret\rX-Header: bad", "ERAGON_MODEL": "model"}, noCatalogue=1, noninteractive=True)
        self.assertNotEqual(reply["exit"], 0)
        self.assertIn("Invalid API key", reply["output"])

    def test_missing_noninteractive_configuration(self):
        for environment, message in [({"ERAGON_API_KEY": "fixture-secret"}, "Model selection needs"), ({"ERAGON_MODEL": "model"}, "Set ERAGON_API_KEY")]:
            with self.subTest(environment=environment):
                reply = self.run_launcher({}, environment=environment, noninteractive=True)
                self.assertNotEqual(reply["exit"], 0)
                self.assertIn(message, reply["output"])
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_endpoint_is_required(self):
        reply = self.run_launcher({}, provideEndpoint=False, noninteractive=True,
                                  environment={"ERAGON_API_KEY": "fixture-secret", "ERAGON_MODEL": "model"}, noCatalogue=1)
        self.assertNotEqual(reply["exit"], 0)
        self.assertIn("Endpoint required", reply["output"])
        self.assertNotIn("LAUNCHED", reply["output"])

    def test_help_and_invalid_flags(self):
        reply = self.run_launcher({}, args=["--help"], noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn("ERAGON_API_KEY", reply["output"])
        for args in [["--endpoint"], ["--model"], ["--api-key", "fixture-secret"], ["--model", "--help"]]:
            with self.subTest(args=args):
                reply = self.run_launcher({}, args=args, noninteractive=True)
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
