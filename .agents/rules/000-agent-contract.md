# 000 - Agent Contract

Always-on operating contract for this repo.
Supersedes habit;
only an explicit user instruction overrides it.

## Don't Guess

- State assumptions explicitly.
  If uncertain, ask rather than guess.
- **Do not guess when source, tests, docs, `git`, or `grep` can answer.**
- Do not present unverified assumptions as facts;
  if verification is impossible or too expensive, say what is unverified and why.
- Before changing the checker, read the extraction path you are touching
  and the fixtures that pin its behavior.

## Keep Changes Small

- Make the minimum change that solves the problem.
- Touch only what you must;
  clean up only the orphans your own change created.
- No speculative features, one-off abstractions, or drive-by refactors.
- Match existing style even if you'd do it differently.
- Test: every changed line should trace to the user's request.

## Surface Conflicts

- If two patterns contradict, pick one explicitly and explain why.
- Prefer the more recent, more tested, or more local convention.
- If a convention looks harmful, surface it instead of silently forking.

## Fail Loud

- Define success criteria and loop until verified.
- Do not say "done" or "tests pass" if anything was skipped or unverified.
- Default to surfacing uncertainty, not hiding it.

## No Jargon

State facts plainly — in rules, code comments, commits, everywhere.
A future reader has no memory of the conversation, plan, or review round
that produced a change.
Never cite sequencing labels, review rounds, task numbers, or `tmp/*` paths;
state the current fact, not the process that produced it.

## Semantic Linefeeds Everywhere

This repo enforces its own rule on itself.
Write every comment, docstring, and Markdown paragraph with semantic line breaks:
one sentence per line,
and a long sentence splits only at a real clause boundary.
Check every touched Markdown file with `python3 scripts/check_linefeeds.py --file <file>` before committing;
zero `fused`/`wrap` findings is the bar.
