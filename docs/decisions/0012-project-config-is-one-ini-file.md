# ADR-0012: Project configuration is one `.semlf.ini` file

**Status:** accepted
**Date:** 2026-08-13
**Amended:** 2026-08-13 —
[ADR-0013](0013-git-modes-read-snapshots-through-providers.md) adds the `exclude` key
and rules that an invalid **value** for one key now drops only that key, not the whole file;
the whole-file-drop rule below stays accurate for file-level trouble only —
a missing, unreadable, undecodable, or unparsable-as-INI file.
**Amended:** 2026-08-14 —
[ADR-0017](0017-experimental-wrap-also-lives-in-ini.md) adds a third key,
`experimental-wrap`, and gives it its own precedence order — env beats ini beats off,
the reverse of the flag-beats-env-beats-ini order below —
because `wrap`'s opt-in has no flag leg to defer to.

## Decision

A repository may tune the checker once, for every hook and every `--file` audit, with one file:
`.semlf.ini` at the repository root, INI format, one section, `[semlf]`.
v0.6a ships exactly one key, `long-limit`:

```ini
[semlf]
long-limit = 100
```

Discovery lives in the core, as `load_config(start_dir)`,
because [ADR-0004](0004-portable-core-and-repository-cli.md) already places policy discovery in the core rather than the CLI —
every adapter invokes the core directly,
so a CLI-only discovery function would let hooks and CI read different policy for the same repository.
The walk is physical: `start_dir` is resolved through symlinks once,
then parents are taken lexically from the resolved path,
so candidates, parents, and the boundary check all share one representation.
It climbs from `start_dir` and stops at the first directory holding either `.semlf.ini`
or a `.git` entry, file or directory —
a worktree's `.git` is a file, and the walk must stop there the same as at a directory —
so a config can never leak across a repository boundary.
When both live in the same directory, the config wins,
which is what makes a repository-root config readable at all.

Precedence is `--long-limit` flag, then `$SEMLF_LONG_LINE`, then the discovered config, then the built-in default of 120 —
each leg answers before the next is even attempted,
so a flag or an environment variable always overrides a committed file without editing it.

A malformed file is inert.
A missing file, an unreadable file, a file without a `[semlf]` section, a `long-limit` value
that doesn't parse as an integer,
and a negative `long-limit` all return no configuration and fall through to the next precedence leg, the same as if no file existed.
The checker's own precision contract — a false positive is a bug, a miss is acceptable — extends to its own configuration:
a typo in a config file must never crash a hook or silently disable the checker outright,
it must simply fail to apply the tuning the file intended.

The extension names the format.
An editor, a linter, and an agent reading the repository tree all learn what `.semlf.ini` is from its suffix alone, with no need to open the file first,
the same convention `pytest.ini`, `mypy.ini`, and `tox.ini` already rely on.
The competing `setup.cfg`-style convention — one shared file, many `[tool:x]` sections —
is fading across the ecosystem precisely because it couples unrelated tools' configuration and versioning to one file,
and it offers no format signal from the filename.

## Evidence

- [ADR-0004](0004-portable-core-and-repository-cli.md) already decided that hook configuration discovery belongs in the core, not the CLI, to keep hooks and CI from disagreeing;
  this record extends that placement to project configuration rather than reopening it.
- `configparser` is in the stdlib at Python 3.9,
  the core's floor per [`.agents/rules/100-project-map.md`](../../.agents/rules/100-project-map.md),
  so adding config support costs the core no new dependency and no version-conditional import.
- `pytest.ini`, `mypy.ini`, and `tox.ini` are established precedent for a tool naming its config format through the file extension rather than through a shared, multi-tool file.

## Alternatives rejected

- **TOML.**
  `tomllib` is stdlib only from Python 3.11 (PEP 680),
  three minor versions above the core's 3.9 floor.
  Reading TOML at 3.9 would need a version-conditional parser —
  `tomllib` where available, a vendored fallback or an optional dependency otherwise —
  and that branch is exactly the kind of environment-dependent behavior that lets a hook and a CI run disagree about the same file,
  which is the failure [ADR-0004](0004-portable-core-and-repository-cli.md) already rejects.
  The future note below keeps this option live for later, once the floor itself moves.
- **Strict JSON.**
  JSON has no comment syntax,
  and a human-edited policy file without comments loses the ability to explain why a value is set the way it is.
  Worse, a trailing-comma typo is a common JSON mistake,
  and under the malformed-is-inert rule it would silently disable the whole config with no visible signal —
  the failure mode is invisible exactly where a human is most likely to trigger it by hand.
- **Hand-rolled JSONC stripping.**
  Stripping `//` comments before parsing as JSON was considered as a way to keep JSON's structure
  while adding comments.
  A naive regex strips `//` wherever it appears,
  and a naive regex therefore corrupts any legal value that legitimately contains `//` — a URL in a comment, a regex pattern, a file path.
  A correct string-aware scanner avoids that, but writing one is parser code,
  and the precision contract this project holds itself to is about the checker's own detectors,
  not about growing a second hand-rolled parser to maintain.
- **YAML.**
  Never in the Python stdlib at any version;
  ruled out on the same "the core imports stdlib only" ground everything else in the core answers to.
- **CLI-side discovery.**
  Every adapter invokes the core directly, without the repository CLI,
  so discovery living only in the CLI would leave every hook path unconfigured while `semlf check` alone honored the file —
  the same hook-versus-CI disagreement [ADR-0004](0004-portable-core-and-repository-cli.md) already forecloses, restated for project config instead of hook config.

## Future note

If the core's floor ever rises to Python 3.11 — a v1.0-era question at the earliest, and not one this record settles —
`tomllib` stops being a version-conditional dependency and becomes a plain stdlib import.
At that point TOML becomes the natural migration target,
and this record is the one a future ADR would supersede.
