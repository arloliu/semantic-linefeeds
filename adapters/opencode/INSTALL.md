# opencode install

opencode plugins are in-process TypeScript; this one shells out to the same core CLI.

1. Copy `adapters/opencode/semantic-linefeeds.ts` and `scripts/check_linefeeds.py`
   into `~/.config/opencode/plugins/` (global) or `<project>/.opencode/plugins/` —
   the two files must sit side by side
   (or export `SEMANTIC_LINEFEEDS_CHECK=/abs/path/to/check_linefeeds.py` instead of copying the script).
2. The skill needs no port:
   opencode reads `.claude/skills/` and `~/.claude/skills/` natively,
   so if the Claude plugin is installed the skill is already visible.
   Otherwise copy `skills/semantic-linefeeds/` into `~/.config/opencode/skills/`.
3. Findings appear appended to the edit/write/apply_patch tool output
   (advisory, same wording as the Claude hook).
