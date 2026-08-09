# Codex CLI install

Codex loads Claude-style lifecycle hooks from `hooks.json` (stable, on by default).

The quick path is the installer,
which merges the hook into an existing `hooks.json` instead of overwriting it:

    python3 scripts/install.py --codex

The manual steps below remain for review or for unusual setups.

1. Clone this repo somewhere stable, e.g. `~/tools/semantic-linefeeds`.
2. Copy `adapters/codex/hooks.json` to `~/.codex/hooks.json` (user scope)
   or `<project>/.codex/hooks.json` (project scope),
   replacing `__REPO__` with the absolute repo path:

       sed "s|__REPO__|$HOME/tools/semantic-linefeeds|" adapters/codex/hooks.json > ~/.codex/hooks.json

   If you already have a `hooks.json`, merge the `PostToolUse` entry instead of overwriting.
3. Codex asks you to trust the hook on first run
   (unmanaged hooks are hashed and must be approved);
   accept it.
4. Optional: copy `adapters/agentsmd/SNIPPET.md` into your `~/.codex/AGENTS.md`
   so the model knows the convention before the hook fires.
