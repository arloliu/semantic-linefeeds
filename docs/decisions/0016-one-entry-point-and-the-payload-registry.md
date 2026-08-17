# ADR-0016: One entry point and the payload registry

**Status:** accepted
**Date:** 2026-08-14
**Supersedes in part:** [ADR-0004](0004-portable-core-and-repository-cli.md),
[ADR-0014](0014-lifecycle-verbs-and-the-provenance-manifest.md),
and [ADR-0015](0015-distribution-channels.md) —
the *Supersedes* section below names every claim this record replaces.

## Decision

### `semlf` is the single entry point

`uv tool install semlf`, or `pipx install semlf`, installs the tool;
`semlf install` then installs the integrations.
`semlf install`, `semlf status`, and `semlf uninstall` are package-door verbs:
they run from a wheel, a zipapp, or a checkout alike,
and none of them needs a repository checkout to find something to copy.
Claude Code keeps its plugin marketplace pair and is never touched by `semlf`.

### Payloads embed through one declarative registry

One declarative registry drives the wheel build, the zipapp build, the installer,
and the identity checks,
so no consumer invents a second mapping.
Each row carries a logical id
(which is also its provenance record name where one exists),
the canonical repository path,
the embedded member path `semlf/payloads/<id>` in both wheel and zipapp,
the installed destination or destinations,
the transform with its required match count,
the owning install target,
and its apply-order position.
A shared staging step reads the registry
and places each canonical source at its member path in the build tree only,
so neither builder copies canonical files by hand
and no packaging copy is ever committed.

Embedding is what dissolves the premise ADR-0014 rejected the package door on.
A `semlf` installed by pipx or uv now carries its payloads inside the artifact,
so "no checkout to copy from" is no longer a fact about the package channel,
and the write-verbs no longer have to live beside the repository tree.

Every transform fails loud when its match count is wrong,
so a canonical-source edit can never silently disable a rewrite.
The installed hook command keeps the shape `python3 <path ending in check_linefeeds.py> --hook codex`,
so ADR-0014's structural ownership rule holds unchanged.

### Hooks and skills target one neutral root

Installed codex hooks and skills reference the checker at one channel-neutral path,
`${XDG_DATA_HOME:-~/.local/share}/semlf/check_linefeeds.py`,
published there as a provenance-managed artifact,
whatever channel `semlf` itself arrived by.
`README.md` publishes beside it,
so the installed skill's suppression-rules link resolves to a local file
and keeps working on an air-gapped machine.
The opencode integration is the one stated exception to the single target:
its plugin resolves the checker beside itself,
so its install publishes a second, colocated copy under the same provenance rules.

The zipapp channel forces this shape anyway —
a hook cannot point into a `.pyz` archive —
and once that real path is the single hook target for every channel,
a hook survives a channel switch, a venv rebuild, or a CLI uninstall untouched.
Published payloads are deliberately left in place
when the last consuming integration is uninstalled,
because their independence from any one integration is the point of the neutral root;
`semlf status` names the leftover directory in one line for manual removal.

### Admission is the three-axis classifier

Admission is decided on three independent axes for every single-file artifact:
object state (absent, readable regular file, unreadable, symlink, directory, other special file),
provenance state (exact current rendering, manifest-managed different rendering, edited, unrecorded),
and execution mode (normal, `--force`, `--dry-run`).

An exact current rendering with a missing or stale record **adopts** it,
because publication and record are separate files
and a correct copy must converge to `managed` on the next run rather than stay `unrecorded` forever.
Versions order as dot-separated integer tuples compared numerically,
and a recorded version that does not parse that way is unorderable,
where the classifier fails closed rather than guessing.
A managed older release replaces without `--force`;
equal version with different bytes replaces,
because two builds can share a version string
and the running artifact's rendering is the one its record must describe.
A managed **newer** release is a downgrade and refuses by default,
so an old zipapp or checkout run cannot silently drag every hook's checker backwards;
`--force` states the intent and the refusal message names it.
`edited` and `unrecorded` refuse, and name the finding;
`--force` takes an exclusive `O_EXCL` backup first,
and an occupied or non-regular backup slot refuses either way.
Force never overrides an object-state refusal.
`--dry-run` never prompts, never writes, never mutates a record,
prints each artifact's classification and the action normal mode would take —
including any refusal it would hit —
and exits 0.

### Installs are request-wide preflight, then ordered apply

`semlf install` classifies every artifact of the whole request read-only first,
and any refusal aborts the run before the first write,
reporting every artifact's verdict.
Preflight admits the provenance side too:
the state root must resolve,
and each record's parent and leaf must be writable paths,
before the first destination is touched.
Apply order follows the registry's order field,
neutral `checker` and `readme` first, then each integration's own files.
A mid-apply filesystem failure reports, per artifact,
applied, not applied, or published-but-not-recorded,
and a rerun converges from any of them.
Rollback is deliberately not offered,
and lifecycle-command locking is not either:
concurrent lifecycle commands stay out of scope,
carrying ADR-0014's concurrency boundary forward unchanged.

### Staleness is a digest question, and doctor fails on it

`semlf status` and `semlf doctor` compare payloads by guarded bytes, never by version string alone,
because two builds can differ under one version,
and on a downgrade the published copy is ahead rather than behind.
Every published payload is measured against the payload set embedded in the running artifact.
The version string is the human-facing label,
with distinct wordings for missing, edited, managed-but-lagging, managed-but-ahead,
and same-version-different-bytes.
Expectedness is conditioned on consumers:
an installed integration makes its payloads expected,
a payload with no remaining consumer is a warning with the removal pointer,
and a machine with no integrations passes.
`semlf status` reports;
`semlf doctor` counts any expected-payload mismatch as a failed check and exits 1.

### The zipapp stays behind the checkout door

The package door has no `cli` target.
pipx, uv, and the zipapp all want `~/.local/bin/semlf`,
and a package-installed `semlf uninstall cli --force` could unlink its own shim.
Building and removing the zipapp remains exclusive to the checkout door
(`install.py --cli`).
A zipapp left over from before this redesign is a migration case:
`semlf install` performs a `PATH` check at the end of its run
and warns when `semlf` on `PATH` is not the running artifact's shim,
and status and doctor repeat the report with the checkout-door removal pointer.

`scripts/install.py` stays as the checkout-side door for air-gapped and development use,
keeping its entire current flag vocabulary
as a thin parser over the same shared operations,
so `install.sh` keeps working with zero changes
and both doors render byte-identical artifacts.

### PyPI is the package channel's primary source

The package channel's primary source becomes PyPI:
`uv tool install semlf` and `pipx install semlf` are the documented quickstart,
and the README flips to them in the same release that publishes, never before.
The `git+URL` install is retained as the mirror and private-network story,
so nothing is lost for a machine that cannot reach the index.
Publishing remains a maintainer release act with its own review and versioning decision —
repository automation still never builds or uploads a PyPI artifact —
which is ADR-0015's boundary carried forward, not replaced.

## Supersedes

- **[ADR-0014](0014-lifecycle-verbs-and-the-provenance-manifest.md)** —
  its decision, evidence, and rejected-alternatives claims about the verb split.
  Payload embedding removes the "a pipx-installed `semlf` has no checkout to copy from" premise,
  so install, uninstall, and status move behind `semlf`,
  and `scripts/install.py` becomes a second door over the same operations rather than their home.
- **[ADR-0015](0015-distribution-channels.md)** —
  the wheel and zipapp contents, which now gain the registry's payload rows;
  the package channel's primary source, which becomes PyPI with `git+URL` kept for mirrors;
  and the collision story,
  whose surface moves to uv shim versus pipx shim versus a leftover pre-redesign zipapp.
  The install-time `PATH` warning surfaces it,
  alongside the three refusals ADR-0015 already named.
- **[ADR-0004](0004-portable-core-and-repository-cli.md)** —
  its amendment header, its decision parenthetical,
  and the lifecycle-verb sentence the parenthetical qualifies.
  The parenthetical is the part that names `scripts/install.py`;
  the sentence itself assigns installation lifecycle to the repository CLI,
  which this record restores in full.
  ADR-0004's core rule is untouched:
  the core stays one portable stdlib-only file,
  and every adapter still invokes it without the CLI.

Per the index's own policy,
none of those records is edited in place;
each gains a status line and a superseded-by pointer only,
and the claims above are answered here.

## Carries over unchanged

- **Preflight-then-apply** as the shape of every lifecycle command.
- **The provenance manifest** — one state file per artifact,
  the `managed` / `edited` / `unrecorded` tri-state with one direction of failure,
  and refusal over overwrite on any trouble.
- **Structural hook ownership** — `parse_managed_codex_hook` over matcher, hook type,
  launcher, checker basename, and arguments, never substring.
- **Doctor's replay contract** — end-to-end payload replay rather than file existence,
  and its platform lines as the evidence stream [ADR-0011](0011-go-port-gated-on-field-evidence.md)'s gate reads.
- **The maintainer-act publishing boundary** and **the no-fork mapping rule** from ADR-0015:
  `pyproject.toml` still maps `cli/semlf` and `scripts/check_linefeeds.py` from their real locations,
  rather than forking either into a packaging-only tree.
- **The managed-upgrade rule** is extended by the classifier, not weakened:
  a managed replacement still skips the backup in either direction,
  because a recorded release is not the only copy of anything;
  the classifier adds the version ordering, the downgrade refusal, and adoption on top of it.

## Evidence

- **The registry is the one mapping.**
  [`tests/test_registry.py`](../../tests/test_registry.py) pins the row ids and apply order,
  the `semlf/payloads/<id>` member paths, the owners,
  the two no-record rows, and the identity-compared set,
  and asserts that a wrong transform match count fails loud.
- **Byte identity.**
  [`tests/test_packaging.py`](../../tests/test_packaging.py) inspects the finished artifacts against the registry,
  member for member:
  the zipapp, the wheel, and a wheel built from the sdist.
  It also pins `PYZ_REQUIRED_MEMBERS` as covering the registry's members.
- **Rendering.**
  `test_registry.py` asserts the codex hook entry's single `__CHECKER__` substitution
  and all three codex-skill rewrites against the neutral root.
  [`tests/test_migration.py`](../../tests/test_migration.py) proves rendering from an installed wheel:
  it builds the wheel, installs it into a venv,
  and runs `semlf install codex` from the installed entry point.
  It also replays doctor through a really built zipapp.
  [`tests/test_installer.py`](../../tests/test_installer.py)'s `test_both_doors_render_identical_artifacts` is the two-door parity check.
- **The classifier matrix.**
  [`tests/test_classify.py`](../../tests/test_classify.py) covers every cell:
  version ordering, absent, adoption on an exact rendering,
  managed older, managed newer refused then forced, equal-version-different-bytes,
  unorderable, edited, unrecorded, the occupied backup slot,
  and the object-state rows that refuse even with `--force`.
- **Preflight and convergence.**
  [`tests/test_lifecycle.py`](../../tests/test_lifecycle.py) pins
  that one refusing artifact aborts the request before any write,
  that record-side preflight refuses before any write too,
  that the published-but-not-recorded half-state is reported by name and a rerun converges,
  that crossed destination-and-record interleavings fail closed,
  and that every registry row reaches the classifier.
- **The command surface.**
  [`tests/test_semlf_install.py`](../../tests/test_semlf_install.py)
  covers named-target consent, apply order, the non-TTY plan exiting 1,
  `--dry-run` dominance at exit 0, request-wide refusal,
  the required `agentsmd` path, the shim mismatch warning, the Claude trailer,
  status over lag and no-consumer leftovers, and uninstall including its usage error.
- **Migration.**
  `test_migration.py` starts from checkout-rendered artifacts and old records,
  then exercises package-door install, dry-run, status, doctor, force, and uninstall over them,
  including the leftover-zipapp `PATH` warning.
- **Identity.**
  `test_lifecycle.py`'s per-payload identity states and [`tests/test_doctor.py`](../../tests/test_doctor.py) together pin the reporting:
  doctor passes with current payloads,
  fails on an expected-payload mismatch,
  fails an installed hook with no published payload,
  and warns rather than fails once the consumer is gone.

## Alternatives rejected

- **Routing hooks through the `semlf` command** instead of a published checker path.
  Rejected because hooks run in the agent's environment,
  where `PATH` may lack the shim directory;
  because it would make the CLI a survival dependency of the guardrail,
  so uninstalling the CLI would silently kill enforcement for every agent;
  and because it would fork the hook shape between the package door and the checkout door,
  against [ADR-0004](0004-portable-core-and-repository-cli.md)'s rule
  that every adapter invokes the core without the CLI.
- **Teaching the checker to warn about payload lag at hook time.**
  Rejected because the core stays free of lifecycle knowledge,
  and hook output belongs to findings rather than to installer state.
  `semlf status` reports the lag and `semlf doctor` fails on it instead.
- **A package-door `cli` target.**
  Rejected because pipx, uv, and the zipapp all want `~/.local/bin/semlf`,
  so a package-installed `semlf uninstall cli --force` could unlink its own shim.
  The zipapp stays behind the checkout door,
  and the leftover case is handled as a migration warning.
- **A Node or npm channel.**
  Rejected because the Vercel `skills` CLI installs skills only
  and cannot install the hook, which is this kit's load-bearing layer;
  at most the README names it as a skill-only supplement with that caveat stated.
- **Rollback machinery and lifecycle-command locking.**
  Rejected as machinery the contract does not need:
  request-wide preflight, an idempotent rerun, and fail-closed classification are the whole guarantee,
  and ADR-0014's ruling that concurrent local mutation is out of scope still holds.
