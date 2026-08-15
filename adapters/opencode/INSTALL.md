# opencode install

opencode plugins are in-process TypeScript; this one shells out to the same core CLI.

The quick path is the installer:

    semlf install opencode

On an air-gapped machine with no package index,
the checkout door covers the same install:

    curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh | sh -s -- --opencode

The manual steps below remain for review or for unusual setups.

1. Copy two files into `~/.config/opencode/plugins/` (global) or `<project>/.opencode/plugins/`:
   `adapters/opencode/semantic-linefeeds.ts` and `scripts/check_linefeeds.py`.
   The two files must sit side by side
   (or export `SEMLF_CHECKER=/abs/path/to/check_linefeeds.py` instead of copying the script;
   the old name `SEMANTIC_LINEFEEDS_CHECK` still works as a deprecated alias).
2. Copy `skills/semantic-linefeeds/` into `~/.agents/skills/`.
   opencode reads that directory natively, as does Codex CLI,
   so one copy serves both and nothing needs to go under `~/.config/opencode/skills/`.
   A copy there would compete with this one for the skill's name.

   Requires opencode 1.18.18 or newer.
   `OPENCODE_DISABLE_EXTERNAL_SKILLS` turns that scan off;
   with it set, no copy in `~/.agents/skills` is visible to opencode at all.
3. Findings appear appended to the edit/write/apply_patch tool output
   (advisory, same wording as the Claude hook).
