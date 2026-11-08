# Ollama Launcher

An Omarchy bar widget that does three things:

- Shows the **Ollama Cloud credit** you have left (`🚀 $60`), with the monthly allowance and reset date in the tooltip.
- Lists your **local Ollama models**, each with the description from its ollama.com library page and the facts that matter for coding with it: size, quantization, the context it actually runs with, and tool support.
- Opens **opencode on a model in one click** (or ↵), in `~/Projects` by default.

Models that won't work well in opencode are listed last, with a warning:

- **Small context.** A model with no `num_ctx` runs at Ollama's default (4,096 tokens here), which is too small for opencode's instructions and tool definitions; the start of a conversation can be cut off without warning. When another copy of the same weights has a larger context, the warning names it.
- **No tool support.** opencode can't read files, edit or run commands with the model.

## How the launch works

opencode 2.x normally connects to a shared background service, which ignores per-launch configuration. The launcher runs `opencode --standalone` with `OPENCODE_CONFIG_CONTENT={"model":{"providerID":"ollama","model":"<name>"}}`, so the choice applies to that launch only and `opencode.json` is never written. The session still appears in `opencode session list`.

The `ollama` provider in your opencode config must point at the local Ollama.

## Network use

- `ollama.com/api/balance`, with the API key in `~/.config/omarchy/ollama-usage/api.key`, every 15 minutes (setting) and when the panel opens. Turn off with **Show Ollama Cloud credit: Off**.
- Each model family's `ollama.com/library/<name>` page, at most once a week, cached in `~/.cache/omarchy/ollama-launcher/`. Turn off with **Model descriptions from ollama.com: Off**.

Everything else talks to Ollama at `127.0.0.1:11434`.

## Settings

| Key | Default | |
|---|---|---|
| `projectDir` | `~/Projects` | Folder opencode starts in |
| `creditRefreshMinutes` | `15` | 5–120 |
| `showCredit` | `On` | |
| `fetchDescriptions` | `On` | |

## Development

```sh
python3 -I -m unittest discover -s tests
omarchy plugin validate "$PWD"
```
