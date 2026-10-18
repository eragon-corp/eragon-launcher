# Optional smoke check against installed Pi and OpenCode; no inference calls.
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
for client in ["pi", "opencode"]:
    real_cli = os.environ.get("ERAGON_TEST_" + client.upper() + "_BIN") or shutil.which(client)
    if not real_cli:
        raise SystemExit("Install " + client + " before running this optional check.")
    with tempfile.TemporaryDirectory(prefix="eragon-cli-check-") as taskdir:
        root = pathlib.Path(taskdir)
        shimdir = root / "bin"
        shimdir.mkdir()
        shim = shimdir / client
        shim.write_text('#!/bin/bash\nif [[ "$1" == --version ]]; then exec "$REAL_ROUTER_CLI" --version; fi\n' + (
            'exec "$REAL_ROUTER_CLI" --offline --no-extensions --extension "$2" --list-models eragon_router\n'
            if client == "pi" else 'exec "$REAL_ROUTER_CLI" --pure debug config\n'))
        shim.chmod(0o700)
        env = dict(os.environ, PATH=str(shimdir) + os.pathsep + os.environ["PATH"],
                   REAL_ROUTER_CLI=real_cli, ERAGON_API_KEY="fixture-secret", PI_TELEMETRY="0",
                   PI_CODING_AGENT_DIR=str(root / "pi-agent"), XDG_CONFIG_HOME=str(root / "config"),
                   XDG_DATA_HOME=str(root / "data"), XDG_CACHE_HOME=str(root / "cache"),
                   OPENCODE_DISABLE_MODELS_FETCH="1", TMPDIR=str(root))
        for key in ["ERAGON_COMPATIBILITY_FILE", "ERAGON_CONTEXT_WINDOW", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR"]:
            env.pop(key, None)
        result = subprocess.run(["/bin/bash", str(ROOT / "eragon.sh"), "--client", client,
                                 "--endpoint", "https://gateway.example.com/gw", "--model", "team/coder",
                                 "--context-window", "64000"], env=env, cwd=root,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(client + " smoke check failed: " +
                                 result.stderr.replace("fixture-secret", "[REDACTED]")[-1500:])
        if client == "pi":
            assert "team/coder" in result.stdout
            assert not list(root.glob("eragon-router.*"))
        else:
            config = json.loads(result.stdout[result.stdout.index("{"):])
            assert config["model"] == "eragon_router/team/coder"
            provider = config["provider"]["eragon_router"]
            assert provider["options"]["baseURL"] == "https://gateway.example.com/gw/v1"
            assert provider["options"]["apiKey"] == "fixture-secret"
            assert provider["models"]["team/coder"]["limit"] == {"context": 64000, "output": 8192}
            assert config["compaction"]["reserved"] == 12800
        leaks = [str(p.relative_to(root)) for p in root.rglob("*")
                 if p.is_file() and b"fixture-secret" in p.read_bytes()]
        assert not leaks, "Credential persisted in " + str(leaks)
        print(client + ": real CLI configuration loaded; no inference or credential files; temp extension cleaned.")
