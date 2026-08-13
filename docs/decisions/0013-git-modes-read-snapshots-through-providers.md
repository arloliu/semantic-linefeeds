# ADR-0013: Git modes read snapshots through providers

**Status:** accepted
**Date:** 2026-08-13

## Decision

`semlf` gains three modes that check a git snapshot instead of files named on the command line:
`--staged`, `--diff`, and `--changed`.
Each is one seam — a provider function returning `[(path, text), ...]` — never a separate contract,
and every provider hands its pairs to the same shared runner `--file` already uses,
so rendering and exit codes stay one code path.
The core never learns git exists;
every `git` invocation lives in `cli/semlf/providers.py`,
keeping the "copy one file, runs on bare python3" property
([`.agents/rules/100-project-map.md`](../../.agents/rules/100-project-map.md)) intact.

### The three modes and their content source

- **`--staged`** — the index versus `HEAD`.
  Content is the staged blob itself, read by the object id the enumeration recorded,
  never a second index query that could see a different index.
- **`--diff`** — the worktree versus the index: unstaged changes, read from the worktree.
- **`--changed`** — the worktree versus `HEAD`: staged and unstaged changes together, read from the worktree.

Only `--staged` reads index content;
`--diff` and `--changed` both read worktree bytes for the paths their enumeration names.

### Policy is the working tree's, in every mode

Every mode discovers `.semlf.ini` — `long-limit`, `exclude` — the same way `--file` does:
walking the filesystem from the checked path upward.
This holds for `--staged` too, even though its **content** is the index:
its **policy** is still the checkout the command runs in.
A config staged but not yet present on disk does not govern `--staged`,
and a config edited on disk but not yet staged does govern it —
both directions are a named, accepted divergence window, not a defect,
because the alternative is index-sourced policy discovery,
rejected below against rule 100's one-policy-source principle.

### The policy anchor: the nearest existing ancestor

Discovery starts at the nearest **existing** ancestor directory of the checked path,
not at the path's own (possibly nonexistent) directory.
A path can be staged under a directory the worktree no longer holds.
It still resolves `.semlf.ini` from whatever existing directory sits above it,
so a vanished worktree parent costs a staged file nothing:
the policy above it still applies.

### One enumeration per snapshot

Each provider reads its snapshot with exactly one
`git diff --raw -z --no-abbrev --no-renames --diff-filter=AMTUX` listing,
which carries status, post-image mode, and post-image object id for every path in one pass.
`--no-abbrev` is the flag that forces full object ids in raw output —
`--full-index` governs patch output, not raw, and would not have done this —
so no host `core.abbrev` can shorten an id into an ambiguity-prone prefix before `--staged` hands it to `cat-file`.
`--no-renames` pins the record shape against a host's `diff.renames`/`diff.copies` configuration:
a rename is checked as the addition of its new path, the checkable post-image either way,
never a two-path rename record the parser would have to special-case.
`--staged` reads blobs by exactly the object ids this one listing recorded,
never a second, later index query.

### Tracked changes only

`git diff` never lists an untracked file, so no mode discovers one.
Staging is the declaration of intent an untracked file needs before any mode can see it;
`--changed` in particular does not reach past `git diff`'s own tracked-changes scope to add untracked files back in.

### Symlinks and gitlinks are never checkable

A record's post-image mode is the gate: only `100644` and `100755` are checkable.
`120000` (symlink) and `160000` (gitlink) are excluded in every mode,
because git's **recorded type** is the only thing that can be trusted here —
under `core.symlinks=false`, a checkout materializes a symlink as an ordinary file holding its link text,
and reading that text as prose would be a false positive no filesystem check could catch.
A physical no-follow check (`islink`/`isdir`) stands in front of every worktree `open` as a second belt,
so a worktree read can never follow a link into content the mode gate already excluded.

### Loud failure, never a shorter list

Source trouble is `SourceError`, which the CLI turns into exit 1 — never a silently smaller file list:

- `--diff-filter=AMTUX` requests unmerged (`U`) and unknown (`X`) statuses on purpose,
  so the parser can stop loudly on them instead of git silently omitting them.
- An unparsable or truncated raw record — a bad mode, a bad object id, a missing NUL, trailing garbage — stops loudly.
- `HEAD` failing to resolve on a born branch stops loudly.
  Only a **proven-unborn** branch falls back to the empty tree:
  `HEAD` must be symbolic,
  and its target ref must be **probed absent** with `rev-parse --verify --quiet`,
  whose contract is exit 1 with empty stderr for a missing ref.
  A broken ref emits a diagnostic instead and stays loud,
  because silently diffing against the empty tree there would report every file as changed.
  The empty tree itself is never a literal hardcoded id;
  it is computed with `git hash-object -t tree --stdin`,
  which is what keeps `--changed` correct in a sha256 repository as well as a sha1 one.

### The exclude grammar (from Task 2, restated verbatim)

The same `exclude` key hook mode already honors governs discovery in every git mode.
Four rules, matched per `/`-normalized path against `fnmatchcase`, never against the whole string at once:

- Separators are boundaries: `*` and `?` never cross a `/`,
  so every comparison is per path segment, never whole-string —
  a raw `fnmatch` would let `*` roam across separators, and this grammar never does.
- A trailing `/` names a folder.
  With an inner `/` it is a folder chain, anchored at the config root,
  matching only what lives under exactly that chain — never a plain file whose own path spells the chain.
  Without an inner `/` it is a bare folder name, excluded at **any depth**.
- A pattern without a trailing `/` is a glob.
  With a `/` it must match the whole relative path, segment by segment, at the path's own depth.
  Without one it may match any single path component, at any depth.
- `fnmatchcase` everywhere: matching is case-sensitive on every platform,
  because a rule that changed meaning between hosts would make the same commit clean on one machine and flagged on another.

### The discovery-only scope

Excludes filter discovery — hook mode and the git modes — and nothing else.
An explicitly named `--file` path is always checked, exclude or no exclude:
naming a path is the judgment call excludes exist to encode in the first place,
and silently overriding it would hide a finding the caller asked for.

### An agent never adds an exclude on its own authority

Restated from [ADR-0010](0010-suppression-is-a-stateless-single-line-directive.md#who-writes-one):
an exclude is user-directed, exactly like a suppression directive.
An agent that judges a repeated finding to be noise does not add an `exclude` line to make the noise stop;
it raises the disagreement with the user, who decides whether an exclude is the right answer.

### Amending ADR-0012: an invalid value drops only its own key

[ADR-0012](0012-project-config-is-one-ini-file.md) shipped with `long-limit` as the only key,
and ruled that any trouble — file-level or value-level — dropped the whole file.
With `exclude` added beside `long-limit`, that rule changes for value-level trouble:
an invalid value for one key (a `long-limit` that will not parse as a non-negative integer)
now drops only that key, and a good `exclude` in the same file still applies.
File-level trouble — the file is missing, unreadable, undecodable, or fails to parse as INI —
still drops the whole file, unchanged from ADR-0012.
ADR-0012 carries an `Amended:` header pointing here, in the house style ADR-0010 already uses,
so the two records cannot be read as disagreeing with each other.

## Evidence

- `cli/semlf/providers.py` is the implementation this record describes:
  `_raw_records`, `_parse_raw`, `_head_or_empty_tree`, `_selected`, `_worktree_sources`,
  and the three public `*_sources` functions.
- `scripts/check_linefeeds.py`'s `_exclude_match`, `excluded`, and `_existing_start` carry the grammar and the policy-anchor rule this record restates.
- `tests/test_git_modes.py` pins the content-source matrix, the loud-failure paths,
  and both directions of the policy divergence window
  (`test_matrix_policy_is_the_worktrees_even_for_staged_content`,
  `test_matrix_a_staged_only_exclude_does_not_govern`).
- [ADR-0004](0004-portable-core-and-repository-cli.md) already assigns git snapshot selection to the CLI
  and keeps the core git-free; this record specifies what that CLI module does.
- [ADR-0005](0005-changed-span-analysis-and-ownership.md) already draws the line between
  "analysis sees everything" and "reporting is filtered" for changed-span ownership;
  the discovery-only scope of excludes is the same shape of filter, one layer earlier.

## Alternatives rejected

- **Per-mode content flags** (one flag selecting content, another selecting comparison base) —
  rejected for three near-identical contracts instead of one seam with three selectors.
  A provider function per mode keeps the shared runner, the shared exit codes,
  and the shared rendering exactly as `--file` already has them.
- **Checking worktree bytes in `--staged`** —
  rejected because it defeats the mode's purpose:
  `--staged` exists so a pre-commit hook can check exactly what `git commit` would record,
  and `pass_filenames: false` in [`.pre-commit-hooks.yaml`](../../.pre-commit-hooks.yaml)
  exists precisely so pre-commit never hands the mode worktree paths to read instead.
- **Index-sourced policy for `--staged`** —
  rejected because it replicates the filesystem discovery walk inside the index namespace instead:
  a second `git show :.semlf.ini`-style lookup, its own precedence handling,
  its own malformed-file behavior, kept in step with the worktree walk forever.
  Rule 100's principle is one policy source, so hooks and CI cannot read different rules for the same repository;
  a second, index-shaped source is exactly the kind of second source that principle forecloses.
  The named divergence window above is accepted in its place.
- **Untracked-file discovery in `--changed`** —
  rejected because `git diff` does not enumerate untracked files by design,
  and staging is already the declaration of intent this project asks for elsewhere.
  A second `git status`-style call, reaching past `git diff` to add them back in, would give `--changed` a second enumeration path the loud-failure and single-snapshot rules above do not cover.
- **A regex exclude grammar** —
  rejected in favor of `fnmatch`, the stdlib's floor for glob matching.
  A regex exclude in a committed config file invites a catastrophic pattern
  (worst-case backtracking on a hostile or merely careless path),
  and the fail-open contract this project holds `.semlf.ini` to would then have to defuse regex denial-of-service on top of parse errors and bad values —
  a cost `fnmatch`'s segment-bounded grammar never introduces.
