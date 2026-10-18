#!/usr/bin/env bash
# Eragon Router for Claude Code and Codex. No persistent configuration or credentials.
# Requires Bash 3.2+, curl and jq. Run from your project: bash eragon.sh
set +x
set -euo pipefail

# Keep this script's variables out of child environments, even with bash -a.
set +a
fail() { printf '%s\n' "$1" >&2; exit 1; }
usage() {
  cat <<'HELP'
Usage: bash eragon.sh [--client claude|codex] [--endpoint HTTPS_URL] [--model MODEL_ID] [--context-window TOKENS]

  --client NAME   claude or codex; skip the interactive client menu.
  --endpoint URL  Gateway base URL (Codex also accepts a trailing /v1).
  --model ID      Use this model directly, without fetching a model list.
  --context-window TOKENS  Actual gateway context/input limit (Claude: >=125000; Codex: >=4096).
  -h, --help      Show this help.

Environment: ERAGON_ENDPOINT, ERAGON_MODEL, ERAGON_API_KEY, ERAGON_CONTEXT_WINDOW, ERAGON_CLIENT.
Optional ERAGON_COMPATIBILITY_FILE: local verified-profile JSON (no keys/URLs).
Flags override environment values. An endpoint must be provided explicitly.
Without a key, prompt with hidden input. Without a model, filter the catalogue.
Keys are never saved. Pass a key through the environment or hidden prompt,
not a command-line argument. Fully configured launches skip these prompts.
HELP
}
unset endpoint selected eragon_key context_limit client
eragon_key=${ERAGON_API_KEY-}
unset ERAGON_API_KEY ERAGON_ROUTER_TOKEN
endpoint=${ERAGON_ENDPOINT-}
selected=${ERAGON_MODEL-}
context_limit=${ERAGON_CONTEXT_WINDOW-}
client=${ERAGON_CLIENT-}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --endpoint|--model|--context-window|--client)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail "Missing value for $1."
      case "$1" in
        --client) client=$2 ;;
        --endpoint) endpoint=$2 ;;
        --model) selected=$2 ;;
        --context-window) context_limit=$2 ;;
      esac
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail 'Unknown option. Run bash eragon.sh --help.' ;;
  esac
done
[[ -n "$endpoint" ]] || fail 'Endpoint required. Use --endpoint or ERAGON_ENDPOINT.'
if [[ -z "$client" ]]; then
  if [[ -t 0 && -t 1 ]]; then
    printf 'Choose a client:\n  1) Claude Code\n  2) Codex\n'
    while true; do
      read -r -p 'Client number [1]: ' client_choice || fail 'Client selection cancelled.'
      case "${client_choice:-1}" in
        1) client=claude; break ;;
        2) client=codex; break ;;
        *) printf 'Enter 1 or 2.\n' ;;
      esac
    done
  else
    # Preserve existing noninteractive invocations.
    client=claude
  fi
fi
case "$client" in
  claude) client_command=claude; client_label='Claude Code'; minimum_context=125000 ;;
  codex) client_command=codex; client_label=Codex; minimum_context=4096 ;;
  *) fail 'Client must be claude or codex.' ;;
esac
for dependency in "$client_command" jq; do
  command -v "$dependency" >/dev/null 2>&1 || fail "Missing $dependency. Install it, then run this script again."
done
# Reject credentials, queries, fragments, control characters and ambiguous URLs.
# Validate before showing the endpoint or sending any credential.
printf '%s' "$endpoint" | jq -eRs '
  test("\\Ahttps://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~%/:-]*)?\\z")
' >/dev/null || fail 'Endpoint must be an HTTPS base URL without credentials, query or fragment.'
while [[ "$endpoint" == */ ]]; do endpoint=${endpoint%/}; done
if [[ "$client" == codex && "$endpoint" == */v1 ]]; then endpoint=${endpoint%/v1}; fi
if [[ -n "$selected" ]]; then
  printf '%s' "$selected" | jq -eRs '
    test("\\A[A-Za-z0-9][A-Za-z0-9._:/-]*\\z")
  ' >/dev/null || fail 'Invalid model ID.'
else
  command -v curl >/dev/null 2>&1 || fail 'Missing curl. Install it, then run this script again.'
  [[ -t 0 && -t 1 ]] || fail 'Model selection needs an interactive terminal. Set --model or ERAGON_MODEL.'
fi
if [[ -n "$context_limit" ]]; then
  printf '%s' "$context_limit" | jq -eRs --argjson minimum "$minimum_context" '
    test("\\A[1-9][0-9]{0,8}\\z") and (tonumber >= $minimum)
  ' >/dev/null || fail "Context window must be an integer from $minimum_context to 999999999 tokens."
fi
# Baselines tested with the CLI overrides used below.
client_version=$("$client_command" --version) || fail "Could not read $client_label version."
if [[ "$client" == claude ]]; then
  client_version=${client_version%% *}; minimum_version='[2,1,302]'
else
  client_version=${client_version##* }; minimum_version='[0,160,0]'
fi
printf '%s' "$client_version" | jq -eRs --argjson minimum "$minimum_version" '
  capture("\\A(?<major>[0-9]+)\\.(?<minor>[0-9]+)\\.(?<patch>[0-9]+)\\z") |
  [.major,.minor,.patch] | map(tonumber) | . >= $minimum
' >/dev/null || fail "Update $client_label to the supported baseline (Claude Code 2.1.302 / Codex 0.160.0) or later. Run claude update or codex update."
printf 'Eragon Router · %s\nEndpoint: %s\n\n' "$client_label" "$endpoint"
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

# Optional local test records. No network or live inference is used to certify.
manifest='{"schema_version":1,"verified":[]}'
endpoint_hash=''
if [[ "$client" == claude && -n "${ERAGON_COMPATIBILITY_FILE-}" ]]; then
  if ! manifest=$(jq -ecs '
    if length != 1 then error("one JSON document required") else .[0] end |
    if (keys - ["schema_version", "verified"] | length) == 0 and
      .schema_version == 1 and (.verified | type == "array") and
      all(.verified[];
        (keys - ["endpoint_sha256", "model_id", "profile", "adapter_version",
                 "claude_code_version", "tested_at", "evidence"] | length) == 0 and
        (.endpoint_sha256 | type == "string" and test("\\A[a-f0-9]{64}\\z")) and
        (.model_id | type == "string" and test("\\A[A-Za-z0-9][A-Za-z0-9._:/-]*\\z")) and
        (.profile == "native" or .profile == "basic") and .adapter_version == 1 and
        (.claude_code_version | type == "string" and length > 0) and
        (.tested_at | type == "string" and length > 0) and
        (.evidence | type == "string" and length > 0))
    then . else error("invalid compatibility manifest") end
  ' "$ERAGON_COMPATIBILITY_FILE" 2>/dev/null); then
    fail 'Invalid compatibility file. See the README schema.'
  fi
fi
if [[ "$(printf '%s' "$manifest" | jq '.verified | length')" != 0 ]]; then
  if command -v shasum >/dev/null 2>&1; then
    endpoint_hash=$(printf '%s' "$endpoint" | shasum -a 256)
  elif command -v sha256sum >/dev/null 2>&1; then
    endpoint_hash=$(printf '%s' "$endpoint" | sha256sum)
  else
    fail 'A SHA-256 tool (shasum or sha256sum) is required for verified profiles.'
  fi
  endpoint_hash=${endpoint_hash%% *}
fi

if [[ -z "$selected" ]]; then
  # Ignore .curlrc, require HTTPS, and do not follow redirects. The credential
  # travels over stdin, so it does not appear in curl's process arguments.
  if ! catalogue=$(printf 'Authorization: Bearer %s\n' "$eragon_key" |
    curl -q --silent --show-error --fail --proto '=https' \
      --connect-timeout 10 --max-time 30 --header @- \
      --url "$endpoint/v1/models"); then
    fail 'Could not load models. Check your key, Gateway access and network, then retry.'
  fi
else
  # Explicit selection preserves the no-discovery path, with an honest warning.
  catalogue=$(jq -cn --arg model "$selected" '{data:[{id:$model}]}')
fi

# Normalize declared capabilities locally. False wins conflicting declarations;
# missing or malformed fields remain unknown. Model names never certify support.
if ! classification=$(printf '%s' "$catalogue" | jq -ecs \
  --arg client "$client" --argjson manifest "$manifest" --arg hash "$endpoint_hash" --arg version "$client_version" '
  def verdict:
    map(select(type == "boolean")) |
    if index(false) != null then false elif index(true) != null then true else null end;
  def cap($name; $flat):
    [.capabilities[$name], .capabilities[$flat], .[$flat], .model_info[$flat]] | verdict;
  def textcap($field):
    [.[$field], .architecture[$field]] |
    map(select(type == "array" and all(.[]; type == "string")) | index("text") != null) | verdict;
  def positive_limit:
    map(select(type == "number" and . > 0 and . <= 999999999 and . == floor)) |
    if length > 0 then min else null end;
  def classify:
    (cap("tools"; "supports_function_calling")) as $tools |
    (cap("streaming"; "supports_streaming")) as $stream |
    (cap("responses"; "supports_responses")) as $responses |
    ([textcap("input_modalities"), .capabilities.text_input,
      (if (.supported_modalities | type) == "array" and
          (.supported_modalities | all(.[]; type == "string")) then
         (.supported_modalities | index("text") != null) else null end)] | verdict) as $input |
    ([textcap("output_modalities"), .capabilities.text_output] | verdict) as $output |
    [.mode, .model_info.mode] as $modes |
    {id:.id,
     context:([.context_length,.context_window,.max_input_tokens,
       .model_info.context_length,.model_info.context_window,.model_info.max_input_tokens] | positive_limit),
     max_output:([.max_output_tokens,.model_info.max_output_tokens] | positive_limit),
     responses:$responses, tools:$tools, streaming:$stream, input:$input, output:$output,
     nonchat: any($modes[]; . == "embedding" or . == "image_generation" or
       . == "audio_generation" or . == "audio_transcription" or . == "audio_speech" or . == "speech" or
       . == "video_generation" or . == "rerank" or . == "moderation")};
  if length != 1 then error("one catalogue document required") else .[0] end |
  ($manifest.verified | map(select(.endpoint_sha256 == $hash and .claude_code_version == $version)) |
    group_by(.model_id) | map({key:.[0].model_id,value:unique_by(.profile)}) | from_entries) as $verified |
  if (.data | type) != "array" then error("invalid catalogue") else . end |
  [.data[] | select(type == "object") |
    select(.id | type == "string") |
    select(.id | test("\\A[A-Za-z0-9][A-Za-z0-9._:/-]*\\z")) |
    .capabilities = (if (.capabilities | type) == "object" then .capabilities else {} end) |
    .model_info = (if (.model_info | type) == "object" then .model_info else {} end) |
    .architecture = (if (.architecture | type) == "object" then .architecture else {} end) |
    classify] |
  group_by(.id) | map(
    . as $duplicates | .[0].id as $id |
    ([$duplicates[].responses] | verdict) as $responses |
    ([$duplicates[].tools] | verdict) as $tools |
    ([$duplicates[].streaming] | verdict) as $stream |
    ([$duplicates[].input] | verdict) as $input |
    ([$duplicates[].output] | verdict) as $output |
    (any($duplicates[]; .nonchat)) as $nonchat |
    ($verified[$id] // []) as $records |
    {id:$id,
     context:([$duplicates[].context] | positive_limit),
     max_output:([$duplicates[].max_output] | positive_limit),
     status:(if ($client == "codex" and $responses == false) or $nonchat or $tools == false or $stream == false or $input == false or $output == false
       then "unsupported"
       elif ($records | length) == 1 then "verified"
       elif $tools == true and $stream == true and $input == true and $output == true and ($client != "codex" or $responses == true)
       then "candidate" else "unverified" end),
     profile:(if ($records | length) == 1 then $records[0].profile
       elif ($id | startswith("claude-")) then "native" else "basic" end)}) |
  {excluded:([.[] | select(.status == "unsupported")] | length),
   models:([.[] | select(.status != "unsupported")] |
      sort_by((if .status == "verified" then 0 elif .status == "candidate" then 1 else 2 end), .id))}
'); then
  fail 'Could not read the model catalogue.'
fi
unset catalogue manifest

if [[ -n "$selected" ]]; then
  profile=$(printf '%s' "$classification" | jq -r '.models[0].profile')
  status=$(printf '%s' "$classification" | jq -r '.models[0].status')
  [[ "$status" == verified ]] || printf 'Explicit model: capabilities and tool compatibility have not been verified.\n'
else
  rows=$(printf '%s' "$classification" | jq -r '.models[] | [.id,.status,.profile] | @tsv')
  [[ -n "$rows" ]] || fail 'No usable models: catalogue is empty or declares unsupported capabilities.'
  models=(); statuses=(); profiles=(); primary_count=0
  while IFS=$'\t' read -r model status profile; do
    models+=("$model"); statuses+=("$status"); profiles+=("$profile")
    if [[ "$status" != unverified ]]; then primary_count=$((primary_count + 1)); fi
  done <<< "$rows"
  excluded=$(printf '%s' "$classification" | jq '.excluded')
  printf '\nCapability screening: %s unsupported model(s) excluded. No inference probes.\n' "$excluded"
  visible_count=$primary_count
  if [[ "$visible_count" == 0 ]]; then
    visible_count=${#models[@]}
    printf 'No verified or fully declared candidates; showing unverified models.\n'
  fi
  while true; do
    printf '\nChoose a model:\n'
    for ((index=0; index<visible_count; index++)); do
      case "${statuses[index]}" in
        verified) label='verified for this endpoint/client/adapter' ;;
        candidate) label='capabilities declared; not tested' ;;
        *) label='unverified' ;;
      esac
      printf '  %d) %s [%s]\n' "$((index + 1))" "${models[index]}" "$label"
    done
    if [[ "$visible_count" != "${#models[@]}" ]]; then
      printf '  m) Show %d unverified model(s)\n' "$((${#models[@]} - visible_count))"
    fi
    read -r -p 'Model number [1]: ' choice
    choice=${choice:-1}
    if [[ "$choice" == m ]]; then visible_count=${#models[@]}; continue; fi
    selected=''
    for ((index=0; index<visible_count; index++)); do
      if [[ "$choice" == "$((index + 1))" ]]; then
        selected=${models[index]}; profile=${profiles[index]}; break
      fi
    done
    [[ -n "$selected" ]] && break
    printf 'Enter one of the model numbers above.\n'
  done
fi
# Apply capacity to the selected ID only. Duplicate routes use the smallest
# declared bound; an explicit limit may lower, but never raise, that bound.
limits=$(printf '%s' "$classification" | jq -c --arg id "$selected" \
  '.models[] | select(.id == $id) | {context,max_output}')
context_limit=$(printf '%s' "$limits" | jq -r --arg configured "$context_limit" '
  [.context, (if $configured == "" then null else ($configured | tonumber) end)] |
  map(select(. != null)) | if length > 0 then min else 0 end')
output_limit=$(printf '%s' "$limits" | jq -r '[.max_output,8192] | map(select(. != null)) | min')
if [[ "$client" == codex ]]; then
  if [[ "$context_limit" == 0 ]]; then
    context_limit=125000
    printf 'Context capacity unknown: assuming 125000 tokens. Set --context-window to the actual gateway limit.\n'
  fi
  [[ "$context_limit" -ge "$minimum_context" ]] || fail 'Declared context is below 4096 tokens; choose a model with a larger window.'
  compact_window=$((context_limit / 5 * 4))
  printf 'Codex context: %s tokens; compaction threshold: %s.\n' "$context_limit" "$compact_window"
elif [[ "$context_limit" == 0 ]]; then
  compact_window=100000
  printf 'Context capacity unknown: using a conservative 100000-token compaction window.\n'
  printf 'Set --context-window to the actual limit; limits below 125000 are unsupported.\n'
else
  [[ "$context_limit" -ge 125000 ]] || fail 'Declared context is below 125000 tokens; this launcher cannot safely configure its compaction window for this model.'
  compact_window=$((context_limit / 5 * 4))
  [[ "$compact_window" -le 1000000 ]] || compact_window=1000000
  printf 'Gateway capacity: %s tokens; compaction window: %s; output cap: %s.\n' "$context_limit" "$compact_window" "$output_limit"
fi
unset classification rows limits

if [[ "$client" == codex ]]; then
  # Inline TOML contains public settings and the environment variable NAME only.
  # Replacing the whole provider table prevents inherited auth/header settings.
  provider="{name=\"Eragon Router\",base_url=\"$endpoint/v1\",env_key=\"ERAGON_ROUTER_TOKEN\",wire_api=\"responses\",requires_openai_auth=false,supports_websockets=false}"
  export ERAGON_ROUTER_TOKEN="$eragon_key"
  unset eragon_key ERAGON_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY OPENAI_API_KEY
  printf '\nStarting Codex with %s… Gateway must support Responses streaming and tools.\n' "$selected"
  # Stay in this process tree so an existing shared daemon cannot lose the key.
  # Local compaction uses Responses; no /responses/compact endpoint is required.
  exec codex --no-daemon --model "$selected" \
    -c 'model_provider="eragon_router"' \
    -c "model_providers.eragon_router=$provider" \
    -c "model_context_window=$context_limit" \
    -c "model_auto_compact_token_limit=$compact_window" \
    -c 'model_auto_compact_token_limit_scope="total"' \
    -c 'model_reasoning_summary="none"' \
    -c 'web_search="disabled"'
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
# public connection settings through higher-priority CLI settings; the key stays in env.
# Basic is a client-side compatibility profile, not a protocol translator.
# The configured gateway must expose Anthropic Messages for these models.
if [[ "$profile" == basic ]]; then
  export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1 CLAUDE_CODE_DISABLE_THINKING=1
  export CLAUDE_CODE_EFFORT_LEVEL=auto DISABLE_PROMPT_CACHING=1
  launcher_settings=$(jq -cn --arg url "$endpoint" '{env:{ANTHROPIC_BASE_URL:$url,
    CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS:"1",CLAUDE_CODE_DISABLE_THINKING:"1",
    CLAUDE_CODE_EFFORT_LEVEL:"auto",DISABLE_PROMPT_CACHING:"1"}}')
else
  launcher_settings=$(jq -cn --arg url "$endpoint" '{env:{ANTHROPIC_BASE_URL:$url}}')
fi
# Set compaction rather than MAX_CONTEXT_TOKENS: for recognized Claude IDs the
# latter requires disabling compaction, defeating the protection we need.
export CLAUDE_CODE_AUTO_COMPACT_WINDOW="$compact_window"
export CLAUDE_CODE_MAX_OUTPUT_TOKENS="$output_limit"
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90
unset DISABLE_COMPACT DISABLE_AUTO_COMPACT
launcher_settings=$(printf '%s' "$launcher_settings" | jq -c \
  --arg window "$compact_window" --arg output "$output_limit" '
  .env += {CLAUDE_CODE_AUTO_COMPACT_WINDOW:$window,
    CLAUDE_CODE_MAX_OUTPUT_TOKENS:$output, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE:"90",
    DISABLE_COMPACT:"",DISABLE_AUTO_COMPACT:""}')
exec claude --model "$selected" --settings "$launcher_settings"
