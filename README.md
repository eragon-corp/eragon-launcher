# Eragon Router

Start Claude Code through a configurable Anthropic-compatible HTTPS endpoint. No service endpoint is built in.
Requires macOS or Linux, Bash 3.2+, an installed Claude Code CLI, curl, jq, and an API key for the selected endpoint.

Download [eragon.sh](https://github.com/eragon-corp/eragon-router/raw/refs/heads/main/eragon.sh), then run it from your project folder:

```bash
bash ~/Downloads/eragon.sh --endpoint https://gateway.example.com/gw
```

Paste your key at the hidden prompt, select one of the Claude models available to that key, and Claude Code starts. Press Enter to choose the first model. Model availability and access come from Gateway at runtime.

## Configuration

All three connection values are configurable without editing the script or saving a config file.

| Value | Command-line option | Environment | Default |
| --- | --- | --- | --- |
| Endpoint | `--endpoint URL` | `ERAGON_ENDPOINT` | Required; no built-in endpoint |
| API key | Hidden prompt | `ERAGON_API_KEY` | Ask with hidden input |
| Model | `--model ID` | `ERAGON_MODEL` | Fetch and select a Claude model |

Options override environment values. The endpoint must be an HTTPS base URL without credentials, a query, or a fragment. Trailing slashes are removed. Use the Anthropic-compatible base URL, normally without a `/v1` suffix.

For example, configure an endpoint and model, then enter the key at the hidden prompt:

```bash
bash ~/Downloads/eragon.sh \
  --endpoint https://gateway.example.com/gw \
  --model claude-sonnet-5
```

Alternatively, configure the endpoint and model in your shell, and provide `ERAGON_API_KEY` through your secret manager or parent process environment:

```bash
export ERAGON_ENDPOINT=https://gateway.example.com/gw
export ERAGON_MODEL=claude-sonnet-5
bash ~/Downloads/eragon.sh
```

With all three values configured, the launcher skips its own prompts and terminal checks. Claude Code retains its normal terminal requirements. An explicit model ID bypasses `/v1/models`, so custom model aliases and endpoints without model discovery work too. The selected endpoint decides whether that model is available. If no model is configured, the launcher fetches `/v1/models` using the key and offers native Claude IDs interactively.

There is deliberately no `--api-key` argument: command-line secrets can appear in process listings and shell history. Do not paste literal keys into shell commands or config files. Existing `ANTHROPIC_*` variables are not used as configuration inputs; use the `ERAGON_*` values above.

Run `bash eragon.sh --help` for usage.

## Credentials and data

The launcher does not write your key to disk, shell history, Claude settings, or command arguments. When discovering models, it passes the key to curl over stdin. It passes the key to Claude Code through its process environment. The key remains accessible to processes with sufficient local privileges. The launcher does not add telemetry or install dependencies.

Claude Code sends inference requests, including conversation and project context it uses, to your configured endpoint. The launcher does not change Claude Code's own storage, logging, or data policies. Do not interpret the launcher's no-file-write behavior as a promise that the entire Claude Code session has no local storage.

Review the downloaded script before running it. Never commit a personal key or paste it into an issue.

## Test

Python 3 and jq are required. Tests use fake executables and fixture credentials in a real terminal; they make no network requests or paid model calls.

```bash
bash -n eragon.sh
python3 -m unittest discover -s tests -v
```

The tests cover hidden input, model selection, invalid input/catalogues, cancellation, terminal restoration, authentication failure, credential handling, and file writes.
