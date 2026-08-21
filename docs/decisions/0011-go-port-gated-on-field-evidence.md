# ADR-0011: A Go port is deferred behind a field-evidence gate

**Status:** accepted — gate settled closed by [ADR-0029](0029-the-go-port-gate-closes-at-v1.md)
**Date:** 2026-08-13
**Reviewed:** 2026-08-14 —
gate unchanged at the v0.6→v0.7 boundary:
no field evidence of a missing-runtime adoption blocker;
next review before v1.0.

## Decision

`semlf` ships v0.6 on the Python portable core (ADR-0004).
A prebuilt Go binary is a deferred option, not v0.6 work,
and it opens only when a named entry condition is met:

> Field evidence shows a missing Python runtime is a primary adoption blocker —
> managed CI images, Windows endpoints, or mirrored enterprise environments
> that cannot provide `python3` and therefore cannot install the kit.

The decision is reviewed at the v0.6→v0.7 boundary,
and it must be settled before v1.0 in either direction,
because v1.0 freezes the CLI surface, diagnostic schema, and exit codes,
and a semantic port attempted after that freeze could no longer adjust a contract the port proves wrong.

If the gate opens, the port has one acceptable shape:
Go becomes the sole authoritative implementation behind the same contract,
proven by a differential harness before it replaces anything.
A permanent dual implementation and a Go launcher wrapping the Python checker are both rejected below.

## What v0.6 does to keep the option open

Three obligations land in v0.6 regardless of how the gate resolves,
and each is work v0.6 wants anyway:

- **The contract stays implementation-agnostic.**
  Flags, config schema, diagnostic schema, and exit codes must not leak Python details,
  so a future binary can sit behind the same contract with no adapter change.
- **The differential baseline is already frozen.**
  The v0.5.0 tag pins the detector fixtures, extractor goldens,
  payload tests, and the changed-span suite;
  a future harness runs both implementations against those inputs
  and compares every observable:
  finding kind, line, message, excerpt, ordering,
  stdout, stderr, and exit code.
- **`doctor` and the installers collect the evidence the gate needs:**
  platform distribution, Python availability, and install failures.

## Evidence at the time of decision

- Every field report to date is about packaging or coverage, not runtime.
  The `--agentsmd` absolute-path complaint waits on the packaged CLI,
  and `.tmpl` invisibility is an extraction-coverage gap;
  neither says "we cannot provide python3."
- The zipapp proof (ADR-0004) shows a 10,465-byte artifact running under `python3 -I -S` in an empty directory,
  with a 16.4ms median bare-Python startup on one machine —
  no observed latency pressure on the hook path.
- A full port is estimated at 17–28 person-days before ongoing release-matrix maintenance:
  target architectures, checksums, signing,
  private-mirror and rollback flows,
  and pinned review of a third-party regex dependency.
- The port is not mechanical.
  Go's RE2 engine supports neither the negative lookahead in `FUSED_RE`
  nor the backreference in `DIVIDER_RE`;
  the viable bridge (`regexp2`) is a backtracking engine
  that needs per-pattern timeouts,
  and Python `re` and `regexp2` differ on Unicode classes,
  word boundaries, and byte-versus-rune indexing —
  the ownership ranges of ADR-0005 are code-point ranges,
  so index conversion must be proven, not assumed.
- The precision contract raises the stakes:
  three sealed holdout rounds scored the Python implementation,
  and any new finding on prose already labeled correct is a blocking regression,
  not an acceptable porting cost.

## Alternatives rejected

- **Start the port in v0.6.**
  The cost is misaligned with v0.6's actual bottleneck —
  the workflow gap, which every pillar addresses on the Python core today —
  and the CLI contract is still converging,
  so differential testing would aim at a moving target.
  Porting against the frozen v0.6 contract is strictly cheaper and safer.
- **A Go launcher wrapping the Python checker.**
  It keeps the Python runtime prerequisite
  while adding a second release and upgrade path —
  the costs of both worlds and the benefits of neither.
- **A permanent dual implementation.**
  Two detectors drift,
  and the precision numbers were earned against labels by one of them;
  after the differential transition, exactly one implementation is authoritative.
- **Deciding after v1.0.**
  Stability contracts are promised at v1.0;
  a port that discovers a contract defect after the freeze has no room to fix it.
