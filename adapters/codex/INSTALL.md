# Codex CLI install

Codex loads Claude-style lifecycle hooks from `hooks.json` (stable, on by default).

The quick path is the installer,
which merges the hook into an existing `hooks.json` instead of overwriting it,
and installs the judgment-layer skill alongside it:

    python3 scripts/install.py --codex

This is the canonical route.
It performs three exact rewrites on `skills/semantic-linefeeds/SKILL.md` before installing the copy.
A hand copy must reproduce all three,
or the installed file will not work correctly once it is moved outside this checkout
(see "The judgment-layer skill" below).
The manual steps are for review or for unusual setups only.

1. Clone this repo somewhere stable, e.g. `~/tools/semantic-linefeeds`.
2. Copy `adapters/codex/hooks.json` to `~/.codex/hooks.json` (user scope)
   or `<project>/.codex/hooks.json` (project scope),
   replacing `__REPO__` with the absolute repo path:

       sed "s|__REPO__|$HOME/tools/semantic-linefeeds|" adapters/codex/hooks.json > ~/.codex/hooks.json

   If you already have a `hooks.json`, merge the `PostToolUse` entry instead of overwriting.
3. Codex asks you to trust the hook on first run
   (unmanaged hooks are hashed and must be approved);
   accept it.
4. To install the skill by hand instead of running `--codex`,
   copy `skills/semantic-linefeeds/SKILL.md` to `~/.agents/skills/semantic-linefeeds/SKILL.md`
   and make all three of the edits `--codex` makes:

   - rewrite the fenced checker command,
     `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" --file <files>`,
     to use the absolute path of this checkout's `scripts/check_linefeeds.py`
     in place of `${CLAUDE_PLUGIN_ROOT}`;
   - remove the sentence
     "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at `../../scripts/check_linefeeds.py` relative to this SKILL.md.)"
     entirely — it only makes sense inside this checkout;
   - rewrite the `../../README.md` suppression-section link to this checkout's absolute `README.md` path.

   The result must be byte-identical to what `python3 scripts/install.py --codex` writes;
   `scripts/install.py` (no flags) reports whether an installed copy matches.

## The judgment-layer skill

Codex CLI resolves standalone `SKILL.md` skills from `$HOME/.agents/skills`
and from a repository's own `.agents/skills` directory.
`--codex` writes the user-level copy at
`~/.agents/skills/semantic-linefeeds/SKILL.md`,
performing the three rewrites above so the installed file stays self-contained outside this checkout.
`$HOME` resolves the same way Python's `Path.home()` resolves it:
when the `HOME` environment variable is unset,
it falls back to your account's entry in the system's user database,
and the skill lands there instead.

A byte-identical re-run is a no-op.
A hand-edited or older copy is left alone unless you pass `--force`,
which backs it up to `SKILL.md.bak` first.
Hook feedback names the skill whenever a usable copy is present at either location
Codex resolves skills from — the installer is the supported way to put one there,
not something the hook checks for directly.
`scripts/install.py` (no flags) reports its state as installed, diverged, or not installed.

`adapters/agentsmd/SNIPPET.md` remains the fallback for agents with no skill mechanism at all;
`--codex` does not touch it, and `--agentsmd` stays a separate, optional install step.
