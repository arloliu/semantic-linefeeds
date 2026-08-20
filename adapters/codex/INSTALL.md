# Codex CLI install

Codex loads Claude-style lifecycle hooks from `hooks.json` (stable, on by default).

The quick path is the installer:

    semlf install codex

This merges the hook into an existing `hooks.json` instead of overwriting it,
publishes the checker and this README under the neutral data root
(`${XDG_DATA_HOME:-~/.local/share}/semlf`),
and installs the judgment-layer skill pointed at that same neutral root.
This is the canonical route.
It performs three exact rewrites on `skills/semantic-linefeeds/SKILL.md` before installing the copy.
A hand copy must reproduce all three,
or the installed file will not work correctly once it is moved outside this checkout
(see "The judgment-layer skill" below).
The manual steps below are for review, for unusual setups,
or for an air-gapped machine with no package index — use the checkout door there instead:

    curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh | sh -s -- --codex

1. Clone this repo somewhere stable, e.g. `~/tools/semantic-linefeeds`
   (the checkout door above does this for you).
2. Copy `adapters/codex/hooks.json` to `~/.codex/hooks.json` (user scope)
   or `<project>/.codex/hooks.json` (project scope),
   replacing the `__CHECKER__` placeholder with the neutral checker path,
   `${XDG_DATA_HOME:-~/.local/share}/semlf/check_linefeeds.py`:

       sed "s|__CHECKER__|$HOME/.local/share/semlf/check_linefeeds.py|" adapters/codex/hooks.json > ~/.codex/hooks.json

   If you already have a `hooks.json`, merge the `PostToolUse` entry instead of overwriting.
   Either installer publishes the checker itself to that same neutral path;
   a hand merge still needs you to copy `scripts/check_linefeeds.py` there yourself.
3. Codex asks you to trust the hook on first run
   (unmanaged hooks are hashed and must be approved);
   accept it.
4. To install the skill by hand instead of running the installer,
   copy `skills/semantic-linefeeds/SKILL.md` to `~/.agents/skills/semantic-linefeeds/SKILL.md`
   and make all three of the edits the installer makes:

   - rewrite the fenced checker command,
     `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" --file <files>`,
     to use the neutral checker path, `${XDG_DATA_HOME:-~/.local/share}/semlf/check_linefeeds.py`,
     in place of `${CLAUDE_PLUGIN_ROOT}`;
   - remove the sentence
     "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at `../../scripts/check_linefeeds.py` relative to this SKILL.md.)"
     entirely — it only makes sense inside this checkout;
   - rewrite the `../../README.md` suppression-section link to the neutral root's `README.md`, published beside the checker.

   The result must be byte-identical to what `semlf install codex` writes;
   `semlf status` reports whether an installed copy matches.

## The judgment-layer skill

Codex CLI resolves standalone `SKILL.md` skills from `$HOME/.agents/skills`
and from a repository's own `.agents/skills` directory.
The installer writes the user-level copy at `~/.agents/skills/semantic-linefeeds/SKILL.md`,
performing the three rewrites above so the installed file stays self-contained,
even on a machine with no checkout at all.
`$HOME` resolves the same way Python's `Path.home()` resolves it:
when the `HOME` environment variable is unset,
it falls back to your account's entry in the system's user database,
and the skill lands there instead.

A byte-identical re-run is a no-op,
and an older managed copy upgrades silently, no `--force` needed.
A hand-edited or unrecorded copy is left alone unless you pass `--force`,
which backs it up to `SKILL.md.bak` first.
Hook feedback names the skill whenever a usable copy is present at either location
Codex resolves skills from — the installer is the supported way to put one there,
not something the hook checks for directly.
`semlf status` prints the classifier's verdict verbatim —
`exact`, `managed-older`, `edited`, `unrecorded`, and so on — or `not installed`.

`adapters/agentsmd/SNIPPET.md` remains the fallback for agents with no skill mechanism at all;
`--codex` does not touch it, and `--agentsmd` stays a separate, optional install step.
