# Eragon Router

Start Claude Code through a configurable Anthropic-compatible HTTPS endpoint. No service endpoint is built in.
Requires macOS or Linux, Bash 3.2+, Claude Code 2.1.302 or later, curl, jq, and an API key for the selected endpoint.

Download [eragon.sh](https://github.com/eragon-corp/eragon-router/raw/refs/heads/main/eragon.sh), then run it from your project folder:

```bash
bash ~/Downloads/eragon.sh --endpoint https://gateway.example.com/gw
```

Paste your key at the hidden prompt, select a model from the screened catalogue, and Claude Code starts. Press Enter to choose the first displayed model. Model availability and access come from your configured gateway at runtime.

## Configuration

All three connection values are configurable without editing the script or saving a config file.

| Value | Command-line option | Environment | Default |
| --- | --- | --- | --- |
| Endpoint | `--endpoint URL` | `ERAGON_ENDPOINT` | Required; no built-in endpoint |
| API key | Hidden prompt | `ERAGON_API_KEY` | Ask with hidden input |
| Model | `--model ID` | `ERAGON_MODEL` | Fetch, screen and select a model |
| Context/input capacity | `--context-window TOKENS` | `ERAGON_CONTEXT_WINDOW` | Catalogue metadata, otherwise conservative fallback |

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

With all three values configured, the launcher skips its own prompts and terminal checks. Claude Code retains its normal terminal requirements. An explicit model ID bypasses `/v1/models`, so custom model aliases and endpoints without model discovery work too. The selected endpoint decides whether that model is available. If no model is configured, the launcher fetches `/v1/models` using the key and screens the returned capability metadata locally and offers usable models interactively.

There is deliberately no `--api-key` argument: command-line secrets can appear in process listings and shell history. Do not paste literal keys into shell commands or config files. Existing `ANTHROPIC_*` variables are not used as configuration inputs; use the `ERAGON_*` values above.

Run `bash eragon.sh --help` for usage.

## Fast capability screening

Startup makes **one catalogue request**, not a paid inference request per model. Screening uses that response locally; it never guesses compatibility from a model name.

- **Verified**: an exact record in your optional local compatibility file matches the endpoint SHA-256, model ID, installed Claude Code version, and adapter version.
- **Capabilities declared; not tested**: text input/output, tools and streaming are all explicitly declared. This is a candidate, not a certification.
- **Unverified**: required metadata is missing. Press `m` to show these models. If every model is unverified, they are displayed with a warning so minimal `/v1/models` endpoints remain usable.
- **Unsupported**: an explicit false for a required capability, text excluded from declared modalities, or a dedicated embedding/image/audio/video/rerank/moderation mode excludes the model. Negative declarations win conflicts, including duplicate model IDs.

Recognized fields include `capabilities.tools`, `capabilities.streaming`, `capabilities.text_input`, `capabilities.text_output`; `supports_function_calling` and `supports_streaming` at the top level, under `capabilities`, or in `model_info`; and `input_modalities` / `output_modalities` arrays at the top level or in `architecture`. `supported_modalities` is also recognized for input. Missing or malformed fields stay unknown. An ID-only catalogue does not supply enough metadata to certify even a Claude model.

Models named `claude-*` use the native profile by default. Other IDs use the basic profile: disable experimental betas, thinking and prompt caching, and select automatic effort. These settings are pinned through CLI settings to override saved project settings. A verified record can select a different profile for a custom alias. These profiles configure the client; they **do not translate protocols**. The gateway must expose Anthropic Messages for the selected model. Metadata alone cannot guarantee that tool execution works.

An explicit `--model` or `ERAGON_MODEL` bypasses catalogue screening and prints an unverified warning unless a matching verification record exists. It still applies the appropriate client profile.

### Context capacity and early compaction

The launcher reads positive integer `context_length`, `context_window`, and `max_input_tokens` values at the top level or in `model_info`. It uses the smallest declared limit across fields and duplicate routes. `--context-window` / `ERAGON_CONTEXT_WINDOW` can lower that bound; it cannot increase a declared bound. For explicit model IDs, discovery is still skipped, so supply the actual gateway limit yourself:

```bash
bash ~/Downloads/eragon.sh --endpoint https://gateway.example.com/gw \
  --model example/coder --context-window 200000
```

The launcher sets `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to 80% of that limit, capped at 1M, and `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90` to compact earlier where the client supports proactive compaction. It caps most response requests at 8192 output tokens, or a smaller declared `max_output_tokens`. These values are pinned through CLI settings; inherited compaction-disable switches are cleared. This changes compaction timing, not the model's actual capacity. It deliberately does not use `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, whose effect for recognized Claude IDs requires disabling compaction. See the [Claude Code context configuration](https://code.claude.com/docs/en/model-config#context-window-and-auto-compaction).

Without capacity metadata, startup warns and uses a 100K compaction window plus the output cap. This is a conservative fallback, **not proof that the gateway supports that capacity**. The supported auto-compact window starts at 100K; with headroom, declared limits below 125K are refused. Use a larger model for those routes. Missing, stale or inaccurate metadata, a sudden large tool result, or a gateway fallback to a smaller model can still cause an overflow. The launcher makes no extra inference probes.

Use an up-to-date CLI (`claude update`); the launcher requires 2.1.302 or later as its supported baseline. Start a new session after changing model or capacity so the selected model's budget is reapplied. Existing oversized conversations may need a smaller summary in a new session; this cannot retroactively shrink an already rejected request. Capability verification records do not certify context capacity.

### Optional compatibility records

The built-in verification list is empty. No model or endpoint is certified merely by installing this script. There are no extra remote manifest downloads, background probes, or on-disk caches. The launcher remains a single downloadable file.

Copy `compatibility.example.json` to `compatibility.local.json` and set `ERAGON_COMPATIBILITY_FILE` to its path. The local filename is ignored by Git. After testing a real text stream, tool call, tool-result follow-up, multiple turns and cancellation, add a record like this (all values below are placeholders):

```json
{
  "schema_version": 1,
  "verified": [{
    "endpoint_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "model_id": "example/coder",
    "profile": "basic",
    "adapter_version": 1,
    "claude_code_version": "YOUR_INSTALLED_VERSION",
    "tested_at": "YOUR_TEST_DATE",
    "evidence": "YOUR_TEST_REPORT_PATH_OR_IDENTIFIER"
  }]
}
```

Hash the HTTPS endpoint with trailing slashes removed, **without a newline** (`printf %s "$ERAGON_ENDPOINT" | shasum -a 256`, or `sha256sum` on Linux). Use the first token from `claude --version` as `claude_code_version`. Do not put API keys or real endpoint URLs in records. Both `native` and `basic` profiles are supported. A conflicting pair of profiles is not treated as verified. Invalid schemas fail before catalogue requests.

Records are trusted, operator-maintained test results, not proof generated by the launcher. Rerun certification and remove stale records whenever the gateway configuration or upstream model changes. Hashes keep endpoint literals out of the file; they do not make a known endpoint secret.

## Credentials and data

The launcher does not write your key to disk, shell history, Claude settings, or command arguments. When discovering models, it passes the key to curl over stdin. It passes the key to Claude Code through its process environment. The key remains accessible to processes with sufficient local privileges. The launcher does not add telemetry or install dependencies.

Claude Code sends inference requests, including conversation and project context it uses, to your configured endpoint. The launcher does not change Claude Code's own storage, logging, or data policies. Do not interpret the launcher's no-file-write behavior as a promise that the entire Claude Code session has no local storage.

Review the downloaded script before running it. Never commit a personal key or paste it into an issue.

## Test

Python 3.9+ and jq are required. Tests use fake executables and fixture credentials in a real terminal; they make no network requests or paid model calls.

```bash
bash -n eragon.sh
python3 -m unittest discover -s tests -v
```

The tests cover hidden input, model selection, invalid input/catalogues, cancellation, terminal restoration, authentication failure, credential handling, and file writes.
