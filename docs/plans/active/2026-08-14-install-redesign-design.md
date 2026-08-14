# Install UX Redesign — Design

**Status:** fourth revision, awaiting review
**Date:** 2026-08-14

## Problem

Two defects in the current install experience,
both reported from a fresh-user reading of the README.

1. **No component model.**
   The README's "three layers" section explains design philosophy,
   not what gets installed, where, or who needs each piece.
   The `semlf` CLI is the worst case:
   its check commands exist for humans and CI —
   manual audits, git modes, pre-commit, doctor —
   and no agent hook ever calls it,
   yet the Quick Start's first example is `--codex --cli` with no explanation,
   and two CLI channels (zipapp and pipx) appear later with a "pick one" warning.
2. **The install path is a three-hop black box.**
   `curl | sh` clones a hidden checkout under `~/.local/share/semantic-linefeeds`,
   then hands off to `install.py`,
   which writes files into several locations the user never sees named up front.

## Patterns adopted from the field

Three healthy READMEs were surveyed
(obra/superpowers, mattpocock/skills, headroomlabs-ai/headroom):

- **headroom** — a two-tier install document
  (a 60-second quickstart on top, exhaustive channel and corporate-network detail in an appendix),
  a `doctor` verification step inside the quickstart itself,
  and naming exactly which files an install touches.
  The more invasive the tool, the more disclosure it owes;
  this kit writes hook configs, skill files, and a bin executable,
  so it sits at the high-disclosure end.
- **superpowers** — installs organized per host agent,
  one short command block per agent, so the only decision is "which agent do you use".
- **mattpocock/skills** — the only survey entry that names channel conflict outright
  ("Pick one — installing both leaves you with every skill twice").

## Decision

### One entry point: install the tool, the tool installs the integrations

```bash
uv tool install semlf        # or: pipx install semlf
semlf install                # detects agents, lists every path it would write, asks y/N
semlf doctor                 # replays the payloads end to end
```

Claude Code stays on its plugin marketplace pair and is never touched by `semlf`.

### The neutral payload root

Installed codex hooks and skills reference the checker at one channel-neutral path:

```
${XDG_DATA_HOME:-~/.local/share}/semlf/check_linefeeds.py
```

Installing the codex integration publishes the checker there as a provenance-managed artifact,
whatever channel `semlf` itself arrived by —
wheel, zipapp, or checkout —
and publishes `README.md` beside it,
so the installed skill's suppression-rules link resolves to a local file
and keeps working on air-gapped machines.
The opencode integration is the stated exception to the single target:
its plugin resolves the checker beside itself,
so its install publishes a second, colocated checker copy under the same provenance rules.

The zipapp channel forces the neutral-root shape anyway:
a hook cannot point into a `.pyz` archive,
so the checker must be published to a real path,
and when that path is the single hook target for every channel,
a hook survives a channel switch, a venv rebuild, or a CLI uninstall untouched.
The alternative — routing hooks through the `semlf` command itself —
was analyzed and rejected:
hooks run in the agent's environment, where `PATH` may lack the shim directory;
it would make the CLI a survival dependency of the guardrail
(uninstalling the CLI would silently kill enforcement for every agent);
and it would fork the hook shape between the package door and the checkout door,
against ADR-0004's rule that adapters invoke the core without the CLI.

One residual risk is accepted and mitigated:
after `uv tool upgrade semlf`,
the published payloads lag until `semlf install` runs again.
`semlf status` reports the lag and `semlf doctor` fails on it
(the identity check below),
and the documented upgrade command is the pair
`uv tool upgrade semlf && semlf install`.
Teaching the checker itself to warn about lag at hook time was considered and rejected:
the core stays free of lifecycle knowledge,
and hook output belongs to findings, not to installer state.

The published payloads are deliberately left in place
when the last consuming integration is uninstalled:
their independence from any one integration is the point of the neutral root.
When `semlf status` sees published payloads with no consumer,
it says so in one line and names the directory for manual removal.

### The payload registry

One declarative registry drives the wheel build, the zipapp build, the installer,
and the identity checks,
so no consumer invents a second mapping.
Each row carries:
a logical id (which is also its provenance record name where one exists),
the canonical repository path,
the embedded member path (`semlf/payloads/<id>` in both wheel and zipapp),
the installed destination or destinations,
the transform with its required match count,
the owning install target,
and its apply-order position.
The registry lives as one table in a `cli/semlf/` module,
imported by the installer, both builders, and the tests.
Neither builder copies canonical files by hand:
a shared staging step reads the registry
and places each canonical source at its member path in the build tree only —
the wheel's build hook and the zipapp builder both call it,
and no packaging copy is ever committed to the repository.

| Id | Canonical source | Installed destination | Transform | Owner |
|---|---|---|---|---|
| `checker` | `scripts/check_linefeeds.py` | `<data root>/semlf/check_linefeeds.py` | byte copy | codex |
| `readme` | `README.md` | `<data root>/semlf/README.md` | byte copy | codex |
| `codex-hook-template` (structural admission, no record) | `adapters/codex/hooks.json` | merged entry in `$CODEX_HOME/hooks.json` | `__CHECKER__` → neutral checker path | codex |
| `codex-skill` | `skills/semantic-linefeeds/SKILL.md` | `~/.agents/skills/semantic-linefeeds/SKILL.md` | three rewrites, each must match exactly once | codex |
| `opencode-plugin` | `adapters/opencode/semantic-linefeeds.ts` | opencode plugins dir | byte copy | opencode |
| `opencode-checker` | `scripts/check_linefeeds.py` | checker beside the plugin | byte copy | opencode |
| `agentsmd-snippet` (sentinel admission, no record) | `adapters/agentsmd/SNIPPET.md` | sentinel block in the path the user names | byte splice | agentsmd |

`manifest.KNOWN` grows the `checker` and `readme` names;
the codex hook keeps structural admission
(`parse_managed_codex_hook` over the shared `hooks.json`, never per-file bytes),
and the agentsmd snippet keeps sentinel-block admission in a user-owned file.
The canonical hook template's placeholder becomes `__CHECKER__`
and carries the full checker path,
because substituting a directory into today's `__REPO__/scripts/...` shape bakes a stray `/scripts/` segment into the command.
Every transform fails loud when its match count is wrong,
so a canonical-source edit can never silently disable a rewrite.
The codex-skill rewrites are pinned to the neutral root:
the fenced command's checker path becomes `<data root>/semlf/check_linefeeds.py`,
the suppression link becomes `<data root>/semlf/README.md`,
and the checkout-only fallback sentence is removed;
the rendering test asserts all three rendered strings.
The two no-record rows still have ids
so their member paths exist —
the hook template and the snippet ride in both artifacts for rendering and for `semlf install agentsmd PATH`.
The installed hook command keeps the shape
`python3 <path ending in check_linefeeds.py> --hook codex`,
so the structural ownership rule holds unchanged.
`PYZ_REQUIRED_MEMBERS` grows by the registry's embedded member paths,
and the packaging tests inspect the finished wheel and zipapp against the registry.

### The artifact classifier

Admission is decided on three independent axes,
for every registry row that is a single-file artifact
(`checker`, `readme`, `codex-skill`, `opencode-plugin`, `opencode-checker`):

- **Object state** — absent; readable regular file; unreadable regular file;
  symlink; directory; other special file.
- **Provenance state** (for a readable regular file) —
  exact current rendering; manifest-managed different release; edited; unrecorded.
- **Execution mode** — normal; `--force`; `--dry-run` (orthogonal to the other two).

| Object × provenance | Normal | With `--force` |
|---|---|---|
| absent | write, record provenance | same |
| exact current rendering | no-op; adopt or refresh a missing or stale record | same |
| managed older release | replace, refresh record, no backup | same |
| managed newer release (downgrade) | refuse: "published is newer than this artifact — rerun with `--force` to downgrade" | replace, refresh record, no backup |
| managed, equal version, different bytes | replace, refresh record, no backup | same |
| managed, unorderable version | refuse: "cannot order the recorded version against this artifact's" | replace, refresh record, no backup |
| edited or unrecorded | refuse, name the finding | exclusive `O_EXCL` backup, then replace and record |
| backup slot occupied or non-regular | refuse | still refuse |
| symlink, directory, special, unreadable | refuse | still refuse — force never overrides an object-state refusal |

Adoption in the exact-rendering row is deliberate:
publication and record are separate files,
so a correct copy with a missing record must converge to `managed` on the next run,
not stay `unrecorded` forever.
Versions order as dot-separated integer tuples, compared numerically;
a recorded version that does not parse that way is unorderable,
and the classifier fails closed on it rather than guessing.
Equal version with different bytes replaces:
two builds can share a version string,
and the running artifact's rendering is the one its record must describe.
Downgrade refusal is the default
because an old zipapp or checkout run must not silently drag every hook's checker backwards;
`--force` states the intent, and the refusal message names it.
Managed replacements in either direction skip the backup —
ADR-0014's rationale stands: a recorded release is not the only copy of anything.
`--dry-run` never prompts, never writes a destination, never mutates a record,
prints each artifact's classification and the action normal mode would take
(including any refusal it would hit),
and exits 0.
That last point is a deliberate behavioral change for the checkout door,
whose dry-run today exits nonzero on a diverged skill or plugin file.

### Request-wide preflight, apply order, and concurrency

`semlf install` classifies every artifact of the whole request read-only first;
any refusal aborts the run before the first write,
reporting every artifact's verdict.
Preflight admits the provenance side too:
the state root must resolve,
and each record's parent and leaf must be writable paths,
not directories or special files,
before the first destination is touched.
Apply order follows the registry's order field:
the neutral `checker` and `readme` first,
then each integration's own files.
If the filesystem fails mid-apply anyway,
the run reports, per artifact,
applied, not applied,
or published-but-not-recorded —
the half-state where a destination replaced but its record write failed —
and a rerun converges:
every completed artifact classifies as exact rendering
and no-ops or adopts its missing record,
every incomplete one is attempted again.
Rollback is deliberately not offered.

Concurrent lifecycle commands stay out of scope,
carrying ADR-0014's boundary forward unchanged.
What the design does require is atomic complete-file publication
(the existing same-directory temp file and `os.replace`),
provenance recorded immediately after each artifact's publication,
and a test pinning that every crossed destination-and-record interleaving fails closed as `edited` or `unrecorded` —
degraded classification, never a silent overwrite.

### Command surface

| Command | Behavior |
|---|---|
| `semlf install` | detect codex and opencode; print every path the plan writes; TTY: confirm `y/N`; non-TTY without `--yes`: print the plan, exit 1 with a `--yes` hint |
| `semlf install codex opencode` | naming a target is consent: apply directly, no prompt, TTY or not |
| `semlf install agentsmd PATH` | first-class; the path is required, never defaulted, never auto-detected |
| `semlf install --yes` | apply without prompting, any mode |
| `semlf install --dry-run` | print every artifact's classification and planned action, write nothing, exit 0 |
| `semlf status` | report every discoverable or recorded artifact's state, including published-payload lag and no-consumer leftovers; the agentsmd snippet lives at a user-named path and is excluded |
| `semlf status agentsmd PATH` | report the sentinel block's state in the named file |
| `semlf uninstall codex` | preflight-then-apply removal, ADR-0014 semantics unchanged |
| `semlf uninstall agentsmd PATH` | removes the sentinel block from the named file; path required, mirroring install |
| `semlf uninstall` (no target) | usage error, exit 64 |
| `semlf doctor` | today's replay, plus the published-payload identity check below |

Precedence is fixed:
`--dry-run` dominates everything —
it never prompts and exits 0 whatever the TTY state,
consent flags, or would-be refusals, which it reports instead of taking.
Consent (`--yes` or a named target) affects only a non-dry apply.
A TTY prompt answered `n`, closed by EOF, or interrupted declines the run: exit 1.
Detection that finds zero targets is an explicit no-op:
it says so and exits 0.
`--help` states plainly that naming a target applies it immediately.
Auto-detection covers codex and opencode only;
the agentsmd snippet is never auto-installed,
and the zipapp never is (next section).
Exit codes stay 0 success or no-op, 1 refusal or error, 64 usage —
the non-TTY unconfirmed plan exits 1
because a provisioning script that forgot `--yes` must fail loud,
not report green over an install that never happened.

When the `claude` binary is on `PATH` or `~/.claude` exists,
`semlf install` and `semlf status` end their output with the two marketplace commands,
visually set off as the last block
so multi-agent install output cannot scroll it away,
and a user cannot mistake Claude Code for something `semlf` configured.

### Staleness is a digest question, and doctor fails on it

`semlf status` and `semlf doctor` compare every published payload —
both checker copies and the readme —
against the payload set embedded in the running artifact,
by guarded bytes, never by version string alone:
two builds can differ under one version,
and on a downgrade the published copy is ahead, not behind.
The version string is the human-facing label in the report,
with distinct wordings for missing, edited,
managed-but-lagging, managed-but-ahead,
and same-version-different-bytes.
Expectedness is conditioned on consumers:
an installed integration makes its payloads expected,
and a mismatch on an expected payload is what doctor fails on.
A payload with no remaining consumer —
the deliberately retained leftovers above —
is reported as a warning with the manual-removal pointer, never a failure,
a machine with no integrations passes,
and a codex-only machine is never failed over the absent opencode copy.
`semlf status` reports; `semlf doctor` counts any expected-payload mismatch as a failed check and exits 1.
The doctor row in the command table above is this addition;
doctor's existing replay contract is otherwise untouched.

### The zipapp stays behind the checkout door

The package door has no `cli` target:
pipx, uv, and the zipapp all want `~/.local/bin/semlf`,
and a package-installed `semlf uninstall cli --force` could unlink the very shim the running command came from.
Building and removing the zipapp remains exclusive to the checkout door
(`install.py --cli`, as today).
A zipapp left over from before this redesign is a migration case:
`semlf install` itself performs the `PATH` check at the end of its run
and warns immediately when `semlf` on `PATH` is not the running artifact's shim,
and `semlf status` and `semlf doctor` repeat the report with the checkout-door removal pointer.

### One implementation, two doors

The lifecycle code moves into `cli/semlf/` modules.
`scripts/install.py` remains as the checkout-side door for air-gapped and development use,
keeping its entire current flag vocabulary —
`--codex`, `--opencode`, `--agentsmd PATH`, `--cli`, `--auto`,
`--uninstall`, `--dry-run`, `--force`, and no-flag status —
as a thin parser over the same shared operations,
so `install.sh` keeps working with zero changes.
`--codex` and `--auto` publish the neutral checker and readme through the same shared operation the package door uses;
an `install.py --codex` run and a `semlf install codex` run produce byte-identical artifacts everywhere.
`--auto` is itself consent (it is an explicit action),
prints the same plan while applying,
and keeps installing the zipapp unconditionally;
the package door's `semlf install` never does.

The flag surface is unchanged;
the behavior deltas under it are enumerated here, documented, and called out in the release notes:
the installed hook's target path moves from the checkout to the neutral root;
`--dry-run` on a diverged file prints the would-be refusal at exit 0 instead of exiting nonzero;
a manifest-managed older skill or opencode file now upgrades without `--force`;
managed replacements skip the backup that `atomic_write` takes today;
an occupied backup slot now refuses uniformly,
where today the skill and opencode paths overwrite a stale `.bak` last-run-wins;
`--codex` newly publishes the neutral checker and readme;
and argumentless status stops probing `./AGENTS.md`,
which `semlf status agentsmd PATH` replaces.

### Channels after the change

| Channel | Command | Audience |
|---|---|---|
| Package (primary) | `uv tool install semlf` / `pipx install semlf`, then `semlf install` | anyone whose machine reaches PyPI or a git host |
| Package from a mirror | same, with `git+ssh://git.internal/...` or an internal index | private networks |
| Checkout | `git clone` + `python3 scripts/install.py`, or `install.sh` | air-gapped machines, development |
| Claude Code | `claude plugin marketplace add` + `claude plugin install` | unchanged |

One channel per machine stays the rule.
The collision surface moves with the redesign —
uv shim versus pipx shim versus a leftover pre-redesign zipapp —
and the install-time `PATH` warning plus the status/doctor migration report above are what surface it.

### PyPI

The first PyPI publish is a required step of this slice:
the README quickstart flips to `uv tool install semlf` in the same release that publishes,
never before.
Name availability on PyPI is a release gate to verify at publish time.
Publishing stays a maintainer release act —
repository automation never builds or uploads a PyPI artifact —
and the git-URL install remains fully supported as the mirror story,
so private networks lose nothing.
The agentsmd snippet's own fallback install line is updated to the new command
as part of the payload work.

### README restructure

Two tiers, in this order:

1. What it is and the diff argument (current opening, trimmed).
2. **Quickstart** — the three-line block above,
   plus the Claude Code marketplace pair,
   plus a per-agent table for readers who want exactly one integration.
3. **What gets installed** — a matrix: component × location × purpose × who needs it.
   The CLI's optionality is stated per channel, because it differs:
   on the package channel the `semlf` package is the installer and cannot be skipped,
   but its check commands remain optional;
   a guardrail-only machine with no CLI at all is the checkout door's offer
   (`install.sh --codex`, no `--cli`).
4. The layers, suppression, configuration, and git-modes sections, as today.
5. **Appendix** — air-gapped and mirror installs
   (`install.sh`, `SEMLF_REPO`, the zipapp channel), lifecycle detail, testing.

A channel-conflict note sits with the quickstart:
one channel per machine, and `semlf doctor` names a collision when it sees one.

### ADR impact

The decisions index's own policy holds:
an accepted record is never edited,
so the redesign is recorded as one new ADR
that supersedes the affected parts of ADR-0004, ADR-0014, and ADR-0015,
and the superseded records gain only status and superseded-by pointers.
The sweep below names what the new record must cover,
because decision text, evidence lists, rejected-alternative entries,
amendment headers, the decisions index, and the project rule all restate the old verb split and the old packaging shape.

- **ADR-0014** — the new record supersedes its decision, evidence, and rejected-alternatives claims:
  payload embedding removes the "no payload to copy from" premise,
  and install, uninstall, and status move behind `semlf`.
  Preflight-then-apply, the provenance manifest,
  structural hook ownership, and doctor's contract carry over;
  the managed-upgrade rule is extended by the classifier above, not weakened.
- **ADR-0015** — the new record supersedes three areas:
  wheel and zipapp contents gain the registry's rows,
  the package channel gains PyPI as its primary source
  (git-URL retained for mirrors),
  and the collision story records the moved surface;
  its evidence list and rejected collision alternative are updated with it.
  The maintainer-act publishing boundary and the no-fork mapping rule stand.
- **ADR-0004** — the amendment header, the decision parenthetical,
  and the lifecycle-verb sentence are superseded together,
  each marked by a pointer to the new record, never rewritten in place.
- **`.agents/rules/100-project-map.md`** and **`docs/decisions/README.md`** —
  living documents, not records —
  their verb-assignment and distribution summaries are amended in the same commit as the new record.

## Non-goals

- No Node or npm channel.
  The Vercel `skills` CLI (`npx skills add`) installs skills only —
  it cannot install the hook, which is this kit's load-bearing layer —
  so at most the README mentions it as a skill-only supplement with that caveat stated.
- No change to the Claude Code install.
- No change to detector behavior, hook wire formats, or the one-file core rule.
- No rollback machinery and no lifecycle-command locking;
  the preflight, idempotent-rerun, and fail-closed rules above are the whole contract.
- `semlf update` (headroom-style, channel-detecting self-update)
  and `semlf clean` (removing no-consumer leftovers) are possible follow-ups,
  not part of this slice.

## Testing

- Byte-identity: embedded payloads match their canonical sources,
  and the wheel's payload set matches the zipapp's, member for member,
  both inspected against the registry.
- Rendering: the installed codex hook entry and skill body are asserted against the registry's transforms,
  including the exactly-once match counts,
  from a wheel install and a zipapp install, not only the checkout.
- Classifier: every object-state × provenance-state × mode cell above is tested per artifact,
  including adoption, downgrade refusal and forced downgrade,
  the occupied backup slot, and the force-never-overrides object-state rows.
- Preflight: a request with one refusing artifact mutates nothing;
  a mid-apply failure leaves a state a rerun converges from,
  including the published-but-not-recorded half-state
  and permanent record-side failures —
  no resolvable state root, a directory at the record path;
  crossed destination-and-record interleavings classify as `edited` or `unrecorded`.
- Migration: tests begin from current checkout-rendered artifacts
  and existing provenance records,
  then exercise package-door install, status, doctor, dry-run, force, and uninstall over them —
  including the leftover-zipapp `PATH` warning.
- Identity: status and doctor distinguish missing, edited, lagging, ahead,
  and same-version-different-bytes for both checker copies and the readme.
- `tests/test_packaging.py` extends to pin the payload members.

## Sequencing

This is a full slice (CLI surface, packaging, ADR amendments, README rewrite),
sized like v0.6c, with the first PyPI publish as its closing step.
Where it lands relative to the ADR-0011 gate review is a scheduling call for the owner;
nothing in it depends on the gate's outcome.
The README's component-model matrix and section reorder (tier 2 and 3 above)
could ship earlier as a docs-only change if a stopgap is wanted.
