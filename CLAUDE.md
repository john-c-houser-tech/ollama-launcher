# Ollama Launcher

An Omarchy bar widget: Ollama Cloud credit in the bar, and a panel listing the
local Ollama models with descriptions that launches opencode on one. See
`README.md` for what it does, its network use and its settings.

## Files

- `ollama-launcher` is the Python helper. It does all the data work:
  `models`, `descriptions`, `credit`, `folders`, `launch`. Each command prints
  one JSON object, even on an unexpected error.
- `BarWidget.qml` is the bar face and owns the credit; `Panel.qml` is the model
  list and folder picker. The QML displays what the helper returns, adding
  only formatting (amounts, dates).
- `manifest.json` is the Omarchy plugin manifest.
- `tests/test_helper.py` has the tests, including the manifest checks.
- `githooks/pre-commit` runs the checks before each commit;
  `.github/workflows/ci.yml` runs them on every PR.

## Commands

- `python3 -I -B -m unittest discover -s tests` runs the tests. They stub
  Ollama, ollama.com, `systemctl` and the terminal, and use temporary folders
  for the cache and key, so they touch nothing real.
- `omarchy plugin validate "$PWD"` checks the manifest the way Omarchy does.
- `git config core.hooksPath githooks` enables the pre-commit hook, once per
  clone. Until then nothing runs at commit time, so run the tests yourself.
  The hook tests the working tree (unstaged edits count) and scans only the
  staged files for bidi characters.

## Code rules

- Python 3.12 is the floor (the oldest version in CI): no newer syntax.
- The helper uses the standard library only; add no dependencies.
- Render every string from Ollama, ollama.com or the file system as plain
  text: each `Text` in the plugin sets `textFormat: Text.PlainText`. The bar
  label and tooltip go through the shell's `WidgetButton`, which does this
  itself.
- Send structured data to QML as flat strings: nested JSON lists reach QML as
  a type `Array.isArray` rejects.
- Never write a bidi control character (U+202A–U+202E, U+2066–U+2069) into a
  file: build test strings with `chr()`. The hook and CI reject them.

## Rules for agents

- Never open the panel, launch opencode, or open any terminal or window on the
  user's desktop: it takes their focus while they type. Never run the
  helper's `launch` command at all; the tests mock `subprocess.Popen`.
- `models` and `folders` are local only and safe to run. Run `credit` or
  `descriptions` by hand only with a scratch cache,
  `OLLAMA_LAUNCHER_CACHE=$(mktemp -d)`, so you don't change what the live bar
  shows. Never pass `credit --force` (it skips the rate-limit backoff), never
  call ollama.com directly, and never print the API key in
  `~/.config/omarchy/ollama-usage/api.key`.
- The plugin folder (`~/.config/omarchy/plugins/io.github.john-c-houser-tech.ollama-launcher`)
  is a symlink to this repo, and the shell doesn't hot-reload edits made
  through it. After a QML change, say so and run `omarchy restart shell` (the
  bar blinks), then check `journalctl --user -t omarchy-shell --since -2min | grep ollama-launcher`.
  The `qmlscanner` warning that the module path "is outside of the config
  folder" comes from the symlink and is harmless.
- Commit only when asked.

## Git

The repository is https://github.com/john-c-houser-tech/ollama-launcher. `main`
is John's: never commit or push to it, and never force-push. `dev` is the
integration branch.

1. Before any new work: `git checkout dev && git pull --ff-only`.
2. Branch from dev: `git checkout -b <feature>`. Check `git branch --show-current`
   before every commit.
3. Commit there, push the branch, and open a PR into dev: `gh pr create --base dev`.
4. Wait for `gh pr checks <n>` to pass. dev's ruleset doesn't require CI, but
   main's requires the `CI result` check, so a red PR merged into dev blocks
   the next merge to main.
5. Before review requests, run independent agent reviews of the PR and fix
   what they find. Then request a Copilot review (`gh pr edit <n> --add-reviewer @copilot`)
   when Copilot credits are available, and address its comments with
   follow-up commits.
6. John merges to main. Wait for him.
