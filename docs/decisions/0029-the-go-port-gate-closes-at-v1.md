# ADR-0029: The Go-port gate closes at v1.0

**Status:** accepted
**Date:** 2026-08-21
**Supersedes:** [ADR-0011](0011-go-port-gated-on-field-evidence.md)'s open review clause;
its port-shape constraints carry forward unchanged

## Decision

The gate ADR-0011 required settling before v1.0 is settled **closed**.
v1.0.0 ships on the Python portable core as the authoritative implementation,
and no port work opens before or with the freeze.

Three consequences, stated so the freeze cannot be read around:

- The frozen observable contract remains implementation-agnostic,
  exactly as ADR-0011 obligated v0.6 to keep it.
- A differential-proven port may still become the sole authoritative implementation later,
  in the one acceptable shape ADR-0011 records:
  behind the same contract, proven by the differential harness against the frozen baselines,
  replacing the Python core rather than coexisting with it.
- What closing the gate forecloses is narrower and permanent:
  a port can no longer adjust a contract it proves wrong.
  After v1.0, a contract defect a port surfaces costs a major version like any other break.

## Evidence inventory

Settlement cutoff 2026-08-21.
Two channels were inventoried.

**The GitHub issue tracker** is enabled and holds zero issues, open or closed.

**Field reports recorded in `docs/`** number three:

| Report | Class | Disposition |
|---|---|---|
| The `--agentsmd` absolute-path complaint | packaging | resolved by the packaged CLI |
| The `.tmpl` invisibility report | extraction coverage | deferred in `docs/ROADMAP.md` with its entry condition |
| The v0.8.0 over-long-repair report | detector and repair-feedback behavior | fixed by the long-advisory change in [the detector-precision plan](../plans/done/2026-08-16-detector-precision-fixes.md) |

`doctor` prints the invoking machine's platform and Python version for a human to relay;
it aggregates nothing, so the inventory counts reports rather than telemetry.

The settlement rests on the narrow supported fact:
**no inventoried report identifies unavailable `python3` as an adoption blocker.**
ADR-0011's entry condition — managed CI images, Windows endpoints,
or mirrored enterprise environments that cannot provide `python3` —
has not been met in any channel over the gate's whole lifetime.

## What would reopen this

Nothing in this record forbids a port forever.
The entry condition survives as written in ADR-0011:
field evidence that a missing Python runtime is a primary adoption blocker.
What changes at v1.0 is only what a port may do about the contract it finds.
