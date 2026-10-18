# Eragon Router

Start Claude Code through Eragon Gateway with an interactive model selector.
Requires macOS or Linux, Bash 3.2+, an installed Claude Code CLI, curl, jq, and a personal Eragon API key.

Download [eragon.sh](https://github.com/eragon-corp/eragon-router/raw/refs/heads/main/eragon.sh), then run it from your project folder:

```bash
ERAGON_ENDPOINT=https://gateway.example.com/gw bash ~/Downloads/eragon.sh
```

Paste your key at the hidden prompt, select one of the Claude models available to that key, and Claude Code starts. Press Enter to choose the first model. Model availability and access come from Gateway at runtime.

Set `ERAGON_ENDPOINT` to your HTTPS base URL before launching. No service endpoint is built in; the URL above is a documentation placeholder.

## Credentials and data

The launcher does not write your key to disk, shell history, Claude settings, or command arguments. It passes the key to curl over stdin to retrieve models and to Claude Code through its process environment. The key remains accessible to processes with sufficient local privileges. The launcher does not add telemetry or install dependencies.

Claude Code sends inference requests, including conversation and project context it uses, through Eragon Gateway to model providers. The launcher does not change Claude Code's own storage, logging, or data policies. Do not interpret the launcher's no-file-write behavior as a promise that the entire Claude Code session has no local storage.

Review the downloaded script before running it. Never commit a personal key or paste it into an issue.

## Test

Python 3 and jq are required. Tests use fake executables and fixture credentials in a real terminal; they make no network requests or paid model calls.

```bash
bash -n eragon.sh
python3 -m unittest discover -s tests -v
```

The tests cover hidden input, model selection, invalid input/catalogues, cancellation, terminal restoration, authentication failure, credential handling, and file writes.
