"""Exercise the actual npm tarball and installed executable in isolated directories."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("npm"), "npm is required for packaging checks")
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="eragon-package-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = pathlib.Path(cls.temp.name)
        cls.environment = dict(os.environ, npm_config_cache=str(cls.directory / "cache"),
                               npm_config_update_notifier="false")
        result = cls.run_command(["npm", "pack", "--json", "--ignore-scripts",
                                  "--pack-destination", str(cls.directory)], cwd=ROOT)
        cls.package = json.loads(result.stdout)[0]
        archive = cls.directory / cls.package["filename"]
        cls.prefix = cls.directory / "installed"
        cls.run_command(["npm", "install", "--global", "--prefix", str(cls.prefix),
                         "--ignore-scripts", "--no-audit", "--no-fund", str(archive)])
        cls.command = str(cls.prefix / "bin" / "eragon-router")

    @classmethod
    def run_command(cls, args, **kwargs):
        result = subprocess.run(args, env=cls.environment, capture_output=True,
                                text=True, timeout=60, **kwargs)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def test_package_contents_and_version(self):
        self.assertEqual({entry["path"] for entry in self.package["files"]}, {
            "package.json", "eragon.sh", "README.md", "LICENSE",
            "docs/technical-reference.md", "compatibility.example.json"})
        metadata = json.loads((ROOT / "package.json").read_text())
        for args in [[self.command, "--version"], ["/bin/bash", str(ROOT / "eragon.sh"), "-v"]]:
            self.assertEqual(self.run_command(args).stdout.strip(), "Eragon Router " + metadata["version"])
        self.assertIn("Usage: eragon-router", self.run_command([self.command, "--help"]).stdout)
        self.assertFalse(metadata.get("dependencies"))

    def test_installed_cli_launches_all_clients(self):
        for client in ["claude", "codex", "pi", "opencode"]:
            with self.subTest(client=client):
                request = dict(script=(ROOT / "eragon.sh").read_text(), command=[self.command],
                               models="unused", args=["--client", client, "--model", "coder"],
                               noCatalogue=1, noninteractive=True,
                               environment={"ERAGON_API_KEY": "fixture-secret"})
                result = subprocess.run([sys.executable, str(ROOT / "tests/pty_runner.py")],
                                        input=json.dumps(request), text=True, capture_output=True, timeout=12)
                self.assertEqual(result.returncode, 0, result.stderr)
                reply = json.loads(result.stdout)
                self.assertEqual(reply["exit"], 0, reply["output"])
                self.assertIn("LAUNCHED", reply["output"])
                self.assertNotIn("fixture-secret", reply["output"])

    def test_installed_cli_interactive_selection(self):
        request = dict(script=(ROOT / "eragon.sh").read_text(), command=[self.command],
                       models=json.dumps({"data": [{"id": "claude-sonnet-5"}]}))
        result = subprocess.run([sys.executable, str(ROOT / "tests/pty_runner.py")],
                                input=json.dumps(request), text=True, capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Personal API Key", reply["output"])
        self.assertIn("LAUNCHED", reply["output"])
        self.assertNotIn("fixture-secret", reply["output"])
