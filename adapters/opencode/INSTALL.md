# opencode install

opencode plugins are in-process TypeScript; this one shells out to the same core CLI.

The quick path is the installer:

    python3 scripts/install.py --opencode

The manual steps below remain for review or for unusual setups.

1. Copy two files into `~/.config/opencode/plugins/` (global) or `<project>/.opencode/plugins/`:
   `adapters/opencode/semantic-linefeeds.ts` and `scripts/check_linefeeds.py`.
   The two files must sit side by side
   (or export `SEMLF_CHECKER=/abs/path/to/check_linefeeds.py` instead of copying the script;
   the old name `SEMANTIC_LINEFEEDS_CHECK` still works as a deprecated alias).
2. The skill needs no port:
   opencode reads `.claude/skills/` and `~/.claude/skills/` natively,
   so if the Claude plugin is installed the skill is already visible.
   Otherwise copy `skills/semantic-linefeeds/` into `~/.config/opencode/skills/`.
3. Findings appear appended to the edit/write/apply_patch tool output
   (advisory, same wording as the Claude hook).
