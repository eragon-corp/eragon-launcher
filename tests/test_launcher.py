import json
import hashlib
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
        self.assertLessEqual(reply["output"].count("FIXTURE_CATALOGUE_REQUEST"), 1)
        return reply

    def test_syntax(self):
        subprocess.run(["bash", "-n", str(ROOT / "eragon.sh")], check=True)

    def test_selection_and_no_persistence(self):
        reply = self.run_launcher({"data": [{"id": "claude-sonnet-5"}, {"id": "claude-opus-5"},
                                                 {"id": "gpt-6", "supports_function_calling": False}, {"id": "claude-$(touch injected)"}]}, choices=["2"])
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"model": "claude-sonnet-5"', reply["output"])
        self.assertNotIn("gpt-6", reply["output"])
        self.assertNotIn("touch injected", reply["output"])

    def test_invalid_input_then_default(self):
        reply = self.run_launcher({"data": [{"id": "claude-sonnet-5"}]}, choices=["$(touch injected)", ""])
        self.assertEqual(reply["exit"], 0)
        self.assertIn("Enter one of the model numbers", reply["output"])

    def test_unusable_catalogue(self):
        for models in ["invalid json", {"data": []}, {"data": [{"id": "embed", "mode": "embedding"}]}]:
            with self.subTest(models=models):
                reply = self.run_launcher(models)
                self.assertNotEqual(reply["exit"], 0)
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_multiple_catalogue_documents_are_rejected(self):
        document = json.dumps({"data": [{"id": "claude-fixture"}]})
        reply = self.run_launcher(document + document)
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

    def candidate(self, model="other/coder"):
        return {"id": model, "capabilities": {"tools": True, "streaming": True},
                "input_modalities": ["text"], "output_modalities": ["text"]}

    def certificate(self, **overrides):
        record = {"endpoint_sha256": hashlib.sha256(b"https://gateway.example.com/gw").hexdigest(),
                  "model_id": "other/coder", "profile": "basic", "adapter_version": 1,
                  "claude_code_version": "2.1.302", "tested_at": "fixture-only", "evidence": "fixture-only"}
        record.update(overrides)
        return {"schema_version": 1, "verified": [record]}

    def test_capability_candidates_hide_unknown_and_block_unsupported(self):
        models = {"data": [self.candidate(), {"id": "unknown-model"},
                           self.candidate("no-tools") | {"supports_function_calling": False},
                           {"id": "image", "mode": "image_generation"}]}
        reply = self.run_launcher(models)
        self.assertEqual(reply["exit"], 0)
        self.assertIn("capabilities declared; not tested", reply["output"])
        self.assertIn("m) Show 1 unverified", reply["output"])
        self.assertNotIn("unknown-model", reply["output"])
        self.assertNotIn("no-tools", reply["output"])
        self.assertIn("2 unsupported", reply["output"])
        self.assertEqual(reply["output"].count("FIXTURE_CATALOGUE_REQUEST"), 1)
        self.assertIn('"model": "other/coder"', reply["output"])

    def test_show_more_can_select_unknown(self):
        reply = self.run_launcher({"data": [self.candidate(), {"id": "unknown-model"}]}, choices=["m", "2"])
        self.assertEqual(reply["exit"], 0)
        self.assertIn("unknown-model [unverified]", reply["output"])
        self.assertIn('"model": "unknown-model"', reply["output"])

    def test_missing_metadata_is_unverified_even_for_claude(self):
        reply = self.run_launcher({"data": [{"id": "claude-fixture"}, {"id": "gpt-fixture"}]})
        self.assertEqual(reply["exit"], 0)
        self.assertIn("showing unverified", reply["output"])
        self.assertIn("claude-fixture [unverified]", reply["output"])
        self.assertIn("gpt-fixture [unverified]", reply["output"])

    def test_false_capabilities_and_nonchat_modes_always_exclude(self):
        cases = [self.candidate() | {"supports_streaming": False},
                 self.candidate() | {"input_modalities": ["image"]},
                 self.candidate() | {"output_modalities": ["audio"]},
                 self.candidate() | {"mode": "embedding"}]
        for model in cases:
            with self.subTest(model=model):
                reply = self.run_launcher({"data": [model]}, manifest=self.certificate())
                self.assertNotEqual(reply["exit"], 0)
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_duplicate_conflicts_cannot_hide_explicit_false(self):
        reply = self.run_launcher({"data": [self.candidate(), {"id": "other/coder", "supports_function_calling": False}]})
        self.assertNotEqual(reply["exit"], 0)
        self.assertNotIn("LAUNCHED", reply["output"])

    def test_nested_metadata_and_malformed_metadata(self):
        reply = self.run_launcher({"data": [{"id": "nested", "model_info": {"supports_function_calling": True, "supports_streaming": True},
                                             "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
                                            {"id": "unknown", "capabilities": False, "model_info": "bad"}]})
        self.assertEqual(reply["exit"], 0)
        self.assertIn("nested [capabilities declared; not tested]", reply["output"])
        self.assertNotIn("unknown [", reply["output"])

    def test_certificate_matches_endpoint_model_client_and_adapter(self):
        reply = self.run_launcher({"data": [{"id": "other/coder"}]}, manifest=self.certificate())
        self.assertEqual(reply["exit"], 0)
        self.assertIn("verified for this endpoint/client/adapter", reply["output"])
        for overrides in [{"endpoint_sha256": "0" * 64}, {"model_id": "other-model"}, {"claude_code_version": "0.0.0"}]:
            with self.subTest(overrides=overrides):
                reply = self.run_launcher({"data": [{"id": "other/coder"}]}, manifest=self.certificate(**overrides))
                self.assertEqual(reply["exit"], 0)
                self.assertNotIn("verified for this endpoint/client/adapter", reply["output"])
                self.assertIn("other/coder [unverified]", reply["output"])

    def test_certificate_can_select_native_profile_for_alias(self):
        reply = self.run_launcher({}, args=["--model", "other/coder"], noCatalogue=1,
                                  manifest=self.certificate(profile="native"), expectedProfile="native")
        self.assertEqual(reply["exit"], 0)
        self.assertNotIn("have not been verified", reply["output"])

    def test_conflicting_certificates_are_not_verified(self):
        manifest = self.certificate()
        manifest["verified"].append(self.certificate(profile="native")["verified"][0])
        reply = self.run_launcher({"data": [{"id": "other/coder"}]}, manifest=manifest)
        self.assertEqual(reply["exit"], 0)
        self.assertIn("other/coder [unverified]", reply["output"])
        self.assertNotIn("verified for this endpoint/client/adapter", reply["output"])

    def test_malformed_capability_fields_remain_unknown(self):
        reply = self.run_launcher({"data": [{"id": "other/coder", "supports_function_calling": "true",
                                            "supports_streaming": 1, "supported_modalities": [123],
                                            "input_modalities": [None], "output_modalities": "text"}]})
        self.assertEqual(reply["exit"], 0)
        self.assertIn("other/coder [unverified]", reply["output"])
        self.assertNotIn("capabilities declared; not tested", reply["output"])

    def test_invalid_manifest_fails_before_catalogue_request(self):
        for manifest in [{}, self.certificate(adapter_version=2), self.certificate(endpoint_sha256="not-a-hash"), self.certificate() | {"api_key": "do-not-store-credentials"}]:
            with self.subTest(manifest=manifest):
                reply = self.run_launcher({"data": [self.candidate()]}, manifest=manifest, noCatalogue=1)
                self.assertNotEqual(reply["exit"], 0)
                self.assertIn("Invalid compatibility file", reply["output"])

    def test_capacity_metadata_and_duplicate_routes_use_minimum(self):
        reply = self.run_launcher({"data": [
            {"id": "claude-fixture", "context_window": 1000000},
            {"id": "claude-fixture", "model_info": {"max_input_tokens": 128000, "max_output_tokens": 4096}}]})
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "102400"', reply["output"])
        self.assertIn('"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "4096"', reply["output"])

    def test_explicit_capacity_no_catalogue_and_flags_override_environment(self):
        reply = self.run_launcher({}, args=["--model", "claude-fixture", "--context-window", "200000"],
                                  environment={"ERAGON_CONTEXT_WINDOW": "1000000", "ERAGON_API_KEY": "fixture-secret",
                                               "DISABLE_COMPACT": "1", "DISABLE_AUTO_COMPACT": "1",
                                               "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000"},
                                  noCatalogue=1, noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "160000"', reply["output"])
        self.assertIn('"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "8192"', reply["output"])

    def test_override_cannot_increase_declared_capacity(self):
        reply = self.run_launcher({"data": [{"id": "custom", "context_length": 200000}]},
                                  environment={"ERAGON_CONTEXT_WINDOW": "1000000"})
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "160000"', reply["output"])

    def test_selected_model_budget_and_smaller_override(self):
        models = {"data": [{"id": "claude-a", "context_length": 1000000},
                           {"id": "claude-b", "max_input_tokens": 200000}]}
        reply = self.run_launcher(models, choices=["2"], environment={"ERAGON_CONTEXT_WINDOW": "150000"})
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"model": "claude-b"', reply["output"])
        self.assertIn('"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "120000"', reply["output"])

    def test_unknown_or_malformed_capacity_uses_warned_fallback(self):
        for metadata in [{}, {"context_window": "128000", "max_input_tokens": -1},
                         {"context_length": 1.5, "max_output_tokens": 0}]:
            with self.subTest(metadata=metadata):
                reply = self.run_launcher({"data": [{"id": "custom", **metadata}]})
                self.assertEqual(reply["exit"], 0)
                self.assertIn("Context capacity unknown", reply["output"])
                self.assertIn('"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "100000"', reply["output"])

    def test_large_context_is_capped_to_supported_compaction_window(self):
        reply = self.run_launcher({"data": [{"id": "custom", "context_window": 2000000}]})
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000"', reply["output"])

    def test_small_declared_context_refuses_unsafe_launch(self):
        reply = self.run_launcher({"data": [{"id": "small", "max_input_tokens": 64000}]})
        self.assertNotEqual(reply["exit"], 0)
        self.assertNotIn("LAUNCHED", reply["output"])
        self.assertIn("below 125000", reply["output"])

    def test_invalid_context_configuration_rejected_before_request(self):
        for value in ["0", "64000", "200k", "200000\n", "9999999999", "$(touch injected)"]:
            with self.subTest(value=value):
                reply = self.run_launcher({}, args=["--context-window", value], noCatalogue=1)
                self.assertNotEqual(reply["exit"], 0)
                self.assertNotIn("LAUNCHED", reply["output"])

    def test_old_client_cannot_silently_ignore_capacity_settings(self):
        reply = self.run_launcher({}, environment={"FIXTURE_CLAUDE_VERSION": "2.1.0"}, noCatalogue=1)
        self.assertNotEqual(reply["exit"], 0)
        self.assertIn("claude update", reply["output"])
        self.assertNotIn("LAUNCHED", reply["output"])

    def test_interactive_client_selection(self):
        for choices, expected in [([""], "Starting Claude Code"), (["2"], "CODEX_LAUNCHED"),
                                  (["invalid", "5", "2"], "CODEX_LAUNCHED")]:
            with self.subTest(choices=choices):
                reply = self.run_launcher({}, args=["--model", "custom"], noCatalogue=1, clientChoices=choices)
                self.assertEqual(reply["exit"], 0)
                self.assertIn("Choose a client", reply["output"])
                self.assertIn(expected, reply["output"])

    def test_configured_client_skips_client_menu(self):
        for options in [{"args": ["--client", "codex", "--model", "custom"]},
                        {"environment": {"ERAGON_CLIENT": "claude", "ERAGON_MODEL": "custom"}}]:
            with self.subTest(options=options):
                reply = self.run_launcher({}, noCatalogue=1, **options)
                self.assertEqual(reply["exit"], 0)
                self.assertNotIn("Choose a client", reply["output"])

    def test_codex_explicit_model_and_capacity_without_discovery(self):
        reply = self.run_launcher({}, args=["--client", "codex", "--model", "custom/coder", "--context-window", "64000"],
                                  noCatalogue=1, noninteractive=True,
                                  environment={"ERAGON_API_KEY": "fixture-secret", "OPENAI_API_KEY": "stale",
                                               "ANTHROPIC_AUTH_TOKEN": "stale"})
        self.assertEqual(reply["exit"], 0)
        self.assertIn('CODEX_LAUNCHED', reply["output"])
        self.assertIn('"context": 64000', reply["output"])

    def test_codex_responses_screening_and_context(self):
        model = self.candidate("example/coder")
        model.update(context_window=128000, supports_responses=True)
        blocked = self.candidate("blocked") | {"supports_responses": False}
        reply = self.run_launcher({"data": [model, blocked, self.candidate("unknown")]}, args=["--client", "codex"])
        self.assertEqual(reply["exit"], 0)
        self.assertIn('"context": 128000', reply["output"])
        self.assertIn('example/coder [capabilities declared; not tested]', reply["output"])
        self.assertNotIn('blocked [', reply["output"])
        self.assertNotIn('unknown [', reply["output"])

    def test_codex_conflicting_response_support_excludes_model(self):
        model = self.candidate("custom") | {"supports_responses": True}
        reply = self.run_launcher({"data": [model, {"id": "custom", "model_info": {"supports_responses": False}}]},
                                  args=["--client", "codex"])
        self.assertNotEqual(reply["exit"], 0)
        self.assertNotIn('CODEX_LAUNCHED', reply["output"])

    def test_client_flag_overrides_environment(self):
        reply = self.run_launcher({}, args=["--client", "codex", "--model", "custom"],
                                  environment={"ERAGON_CLIENT": "invalid", "ERAGON_API_KEY": "fixture-secret"},
                                  noCatalogue=1, noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn('CODEX_LAUNCHED', reply["output"])

    def test_codex_accepts_v1_endpoint_without_duplicating_version(self):
        reply = self.run_launcher({"data": [{"id": "custom"}]},
                                  args=["--client", "codex", "--endpoint", "https://gateway.example.com/gw/v1/"])
        self.assertEqual(reply["exit"], 0)
        self.assertIn('CODEX_LAUNCHED', reply["output"])
        self.assertIn('Context capacity unknown', reply["output"])
        self.assertIn('"context": 125000', reply["output"])

    def test_codex_does_not_reuse_claude_certificates(self):
        reply = self.run_launcher({"data": [{"id": "other/coder"}]}, manifest=self.certificate(),
                                  environment={"ERAGON_CLIENT": "codex"})
        self.assertEqual(reply["exit"], 0)
        self.assertNotIn('verified for this endpoint/client/adapter', reply["output"])
        self.assertIn('other/coder [unverified]', reply["output"])

    def test_codex_invalid_client_and_old_version(self):
        for environment in [{"ERAGON_CLIENT": "invalid"},
                            {"ERAGON_CLIENT": "codex", "FIXTURE_CODEX_VERSION": "codex-cli 0.159.0"}]:
            reply = self.run_launcher({}, environment=environment, noCatalogue=1)
            self.assertNotEqual(reply["exit"], 0)
            self.assertNotIn('CODEX_LAUNCHED', reply["output"])

    def test_codex_hidden_key_interrupt_and_capacity_floor(self):
        reply = self.run_launcher({}, args=["--client", "codex", "--model", "custom"], noCatalogue=1, interrupt=True)
        self.assertEqual(reply["exit"], 130)
        reply = self.run_launcher({"data": [{"id": "small", "max_input_tokens": 2048}]}, args=["--client", "codex"])
        self.assertNotEqual(reply["exit"], 0)
        self.assertNotIn('CODEX_LAUNCHED', reply["output"])

    def test_pi_and_opencode_menu_and_explicit_launch(self):
        for client, number, marker in [("pi", "3", "PI_LAUNCHED"), ("opencode", "4", "OPENCODE_LAUNCHED")]:
            with self.subTest(client=client):
                reply = self.run_launcher({}, args=["--model", "team/coder"], noCatalogue=1, clientChoices=[number])
                self.assertEqual(reply["exit"], 0)
                self.assertIn(marker, reply["output"])
                reply = self.run_launcher({}, args=["--client", client, "--model", "team/coder", "--context-window", "64000"],
                                          environment={"ERAGON_API_KEY":"fixture-secret"}, noCatalogue=1, noninteractive=True)
                self.assertEqual(reply["exit"], 0)
                self.assertIn(marker, reply["output"])

    def test_chat_completions_screening_and_limits(self):
        for client in ["pi", "opencode"]:
            with self.subTest(client=client):
                model = self.candidate("team/coder") | {"supports_chat_completions": True, "max_input_tokens": 64000, "max_output_tokens": 4096}
                reply = self.run_launcher({"data": [model, self.candidate("unknown"),
                    self.candidate("unsupported") | {"supports_chat_completions": False}]}, args=["--client", client])
                self.assertEqual(reply["exit"], 0)
                self.assertIn('team/coder [capabilities declared; not tested]', reply["output"])
                self.assertNotIn('unknown [', reply["output"])
                self.assertNotIn('unsupported [', reply["output"])
                self.assertIn('64000', reply["output"])
                self.assertIn('4096', reply["output"])

    def test_chat_completions_conflicts_are_excluded(self):
        for client in ["pi", "opencode"]:
            reply = self.run_launcher({"data": [self.candidate("custom") | {"supports_chat_completions": True},
                {"id":"custom", "model_info":{"supports_chat_completions":False}}]}, args=["--client", client])
            self.assertNotEqual(reply["exit"], 0)
            self.assertNotIn('_LAUNCHED', reply["output"])

    def test_pi_cleanup_on_failure_and_v1_auth_reference(self):
        reply = self.run_launcher({}, args=["--client", "pi", "--model", "coder"], noCatalogue=1,
                                  environment={"ERAGON_API_KEY":"fixture-secret", "FIXTURE_PI_EXIT":"7"}, noninteractive=True)
        self.assertEqual(reply["exit"], 7)
        reply = self.run_launcher({}, args=["--client", "pi", "--model", "coder"], noCatalogue=1,
                                  environment={"ERAGON_API_KEY":"fixture-secret", "FIXTURE_PI_VERSION":"1.0.0"}, noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn('$ERAGON_ROUTER_TOKEN', reply["output"])

    def test_pi_opencode_v1_endpoints_and_minimum_context(self):
        for client in ["pi", "opencode"]:
            reply = self.run_launcher({"data":[{"id":"coder"}]}, args=["--client",client,"--endpoint","https://gateway.example.com/gw/v1/"])
            self.assertEqual(reply["exit"], 0)
        reply = self.run_launcher({}, args=["--client","opencode","--model","coder","--context-window","4096"],
                                  noCatalogue=1,environment={"ERAGON_API_KEY":"fixture-secret"},noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        reply = self.run_launcher({"data":[{"id":"coder","max_input_tokens":16000}]},args=["--client","pi"])
        self.assertNotEqual(reply["exit"], 0)
        self.assertIn('below 32768', reply["output"])

    def test_pi_opencode_versions_and_hidden_input_cancellation(self):
        for client, version_var, version in [("pi","FIXTURE_PI_VERSION","0.72.0"), ("opencode","FIXTURE_OPENCODE_VERSION","1.3.6")]:
            reply = self.run_launcher({}, args=["--client",client,"--model","coder"], noCatalogue=1,environment={version_var:version})
            self.assertNotEqual(reply["exit"], 0)
            reply = self.run_launcher({}, args=["--client",client,"--model","coder"], noCatalogue=1,interrupt=True)
            self.assertEqual(reply["exit"], 130)

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
