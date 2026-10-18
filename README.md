# Eragon Router

Connect Claude Code, Codex, Pi Agent, or OpenCode to your model Gateway from one interactive launcher. Choose a client, enter your Gateway URL and API key, and find the model you want to use.

## Get started

You need:

- macOS or Linux with Bash 3.2+, `curl`, and `jq`.
- A Gateway URL and an API key with access to your chosen model, provided by your administrator.
- One of the supported clients installed. You only need the client you plan to use.

| Client | Minimum supported version |
| --- | --- |
| Claude Code | 2.1.302 |
| Codex | 0.160.0 |
| Pi Agent | 0.73.1 |
| OpenCode | 1.3.7 |

1. Download the launcher from the public [Eragon Router repository](https://github.com/eragon-corp/eragon-router):

   ```bash
   mkdir -p "$HOME/Downloads"
   curl -fsSL https://raw.githubusercontent.com/eragon-corp/eragon-router/main/eragon.sh \
     -o "$HOME/Downloads/eragon.sh"
   ```

   You can also [download eragon.sh directly](https://raw.githubusercontent.com/eragon-corp/eragon-router/main/eragon.sh) and save it to your Downloads folder.

2. Open a terminal in the project you want to work on.
3. Run:

   ```bash
   bash ~/Downloads/eragon.sh
   ```

The launcher guides you through these steps:

1. **Enter your Gateway URL.** Use the HTTPS base URL supplied by your administrator. No Gateway address is built in.
2. **Choose a client.** Select Claude Code, Codex, Pi Agent, or OpenCode.
3. **Enter your API key.** Input is hidden, so nothing appears as you type or paste.
4. **Choose a model.** Enter a number, or type `/keyword` to search.
5. **Choose whether to remember your key.** Enter `y` to save it locally, or press Enter to use it for this run only.

Your selected client then opens in your current project folder.

## Next time you run it

Run the same command:

```bash
bash ~/Downloads/eragon.sh
```

If you remembered credentials, press Enter at the Gateway prompt to reuse the saved address. After choosing a client, you can use the saved key or update it:

```text
API key saved for this Gateway:
  1) Use saved key
  2) Update saved key
  q) Quit
Key action [1]:
```

Press Enter to continue with the saved key. Choose `2` to enter a replacement. Updates apply only to the selected Gateway; other saved Gateways keep their own keys. Cancelling or failing to load the model list preserves the old key.

To use a different Gateway, enter its URL at the first prompt. A key saved for another Gateway is not automatically reused.

## Find a model

The model menu shows models available through your Gateway and key. Models that explicitly declare incompatible capabilities are excluded.

| Input | Action |
| --- | --- |
| A model number | Select that model from the current results |
| Enter | Select the first displayed model |
| `/keyword` | Search model IDs, ignoring letter case |
| `/` | Clear the search |
| `m` | Show all usable models, including unverified entries |

For example, enter `/sonnet` to find IDs containing `sonnet`. Search runs locally and does not send additional requests to the Gateway.

Models with incomplete compatibility information appear without a status label. A model marked **capabilities declared; not tested** has the required metadata but has not been tested by the launcher. A displayed model is not a guarantee that every client feature will work. Ask your administrator which models are supported for your client.

## Manage your API key

Saving is optional. Remembered Gateway URLs and keys are stored in a **local plaintext file**:

```text
~/.config/eragon-router/credentials.json
```

If `XDG_CONFIG_HOME` is set, the file is stored under that directory instead. The launcher sets the directory permissions to `700` and the file permissions to `600`, limiting access to your user account. This is not encrypted storage; anyone with sufficient local privileges can read it.

You can update a saved key from the interactive menu, or go directly to the replacement flow:

```bash
bash ~/Downloads/eragon.sh --update-key
```

To remove **all** remembered Gateway credentials:

```bash
bash ~/Downloads/eragon.sh --forget-key
```

Keys are not displayed or placed in command arguments. Do not paste a key into a terminal command, commit it to a repository, or include it in a support request.

## Optional shortcuts

Choose a client without the client menu:

```bash
bash ~/Downloads/eragon.sh --client codex
```

The available client names are `claude`, `codex`, `pi`, and `opencode`.

Start with a model search already applied:

```bash
bash ~/Downloads/eragon.sh --search sonnet
```

If your administrator supplied an exact model ID, use it directly:

```bash
bash ~/Downloads/eragon.sh --model example/coder
```

Replace `example/coder` with your actual model ID. This skips the model list and compatibility screening. If the model has a known context limit, add `--context-window TOKENS` using the value supplied by your administrator.

Use `--endpoint URL` to skip the Gateway prompt. Supply the HTTPS base URL without `/v1`; Codex, Pi, and OpenCode also accept a trailing `/v1`.

For scripts and secret-manager integrations, the launcher accepts `ERAGON_CLIENT`, `ERAGON_ENDPOINT`, `ERAGON_MODEL`, `ERAGON_API_KEY`, and `ERAGON_CONTEXT_WINDOW`. Command-line options override matching environment settings; an environment key overrides a saved key. Noninteractive launches require an explicit endpoint, model, and an environment or matching saved key.

See all options with:

```bash
bash ~/Downloads/eragon.sh --help
```

## Troubleshooting

| Message or issue | What to do |
| --- | --- |
| `Missing jq`, `Missing curl`, or a missing client | Install the named tool, then run the launcher again. |
| A client version warning | Update that client. Check which installation your terminal finds if you have multiple versions. |
| `Could not load models` or a TLS connection error | Check the Gateway URL, network access, and key permissions. Use the real URL supplied by your administrator. |
| A model is missing | Try `/keyword` or `m`. Ask your administrator whether your key has access and whether the model supports your client. |
| Your Gateway does not offer a model list | Use `--model` with the exact ID supplied by your administrator. |
| `Your input exceeds the context window` | Start a fresh session with a shorter summary, or select a model with a larger supported context. If the displayed capacity is wrong, ask your administrator for the actual limit and use `--context-window`. |
| The client starts but requests or tool calls fail | Confirm that the Gateway supports the selected client's API and that the key can use the selected model. |

The Gateway must support Anthropic Messages for Claude Code, Responses for Codex, or Chat Completions for Pi and OpenCode, including streaming and tool calls. Eragon Router configures the client; it does not translate between these APIs. Model availability, usage charges, and access permissions are managed by your Gateway. Pi may display a zero cost estimate for custom models; Gateway usage can still be billed.

## Privacy

Your chosen client sends the conversation and any project context it uses to your configured Gateway. Eragon Router does not add telemetry or change the client's own session storage, logging, or data policies. It does not modify the client's persistent login or configuration files.

When requesting support, share the client name, version, and error message. Remove API keys and sensitive project content first.

For Gateway configuration, capacity handling, compatibility records, and contributor tests, see the [technical reference](docs/technical-reference.md).
