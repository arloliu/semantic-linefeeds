# ADR-0014: Lifecycle verbs and the provenance manifest

**Status:** accepted — superseded in part by [ADR-0016](0016-one-entry-point-and-the-payload-registry.md)
**Date:** 2026-08-14
**Superseded in part:** 2026-08-14 —
[ADR-0016](0016-one-entry-point-and-the-payload-registry.md)
supersedes the verb split in the decision, evidence,
and rejected-alternatives sections below;
payload embedding removes the "no checkout to copy from" premise.

## Decision

### The verb split

The verb split refines [ADR-0004](0004-portable-core-and-repository-cli.md)'s assignment by what each verb needs.
Install, uninstall, and status stay in `scripts/install.py`
because the adapter payloads they copy exist only in the checkout.
Doctor and the identity module (`manifest.py`) ship inside the artifact
because they must run on machines that have only the artifact.
Approving the v0.6c plan is what authorized this amendment;
the rejected alternative is moving the verbs behind `semlf` with an explicit checkout-required error path.

### Provenance identity: one file per artifact

Provenance identity is the sha256 of the published bytes,
computed from the staged or rendered payload before publication
and recorded one file per artifact under `$XDG_STATE_HOME/semlf/artifacts/`.
A record proves schema, path identity, and digest, or it proves nothing;
the tri-state (`managed` / `edited` / `unrecorded`) has one direction of failure —
every trouble degrades to `unrecorded`,
which means refusal, never overwrite.
One file per artifact is the concurrency ruling:
no writer can drop or resurrect another artifact's state,
and a same-name race resolves to one of the two racing intents.
The rejected alternatives are a whole-file manifest
(a stale record could resurrect a forgotten entry)
and a cross-platform lock protocol with a stale-lock policy
(machinery a single-user state file does not earn).

### Ownership of the hook entry, and reading lifecycle state

Ownership of the Codex hook entry is structural over matcher, hook type,
launcher, checker basename, and arguments (`parse_managed_codex_hook`),
never substring.
Lifecycle state is read only through the guarded no-follow, bounded reader.

### The concurrency boundary

A local actor mutating lifecycle paths concurrently is out of scope,
extending the umbrella's v0.6a ruling —
that boundary cannot be held from inside the installer.
Every such absolute claim — never follows, never edits, never executes —
is therefore scoped to the state observed at classification time.
fd-identity revalidation between preflight and apply stays rejected
as machinery without a threat behind it,
and on platforms without `O_NOFOLLOW` the symlink guard is `lstat` alone.

### Managed upgrades skip the backup

A recorded release is not the only copy of anything,
so managed upgrades skip the backup.
The exclusive `O_EXCL` backup exists for hand-edited copies alone,
per the umbrella's ruling on the v0.6a finding.

### Uninstall

Uninstall is preflight-then-apply
and removes only what it can identify —
the current rendering, or a manifest-managed one —
requiring `--force` otherwise.
For the cli artifact specifically,
a manifest classification of `edited` refuses removal even when a fresh build's pyz identity matches the installed bytes:
bytes appended past the zip archive's `EOCD` change nothing a per-member digest can see,
but they do change the manifest's digest of the full raw file,
so identity substitutes for a missing record and never overrides one that already says `edited`.
It never deletes shared files (`hooks.json`, the AGENTS.md target),
and it never touches `semlf.bak`.
A `hooks.json` too strangely shaped to locate `PostToolUse` in refuses the same way
`install_codex`'s own guard does, rather than silently doing nothing.
Skill removal for every installed adapter is covered here,
closing the deferral [ADR-0006](0006-judgment-layer-for-every-agent.md) recorded.

### Doctor

Doctor replays payloads end to end rather than checking file existence,
certifies an installed hook in both directions or fails it,
and its platform lines are the evidence stream
[ADR-0011](0011-go-port-gated-on-field-evidence.md)'s gate reads.

## Evidence

- [ADR-0004](0004-portable-core-and-repository-cli.md) already assigns
  "installation lifecycle, doctor, and SARIF rendering" to the repository CLI;
  this record is the refinement that sentence now points to.
- [ADR-0006](0006-judgment-layer-for-every-agent.md)'s amendment already deferred native-skill removal to "v0.6's `uninstall` command";
  this record is that command's decision.
- [ADR-0011](0011-go-port-gated-on-field-evidence.md) already names doctor and the installers as the source of the platform-distribution and install-failure evidence its gate needs;
  this record specifies what doctor certifies to produce that evidence.
- `docs/plans/done/v0.6-repository-tooling-umbrella.md`'s v0.6c slice already names uninstall, doctor, the provenance manifest, and the exclusive backup as this slice's scope;
  this record is the architecture those tasks implement against.
- `scripts/install.py` already holds `install_cli`, `install_codex`, `install_codex_skill`,
  `install_opencode`, `install_agentsmd`, and `status`,
  the checkout-side functions uninstall joins.

## Alternatives rejected

- **Moving install, uninstall, and status behind `semlf`**,
  with or without an explicit checkout-required error path for a pipx install.
  Rejected because the write-verbs belong beside the payloads they copy,
  and a pipx-installed `semlf` has no checkout to copy from —
  an error path papers over a structural mismatch rather than resolving it.
- **A per-artifact manifest beside each install**,
  rather than centralized under `$XDG_STATE_HOME/semlf/artifacts/`.
  Rejected for litter beside every installed payload
  and for the partial-removal states a scattered manifest invites.
- **A whole-file manifest**, one record listing every artifact.
  Rejected because a stale whole-file record could resurrect an entry a later, narrower write forgot to touch.
- **A cross-platform lock protocol with a stale-lock policy** for concurrent manifest writes.
  Rejected as machinery a single-user state file does not earn;
  the one-file-per-artifact rule already resolves a same-name race to one of the two racing intents without a lock.
- **fd-identity revalidation between preflight and apply** for the symlink guard.
  Rejected as machinery without a threat behind it,
  given the concurrency boundary above is already ruled out of scope.
