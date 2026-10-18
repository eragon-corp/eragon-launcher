#!/usr/bin/env bash
# Eragon Router for Claude Code. Contains the public Gateway URL, never a key.
# Requires Bash 3.2+, curl and jq. Run from your project: bash eragon.sh
set +x
set -euo pipefail

# Keep this script's variables out of child environments, even with bash -a.
set +a
ERAGON_GATEWAY_URL="${ERAGON_ENDPOINT-}"

fail() { printf '%s\n' "$1" >&2; exit 1; }
for dependency in claude curl jq stty; do
  command -v "$dependency" >/dev/null 2>&1 || fail "Missing $dependency. Install it, then run this script again."
done
[[ -t 0 && -t 1 ]] || fail 'Run this script in an interactive terminal: bash eragon.sh'
[[ "$ERAGON_GATEWAY_URL" == https://* ]] || fail 'Set ERAGON_ENDPOINT to an HTTPS base URL.'

printf 'Eragon Router · Claude Code\n\n'
# A private shell variable: not a command argument, file or exported variable.
# Disable echo before printing the prompt, so an immediate paste is hidden too.
terminal_mode=$(stty -g)
trap 'stty "$terminal_mode"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
stty -echo
unset eragon_key
read -r -p 'Personal API Key: ' eragon_key
stty "$terminal_mode"
trap - EXIT INT TERM
unset terminal_mode
printf '\n'
[[ -n "$eragon_key" ]] || fail 'An API key is required.'
# Reject header injection, including pasted carriage returns.
[[ "$eragon_key" != *$'\r'* && "$eragon_key" != *$'\n'* ]] || fail 'Invalid API key.'

# Ignore .curlrc, require HTTPS, and do not follow redirects. The credential
# travels over stdin, so it does not appear in curl's process arguments.
if ! catalogue=$(printf 'Authorization: Bearer %s\n' "$eragon_key" |
  curl -q --silent --show-error --fail --proto '=https' \
    --connect-timeout 10 --max-time 30 --header @- \
    --url "$ERAGON_GATEWAY_URL/v1/models"); then
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

export ANTHROPIC_BASE_URL="$ERAGON_GATEWAY_URL"
export ANTHROPIC_AUTH_TOKEN="$eragon_key"
unset eragon_key ANTHROPIC_API_KEY ERAGON_API_KEY
# Clear basic-compatibility settings left by a previous non-Claude setup.
unset CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS CLAUDE_CODE_DISABLE_THINKING
unset CLAUDE_CODE_EFFORT_LEVEL DISABLE_PROMPT_CACHING
export ANTHROPIC_CUSTOM_MODEL_OPTION="$selected"
printf '\nStarting Claude Code with %s…\n' "$selected"
# Saved user/project settings.env can override terminal exports. Pin only the
# public endpoint through higher-priority CLI settings; the key stays in env.
launcher_settings=$(jq -cn --arg url "$ERAGON_GATEWAY_URL" '{env:{ANTHROPIC_BASE_URL:$url}}')
exec claude --model "$selected" --settings "$launcher_settings"
