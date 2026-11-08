# Ollama Launcher

An Omarchy bar widget: Ollama Cloud credit in the bar, and a panel listing the
local Ollama models with descriptions that launches opencode on one. See
`README.md` for what it does, its network use and its settings.

## Files

- `ollama-launcher` is the Python helper (standard library only). It does all
  the data work: `models`, `descriptions`, `credit`, `folders`, `launch`. Each
  command prints one JSON object.
- `BarWidget.qml` is the bar face and owns the credit; `Panel.qml` is the model
  list and folder picker. QML only displays what the helper returns.
- `manifest.json` is the Omarchy plugin manifest.
- `tests/test_helper.py` has the helper's tests.
- `githooks/pre-commit` runs the checks before each commit.

## Commands

- `python3 -I -B -m unittest discover -s tests` runs the tests.
- `omarchy plugin validate "$PWD"` checks the manifest.
- `git config core.hooksPath githooks` enables the pre-commit hook (once per clone).

## Rules for agents

- Never open the panel, launch opencode, or open any terminal or window on the
  user's desktop: it takes their focus while they type. Don't run the
  helper's `launch` command with a real model; the tests stub the terminal.
- The plugin folder (`~/.config/omarchy/plugins/io.github.john-c-houser-tech.ollama-launcher`)
  is a symlink to this repo, and the shell doesn't hot-reload edits made
  through it. After a QML change, say so and run `omarchy restart shell`
  (the bar blinks), then check `journalctl --user` for the plugin's errors.
- Render every string from Ollama, ollama.com or the file system as plain text
  (`textFormat: Text.PlainText`), and send structured data to QML as flat
  strings: nested JSON lists reach QML as a type `Array.isArray` rejects.
- ollama.com rate-limits (HTTP 429): call it by hand at most once per task,
  and never print the API key in `~/.config/omarchy/ollama-usage/api.key`.
- Never write a bidi control character (U+202A–U+202E, U+2066–U+2069) into a
  file: build test strings with `chr()`. The pre-commit hook and CI reject them.
- Commit only when asked.

## Git

The repository is https://github.com/john-c-houser-tech/ollama-launcher. `main`
is John's: never commit or push to it, and never force-push. `dev` is the
integration branch.

1. Before any new work: `git checkout dev && git pull --ff-only`.
2. Branch from dev: `git checkout -b <feature>`. Check `git branch --show-current`
   before every commit.
3. Commit there, push the branch, and open a PR into dev: `gh pr create --base dev`.
4. Before review requests, run independent agent reviews of the PR and fix
   what they find. Then request a Copilot review (`gh pr edit <n> --add-reviewer @copilot`)
   when Copilot credits are available, and address its comments with
   follow-up commits.
5. John merges to main. Wait for him.
