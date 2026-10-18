#!/usr/bin/env bash
# Eragon Router for Claude Code. No persistent configuration or credentials.
# Requires Bash 3.2+, curl and jq. Run from your project: bash eragon.sh
set +x
set -euo pipefail

# Keep this script's variables out of child environments, even with bash -a.
set +a
fail() { printf '%s\n' "$1" >&2; exit 1; }
usage() {
  cat <<'HELP'
Usage: bash eragon.sh [--endpoint HTTPS_URL] [--model MODEL_ID]

  --endpoint URL  Anthropic-compatible base URL (no /v1 suffix).
  --model ID      Use this model directly, without fetching a model list.
  -h, --help      Show this help.

Environment: ERAGON_ENDPOINT, ERAGON_MODEL, ERAGON_API_KEY.
Flags override environment values. An endpoint must be provided explicitly.
Without a key, prompt with hidden input. Without a model, offer Claude models.
Keys are never saved. Pass a key through the environment or hidden prompt,
not a command-line argument. Fully configured launches skip these prompts.
HELP
}
unset endpoint selected eragon_key
eragon_key=${ERAGON_API_KEY-}
unset ERAGON_API_KEY
endpoint=${ERAGON_ENDPOINT-}
selected=${ERAGON_MODEL-}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --endpoint|--model)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail "Missing value for $1."
      if [[ "$1" == --endpoint ]]; then endpoint=$2; else selected=$2; fi
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail 'Unknown option. Run bash eragon.sh --help.' ;;
  esac
done
[[ -n "$endpoint" ]] || fail 'Endpoint required. Use --endpoint or ERAGON_ENDPOINT.'
for dependency in claude jq; do
  command -v "$dependency" >/dev/null 2>&1 || fail "Missing $dependency. Install it, then run this script again."
done
# Reject credentials, queries, fragments, control characters and ambiguous URLs.
# Validate before showing the endpoint or sending any credential.
printf '%s' "$endpoint" | jq -eRs '
  test("\\Ahttps://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~%/:-]*)?\\z")
' >/dev/null || fail 'Endpoint must be an HTTPS base URL without credentials, query or fragment.'
while [[ "$endpoint" == */ ]]; do endpoint=${endpoint%/}; done
if [[ -n "$selected" ]]; then
  printf '%s' "$selected" | jq -eRs '
    test("\\A[A-Za-z0-9][A-Za-z0-9._:/-]*\\z")
  ' >/dev/null || fail 'Invalid model ID.'
else
  command -v curl >/dev/null 2>&1 || fail 'Missing curl. Install it, then run this script again.'
  [[ -t 0 && -t 1 ]] || fail 'Model selection needs an interactive terminal. Set --model or ERAGON_MODEL.'
fi
printf 'Eragon Router · Claude Code\nEndpoint: %s\n\n' "$endpoint"
if [[ -z "$eragon_key" ]]; then
  [[ -t 0 && -t 1 ]] || fail 'Set ERAGON_API_KEY or run in an interactive terminal to enter a key.'
  command -v stty >/dev/null 2>&1 || fail 'Missing stty.'
  # Disable echo before printing the prompt, including an immediate paste.
  terminal_mode=$(stty -g)
  trap 'stty "$terminal_mode"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  stty -echo
  read -r -p 'Personal API Key: ' eragon_key
  stty "$terminal_mode"
  trap - EXIT INT TERM
  unset terminal_mode
  printf '\n'
fi
[[ -n "$eragon_key" ]] || fail 'An API key is required.'
# Reject header injection, including pasted carriage returns.
[[ "$eragon_key" != *$'\r'* && "$eragon_key" != *$'\n'* ]] || fail 'Invalid API key.'

if [[ -z "$selected" ]]; then
  # Ignore .curlrc, require HTTPS, and do not follow redirects. The credential
  # travels over stdin, so it does not appear in curl's process arguments.
  if ! catalogue=$(printf 'Authorization: Bearer %s\n' "$eragon_key" |
    curl -q --silent --show-error --fail --proto '=https' \
      --connect-timeout 10 --max-time 30 --header @- \
      --url "$endpoint/v1/models"); then
    fail 'Could not load models. Check your key, Gateway access and network, then retry.'
  fi

  # Only literal Claude IDs are offered. Never evaluate server-provided text.
  if ! model_list=$(printf '%s' "$catalogue" | jq -er '
    [.data[] | .id | select(type == "string") |
      select(test("\\Aclaude-[a-zA-Z0-9._:-]+\\z"))] | unique | .[]'); then
    fail 'No Claude models are available. Check this key’s model access in Keys.'
  fi
  unset catalogue
  models=()
  while IFS= read -r model; do models+=("$model"); done <<< "$model_list"
  unset model_list
  printf '\nChoose a model:\n'
  for index in "${!models[@]}"; do
    printf '  %d) %s\n' "$((index + 1))" "${models[index]}"
  done
  while true; do
    read -r -p 'Model number [1]: ' choice
    choice=${choice:-1}
    # Match the displayed numbers literally; never evaluate input as arithmetic.
    selected=''
    for index in "${!models[@]}"; do
      if [[ "$choice" == "$((index + 1))" ]]; then selected=${models[index]}; break; fi
    done
    [[ -n "$selected" ]] && break
    printf 'Enter one of the model numbers above.\n'
  done
fi

export ANTHROPIC_BASE_URL="$endpoint"
export ANTHROPIC_AUTH_TOKEN="$eragon_key"
unset eragon_key ANTHROPIC_API_KEY ERAGON_API_KEY
# Clear basic-compatibility settings left by a previous non-Claude setup.
unset CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS CLAUDE_CODE_DISABLE_THINKING
unset CLAUDE_CODE_EFFORT_LEVEL DISABLE_PROMPT_CACHING
export ANTHROPIC_CUSTOM_MODEL_OPTION="$selected"
printf '\nStarting Claude Code with %s…\n' "$selected"
# Saved user/project settings.env can override terminal exports. Pin only the
# public endpoint through higher-priority CLI settings; the key stays in env.
launcher_settings=$(jq -cn --arg url "$endpoint" '{env:{ANTHROPIC_BASE_URL:$url}}')
exec claude --model "$selected" --settings "$launcher_settings"
