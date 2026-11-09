# Ollama Launcher

An Omarchy bar widget that does three things:

- Shows the **Ollama Cloud credit** you have left, as the Nerd Font rocket (U+F135) followed by the amount, such as `$60`, with the allowance and reset date in the tooltip. The amount dims when the reading is stale or missing.
- Lists your **local Ollama models**, each with the description from its ollama.com library page and the facts that matter for coding with it: size, quantization, the context it actually runs with, and tool support.
- Opens **opencode on a model in one click** (or ↵ / Space), in `~/Projects` by default. The **Start in** line at the top of the panel (or `f`) switches to a list of the `projectDir` folder and its subfolders that you can enter, most recently worked in first (a git repo counts from its last stage or checkout; the 40 most recent are shown). A folder picked there applies until the panel closes; every opening starts at `projectDir` again.

Models that won't work well in opencode are listed last, with a warning:

- **Small context.** A model with no `num_ctx` runs at Ollama's default (4,096 tokens on Ollama 0.40.7), which is too small for opencode's instructions and tool definitions; the start of a conversation can be cut off without warning. When another copy of the same weights has a larger context, the warning names it. A server-wide `OLLAMA_CONTEXT_LENGTH` in the `ollama` user unit (inline or in an `EnvironmentFile`) is taken into account.
- **No tool support.** opencode can't read files, edit or run commands with the model.

## Requirements

- Omarchy with the Quattro shell. It provides `uwsm-app`, `xdg-terminal-exec` and the Nerd Font the bar uses.
- Python 3.12 or newer. The helper uses the standard library only.
- [Ollama](https://ollama.com) running locally on `127.0.0.1:11434`.
- [opencode](https://opencode.ai) 2.x on your `PATH`, with an `ollama` provider pointing at the local Ollama.
- For the credit only: an ollama.com API key in `~/.config/omarchy/ollama-usage/api.key` (the same file the Ollama Usage plugin reads). Without one, set `showCredit` to `Off`.

## Install

From Plugin Depot, or:

```sh
omarchy plugin add https://github.com/john-c-houser-tech/ollama-launcher.git --enable
```

To add the credit key yourself:

```sh
mkdir -p ~/.config/omarchy/ollama-usage
install -m 600 /dev/null ~/.config/omarchy/ollama-usage/api.key
$EDITOR ~/.config/omarchy/ollama-usage/api.key
```

The plugin writes nothing outside its cache folder: no opencode or Ollama configuration is changed.

## Remove

```sh
omarchy plugin remove io.github.john-c-houser-tech.ollama-launcher
rm -rf ~/.cache/omarchy/ollama-launcher
```

Leave `~/.config/omarchy/ollama-usage/api.key` in place if the Ollama Usage plugin still uses it.

## How the launch works

opencode 2.x normally connects to a shared background service, which ignores per-launch configuration. The launcher runs `opencode --standalone` with `OPENCODE_CONFIG_CONTENT` set to the chosen model, for both the main model and the `title` agent, so nothing in the session goes to a cloud model and `opencode.json` is never written. The session still appears in `opencode session list`.

The `ollama` provider in your opencode config must point at the local Ollama.

## Network use

- **Credit:** `ollama.com/api/balance`, with the API key in `~/.config/omarchy/ollama-usage/api.key`, every 15 minutes and when the panel opens. Answers and failures are cached under a lock in `~/.cache/omarchy/ollama-launcher/`, so bars on several monitors share one request, and a rate limit (`Retry-After`) or a rejected key is waited out. The key is never sent along a redirect.
- **Descriptions:** each model family's `ollama.com/library/<name>` page, at most once a week, fetched after the model list is already showing and within a 12-second budget. A local model with no parent model is looked up under its own name, so a custom model's name is sent to ollama.com.

Everything else talks to Ollama at `127.0.0.1:11434`.

## Settings

Set them with `omarchy bar set io.github.john-c-houser-tech.ollama-launcher <key> <value>`:

| Key | Default | |
|---|---|---|
| `projectDir` | `~/Projects` | Folder opencode starts in (relative paths are under your home folder) |
| `creditRefreshMinutes` | `15` | 5–120 |
| `showCredit` | `On` | `Off` hides the amount and stops the balance requests |
| `fetchDescriptions` | `On` | `Off` stops the library-page requests |

## Development

```sh
python3 -I -B -m unittest discover -s tests
omarchy plugin validate "$PWD"
```

The plugin folder is a symlink to this repo, and the shell doesn't hot-reload edits made through it: run `omarchy restart shell` after changing QML.
