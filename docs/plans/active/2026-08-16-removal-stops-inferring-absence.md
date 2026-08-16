# Removal stops inferring absence — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended)
> or `superpowers:executing-plans` to implement this plan task by task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Date:** 2026-08-16
**Status:** implemented, unreleased
**Branch:** `fix/removal-stops-inferring-absence`, cut from `main` at `e512200`.

> **One correction the execution earned.**
> Task 1 named four tests to update.
> Seventeen failed, in two files the plan never mentioned:
> five in `tests/test_installer.py`,
> where `--uninstall --codex` was the fixture that produced a refusal from the shared skill leg,
> and the rest in `tests/test_semlf_install.py`.
> Every one was the same shape — a command naming one target that has to name both to reach the skills —
> so the plan's design held and only its enumeration was short.

**Goal:**
Stop `semlf uninstall` from deleting the shared skills on evidence it cannot actually reach,
and stop it from stranding a record it can no longer name.

**Architecture:**
The shared skills are removed only when the request names every agent target,
so no predicate has to prove that an unnamed target is absent.
`target_present` — the predicate that had to prove it, and could not for a Codex under a non-default `CODEX_HOME` —
is deleted rather than extended.
Retention without reporting is how a machine silently accumulates skills nobody reads,
so `status` names an unconsumed shared skill and prints the command that removes it.
Separately, the removal door projects retired records the way the install door already does,
so a machine that upgraded from 0.7.0 is provable rather than merely byte-identical,
and the retired record leaves with the file it proved.

**Tech stack:** Python 3.9+, stdlib only in the core; `pytest` for the suite; `ruff` for lint and format.

**Design:** this file is both design and plan — approved in conversation on 2026-08-16.
The two shape decisions it rests on were made explicitly:
removal drops the automatic absence inference rather than gaining new provenance for the codex hook,
and naming every agent target is the deliberate removal channel rather than a new `--all` flag.

## Why the codex hook was never recorded

The obvious fix for the `CODEX_HOME` gap — "give the codex hook a recorded row" — does not fit this codebase,
and the reason is worth stating so nobody re-proposes it.

The codex hook is not a file this kit owns.
It is one entry merged into the user's own `hooks.json`,
which [ADR-0014](../../decisions/0014-lifecycle-verbs-and-the-provenance-manifest.md) names as a shared file this kit never deletes.
A record is `{path, sha256, version}` where the digest covers the whole file,
and the user's own hooks live in that same file,
so no whole-file digest stays valid.
Ownership of the entry is established structurally instead, by `manifest.parse_managed_codex_hook`.

Recording it would therefore mean a record whose `sha256` means something different from every other record's,
which `manifest.load`, `classify_entry`, `doctor`'s provenance loop and `status` would all have to learn.
Deleting the predicate costs nothing and closes the same gap.

## Global constraints

- The core stays one file: `scripts/check_linefeeds.py`, Python 3.9+, stdlib imports only.
  This plan does not touch it.
- Precision over recall: a refusal is acceptable, a wrong removal is a bug.
- Every touched Markdown file must pass `python3 scripts/check_linefeeds.py --file <file>` with zero `fused` and zero `wrap` findings.
- Commits follow Conventional Commits: header ≤ 50 chars, body lines ≤ 72 chars,
  no attribution trailers, no plan or review jargon in the message.
- Run `python3 -m pytest tests/ -q` before every commit.
  `bun test adapters/opencode/` is not needed: no adapter TypeScript changes here.

## File structure

| File | Responsibility in this change |
|---|---|
| `cli/semlf/lifecycle.py` | `plan_shared_removal` gains the naming rule and the projection; `target_present` and `_probe` are deleted; `plan_remove_file` accepts a snapshot and aliases; `status_command` names unconsumed skills. |
| `tests/test_lifecycle.py` | The nine `target_present` assertions go; the two `hooks.json` tests re-point at `installed_consumers`. |
| `tests/test_semlf_install.py` | The removal rule's behavior tests, including the case the deleted predicate existed for. |
| `tests/test_migration.py` | The pre-change machine's uninstall stops needing `--force` and stops stranding a record. |
| `CHANGELOG.md` | The `[Unreleased]` entry describing the old rule is rewritten. |

---

## Task 1: Removal requires naming every agent target

**Files:**

- Modify: `cli/semlf/lifecycle.py:1601-1646` (`plan_shared_removal`)
- Modify: `cli/semlf/lifecycle.py:1042-1114` (delete `_probe` and `target_present`)
- Modify: `tests/test_lifecycle.py:666-738`
- Modify: `tests/test_semlf_install.py`

**Interfaces:**

- Consumes: `AGENT_TARGETS = ("codex", "opencode")` at `cli/semlf/lifecycle.py:580`.
- Produces: `plan_shared_removal(targets, force, planned, refusals)` keeps its signature.
  `target_present` and `_probe` no longer exist; nothing outside this task referenced them
  (`plan_shared_removal` was `target_present`'s only caller, and `_probe`'s only caller was `target_present`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_semlf_install.py`:

```python
def test_naming_one_agent_target_never_removes_the_shared_skills(tmp_path):
    """Removal acts on what the request names, never on what it infers about the rest.

    The old rule removed the skills as soon as every unnamed target looked absent.
    Looking absent is not being absent, and the file is gone either way.
    """
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "opencode"], env).returncode == 0
    assert skill.is_file()

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert skill.is_file(), "a request naming one agent target removed the shared skill"


def test_naming_every_agent_target_removes_the_shared_skills(tmp_path):
    """The deliberate channel, and the only one."""
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    setup_skill, _ = setup_skill_paths(tmp_path)
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "opencode"], env).returncode == 0

    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not skill.exists()
    assert not setup_skill.exists()


def test_a_codex_under_another_home_keeps_its_skills(tmp_path):
    """The case the deleted predicate could not decide.

    Codex installs under one CODEX_HOME and is then operated without that variable,
    so its hook entry is nowhere this environment looks.
    The old rule read that as absent and removed the skills that Codex still reads.
    """
    env = isolated_env(tmp_path)
    codex_env = dict(env, CODEX_HOME=str(tmp_path / "elsewhere-codex"))
    assert run_semlf(["install", "codex"], codex_env).returncode == 0
    assert run_semlf(["install", "opencode"], env).returncode == 0
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert skill.is_file()

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert skill.is_file(), "removed a skill a Codex under another home still reads"
```

- [ ] **Step 2: Run them to verify they fail**

Run:

```bash
python3 -m pytest tests/test_semlf_install.py -q \
  -k "naming_one_agent_target or naming_every_agent_target or another_home"
```

Expected: `test_naming_one_agent_target_never_removes_the_shared_skills` and
`test_a_codex_under_another_home_keeps_its_skills` FAIL on the `skill.is_file()` assertion,
because the old rule finds no other target present and removes the file.
`test_naming_every_agent_target_removes_the_shared_skills` passes already —
it is the regression guard for the channel that must keep working.

- [ ] **Step 3: Replace the rule**

In `cli/semlf/lifecycle.py`, replace the body and docstring of `plan_shared_removal` with:

```python
def plan_shared_removal(targets, force, planned, refusals):
    """Remove the shared skills only when this request names every agent target.

    The rule is what the request says, never what the machine seems to say.
    The predicate this replaced asked whether each unnamed target was still present,
    and answering that needs evidence the current environment cannot always reach:
    a Codex installed under one CODEX_HOME and operated without it is nowhere this process looks,
    and reading that as absent removed the skills a live installation still uses.
    Naming every target is a statement the user makes, so nothing has to be inferred.

    The cost is retention, which is the safe direction and the one this project's principle asks for.
    A machine that only ever had opencode keeps its skills until the user names both targets,
    and `status` names them and prints that command so the user is not left guessing.

    A request naming no agent target still removes no shared skill;
    that case is subsumed here, since it cannot name every one of them.
    """
    if not all(t in targets for t in AGENT_TARGETS):
        return
    destinations = payload_destinations()
    for name, label in (("skill", "skill"), ("setup-skill", "setup skill")):
        plan_remove_file(
            label,
            destinations[name],
            name,
            force,
            planned,
            refusals,
            prune_parent=True,
        )
```

Then delete `_probe` (`cli/semlf/lifecycle.py:1042-1056`) and
`target_present` (`cli/semlf/lifecycle.py:1059-1114`) entirely, docstrings included.

- [ ] **Step 4: Update the tests that pinned the deleted predicate**

In `tests/test_lifecycle.py`, delete these six tests outright —
they assert the behavior of a function that no longer exists:

- `test_a_never_installed_target_is_absent`
- `test_a_present_destination_makes_a_target_present`
- `test_a_record_outside_the_current_environment_still_counts`
- `test_a_record_whose_file_is_proven_gone_counts_absent`
- `test_an_unresolvable_destination_counts_present`
- `test_a_foreign_hooks_json_leaves_codex_absent`

Replace the two `hooks.json` tests with versions that pin the reporting predicate,
which is what those files still govern:

```python
def test_an_unreadable_hooks_json_leaves_codex_out_of_the_consumers(home, capsys):
    """The reporting predicate fails closed, and that is now only a warning's problem.

    Nothing decides a removal from this answer any more,
    so failing closed to absent costs a report rather than a file.
    """
    hooks = manifest.codex_home() / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    hooks.write_text("{ not json", encoding="utf-8")
    assert lifecycle.installed_consumers() == set()


def test_a_foreign_hooks_json_is_not_a_codex_consumer(home, capsys):
    """A consumer is this kit's own entry, not any hooks.json at all."""
    hooks = manifest.codex_home() / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    hooks.write_text('{"hooks": {"PostToolUse": []}}', encoding="utf-8")
    assert lifecycle.installed_consumers() == set()
```

In `tests/test_semlf_install.py`, update the three tests whose commands no longer reach removal.

`test_uninstall_removes_the_setup_artifacts_each_target_owns` —
change its second command from `["uninstall", "codex"]` to `["uninstall", "codex", "opencode"]`,
and replace its docstring's last line with:

```python
    a target's uninstall removes the artifacts that target owns,
    and the shared skill leaves only when the request names every agent target.
```

`test_naming_an_agent_target_still_collects_the_orphaned_skills` — rename to
`test_naming_every_agent_target_still_collects_the_orphaned_skills`,
change its command to `["uninstall", "codex", "opencode"]`,
and replace its docstring with:

```python
    """The rule costs no convergence.

    A machine where nothing is installed still gives up the skills it once wrote,
    as long as the request names every agent target.
    """
```

`test_an_uninstalled_opencode_machine_reports_its_orphaned_payloads` —
the skills are now retained alongside the payloads.
Replace its docstring and its skill assertion with:

```python
    """Everything shared is retained and reported now, the skills included.

    The skills used to leave with the last consumer.
    That rule rested on proving the other target absent, which is not always reachable,
    so retention is the answer and `status` is what keeps it from being silent.
    """
```

```python
    assert skill.is_file(), "the skills are retained until the user names every target"
```

Two more tests keep passing but state a reason that is no longer the operative one.
Update the docstring of `test_an_unreadable_hooks_json_retains_the_shared_skills` to:

```python
    """Retention no longer depends on reading this file at all.

    The request named one target, so the shared skills stay whatever hooks.json says.
    """
```

and rename `test_a_target_recorded_under_another_config_home_counts_present` at `tests/test_semlf_install.py:719` to `test_a_target_recorded_under_another_config_home_keeps_the_skills`, giving it this docstring:

```python
    """A request naming one target leaves the shared skills alone.

    This machine's opencode lives where this environment does not look,
    which used to be the interesting part; it no longer decides anything.
    """
```

- [ ] **Step 5: Run the suite**

Run: `python3 -m pytest tests/ -q`
Expected: all pass, with the three new tests from Step 1 included.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add cli/semlf/lifecycle.py tests/test_lifecycle.py tests/test_semlf_install.py
git commit -F - <<'EOF'
fix(uninstall): remove shared skills only when named

The shared skills left as soon as every unnamed target looked absent.
Looking absent is not being absent: a Codex installed under one
CODEX_HOME and operated without it is nowhere the running process
looks, so its skills were removed while it was still reading them.

Removal now acts on what the request names. Naming every agent target
is a statement the user makes, so nothing has to be inferred, and the
predicate that had to prove absence is deleted rather than extended.
Retention is the safe direction; status names what is left.
EOF
```

---

## Task 2: Status names an unconsumed shared skill

**Files:**

- Modify: `cli/semlf/lifecycle.py:1272-1299` (the integration-artifact loop in `status_command`)
- Modify: `tests/test_semlf_install.py`

**Interfaces:**

- Consumes: `installed_consumers()` at `cli/semlf/lifecycle.py:1015`,
  `expected_by(row, consumers)` at `cli/semlf/lifecycle.py:596`,
  `registry.BY_ID`, and `AGENT_TARGETS`.
- Produces: one new stdout line; no new function.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_semlf_install.py`:

```python
def test_status_names_the_skills_no_agent_reads_any_more(tmp_path):
    """Retention without reporting is how a machine accumulates skills nobody reads.

    The removal rule keeps the skills until the user names every agent target,
    so status has to say they are there and print the command that takes them.
    """
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "opencode"], env).returncode == 0
    assert run_semlf(["uninstall", "opencode"], env).returncode == 0

    r = run_semlf(["status"], env)
    assert r.returncode == 0, r.stderr
    assert "skills: no agent reads these any more" in r.stdout
    assert "semlf uninstall codex opencode" in r.stdout
    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert str(skill) in r.stdout


def test_status_does_not_call_the_skills_orphaned_while_an_agent_reads_them(tmp_path):
    """The line is about having no consumer, not about being installed."""
    env = isolated_env(tmp_path)
    assert run_semlf(["install", "opencode"], env).returncode == 0

    r = run_semlf(["status"], env)
    assert r.returncode == 0, r.stderr
    assert "skills: no agent reads these any more" not in r.stdout
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_semlf_install.py -q -k "status_names_the_skills or orphaned_while_an_agent"`
Expected: `test_status_names_the_skills_no_agent_reads_any_more` FAILS on
`assert "skills: no agent reads these any more" in r.stdout` — status prints only the classifier state line today.
The second test passes already; it is the guard against reporting the line on a healthy machine.

- [ ] **Step 3: Add the report**

In `cli/semlf/lifecycle.py`, in `status_command`, initialise a list beside `leftover_paths`
(which is declared at `cli/semlf/lifecycle.py:1229`):

```python
    orphaned_skills = []
```

Then, inside the integration-artifact loop, after the line that prints the verdict
(`print(f"{label}: {verdict.state} ({dest})")`), add:

```python
        # A shared row with no consumer is a skill advertised to every model that scans the root.
        # Removal retains it on purpose, so this line is what keeps the retention from being silent,
        # and it names the one command that takes it.
        row = registry.BY_ID[name]
        if row.owner == "shared" and not expected_by(row, consumers):
            orphaned_skills.append(dest)
```

Then, immediately before the existing `if leftover_paths:` block at `cli/semlf/lifecycle.py:1295`, add:

```python
    if orphaned_skills:
        listed = ", ".join(str(p) for p in orphaned_skills)
        wanted = " ".join(AGENT_TARGETS)
        print(
            f"skills: no agent reads these any more; "
            f"`semlf uninstall {wanted}` removes {listed}."
        )
```

The wording is deliberate, and the two lines are meant to be read together.
An orphaned machine prints this line next to the existing payloads line at `cli/semlf/lifecycle.py:1295`,
which opens "payloads: no remaining consumer" and ends "remove them by hand if unwanted".
Repeating "no remaining consumer" here would make one report look like it says the same thing twice
while offering two different remedies.
The split that matters is which of them a command can take:
a verb removes the skills, and nothing but a hand removes the payloads,
so each line leads with its own remedy.

- [ ] **Step 4: Run the suite**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add cli/semlf/lifecycle.py tests/test_semlf_install.py
git commit -F - <<'EOF'
feat(status): name the skills no agent reads any more

Removal keeps the shared skills until the request names every agent
target, so a machine can now carry a skill with no consumer left. A
skill sitting in the shared root is advertised to every model that
scans it, and one nobody asked for is worse than one nobody removed.

Status names such a skill and prints the command that removes it, the
way it already reports the retained checker and README.
EOF
```

---

## Task 3: The removal door projects retired records

**Files:**

- Modify: `cli/semlf/lifecycle.py:1326-1398` (`plan_remove_file`)
- Modify: `cli/semlf/lifecycle.py` (`plan_shared_removal`, as rewritten in Task 1)
- Modify: `tests/test_migration.py:220-243`

**Interfaces:**

- Consumes: `project_retired(snapshot, destinations)` at `cli/semlf/lifecycle.py:702`,
  which returns `(projected_snapshot, aliases)`
  where `aliases` maps a live row id to the list of retired names proving it;
  `RetiredRecordConflict` at `cli/semlf/lifecycle.py:698`;
  `manifest.classify_entry(entry, path)`; `_forget_note(dest, name)`.
- Produces: `plan_remove_file` gains two keyword arguments,
  `snapshot=None` and `aliases=()`.
  `snapshot=None` keeps the existing lookup-by-name behavior,
  so the opencode legs and the agentsmd leg need no change.

- [ ] **Step 1: Write the failing test**

Replace `test_uninstall_refuses_a_pre_rename_recorded_skill` in `tests/test_migration.py:220` with this test,
which asserts the opposite outcome:

```python
def test_uninstall_projects_a_pre_rename_recorded_skill(tmp_path):
    """The upgrade boundary must not need --force, and must not strand the record.

    The old machine's proof sits under the retired `codex-skill` name.
    Reading the live name only, removal fell back to comparing bytes against the
    current rendering, which refuses the moment a release changes the skill body.
    It also cleared a record that never existed and left the retired one naming a
    path it had just deleted, where nothing afterwards can read or name it.
    """
    env, hooks, skill = old_checkout_state(tmp_path)
    state = tmp_path / "state" / "semlf" / "artifacts"
    assert (state / "codex-skill.json").is_file()

    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not skill.exists()
    assert not (state / "codex-skill.json").exists(), "the retired record was stranded"

    data = json.loads(hooks.read_text(encoding="utf-8"))
    from semlf import manifest

    assert manifest.owned_codex_hooks(data) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_migration.py -q -k "projects_a_pre_rename"`
Expected: FAIL with exit code 1 and "content differs" on stderr.

The fixture is why that is the certain outcome rather than one of two.
`old_checkout_state` at `tests/test_migration.py:55` writes the skill to
`~/.agents/skills/semantic-linefeeds/SKILL.md` — the current `skill` row's own destination —
with a body rendered against checkout paths rather than the data root,
and records it under `codex-skill` with that path and that body's digest.
So the bytes cannot equal this build's rendering,
the live `skill` record does not exist,
and admission has nothing left to succeed on.

That same fixture is what makes the fix work:
the retired record's path resolves to the destination,
which is exactly the condition `project_retired` requires before it collects an alias.

- [ ] **Step 3: Let `plan_remove_file` take a snapshot and its aliases**

In `cli/semlf/lifecycle.py`, change the signature at line 1326 to:

```python
def plan_remove_file(
    label,
    dest,
    name,
    force,
    planned,
    refusals,
    prune_parent=False,
    snapshot=None,
    aliases=(),
):
    """Plan removal of one installer-owned file, or a refusal.

    Shared by the two shared skills and the opencode files.

    `snapshot` is the caller's one manifest snapshot when it has taken one,
    and None when the caller wants the record looked up by name.
    A caller that projected retired records must pass the projection:
    the live name has no record on a machine that upgraded from an older layout,
    so looking it up by name would refuse a file a retired record proves.

    `aliases` are the retired names that proved this destination.
    They are forgotten together with the live name, and only after the unlink succeeds,
    because a record cleared before the file goes leaves a file nothing can prove.
    """
```

Replace the admission line at `cli/semlf/lifecycle.py:1379`:

```python
            if current == rendered or manifest.classify(name, dest) == "managed":
```

with:

```python
            if snapshot is None:
                provenance = manifest.classify(name, dest)
            else:
                provenance = manifest.classify_entry(snapshot.get(name), dest)
            if current == rendered or provenance == "managed":
```

Replace the `_do` closure at `cli/semlf/lifecycle.py:1391-1396`:

```python
    def _do(dest=dest, name=name, prune_parent=prune_parent, aliases=tuple(aliases)):
        os.unlink(dest)
        notes = [_forget_note(dest, n) for n in (name,) + aliases]
        if prune_parent:
            _prune_empty_parent(dest)
        return next((note for note in notes if note is not None), None)
```

- [ ] **Step 4: Project on the removal door**

In `plan_shared_removal`, replace the body written in Task 1 Step 3 with:

```python
    if not all(t in targets for t in AGENT_TARGETS):
        return
    destinations = payload_destinations()
    try:
        snapshot, aliases = project_retired(manifest.load(), destinations)
    except RetiredRecordConflict as exc:
        # The install door refuses the same way rather than choosing between two digests for one file.
        refusals.append(str(exc))
        return
    for name, label in (("skill", "skill"), ("setup-skill", "setup skill")):
        plan_remove_file(
            label,
            destinations[name],
            name,
            force,
            planned,
            refusals,
            prune_parent=True,
            snapshot=snapshot,
            aliases=aliases.get(name, ()),
        )
```

Add this paragraph to `plan_shared_removal`'s docstring, after the existing text:

```python
    The snapshot is projected, as the install door's is.
    A machine that upgraded from an older layout proves these files under a retired name,
    and reading the live name alone would refuse a file this kit demonstrably wrote
    the moment a release changes the skill body.
    The retired names leave with the file they proved.
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_migration.py -q -k "projects_a_pre_rename"`
Expected: PASS.

Run: `python3 -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add cli/semlf/lifecycle.py tests/test_migration.py
git commit -F - <<'EOF'
fix(uninstall): project retired records before removing

Removal read the live record name only. A machine that upgraded from
an older layout proves the shared skills under a retired name, so
admission fell back to comparing bytes against the current rendering
— which stops holding the moment a release changes the skill body.

It also cleared a record that never existed and left the retired one
naming the path it had just unlinked, where nothing afterwards can
read or name it. The removal door now projects the same way the
install door does, and the retired names leave with the file.
EOF
```

---

## Task 4: Rewrite the release note the change invalidates

**Files:**

- Modify: `CHANGELOG.md:40-44`

**Interfaces:** none — prose only.

- [ ] **Step 1: Replace the entry**

The `[Unreleased]` section carries an entry describing the rule this plan replaces.
It is unreleased, so it is rewritten in place rather than corrected in a later entry.

Replace `CHANGELOG.md:40-44`:

```markdown
- **The skill is removed only when the last agent that reads it goes.**
  Because one copy now serves both agents, uninstalling one of two leaves it in place for the other,
  and it is taken only by the uninstall that leaves you with no agent using it.
  The checker and the README are always kept, as before;
  `semlf status` lists them if you want them gone.
```

with:

```markdown
- **The skill is removed only when you ask for both agents by name.**
  One copy now serves both agents, so uninstalling one of them leaves it in place for the other.
  `semlf uninstall codex opencode` is what takes it,
  and nothing else does — including on a machine where you only ever used one of them.
  That is deliberate: `semlf` cannot always see a Codex you installed somewhere unusual,
  and it would rather leave you a file you can delete than delete one you were still using.
  The checker and the README are always kept, as before,
  and `semlf status` now lists the skills too when no agent is left to read them.
```

- [ ] **Step 2: Check the prose**

Run: `python3 scripts/check_linefeeds.py --file CHANGELOG.md`
Expected: zero `fused` and zero `wrap` findings.
Any `long` finding on a line this task did not write is left alone.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: restate how the shared skill is removed"
```

---

## Task 5: Full validation

**Files:** none modified.

- [ ] **Step 1: Run everything**

```bash
python3 -m pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
python3 scripts/check_linefeeds.py --file CHANGELOG.md docs/plans/active/2026-08-16-removal-stops-inferring-absence.md
```

Expected: the suite passes with no failures;
`ruff check` prints `[]`;
`ruff format --check` reports every file already formatted;
the checker reports zero `fused` and zero `wrap`.

- [ ] **Step 2: Confirm the deleted predicate is really gone**

```bash
grep -rn "target_present\|_probe" cli/ scripts/ tests/ --include=*.py
```

Expected: no matches.
A match in `tests/` means a test was updated to keep compiling rather than deleted.

- [ ] **Step 3: Confirm the removal channel by hand**

```bash
grep -rn "uninstall codex opencode" CHANGELOG.md cli/semlf/lifecycle.py
```

Expected: the changelog entry from Task 4,
and the status line from Task 2 rendered from `AGENT_TARGETS` rather than typed as a literal.
The status line will not match this grep, because it builds the command from the tuple —
confirm by reading `status_command` instead, and treat a literal there as a defect to fix.

## Follow-ups this plan does not do

- `semlf uninstall` still requires a named target and has no `--all`.
  Naming every target was chosen over adding a flag; revisit only if users ask.
- `doctor`'s competing-copy advice is fixed on the separate branch
  `fix/doctor-competing-copy-advice`, which is independent of this one.
  Both touch `cli/semlf/lifecycle.py` and `cli/semlf/doctor.py` in different functions,
  so they merge without conflict in either order.
- The version bump and the `[Unreleased]` heading collapse belong to the release, not here.
