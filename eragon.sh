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
Optional ERAGON_COMPATIBILITY_FILE: local verified-profile JSON (no keys/URLs).
Flags override environment values. An endpoint must be provided explicitly.
Without a key, prompt with hidden input. Without a model, filter the catalogue.
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

# Optional local test records. No network or live inference is used to certify.
manifest='{"schema_version":1,"verified":[]}'
endpoint_hash=''
client_version=''
if [[ -n "${ERAGON_COMPATIBILITY_FILE-}" ]]; then
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
  client_version=$(claude --version) || fail 'Could not read Claude Code version.'
  client_version=${client_version%% *}
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
  --argjson manifest "$manifest" --arg hash "$endpoint_hash" --arg version "$client_version" '
  def verdict:
    map(select(type == "boolean")) |
    if index(false) != null then false elif index(true) != null then true else null end;
  def cap($name; $flat):
    [.capabilities[$name], .capabilities[$flat], .[$flat], .model_info[$flat]] | verdict;
  def textcap($field):
    [.[$field], .architecture[$field]] |
    map(select(type == "array" and all(.[]; type == "string")) | index("text") != null) | verdict;
  def classify:
    (cap("tools"; "supports_function_calling")) as $tools |
    (cap("streaming"; "supports_streaming")) as $stream |
    ([textcap("input_modalities"), .capabilities.text_input,
      (if (.supported_modalities | type) == "array" and
          (.supported_modalities | all(.[]; type == "string")) then
         (.supported_modalities | index("text") != null) else null end)] | verdict) as $input |
    ([textcap("output_modalities"), .capabilities.text_output] | verdict) as $output |
    [.mode, .model_info.mode] as $modes |
    {id:.id, tools:$tools, streaming:$stream, input:$input, output:$output,
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
    ([$duplicates[].tools] | verdict) as $tools |
    ([$duplicates[].streaming] | verdict) as $stream |
    ([$duplicates[].input] | verdict) as $input |
    ([$duplicates[].output] | verdict) as $output |
    (any($duplicates[]; .nonchat)) as $nonchat |
    ($verified[$id] // []) as $records |
    {id:$id,
     status:(if $nonchat or $tools == false or $stream == false or $input == false or $output == false
       then "unsupported"
       elif ($records | length) == 1 then "verified"
       elif $tools == true and $stream == true and $input == true and $output == true
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
unset classification rows

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
exec claude --model "$selected" --settings "$launcher_settings"
