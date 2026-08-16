# ADR-0019: One skill in the shared root, and no links anywhere else

**Status:** accepted
**Date:** 2026-08-15
**Supersedes:** [ADR-0018](0018-skills-ship-per-target.md) —
it ruled that a skill ships once per target, to a root that target owns.
That rule is overturned here, and its three objections are answered below rather than set aside.
**Amends:** [ADR-0016](0016-one-entry-point-and-the-payload-registry.md) —
a registry row's `owner` may be `shared`, meaning any selected agent target.
Everything else about the registry is unchanged.
**Amended:** 2026-08-16 —
the conservative removal predicate below is withdrawn, and with it the last-consumer rule.
It could not see a Codex installed under a non-default `CODEX_HOME` and operated without that variable,
because the codex hook is an entry merged into the user's own `hooks.json` and no row records it,
so it read a live Codex as absent and authorised deleting the skills that Codex was still reading.
Removal now takes the shared skills only when the request names every agent target,
which is a statement the user makes rather than a fact the tool infers,
and the predicate is deleted rather than extended.
The reporting predicate is untouched and still governs `status` and `doctor`;
`status` now also names a shared skill nothing here reads
and offers the removal command conditionally, since it reads the same partial evidence.

This record states decisions.
The mechanisms that carry them out —
which path comparison each guard uses, how migration projects a retired record, the removal plan's order —
live in the design document, because they are expected to keep moving as they meet tests.

## Context

`~/.agents/skills` is read by Codex CLI and by opencode.
Under ADR-0018 the judgment skill and the setup skill were each published twice,
once there and once under `$XDG_CONFIG_HOME/opencode/skills`,
with the two renderings citing different checker paths.

Three things followed, and all of them trace to the second destination.

A user who points one agent's skills root at a shared skill store —
a common arrangement for someone running several agents, and the one `mattpocock/skills` produces —
collapses two rows onto one inode, and install refuses the whole request rather than proceeding.

A copy in opencode's own root competes with the shared one for the same skill name,
and usually wins, so a machine that stops receiving updates for that copy keeps loading an old skill.

And every dual-agent machine carries two identical setup skills from one source, indefinitely.

## Decision

**A skill is published once, to `~/.agents/skills`.**
Nothing is written under any agent's own skills root.

This removes the second destination instead of managing it.
One row cannot collide with itself,
so a root symlink, a per-skill symlink, an intermediate symlink, a bind mount, or a shared root
that is itself a symlink all resolve to the same single destination and none of them needs a rule.

Four decisions follow from it.

**`checker` and `readme` become `shared` rows.**
One shared skill body can cite one checker and one README,
so the payloads it cites must exist for any target that install selects.
opencode keeps its own checker beside its plugin, which serves a different consumer:
the plugin resolves `./check_linefeeds.py` through `import.meta.url`.

**semlf creates no symlinks in any agent's own skills root.**
An earlier draft did, following `mattpocock/skills`, to occupy the name that wins.
It was dropped on measurement:
skill precedence is a race between paths rather than a published rule,
both paths would have resolved to the same bytes,
and each link costs a duplicate-name warning per session on any machine whose roots are not already joined.

**Codex is inferred from its hook entry, and deletion is authorised by a different predicate.**
Inferring Codex from the presence of a skill file was correct while that file was Codex's alone.
It is now shared, so that inference would invent a Codex consumer on an opencode-only machine.
The reporting predicate is not reused for removals:
a predicate that fails closed to "absent" is harmless when it produces a warning
and destructive when it authorises an unlink,
so a second, conservative predicate answers that question and every ambiguity retains.

*Withdrawn by the 2026-08-16 amendment.*
The reasoning above holds and is the reason the second predicate is gone rather than fixed:
conservatism is not reachable when the evidence is,
so no predicate authorises the delete now.

**Shared skills are removed when the last consumer goes; `checker` and `readme` are retained and reported.**
The asymmetry is about behavior.
A checker left behind does nothing until something calls it.
A skill left behind is advertised to every model that scans the root,
and the checker path in its body may by then point at nothing.

*Amended 2026-08-16.*
The asymmetry survives, the trigger does not:
the skills leave when the request names every agent target, not when the last consumer goes,
and `status` names them meanwhile so retention does not become silent accumulation.

## Answering ADR-0018

**"It installs a skill that references files the install never wrote."**
True while the checker and README were Codex's.
ADR-0018 considered making them neutral and rejected it,
because they would install for an agent that has its own copy beside its plugin and no use for a second.
That reasoning assumed the per-target skills it was defending.
With one shared skill the shared copies have exactly one consumer, that skill,
and the copy beside the plugin serves a different one.
Two copies, two consumers.

**"It corrupts consumer detection."**
It did, through the skill-file inference that existed to protect payloads Codex owned.
Those payloads are shared now, so the inference is removed rather than worked around.

**"It makes uninstall unresolvable."**
The refcounting it feared is one comparison, and it converges in either removal order.
What ADR-0018 did not foresee is that the comparison must be conservative rather than merely correct,
because it authorises a delete.
That is a constraint on the rule, not a reason it cannot exist.

*Amended 2026-08-16.*
The constraint turned out to be unsatisfiable, and the answer is smaller than either ADR imagined:
there is no comparison, because the user names the targets and nothing is refcounted at all.
ADR-0018's objection is still answered — uninstall resolves — just not by counting.

## Consequences

- An opencode-only machine now creates the shared payload root,
  and retains a checker and a README after uninstall, named by `status`.
  It previously uninstalled to nothing.
- Machines installed under ADR-0018 carry files that now compete with the shared copy.
  Install removes them, and refuses rather than guessing when it cannot prove it wrote them.
- The design depends on both targets reading `~/.agents/skills`.
  Codex and opencode 1.18.18 do, verified directly.
  An older opencode would lose the skill with no error, so a minimum version is documented.
- A project-level `.opencode/skill` or `.opencode/skills` copy usually wins over the shared root,
  by the same scan-order race that decides the global roots rather than by any published rule.
  That is a stated carve-out; nothing inspects those paths.
- `OPENCODE_DISABLE_EXTERNAL_SKILLS` turns off the scan the shared copy depends on.
  It is documented beside the version floor, for the same reason:
  both produce a machine that has lost the skill and reports nothing.
- `doctor` gains a check for a competing file at opencode's own skill path,
  which is the state that was previously invisible to every check it ran.

## Alternatives rejected

- **A skill per target, in a root that target owns** ([ADR-0018](0018-skills-ship-per-target.md)).
  Overturned above.
- **One copy plus a symlink in each agent's own root**, which is what `mattpocock/skills` does.
  Rejected on measurement rather than on principle;
  the reason it was attractive — owning the name that wins — turned out to describe a race,
  and both spellings resolved to the same bytes.
- **A skill body that resolves its checker at read time** instead of citing an absolute path.
  Rejected: it makes the skill depend on `semlf` being on `PATH`,
  which is the dependency the shared payload root exists to avoid,
  and it moves the cost into prose that no test can hold.
- **The checker published inside the skill directory**, cited relatively so it travels with the skill.
  Rejected: the Codex hook still needs the copy under the payload root,
  so a dual-agent machine would carry three checkers rather than two.
- **Unifying every same-file comparison in the codebase.**
  Rejected as scope: provenance identity and the removal guards ask different questions
  and fail closed in different directions, and they can disagree only where neither would destroy anything.
