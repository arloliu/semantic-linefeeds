# Setup Skill: an install guardrail for agents, not a second installer

**Date:** 2026-08-15
**Status:** draft

## Purpose

`semlf install` already installs well.
It preflights the whole request as one unit, refuses on conflict, backs up what it replaces, and records provenance for every file it writes.
What is missing is a contract for the *agent* standing between the user and that CLI.

An agent asked to "install semlf" with no instructions improvises:
it guesses a package name, hand-edits `hooks.json`, or reaches for `--force` to make a refusal go away.
This spec adds one skill that removes that improvisation, and nothing else.
The skill shells out to the CLI that already exists;
it never reimplements install logic, and it never writes an artifact the CLI owns.

The inspiration is `setup-matt-pocock-skills`, but the analogy needs correcting up front.
That skill is a *configurator*, not an installer:
its own body says "Scaffold the per-repo configuration" and "This is a prompt-driven skill, not a deterministic script".
The install step in that project belongs to `npx skills@latest add`,
which is the counterpart of `uv tool install semlf`, not of the skill.
This spec keeps that division: the CLI installs, the skill judges and configures.

## Verified findings that shape the design

Each item below was checked against the source or the installed binary on 2026-08-15,
and each one changed the design from what a first reading would suggest.
Two external reviews — Codex CLI and opencode itself — corrected several of them,
and those corrections are folded in here.

### The curl rung needs `git`, and only the checkout door leaves `install.sh` on disk

`install.sh` fetches a checkout into `$SEMLF_HOME` and then execs `scripts/install.py` from it.
Unset, that home resolves to `$XDG_DATA_HOME/semantic-linefeeds` when `XDG_DATA_HOME` is set.
Otherwise it is `~/.local/share/semantic-linefeeds`.

The `git` requirement is real but narrower than it first appears.
A piped run — the form this skill uses — always fetches, so it requires `git` and network reach to the repository.
A local self-checkout with no pinned ref skips both the fetch and the `git` check entirely
(`install.sh:83`, `install.sh:119`),
so the requirement belongs to the curl rung, not to `install.sh` in general.

Two consequences.
A machine installed through the checkout door keeps `install.sh` on disk;
a machine installed through `uv` or `pipx` never has it, because no registry row publishes it.
So the skill may never assume a local `install.sh` — it curls the one-liner or nothing.
And because the curl rung needs `git` plus repository reach, while `pip` needs only an index that is often mirrored internally,
the curl door belongs at the *end* of the fallback ladder, not the front.

### `--auto` already installs the CLI, so `--cli --auto` is a usage error

`--auto` detects agents by evidence and installs a matching mode for each, "plus the cli unconditionally".
It is mutually exclusive with every explicit mode flag,
and `python3 scripts/install.py --cli --auto` exits with the usage error.
The last rung of the ladder is therefore `sh -s -- --auto`, with no `--cli`.

### opencode reads `~/.agents/skills`, but nothing there is user-invocable

The installed opencode (1.18.18) carries its own documentation table in the binary:

```
| External skills (auto-loaded) | ~/.claude/skills/<name>/SKILL.md, ~/.agents/skills/<name>/SKILL.md |
```

The path and the `SKILL.md` format are therefore right, and opencode also scans its own `~/.config/opencode/skills`.
"Auto-loaded" overstates the mechanism, though.
A skill's description is advertised to the model, and its body loads only when the model calls the `skill` tool —
there is no user-typed `/skill` in this TUI.
The `/skill` and `/skills` strings in the binary are HTTP routes in its internal SDK, not slash-commands.

This is what makes a command file necessary rather than redundant.
Command files are the only thing a user can type,
so a design with a skill and no command leaves opencode users with no deterministic trigger at all:
the guardrail would fire only when a model happens to match a prose description,
and a phrasing like "semantic linefeeds isn't running on commit" would miss it.
The binary's own table accepts both `.opencode/command/<name>.md` and `.opencode/commands/<name>.md`.

### opencode users get no skill today

`plan_install` selects rows by `row.recorded and row.owner in targets` (`cli/semlf/lifecycle.py:580`),
and `codex-skill` is owned by `codex`.
So `semlf install opencode` installs the plugin and its bundled checker, and no skill at all.
The judgment layer that [ADR-0006](../../decisions/0006-judgment-layer-for-every-agent.md) promised every agent is absent for opencode users.
This spec does not fix that gap;
it is a dependency problem, not an ownership problem, and the deferred-work section explains why it needs its own spec.

### `doctor` cannot see a stale skill, and its failures are not all repairable

`codex-skill` is deliberately not identity-checked, and `doctor` compares current embedded bytes only for identity rows.
Its provenance loop checks an installed file against its *recorded* digest rather than the running package's rendering,
and provenance warnings do not increment the failure count.
So a package upgrade can leave a skill at old bytes while `doctor` still exits 0.

`doctor` failing is likewise not proof of a stale install.
It can fail because it cannot replay the running artifact, because `hooks.json` is unreadable or malformed —
which install may refuse rather than repair — or, on Windows, unconditionally when a Codex hook is installed.
A skill that reads exit 1 as "re-run install" is wrong in each of those cases.

### `semlf install` refuses to apply on a non-TTY

With auto-detected targets and no `--yes`, install describes the plan, then checks `sys.stdin.isatty()`;
when there is no terminal it prints "re-run with `--yes` to apply this plan" and exits 1 (`cli/semlf/lifecycle.py:676`).
Agent shells are routinely non-interactive,
so a skill that obtains the user's agreement in conversation must then apply with `--yes`:
the agreement it already holds cannot otherwise reach that prompt.

### `status` reports a hard-coded list of integration artifacts

Status walks a literal pair — `("codex-skill", …), ("opencode-plugin", …)` (`cli/semlf/lifecycle.py:871`).
A new non-identity row does not appear there by virtue of existing;
adding it to that loop is part of this change rather than a consequence of it.

### The bootstrap step is rare outside Claude Code, but not unreachable

In Codex and opencode the skill normally arrives *because* `semlf install` ran, so the CLI is usually already present.
That is a tendency, not an invariant.
The skill is installed outside the package environment, so removing a `uv` tool, losing a shim from `PATH`,
or switching channels can leave the skill present and the CLI gone.
Step 0 therefore probes rather than assumes, and the ladder stays reachable in every host.

For Claude Code the plugin lands first and the CLI may never have existed, so the ladder earns its keep there.
The recurring value in all three hosts is the other half — verify, repair, and configure.

## Constraints carried over from AGENTS.md and its rules

- The skill adds no runtime dependency and no second install path
  ([100-project-map.md](../../../.agents/rules/100-project-map.md)).
  Every action against an artifact the CLI owns goes through a `semlf` subcommand.
- Precision over recall applies to install actions as much as to findings:
  a skill that occasionally declines to act is fine, and one that overwrites a user's file is a bug.
  A failed rung is reported with the real error, never classified into a guessed cause.
- The self-hosting rule covers the new `SKILL.md` and this spec:
  both must pass `python3 scripts/check_linefeeds.py --file`.
- Payloads reach agents through the declarative registry, never a hand-maintained call sequence
  ([ADR-0016](../../decisions/0016-one-entry-point-and-the-payload-registry.md)).

## 1. The skill file

One new file, `skills/setup-semlf/SKILL.md`, with four steps.
It references no published payload — no checker path, no README link —
which is what lets every target install its own copy without depending on another target's files.

### Step 0 — locate

Run `semlf --version`.
When it answers, skip to step 2.
When it does not, continue to step 1.

### Step 1 — bootstrap, only when the CLI is absent

A fixed ladder, tried in order, stopping at the first that succeeds:

| Rung | Command | Requires |
|---|---|---|
| 1 | `uv tool install semlf` | `uv`, a reachable index; `uv` provisions its own interpreter unless downloads are disabled |
| 2 | `pipx install semlf` | `pipx`, a reachable index, and an interpreter ≥ 3.9 |
| 3 | `python3 -m pip install --user semlf` | `pip`, a reachable index, and an interpreter ≥ 3.9 |
| 4 | `curl -fsSL https://raw.githubusercontent.com/arloliu/semantic-linefeeds/main/install.sh \| sh -s -- --auto` | `curl`, a POSIX `sh`, `git`, `python3` ≥ 3.9, repository reach |

The skill picks a rung by probing, but it does not run one silently.
It names the chosen rung and its exact command, waits for agreement, and only then executes.
That gate is what stops a stray invocation from installing software, not the `description` field:
a description decides when a skill loads, it cannot constrain what the skill then does.
A README that says "install semlf for me" therefore reaches a prompt, not a shell.

Rung 3 needs an interpreter the package supports, so a version probe guards it.
The probe walks the `python3.N` names present on `PATH` from the newest downward and takes the first at or above 3.9,
rather than testing a hard-coded list that goes stale with each release.
Rung 1 needs no probe, because `uv` provisions its own interpreter.
Rung 2 runs on whatever interpreter `pipx` itself was installed with,
which the probe can only override through `pipx install --python <interpreter> semlf`.
Rung 3 also carries two failure modes worth naming rather than guessing at:
`pip install --user` can refuse inside an active virtual environment,
and `PYTHONUSERBASE` can redirect its destination outside the home.

When a rung fails, the skill reports that rung's actual error.
It does not translate a failure into "a prerequisite was missing",
because index authentication, a proxy, a conflicting install, and virtual-environment policy all fail differently and are fixed differently.
When every rung fails, it stops rather than inventing a fifth path.

After a successful rung the skill does not merely check that `semlf --version` answers.
An older zipapp at `~/.local/bin/semlf` can shadow a newly installed `uv` or `pipx` shim,
and the CLI's own shim warning cannot see it when `PATH` resolved to the old artifact in the first place.
So the skill compares the path the installer reported against `command -v semlf`,
and when they disagree it names both and stops instead of proceeding against the wrong binary.

### Step 2 — verify and repair

This is the main line, and the one that runs in every host.

When step 1 installed or upgraded anything, run `semlf install` — do not consult `doctor` first.
A non-identity artifact can be stale while `doctor` still exits 0,
so an upgrade is repaired on the strength of having happened, not on a health check that cannot see it.

Otherwise run `semlf doctor` and classify what it reports.
Exit 0 means healthy, and the skill moves to step 3.
A failure naming a payload that is missing, stale, or pointing at an old checker path is repairable:
run `semlf install --dry-run`, show the user the planned writes verbatim, and apply after agreement.
Every other failure — replay failure, unreadable or malformed `hooks.json`, the unconditional Windows case —
is surfaced to the user unrepaired, because re-running install does not address it and may refuse outright.

Applying uses `semlf install --yes`.
The user's agreement was obtained in conversation,
and install's own prompt cannot be reached from a non-interactive agent shell;
`--yes` carries the agreement the skill already holds, and is never used to skip asking.
Re-run `semlf doctor` afterward and report the result.

### Step 3 — project configuration

The only per-project artifact is `.semlf.ini`, described by
[ADR-0012](../../decisions/0012-project-config-is-one-ini-file.md) and
[ADR-0017](../../decisions/0017-experimental-wrap-also-lives-in-ini.md).
The skill offers to write one, asking about `long-limit`, `exclude`, and `experimental-wrap`.

It writes the file only after showing its exact content and getting agreement,
and when a `.semlf.ini` already exists it shows a diff first and never silently replaces it.
Since `long-limit` defaults to 120 already, "no file at all" stays a valid outcome the skill is happy to leave in place.

`exclude` carries its own restriction, and the skill states it.
An agent never authors an `exclude` line on its own authority (ADR-0010's principle, restated in the README):
excludes suppress discovery, so the skill may transcribe an exclusion the user dictates,
and may never propose one to make a finding go away.

## 2. Model invocation: a deliberate divergence

`setup-matt-pocock-skills` sets `disable-model-invocation: true`, so only a human can trigger it.
This skill does **not** set that flag, and the reason is the point of the whole spec.

The improvisation this skill exists to prevent happens exactly when a user says "install semlf for me" in prose.
A skill the model cannot invoke is not loaded at that moment, and the agent improvises anyway.

The risk that flag guards against — an agent installing software mid-task on its own initiative — is handled by two other means instead.
The `description` is scoped to an explicit user request rather than to a detected condition,
so "the user asked me to set up semlf" matches and "I noticed semlf is missing" does not.
And every step that installs or writes is gated on showing the exact command or content and getting agreement,
so an unwanted invocation still writes nothing.

Model invocation is a fuzzy trigger, though, and section 3's command file is the deterministic one beside it.

## 3. Distribution: one source, one row per target

Every destination renders from the single source `skills/setup-semlf/SKILL.md`.
No target reads another target's files, so no install can produce a skill referencing something it did not write.

| Host | Destination | Owner |
|---|---|---|
| Claude Code | the plugin's own `skills/setup-semlf/SKILL.md` | none — the marketplace ships it |
| Codex CLI | `~/.agents/skills/setup-semlf/SKILL.md` | `codex` |
| opencode | `~/.config/opencode/skills/setup-semlf/SKILL.md` | `opencode` |
| opencode | `~/.config/opencode/commands/setup-semlf.md` | `opencode` |

Claude Code needs no installer change:
the plugin exposes the skill automatically, as it already does for `skills/semantic-linefeeds/SKILL.md`.

The other three are new registry rows with matching `manifest.KNOWN` entries.
They must also be added to the hard-coded list `status` walks,
which does not pick up new rows on its own.

The command file is a delegation, not a copy.
Its template says to load and follow the `setup-semlf` skill and nothing else,
so the procedure has exactly one home and the command cannot drift away from it.
It exists because a skill in opencode is reachable only when the model elects to call the skill tool,
and a user typing `/setup-semlf` deserves an answer that does not depend on that election.

### Why per-target rows instead of one shared destination

An earlier draft of this spec put both skills at `~/.agents/skills` under a new "neutral" owner installed for any target.
Both external reviews independently found the same defect, and it is fatal to that shape.

The installed judgment skill is rendered with absolute references to the neutral checker and README,
and those two rows are owned by `codex`.
Neutralizing only the skill rows would make `semlf install opencode` write a skill pointing at files that install never wrote.
Worse, `installed_consumers()` treats the presence of that skill file as evidence that Codex is installed,
so an opencode-only machine would invent a Codex consumer and then fail `doctor` for the missing Codex-owned payloads.

Per-target rows avoid the dependency instead of managing it.
They also cost less: no owner semantics change, so `plan_install`, the `doctor` and `status` comparisons,
`installed_consumers()`, and the target-branched `uninstall` all keep working unchanged.

## 4. Deferred: neutral ownership and the opencode judgment layer

Discharging [ADR-0006](../../decisions/0006-judgment-layer-for-every-agent.md) for opencode is still worth doing,
and it is deliberately not done here.
The setup skill can reach opencode users without it,
so bundling the two would delay the cheaper half behind the harder one.

That work is its own spec, and it changes ADR-0016's owner model, so it carries a decision record.
`docs/decisions/README.md` states that an accepted record is not edited and that a changed decision supersedes the old one,
so it lands as ADR-0018 superseding ADR-0016 in part rather than as an amendment.

It has to answer all of the following, which is why it is not a paragraph in this spec:

- Whether the checker and README become neutral too, or whether skills stop referencing them by absolute path.
- How "a shared skill is present" stops implying "Codex is installed" in `installed_consumers()`.
- Last-consumer uninstall: today `uninstall codex` would remove a shared skill that opencode still needs,
  and an opencode-only uninstall would leave shared skills behind.
- Migration for machines installed before the change, where a re-run makes a new file appear in `$HOME`.

## 5. Safety rules the skill states explicitly

- **Never pass `--force` on the skill's own authority.**
  `--force` overwrites a user's file.
  That is a heavier act than adding a suppression directive,
  which this project already forbids an agent from doing on its own authority.
  On a refusal the skill shows the diff between installed and incoming content and asks.
- **Never author an `exclude` line.**
  Excludes suppress discovery, so they are the user's call to make and the skill's only to transcribe.
- **Never use `sudo`.**
  The skill also never sets `SEMLF_HOME`, `PYTHONUSERBASE`, or a manager's destination override to place files outside the home.
  Those variables are the reason "installs inside the home" is a rule the skill follows rather than a property it can verify.
- **Never hand-edit `hooks.json`, a skills directory, or any published payload.**
  Every artifact the CLI owns is written by a `semlf` subcommand,
  so provenance stays accurate and `uninstall` keeps working.
  The two writes that are *not* CLI-owned are named on purpose:
  the bootstrap rung, which runs a package manager, and `.semlf.ini`, which belongs to the project rather than to install.
- **Never move or delete a file that blocks an install.**
  A pre-existing backup blocking `--force` is the user's file and the user's decision.

## Testing

- `python3 -m pytest tests/ -q` stays green, including the new `KNOWN`-versus-registry coupling test.
- Per-target install coverage:
  `semlf install codex` alone writes the Codex skill,
  and `semlf install opencode` alone writes the opencode skill and command.
  Neither target's install references a file the other target owns.
- `status` reports all three new artifacts, and `uninstall` removes each target's own.
- A stale-artifact test: after a version bump, an installed setup skill at old bytes is repaired by re-running install,
  and the test records that `doctor` alone does not report it.
- Non-TTY application: with agreement already obtained, `semlf install --yes` applies where bare `semlf install` exits 1.
- Shadowing: an existing zipapp at `~/.local/bin/semlf` ahead of a newly installed shim is detected and reported, not used.
- `.semlf.ini` handling: an existing file is preserved on decline, a malformed file is surfaced rather than overwritten,
  and no path produces an agent-authored `exclude`.
- `python3 scripts/check_linefeeds.py --file skills/setup-semlf/SKILL.md docs/plans/active/2026-08-15-setup-skill-design.md` reports no `fused` or `wrap` findings.
- Manual: on a machine with the CLI absent, the ladder's first rung installs and `semlf doctor` passes;
  on this machine, where a stale install already exists, step 2 reproduces the repair path.

## Out of scope

- A `semlf setup` CLI subcommand.
  The bootstrap cannot live in the tool it installs, and repair is already `semlf install`.
- Publishing `install.sh` as a payload.
  The curl door is the delivery mechanism for it; a stale local copy would be worse than none.
- Any change to how `semlf install` preflights, refuses, backs up, or records provenance.
  This spec adds rows to the registry and entries to the lists `status` walks;
  it changes no lifecycle semantics, and no existing row's owner or destination.
- The neutral-owner work described in section 4, which is deferred to its own spec and decision record.
