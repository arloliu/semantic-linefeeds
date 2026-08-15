# ADR-0018: A skill ships once per target, never to a shared root

**Status:** accepted
**Date:** 2026-08-15
**Completes:** [ADR-0006](0006-judgment-layer-for-every-agent.md) —
it decided every agent receives the judgment layer "not only the one with a skill mechanism",
and recorded opencode's hand-copied skill as the exception of its day.
That exception outlived the installer that justified it;
this record is how it ends.
**Does not amend** [ADR-0016](0016-one-entry-point-and-the-payload-registry.md) —
its single-owner rows are left exactly as they are,
and the alternative that would have changed them is rejected below.

## Context

`semlf install opencode` published a plugin and a checker and no skill at all.
The hook told the model to load a judgment layer regardless,
because `_judgment_layer_present` answers `True` for the transport the opencode plugin declares,
so opencode users were pointed at a skill their install had never written.
[ADR-0006](0006-judgment-layer-for-every-agent.md) had already ruled that this is not acceptable.

The obvious repair was to notice that opencode reads `~/.agents/skills`,
the directory the Codex skill already occupies,
and to install one copy there for both agents under a new owner meaning "any agent".

That repair is wrong, and two independent external reviews found the same reason.

## Decision

**A skill is published once per target, to a root that target owns.**
Two agents that both read a directory do not share a file in it.

The judgment skill therefore installs twice:

| Target | Skill | Resolves its checker and README at |
|---|---|---|
| Codex CLI | `~/.agents/skills/semantic-linefeeds/SKILL.md` | the neutral data root |
| opencode | `$XDG_CONFIG_HOME/opencode/skills/semantic-linefeeds/SKILL.md` | opencode's own plugins directory |

Each rendering points only at files its own target installs.
This extends the rule `opencode-checker` already followed:
opencode keeps its checker beside its plugin rather than reading the neutral root,
so its integration stays whole when no other agent is installed.

## Why the shared root is wrong

**It installs a skill that references files the install never wrote.**
The rendered skill carries absolute paths to the checker and the README,
and the rows publishing those are owned by `codex`.
Selecting a shared skill for an opencode-only install would write a body pointing into a neutral root that install never creates.
Neutralizing the checker and README as well only moves the problem:
they would then install for an agent that has its own copy beside its plugin and no use for a second one.

**It corrupts consumer detection.**
`installed_consumers()` counts Codex as installed when the skill file is present,
deliberately, because that skill references the neutral payloads and they must not be downgraded to leftovers.
A shared file at that path makes an opencode-only machine report a Codex consumer,
and `doctor` then fails it for Codex payloads nobody installed.

**It makes uninstall unresolvable.**
Removal is per target.
One shared file forces a last-consumer rule — remove it only when no remaining target needs it —
which is refcounting across agents that can be installed and removed independently and out of order.
Per-target copies make the same question trivial:
each target removes what it wrote.

The cost is that two identical files exist on a machine with both agents.
That is the price, and it is small:
the bytes are one source in the registry, so they cannot drift,
and duplication buys independence in install, uninstall, detection, and repair alike.

## Consequences

- Adding an agent means adding rows, never widening an owner.
  The owner field keeps meaning exactly one target.
- A skill's body may only reference paths its own target installs.
  A skill that needs a payload gets that payload published into its target's own root.
- The judgment-layer probe gains opencode's skill location,
  so hook feedback names the layer when it is genuinely reachable and stays quiet when it is not.
- Machines installed before this record gain a skill file on their next `semlf install opencode`.
  It is a normal recorded artifact: preflighted, refused on conflict, removed by `uninstall`.

## Alternatives rejected

- **A neutral owner installed for any selected target.**
  Rejected for the three reasons above.
  It was the original plan for this work and did not survive review.
- **Teaching opencode's skill to read the neutral root.**
  Rejected: it makes an opencode-only install depend on payloads owned by another target,
  which is the dependency this record exists to remove.
- **Leaving opencode with the AGENTS.md snippet instead.**
  Rejected: [ADR-0006](0006-judgment-layer-for-every-agent.md) keeps the snippet for agents with no skill mechanism,
  and opencode has one.
