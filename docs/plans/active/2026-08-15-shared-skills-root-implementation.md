# Shared Skills Root Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL:
> use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish each skill once to `~/.agents/skills`, the root both Codex CLI and opencode already read, and remove the per-target copies that a user's symlink turns into a refusal.

**Architecture:** A registry row's `owner` gains the value `shared`, so `checker`, `readme` and the two skills publish for any selected agent target.
The `opencode-skill`, `opencode-setup-skill` and `opencode-readme` rows are deleted, and the two Codex-named skill rows are renamed to `skill` and `setup-skill`.
Machines installed under the old layout are migrated by carrying their retired provenance records onto the new row names and deleting the files that would otherwise compete with the shared copy.

**Tech Stack:** Python 3.9+, stdlib only, pytest.
No new dependency is introduced by any task in this plan.

**Source documents:**
[the design](2026-08-15-shared-skills-root.md) and [ADR-0019](../../decisions/0019-one-skill-in-the-shared-root.md).
Read the ADR first; it is shorter and it states which decisions are settled.

## Global Constraints

- `scripts/check_linefeeds.py` stays one file, Python 3.9+, stdlib imports only
  (`argparse collections configparser fnmatch json os re sys tempfile`).
  No task in this plan modifies it.
- `cli/semlf/` is stdlib-only too.
  `os.path.samefile` is stdlib and adds nothing.
- Every Markdown file this plan touches must pass
  `python3 scripts/check_linefeeds.py --file <file>` with zero `fused` and zero `wrap` findings.
- Commit messages: Conventional Commits, header ≤ 50 chars, body lines ≤ 72 chars.
  No `Co-Authored-By` and no other attribution trailer.
  No plan step numbers, review-round references, or `tmp/*` paths in any commit message.
- Precision over recall applies to install actions:
  a refusal is acceptable, silently writing over or deleting a user's file is a bug.
- The full suite `python3 -m pytest tests/ -q` must pass at the end of every task, not only at the end of the plan.
- `uv run ruff check .` and `uv run ruff format --check .` must pass before each commit.

## Verification Gap Carried Into This Plan

The external reviewer that found the deepest defects returned "not ready to implement" twice
and never delivered a third verdict.
Its four blockers were addressed in the design, and two other reviewers found no mechanism defects afterwards,
but none of them re-checked those four specifically.

They are therefore treated as unproven and are pinned by tests rather than by any reviewer's agreement.
Each appears below as a required test, named so it can be traced:

| Blocker | Task | Test |
|---|---|---|
| Collision ignores already-installed rows | 3 | `test_a_collision_assembled_across_two_requests_is_refused` |
| The removal predicate had no evidence domain | 6 | `test_a_target_recorded_under_another_config_home_counts_present` |
| `doctor` failed the joined root | 9 | `test_doctor_is_quiet_when_the_opencode_path_is_the_shared_file` |
| Retired-alias convergence | 4 | `test_two_retired_records_naming_one_file_converge` |

## File Structure

| File | Responsibility after this plan |
|---|---|
| `cli/semlf/manifest.py` | provenance records, destinations, and the `same_file` primitive; gains `RETIRED` and retired-name state access |
| `cli/semlf/registry.py` | the payload table; loses three rows, renames two, collapses two renderers into one |
| `cli/semlf/lifecycle.py` | selection, collision, legacy migration, the removal predicate, and both doors' plans |
| `cli/semlf/classify.py` | unchanged |
| `cli/semlf/doctor.py` | shared-row expectedness, and the new competitor check |
| `scripts/install.py` | help text, the compatibility export, and the retained-payload note |
| `tests/test_manifest.py` | `same_file` unit tests |
| `tests/test_registry.py` | row ids, owners, members, and the `KNOWN` coupling |
| `tests/test_semlf_install.py` | install and uninstall over the package door |
| `tests/test_migration.py` | pre-change machines, including both symlink topologies |
| `tests/test_doctor.py` | the competitor check |

---

### Task 1: The same-file primitive

Every later guard asks "would touching this path touch that file".
`os.path.realpath` cannot answer it through a bind mount, so this task adds the primitive the rest of the plan uses.

**Files:**
- Modify: `cli/semlf/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `manifest.same_file(a, b, missing=False) -> bool`.
  `a` and `b` are `str` or `Path`.
  Returns `True` when both exist and are the same file, by device and inode.
  Returns `missing` when either path does not exist, or cannot be inspected.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_manifest.py`:

```python
def test_same_file_is_true_for_one_path_twice(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x", encoding="utf-8")
    assert manifest.same_file(p, p) is True


def test_same_file_follows_a_symlink(tmp_path):
    target = tmp_path / "real.txt"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    assert manifest.same_file(link, target) is True


def test_same_file_is_true_for_a_hard_link(tmp_path):
    target = tmp_path / "real.txt"
    target.write_text("x", encoding="utf-8")
    hard = tmp_path / "hard.txt"
    os.link(target, hard)
    assert manifest.same_file(hard, target) is True


def test_same_file_is_false_for_two_distinct_files(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("x", encoding="utf-8")
    b.write_text("x", encoding="utf-8")
    assert manifest.same_file(a, b) is False


def test_same_file_returns_the_missing_default_when_a_side_is_absent(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x", encoding="utf-8")
    gone = tmp_path / "gone.txt"
    assert manifest.same_file(p, gone) is False
    assert manifest.same_file(p, gone, missing=True) is True
    assert manifest.same_file(gone, gone, missing=True) is True


def test_same_file_returns_the_missing_default_on_a_hostile_path(tmp_path):
    assert manifest.same_file(tmp_path / "a", "\x00bad") is False
```

`tests/test_manifest.py` already imports `manifest`.
Add `import os` at the top if it is not there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_manifest.py -k same_file -q`
Expected: FAIL, `AttributeError: module 'semlf.manifest' has no attribute 'same_file'`

- [ ] **Step 3: Write the implementation**

Add to `cli/semlf/manifest.py`, below `read_regular_bytes`:

```python
def same_file(a, b, missing=False):
    """Whether two paths name one file, by device and inode.

    `os.path.realpath` cannot answer this:
    a bind mount joins two paths it still reports as different,
    and every guard keyed on it would then admit a removal and unlink the shared copy.
    `os.path.samefile` compares st_dev and st_ino, so it is correct through symlinks,
    bind mounts, and hard links alike.

    It follows symlinks, unlike `read_regular_bytes`, which carries O_NOFOLLOW on purpose.
    Following is right here: the question is "are these one file",
    not "may I read this path safely".

    `missing` is the answer when either side does not exist or cannot be inspected.
    It has no safe default across callers —
    a removal guard that assumes "same" strands a legacy file forever,
    and one that assumes "different" can delete the shared copy —
    so every caller states its own.
    """
    try:
        return os.path.samefile(str(a), str(b))
    except (OSError, ValueError):
        # ValueError covers a NUL-carrying path, which raises rather than classifying.
        return missing
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_manifest.py -k same_file -q`
Expected: PASS, 6 tests

- [ ] **Step 5: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass, nothing else changed

- [ ] **Step 6: Commit**

```bash
git add cli/semlf/manifest.py tests/test_manifest.py
git commit -m "feat(manifest): add a device-and-inode same-file test

realpath cannot see through a bind mount, so two paths naming one file
read as different and a guard keyed on it would unlink the shared copy.
samefile compares st_dev and st_ino instead.

The missing-path answer is a parameter rather than a default: a removal
guard that assumes same strands a file forever, and one that assumes
different can delete the wrong one."
```

---

### Task 2: The `shared` owner and the selection rule

**Files:**
- Modify: `cli/semlf/registry.py` (the `checker` and `readme` rows)
- Modify: `cli/semlf/lifecycle.py` (`plan_install`, `status_command`)
- Modify: `cli/semlf/doctor.py` (`_payload_identity_check`)
- Test: `tests/test_registry.py`, `tests/test_semlf_install.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `lifecycle.selects(row, targets) -> bool`, the one selection test every consumer uses.
  `targets` is a collection of target names.
  Returns `True` when `row.owner` is in `targets`.
  Also returns `True` when `row.owner == "shared"` and `targets` names at least one agent target.

- [ ] **Step 1: Write the failing tests**

In `tests/test_registry.py`, change the owner map assertion:

```python
def test_owners_match_the_design_table():
    owners = {r.id: r.owner for r in registry.ROWS}
    assert owners == {
        "checker": "shared",
        "readme": "shared",
        "codex-hook-template": "codex",
        "codex-skill": "codex",
        "opencode-plugin": "opencode",
        "opencode-checker": "opencode",
        "opencode-readme": "opencode",
        "opencode-skill": "opencode",
        "codex-setup-skill": "codex",
        "opencode-setup-skill": "opencode",
        "opencode-setup-command": "opencode",
        "agentsmd-snippet": "agentsmd",
    }
```

Add to `tests/test_registry.py`:

```python
def test_selects_admits_a_shared_row_for_any_agent_target():
    shared = registry.BY_ID["checker"]
    assert lifecycle.selects(shared, ["codex"]) is True
    assert lifecycle.selects(shared, ["opencode"]) is True
    assert lifecycle.selects(shared, ["codex", "opencode"]) is True


def test_selects_refuses_a_shared_row_when_no_agent_target_is_named():
    shared = registry.BY_ID["checker"]
    assert lifecycle.selects(shared, []) is False
    assert lifecycle.selects(shared, ["agentsmd"]) is False


def test_selects_leaves_owned_rows_alone():
    owned = registry.BY_ID["opencode-plugin"]
    assert lifecycle.selects(owned, ["opencode"]) is True
    assert lifecycle.selects(owned, ["codex"]) is False
```

Add `from semlf import lifecycle` to the imports in `tests/test_registry.py`.

Add to `tests/test_semlf_install.py`:

```python
def test_installing_opencode_alone_publishes_the_shared_payloads(tmp_path):
    """The shared skill cites the neutral root, so any target must publish it.

    This inverts the old assertion that an opencode-only install creates no data root:
    under per-target skills that root was Codex's alone, and citing it from opencode's
    copy would have referenced a file the install never wrote. One shared skill body
    can only cite one checker, so the payloads it cites belong to every target.
    """
    r = run_semlf(["install", "opencode"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (data_root(tmp_path) / "check_linefeeds.py").is_file()
    assert (data_root(tmp_path) / "README.md").is_file()


def test_agentsmd_alone_publishes_no_shared_payload(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# Agents\n", encoding="utf-8")
    r = run_semlf(["install", "agentsmd", str(target)], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert not data_root(tmp_path).exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_registry.py tests/test_semlf_install.py -q`
Expected: FAIL — the owner map mismatches, `lifecycle.selects` does not exist,
and `install opencode` creates no data root.

- [ ] **Step 3: Change the two row owners**

In `cli/semlf/registry.py`, change the `checker` row's owner from `"codex"` to `"shared"`,
and the same for `readme`.
Replace the comment above `ROWS` with one that states the new meaning:

```python
# The row lambdas reference render functions defined further down;
# module-level names resolve at call time, so the forward references are safe,
# and the table stays one readable block.
#
# An owner is a target name, or "shared" — published whenever any agent target is selected.
# "shared" exists because one skill body can cite exactly one checker and one README,
# so the payloads it cites cannot belong to a single target (ADR-0019).
```

- [ ] **Step 4: Add the selection test and route every consumer through it**

In `cli/semlf/lifecycle.py`, above `colliding_destinations`:

```python
AGENT_TARGETS = ("codex", "opencode")


def selects(row, targets):
    """Whether this request publishes this row.

    One test, used by planning, collision detection, status and doctor alike,
    so "selected" cannot come to mean different things to different verbs.
    A shared row needs an agent target and not merely any target:
    `agentsmd` is a paragraph of prose with no checker and no skill behind it.
    """
    if row.owner == "shared":
        return any(t in targets for t in AGENT_TARGETS)
    return row.owner in targets
```

In `plan_install`, replace `if row.recorded and row.owner in targets:` with:

```python
        if row.recorded and selects(row, targets):
```

- [ ] **Step 5: Teach status and doctor that a shared row's consumer is any consumer**

In `cli/semlf/lifecycle.py`, `status_command`, replace both `row.owner not in consumers` tests.
Each becomes a call to a shared helper.
Add it beside `selects`:

```python
def expected_by(row, consumers):
    """Whether an installed integration makes this row's payload expected.

    A shared payload is expected as soon as anything is installed,
    since its consumer is whichever integration is present rather than one named target.
    """
    if row.owner == "shared":
        return bool(consumers)
    return row.owner in consumers
```

Then in `status_command`:

```python
        if (
            state == "missing"
            and not expected_by(row, consumers)
            and snapshot.get(row.id) is None
        ):
            continue
        print(f"payload {line}")
        if state != "missing" and not expected_by(row, consumers):
```

And in `cli/semlf/doctor.py`, `_payload_identity_check`:

```python
        expected = lifecycle.expected_by(row, consumers)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_registry.py tests/test_semlf_install.py tests/test_doctor.py -q`
Expected: PASS

- [ ] **Step 7: Fix the one test this deliberately inverts**

`tests/test_semlf_install.py::test_installing_opencode_leaves_no_reference_to_a_codex_owned_file`
asserts `not data_root(tmp_path).exists()`.
That assertion is now wrong by design.
Delete the two lines asserting the data root's absence and the `str(data_root(tmp_path)) not in body` check,
keep the `"check_linefeeds.py" not in body` check on the setup skill,
and replace the docstring with:

```python
def test_the_setup_skill_cites_no_payload(tmp_path):
    """The setup skill references no published file, so it needs no payload to exist.

    The judgment skill is the opposite case and cites the shared root deliberately;
    this one must stay self-contained, because it is what an agent runs when nothing
    is installed yet.
    """
```

- [ ] **Step 8: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add cli/semlf/registry.py cli/semlf/lifecycle.py cli/semlf/doctor.py tests/
git commit -m "feat(registry): let a row be owned by every agent

One skill body can cite exactly one checker and one README, so the
payloads it cites cannot belong to a single target. checker and readme
become shared rows, published whenever any agent target is selected.

An opencode-only machine therefore gains the payload root it previously
never created, which is what lets one shared skill body reference files
every install writes. agentsmd alone still publishes nothing: it is a
paragraph of prose with no checker behind it."
```

---

### Task 3: Collision detection sees what is already installed

`colliding_destinations` compares only the rows a request selects,
so a collision assembled across two separate requests is invisible to it.

**Files:**
- Modify: `cli/semlf/lifecycle.py` (`colliding_destinations`)
- Test: `tests/test_semlf_install.py`

**Interfaces:**
- Consumes: `manifest.same_file` (Task 1), `lifecycle.selects` (Task 2).
- Produces: no new names.
  `colliding_destinations(targets)` keeps its signature and its return type, a list of refusal strings.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_semlf_install.py`:

```python
def test_a_collision_assembled_across_two_requests_is_refused(tmp_path):
    """Two requests, one file, two owners — the state the old check could not see.

    Install codex, point opencode's plugins directory at the payload root, then
    install opencode. The second request selects no shared row, so comparing only
    what it selects finds nothing, and opencode adopts the shared checker under its
    own name. Both rows then record one file, and either uninstall deletes the copy
    the other integration still depends on.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    plugins.parent.mkdir(parents=True, exist_ok=True)
    plugins.symlink_to(data_root(tmp_path), target_is_directory=True)

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 1, r.stdout
    assert "resolve to" in r.stderr
    assert "opencode-checker" in r.stderr


def test_a_collision_between_two_destinations_that_do_not_exist_yet_is_refused(tmp_path):
    """Nothing installed, both roots joined, both leaves absent.

    realpath reports two different paths here, so a fallback keyed on it finds no
    collision, both rows are planned, the first write creates the file and the second
    fails as "appeared after classification" — a half-applied request, which preflight
    exists to make impossible.
    """
    env = isolated_env(tmp_path)
    data = data_root(tmp_path)
    data.mkdir(parents=True, exist_ok=True)
    plugins = tmp_path / "xdg" / "opencode" / "plugins"
    plugins.parent.mkdir(parents=True, exist_ok=True)
    plugins.symlink_to(data, target_is_directory=True)

    r = run_semlf(["install", "codex", "opencode"], env)
    assert r.returncode == 1, r.stdout
    assert "checker" in r.stderr
    assert not (data / "check_linefeeds.py").exists(), "half-applied"
```

A bind mount cannot be created without privilege, so this test uses a symlinked parent,
which reaches the same code path:
both leaves are absent, so the comparison climbs to the parents.
The bind-mount case is covered by the same branch and is verified by hand rather than in CI.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_semlf_install.py -k collision_assembled -q`
Expected: FAIL — return code is 0, the second install succeeds and adopts the shared checker

- [ ] **Step 3: Widen the comparison**

Replace `colliding_destinations` in `cli/semlf/lifecycle.py`:

```python
def colliding_destinations(targets):
    """Refusals for rows that would resolve to one file, or [].

    Two rows on one inode cannot both be installed or removed independently:
    the second write finds a file that "appeared after classification" and errors,
    and a later uninstall of either target deletes the file the other still records.
    Refusing the whole request is the one outcome that leaves nothing half-written.

    The comparison covers two populations, because a collision does not have to be
    assembled inside a single request.
    A user can install codex, join opencode's plugins directory to the payload root,
    and install opencode: the second request selects no shared row, so comparing only
    what it selects would find nothing and let opencode adopt the shared checker.
    So every selected destination is compared against every other selected one,
    and against every destination a valid record already proves.

    Identity is `manifest.same_file` when both paths exist, since a bind mount joins
    two paths `realpath` still reports as different.
    `realpath` is the fallback for a destination that has not been created yet:
    it has no inode to compare, and nothing to delete either.
    """
    snapshot = manifest.load()
    selected = []
    for row in registry.ROWS:
        if not (row.recorded and selects(row, targets)):
            continue
        dest = row.dest()
        if dest is not None:
            selected.append((row.id, dest))

    installed = []
    for row in registry.ROWS:
        if not row.recorded or selects(row, targets):
            continue
        entry = snapshot.get(row.id)
        dest = row.dest()
        if dest is None or entry is None:
            continue
        if classify.object_state(dest) == "regular":
            installed.append((row.id, dest))

    refusals = []
    for i, (name, dest) in enumerate(selected):
        for other_name, other in selected[i + 1 :] + installed:
            if _one_file(dest, other):
                refusals.append(
                    f"refusing: {name} and {other_name} both resolve to "
                    f"{os.path.realpath(str(dest))}; a symlink or bind mount has "
                    "joined two roots this kit keeps separate, so neither could be "
                    "installed or removed independently"
                )
    return refusals


def _anchor(path):
    """(nearest existing ancestor, the unresolved suffix below it)."""
    probe = Path(path)
    suffix = []
    while not os.path.lexists(str(probe)):
        if probe.parent == probe:
            return None, tuple(suffix)
        suffix.append(probe.name)
        probe = probe.parent
    return probe, tuple(reversed(suffix))


def _one_file(a, b):
    """Whether two destinations name one file, even before either exists.

    Both existing is the easy case and `same_file` answers it.

    Neither existing is the case realpath gets wrong. On a fresh machine whose
    opencode plugins directory is bind-mounted onto the payload root, no checker
    destination exists yet, realpath reports two different paths, nothing refuses,
    and the request half-applies: the first write creates the file and the second
    fails as "appeared after classification".

    So each side reduces to its nearest existing ancestor plus the unresolved suffix
    below it. Equal suffixes under one directory mean one destination, whether that
    directory is shared by a bind mount, a symlink, or by being literally the same
    path.
    """
    if os.path.lexists(str(a)) and os.path.lexists(str(b)):
        return manifest.same_file(a, b)
    anchor_a, suffix_a = _anchor(a)
    anchor_b, suffix_b = _anchor(b)
    if anchor_a is None or anchor_b is None or suffix_a != suffix_b:
        return False
    return manifest.same_file(anchor_a, anchor_b)
```

`classify` is already imported in `lifecycle.py`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_semlf_install.py -k collision_assembled -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass.
The existing symlink-collision test still passes: it joins two selected rows, which the first loop covers.

- [ ] **Step 6: Commit**

```bash
git add cli/semlf/lifecycle.py tests/test_semlf_install.py
git commit -m "fix(install): catch a collision built across two requests

Comparing only the rows a request selects misses the state a user
reaches in three ordinary steps: install codex, point opencode's
plugins directory at the payload root, install opencode. That second
request selects no shared row, so nothing refuses, and opencode adopts
the shared checker under its own name. Both records then name one file
and either uninstall deletes what the other depends on.

Selected destinations are now compared against already-installed ones
too, and identity is device-and-inode where both paths exist, so a bind
mount cannot hide the join."
```

---

### Task 4: One skill row, retired names, and record projection

This is the largest task and it cannot be split:
renaming the rows without carrying the old records forward would make every upgraded machine refuse.

**Files:**
- Modify: `cli/semlf/registry.py` (rows, renderers)
- Modify: `cli/semlf/manifest.py` (`KNOWN`, `RETIRED`, state access)
- Modify: `cli/semlf/lifecycle.py` (`plan_install`, `status_command`)
- Test: `tests/test_registry.py`, `tests/test_migration.py`, `tests/test_semlf_install.py`

**Interfaces:**
- Consumes: `manifest.same_file` (Task 1), `lifecycle.selects` (Task 2).
- Produces:
  - Registry ids `skill` and `setup-skill`, replacing `codex-skill` and `codex-setup-skill`.
  - `registry.render_skill(data_dir) -> str`, the one skill renderer.
  - `manifest.RETIRED`, a tuple of retired record names.
  - `manifest.retired_entry(name) -> dict | None`, reading a retired record.
  - `manifest.forget_retired(name) -> None`.
  - `manifest.RETIRED_FOR`, mapping a live row id to the retired names that may prove it.
  - `lifecycle.project_retired(snapshot, destinations) -> (projected_snapshot, aliases)`
    where `aliases` maps a live row id to the list of retired names it absorbed.

- [ ] **Step 1: Write the failing tests**

In `tests/test_registry.py`, update `EXPECTED_IDS`:

```python
EXPECTED_IDS = [
    "checker",
    "readme",
    "codex-hook-template",
    "skill",
    "opencode-plugin",
    "opencode-checker",
    "setup-skill",
    "opencode-setup-command",
    "agentsmd-snippet",
]
```

and the owner map:

```python
def test_owners_match_the_design_table():
    owners = {r.id: r.owner for r in registry.ROWS}
    assert owners == {
        "checker": "shared",
        "readme": "shared",
        "codex-hook-template": "codex",
        "skill": "shared",
        "opencode-plugin": "opencode",
        "opencode-checker": "opencode",
        "setup-skill": "shared",
        "opencode-setup-command": "opencode",
        "agentsmd-snippet": "agentsmd",
    }
```

Replace `test_the_setup_skill_ships_once_per_target_from_one_source` with:

```python
def test_each_skill_ships_exactly_once():
    """One row per skill, which is what makes any symlink arrangement safe.

    Two rows on one inode was the collision the old layout kept refusing.
    A single row cannot collide with itself, so a root symlink, a leaf symlink,
    an intermediate symlink and a bind mount all resolve to the same destination
    and none of them needs a rule.
    """
    skills = [r for r in registry.ROWS if r.id in ("skill", "setup-skill")]
    assert len(skills) == 2
    assert {r.source for r in skills} == {
        "skills/semantic-linefeeds/SKILL.md",
        registry.SETUP_SKILL_SOURCE,
    }
```

and update the identity set:

```python
def test_identity_marks_exactly_the_digest_compared_payloads():
    assert {r.id for r in registry.ROWS if r.identity} == {
        "checker",
        "readme",
        "opencode-checker",
    }
```

Add to `tests/test_migration.py`:

```python
def test_a_renamed_row_adopts_its_retired_record(tmp_path):
    """An upgrade must not stop at a wall because the row was renamed.

    classify_artifact adopts a destination whose bytes already equal the rendering,
    so a machine whose SKILL.md never changed survives without help. A release that
    changes SKILL.md does not: the new name has no record, provenance reads
    unrecorded, and install refuses without --force.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    skill = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "codex-skill.json").write_text(json.dumps(entry), encoding="utf-8")
    (records / "skill.json").unlink()
    skill.write_text(skill.read_text(encoding="utf-8") + "\n<!-- drift -->\n", encoding="utf-8")

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert "<!-- drift -->" not in skill.read_text(encoding="utf-8")
    assert not (records / "codex-skill.json").exists()
    assert json.loads((records / "skill.json").read_text())["path"] == str(skill)


def test_two_retired_records_naming_one_file_converge(tmp_path):
    """A joined root can leave both codex-skill and opencode-skill on one file."""
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    for retired in ("codex-skill", "opencode-skill"):
        (records / f"{retired}.json").write_text(json.dumps(entry), encoding="utf-8")
    (records / "skill.json").unlink()

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert (records / "skill.json").exists()
    assert not (records / "codex-skill.json").exists()
    assert not (records / "opencode-skill.json").exists()


def test_disagreeing_retired_records_refuse_and_name_both(tmp_path):
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "codex-skill.json").write_text(json.dumps(entry), encoding="utf-8")
    other = dict(entry, sha256="0" * 64)
    (records / "opencode-skill.json").write_text(json.dumps(other), encoding="utf-8")
    (records / "skill.json").unlink()

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert "codex-skill" in r.stderr
    assert "opencode-skill" in r.stderr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_registry.py tests/test_migration.py -q`
Expected: FAIL — ids and owners mismatch, `skill.json` does not exist

- [ ] **Step 3: Rewrite the rows**

In `cli/semlf/registry.py`, delete the `opencode-readme`, `opencode-skill` and `opencode-setup-skill` rows,
rename `codex-skill` to `skill` and `codex-setup-skill` to `setup-skill`,
set both to owner `shared`, and renumber `order` so it stays ascending from 0.
The `skill` row's render becomes `lambda data_dir: render_skill(data_dir).encode("utf-8")`
and the `setup-skill` row's stays `payload_bytes`.
Its destination stays `manifest.codex_skill_dest`, renamed in Step 5.

- [ ] **Step 4: Collapse the two renderers into one**

Replace `render_skill`, `render_codex_skill` and `render_opencode_skill` in `cli/semlf/registry.py` with:

```python
def render_skill(data_dir):
    """The installed skill body, pinned to the shared payload root (ADR-0019).

    One rendering, because there is one copy.
    The paths it cites are published by shared rows, so every install that writes
    this skill also writes the checker and README it names — which is the property
    the per-target layout could not offer without duplicating the skill itself.
    """
    if data_dir is None:
        raise ValueError("data_dir cannot be None: no data root resolves here")
    root = Path(data_dir)
    text = payload_bytes("skill").decode("utf-8")
    checker = root / CHECKER_NAME
    text = _replace_exactly_once(
        text,
        SKILL_COMMAND_OLD,
        f'python3 "{checker}" --file <files>',
        "skill command",
    )
    text = _replace_exactly_once(text, SKILL_FALLBACK_LINE, "", "skill fallback line")
    return _replace_exactly_once(
        text,
        SKILL_README_LINK_OLD,
        str(root / "README.md"),
        "skill readme link",
    )
```

- [ ] **Step 5: Rename the destination helpers**

In `cli/semlf/manifest.py`, rename `codex_skill_dest` to `skill_dest`.
Rename `codex_setup_skill_dest` to `setup_skill_dest`.
Delete `opencode_skill_dest` and `opencode_setup_skill_dest`.
Update their docstrings to say the root is shared rather than Codex's.
Keep `_opencode_config_dir` and add:

```python
def opencode_skills_dir():
    """opencode's own skills root, or None when no config dir resolves.

    Nothing is installed here.
    It is inspected so that migration can remove a pre-change copy,
    and so doctor can report a file competing with the shared one.
    """
    base = _opencode_config_dir()
    return None if base is None else base / "skills"
```

- [ ] **Step 6: Update `KNOWN` and add `RETIRED`**

In `cli/semlf/manifest.py`:

```python
KNOWN = (
    "cli",
    "checker",
    "readme",
    "skill",
    "opencode-plugin",
    "opencode-checker",
    "setup-skill",
    "opencode-setup-command",
)

# Record names this kit wrote before the shared root (ADR-0019).
# They are not KNOWN — no row publishes them — but the state accessors must still
# read and clear them, or an upgraded machine keeps a record nothing can reach and
# refuses the install its own file already satisfies.
RETIRED = (
    "codex-skill",
    "opencode-skill",
    "codex-setup-skill",
    "opencode-setup-skill",
    "opencode-readme",
)

# Which retired names may prove which live row.
RETIRED_FOR = {
    "skill": ("codex-skill", "opencode-skill"),
    "setup-skill": ("codex-setup-skill", "opencode-setup-skill"),
    "readme": ("opencode-readme",),
}
```

Change `artifact_state_path` to accept both populations:

```python
def artifact_state_path(name):
    if name not in KNOWN and name not in RETIRED:
        raise ValueError(f"unknown artifact name: {name!r}")
    base = _state_base()
    return None if base is None else base / "artifacts" / (name + ".json")
```

`load()` keeps iterating `KNOWN` only, so a retired record never enters the ordinary snapshot.
Add beside it:

```python
def retired_entry(name):
    """A retired record's entry when it is valid, else None."""
    if name not in RETIRED:
        raise ValueError(f"not a retired artifact name: {name!r}")
    path = artifact_state_path(name)
    if path is None:
        return None
    entry = read_state_json(path)
    return entry if _valid_entry(entry) else None
```

`forget` already routes through `artifact_state_path`, so it now accepts a retired name unchanged.

- [ ] **Step 7: Project retired records into the classification snapshot**

Add to `cli/semlf/lifecycle.py`, above `plan_install`:

```python
def project_retired(snapshot, destinations):
    """(snapshot with retired records presented under their new names, aliases).

    Preflight is read-only so that --dry-run describes exactly what apply would do,
    and one snapshot is taken before any row is classified.
    A rename performed during planning would break the first property;
    performed at apply time it would be too late to affect a classification that
    already happened. Projecting into the snapshot satisfies both: classification
    sees a managed artifact, the dry run says so, and only apply rewrites state.

    A live row can have more than one retired alias — a joined root leaves both
    codex-skill and opencode-skill proving one file — so every alias that proves the
    row's own destination is collected. Agreeing proofs project one and mark the rest
    for removal. Disagreeing proofs raise, because choosing between two digests for
    one file is exactly the guess this project does not make.
    """
    projected = dict(snapshot)
    aliases = {}
    for live, retired_names in manifest.RETIRED_FOR.items():
        dest = destinations.get(live)
        if dest is None:
            continue
        proving = []
        for retired in retired_names:
            entry = manifest.retired_entry(retired)
            if entry is None:
                continue
            if manifest.same_file(entry["path"], dest):
                proving.append((retired, entry))
        if not proving:
            continue
        digests = {entry["sha256"] for _, entry in proving}
        if len(digests) > 1:
            named = " and ".join(name for name, _ in proving)
            raise RetiredRecordConflict(
                f"refusing to migrate {live}: {named} both record "
                f"{dest} with different digests; remove the stale one by hand"
            )
        aliases[live] = [name for name, _ in proving]
        if live not in projected:
            projected[live] = proving[0][1]
    return projected, aliases


class RetiredRecordConflict(ValueError):
    """Two retired records prove one file with different digests."""
```

In `plan_install`, take the projection and clear the aliases after each successful write:

```python
def plan_install(targets, agentsmd_path, force):
    planned, refusals = [], []
    refusals.extend(colliding_destinations(targets))
    snapshot = manifest.load()
    destinations = payload_destinations()
    try:
        snapshot, aliases = project_retired(snapshot, destinations)
    except RetiredRecordConflict as exc:
        return planned, refusals + [str(exc)]
    for row in registry.ROWS:
        if row.recorded and selects(row, targets):
            plan_file(row.id, force, snapshot, destinations, planned, refusals)
            for retired in aliases.get(row.id, ()):
                plan_forget_retired(retired, planned)
        elif row.id == "codex-hook-template" and "codex" in targets:
            plan_codex_hook(planned, refusals)
        elif row.id == "agentsmd-snippet" and agentsmd_path is not None:
            plan_agentsmd(agentsmd_path, planned, refusals)
    return planned, refusals
```

Add the forget step, which must be planned after the write it depends on:

```python
def plan_forget_retired(name, planned):
    """Clear one retired record, after the row that absorbed it is published.

    Ordering is the whole point: a retired record cleared before the new one is
    written leaves a file with no proof at all, and apply_plan has no rollback.
    """

    def _do(name=name):
        try:
            manifest.forget(name)
        except OSError as exc:
            return f"published, but could not clear the {name} record: {exc}"
        return None

    planned.append(
        Planned(
            f"{name}: clear the superseded record",
            name,
            None,
            None,
            _do,
            done=f"cleared the superseded {name} record",
        )
    )
```

- [ ] **Step 8: Update the status artifact list**

In `status_command`, replace the literal tuple with the new names:

```python
    for name, label in (
        ("skill", "skill"),
        ("setup-skill", "setup skill"),
        ("opencode-plugin", "opencode plugin"),
        ("opencode-setup-command", "opencode setup command"),
    ):
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_registry.py tests/test_migration.py tests/test_semlf_install.py -q`
Expected: PASS.
Existing tests naming `codex-skill` destinations need their record names updated to `skill`;
that is a mechanical rename and no assertion's meaning changes.

- [ ] **Step 10: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass

- [ ] **Step 11: Commit**

```bash
git add cli/semlf tests/
git commit -m "feat(registry): publish each skill once to the shared root

Codex and opencode both read ~/.agents/skills, so a second copy under
opencode's own root bought nothing and cost a refusal whenever a user
symlinked the two together. There is now one row per skill, one
renderer, and no opencode-owned skill or README.

Renaming the rows would strand every upgraded machine: the new name has
no record, so a release that changed SKILL.md would read as unrecorded
and refuse. Retired record names stay reachable and are projected onto
the live row during planning, which keeps preflight read-only, and are
cleared only after the row that absorbed them is published."
```

---

### Task 5: Migration removes the pre-change copies

**Files:**
- Modify: `cli/semlf/lifecycle.py`
- Test: `tests/test_migration.py`

**Interfaces:**
- Consumes: `manifest.same_file` (1), `manifest.RETIRED` and `retired_entry` (4).
- Produces: `lifecycle.plan_legacy_cleanup(planned, refusals)`.
  It appends removals for pre-change artifacts.
  Called from `plan_install` after every row is planned, and from `plan_remove_targets` in Task 8.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_migration.py`:

```python
def legacy_opencode_skill(tmp_path, name="semantic-linefeeds"):
    d = tmp_path / "xdg" / "opencode" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    return d / "SKILL.md"


def test_migration_removes_a_proven_legacy_opencode_skill(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    legacy = legacy_opencode_skill(tmp_path)
    body = "---\nname: semantic-linefeeds\n---\n\nold\n"
    legacy.write_text(body, encoding="utf-8")
    records = tmp_path / "state" / "semlf" / "artifacts"
    (records / "opencode-skill.json").write_text(
        json.dumps(
            {
                "path": str(legacy),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "version": check_linefeeds.__version__,
            }
        ),
        encoding="utf-8",
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not legacy.exists()
    assert not legacy.parent.exists()
    assert not (records / "opencode-skill.json").exists()


def test_migration_never_removes_the_shared_file_through_a_joined_root(tmp_path):
    """The trap: on a joined root the legacy record's path IS the shared file."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"

    skills = tmp_path / "xdg" / "opencode" / "skills"
    skills.parent.mkdir(parents=True, exist_ok=True)
    skills.symlink_to(tmp_path / "home" / ".agents" / "skills", target_is_directory=True)

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(skills / "semantic-linefeeds" / "SKILL.md"))),
        encoding="utf-8",
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert shared.is_file(), "the shared skill was deleted through the joined root"


def test_migration_removes_a_hard_linked_legacy_skill(tmp_path):
    """A hard link reads as the same file but must go.

    Sparing it leaves it in place until the shared file is next published:
    publish_bytes stages a temp file and replaces it, the shared path gets a new
    inode, and the spared link is stranded serving last release's bytes.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    legacy = legacy_opencode_skill(tmp_path)
    os.link(shared, legacy)

    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(legacy))), encoding="utf-8"
    )

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not legacy.exists()
    assert shared.is_file()


def test_migration_refuses_an_unproven_legacy_file(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    legacy = legacy_opencode_skill(tmp_path)
    legacy.write_text("hand written\n", encoding="utf-8")

    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 1
    assert str(legacy) in r.stderr
    assert legacy.exists()
```

Add `import hashlib` and `import os` to `tests/test_migration.py` if absent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_migration.py -k migration_ -q`
Expected: FAIL — the legacy files survive

- [ ] **Step 3: Implement the cleanup**

Add to `cli/semlf/lifecycle.py`:

```python
# Each pre-change artifact, and the live destination it must not be confused with.
LEGACY_ARTIFACTS = (
    ("opencode-skill", "semantic-linefeeds", "skill"),
    ("opencode-setup-skill", "setup-semlf", "setup-skill"),
)


def plan_legacy_cleanup(planned, refusals):
    """Remove pre-change copies that would compete with the shared skill.

    opencode reads its own skills root as well as the shared one, and a copy there
    usually wins the name race, so leaving these behind means opencode keeps loading
    last release's skill. Stopping writing them is not enough.

    The guard compares PARENT DIRECTORIES, not the files. The question is whether
    unlinking would destroy the shared file's own directory entry, and only the
    parents answer that: joined roots share a parent, while a hard link or a leaf
    symlink has its own, and unlinking those removes just that entry. Comparing the
    files instead would spare a hard link, which then strands on the old inode the
    next time the shared file is published.
    """
    skills_dir = manifest.opencode_skills_dir()
    destinations = payload_destinations()
    if skills_dir is None:
        return
    for retired, folder, live in LEGACY_ARTIFACTS:
        legacy = skills_dir / folder / "SKILL.md"
        if not os.path.lexists(str(legacy)):
            continue
        shared = destinations.get(live)
        if shared is not None and manifest.same_file(
            legacy.parent, Path(shared).parent, missing=False
        ):
            # A joined root: this path is the shared file by another spelling.
            # The record is carried forward by project_retired, not cleared here.
            continue
        entry = manifest.retired_entry(retired)
        if entry is None or manifest.classify_entry(entry, legacy) != "managed":
            refusals.append(
                f"refusing to remove {legacy}: this kit cannot prove it wrote it; "
                "move it aside and re-run"
            )
            continue

        def _do(legacy=legacy, retired=retired):
            os.unlink(legacy)
            note = _forget_note(legacy, retired)
            _prune_empty_parent(legacy)
            return note

        planned.append(
            Planned(str(legacy), retired, legacy, None, _do, done=f"removed {legacy}")
        )
```

Call it at the end of `plan_install`, before the return:

```python
    plan_legacy_cleanup(planned, refusals)
    return planned, refusals
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_migration.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add cli/semlf/lifecycle.py tests/test_migration.py
git commit -m "fix(install): clear the skill copies that compete

opencode scans its own skills root as well as the shared one, and a copy
there usually wins the name race, so a machine upgraded from the old
layout would keep loading last release's skill. Stopping writing that
copy does not remove the one already there.

The guard compares parent directories rather than files. Joined roots
share a parent and unlinking would destroy the shared entry; a hard link
or leaf symlink has its own parent and unlinking removes only that
entry. Comparing files would spare a hard link, which then strands on
the old inode the next time the shared file is published."
```

---

### Task 6: The conservative removal predicate

**Files:**
- Modify: `cli/semlf/lifecycle.py`
- Test: `tests/test_semlf_install.py`

**Interfaces:**
- Consumes: nothing from earlier tasks beyond the registry.
- Produces: `lifecycle.target_present(target, snapshot) -> bool`, conservative:
  `True` whenever any of the target's current or recorded paths proves bytes or cannot be inspected,
  `False` only when every one was examined and proven missing.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_semlf_install.py`:

```python
def test_a_target_recorded_under_another_config_home_counts_present(tmp_path):
    """The reporting predicate probes only the current environment.

    Install opencode under one XDG_CONFIG_HOME, then operate under another: the
    plugin is not where this environment looks, but its record still proves bytes
    at the path it was installed to. Counting it absent would delete shared skills
    a live installation still uses.
    """
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "opencode"], env)
    assert r.returncode == 0, r.stderr

    moved = dict(env, XDG_CONFIG_HOME=str(tmp_path / "elsewhere"))
    r = run_semlf(["uninstall", "codex"], moved)
    assert r.returncode == 0, r.stderr
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert shared.is_file(), "shared skill removed while opencode is still installed"


def test_an_unreadable_hooks_json_retains_the_shared_skills(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    (tmp_path / "codex" / "hooks.json").write_text("{ not json", encoding="utf-8")

    r = run_semlf(["uninstall", "opencode"], env)
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert shared.is_file(), "an unreadable hooks.json must not authorise a delete"


def test_a_record_whose_file_is_gone_counts_absent(tmp_path):
    """Otherwise a hand-cleaned machine can never converge."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    plugin = tmp_path / "xdg" / "opencode" / "plugins" / "semantic-linefeeds.ts"
    plugin.unlink()

    r = run_semlf(["uninstall", "codex", "opencode"], env)
    assert r.returncode == 0, r.stderr
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert not shared.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_semlf_install.py -k "counts_present or retains_the_shared or counts_absent" -q`
Expected: FAIL — `target_present` does not exist and nothing removes shared skills yet

- [ ] **Step 3: Implement the predicate**

Add to `cli/semlf/lifecycle.py`, below `installed_consumers`:

```python
def _probe(path):
    """'present', 'absent', or 'unknown' for one path.

    Tri-state on purpose. A boolean forces every inspection failure into one of the
    two answers, and for a predicate that authorises a delete the wrong one loses
    data.
    """
    if path is None:
        return "unknown"
    try:
        if not os.path.lexists(str(path)):
            return "absent"
    except (OSError, ValueError):
        return "unknown"
    return "present"


def target_present(target, snapshot):
    """Whether target still has artifacts here, answered conservatively.

    installed_consumers is the reporting predicate and must not decide this. It
    probes only destinations derived from the current environment, and it fails
    closed to absent on every kind of trouble — harmless when the result is a
    warning, destructive when it authorises an unlink.

    Every ambiguity resolves to present, and the places examined are stated rather
    than implied: a path never looked at is not a path found empty. Both the current
    environment's destinations and every path a valid record names are probed, since
    a machine installed under one XDG_CONFIG_HOME may be operated under another.

    A record whose file is proven gone counts absent. Treating every valid record as
    permanent presence would retain the shared skills forever on a machine the user
    cleaned up by hand, since plan_remove_file leaves a vanished destination's record
    in place.
    """
    if target == "codex":
        home = manifest.codex_home()
        if home is not None:
            hooks = home / "hooks.json"
            if os.path.lexists(str(hooks)):
                data = manifest.read_state_json(hooks)
                if data is None:
                    return True  # unreadable is could-not-inspect, never absent
                if manifest.owned_codex_hooks(data):
                    return True
    seen_any = False
    for row in registry.ROWS:
        if row.owner != target or not row.recorded:
            continue
        for path in (row.dest(), (snapshot.get(row.id) or {}).get("path")):
            state = _probe(path)
            if state == "unknown":
                return True
            if state == "present":
                seen_any = True
    return seen_any
```

- [ ] **Step 4: Run the tests to verify the predicate works**

The removal itself lands in Task 7, so at this point run only the predicate's own coverage:

Run: `python3 -m pytest tests/test_semlf_install.py -k counts_present -q`
Expected: PASS.
The other two tests in this group stay red until Task 7 and are expected to.
Mark them with `@pytest.mark.xfail(reason="shared removal lands with the last-consumer rule", strict=True)`
and remove the marker in Task 7.

- [ ] **Step 5: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass, with two xfail

- [ ] **Step 6: Commit**

```bash
git add cli/semlf/lifecycle.py tests/test_semlf_install.py
git commit -m "feat(uninstall): answer presence conservatively

The reporting predicate probes only the current environment and fails
closed to absent on any trouble. That is harmless while it produces a
warning and destructive once it authorises an unlink: an unreadable
hooks.json, or a machine installed under a different XDG_CONFIG_HOME,
would read as nothing installed.

Presence is now tri-state over both current destinations and every path
a valid record names, and every ambiguity resolves to present. A record
whose file is proven gone still counts absent, so a machine cleaned up
by hand can converge instead of retaining forever."
```

---

### Task 7: Last-consumer removal, planned last

**Files:**
- Modify: `cli/semlf/lifecycle.py` (`plan_remove_targets`, `uninstall_command`)
- Modify: `scripts/install.py` (`uninstall`)
- Test: `tests/test_semlf_install.py`

**Interfaces:**
- Consumes: `lifecycle.target_present` (6).
- Produces: `lifecycle.plan_shared_removal(targets, force, planned, refusals)`, appended last.

- [ ] **Step 1: Remove the xfail markers and add the ordering test**

Delete the two `xfail` markers added in Task 6, and add:

```python
def test_removing_one_target_keeps_the_shared_skills(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert shared.is_file()


def test_removing_the_last_target_takes_them_and_keeps_the_payloads(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    run_semlf(["uninstall", "opencode"], env)
    r = run_semlf(["uninstall", "codex"], env)
    assert r.returncode == 0, r.stderr
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert not shared.exists()
    assert (data_root(tmp_path) / "check_linefeeds.py").is_file()
    assert "retained" in r.stdout


def test_shared_removals_are_planned_after_every_target_artifact(tmp_path):
    """apply_plan stops at the first error and has no rollback.

    A shared removal placed early would strand a target with its own artifacts
    installed and its skill gone; planned last, the same failure leaves the skills
    intact and a re-run converges.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "opencode"], env)
    r = run_semlf(["uninstall", "opencode", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.splitlines() if "would remove" in ln]
    plugin = next(i for i, ln in enumerate(lines) if "semantic-linefeeds.ts" in ln)
    skill = next(i for i, ln in enumerate(lines) if "skills" in ln and "SKILL.md" in ln)
    assert plugin < skill
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_semlf_install.py -k "shared_skills or last_target or planned_after" -q`
Expected: FAIL — nothing removes the shared skills

- [ ] **Step 3: Implement the rule**

Add to `cli/semlf/lifecycle.py`:

```python
def plan_shared_removal(targets, force, planned, refusals):
    """Remove the shared skills when this request covers every target still present.

    A shared skill is removed when, for every agent target, either the target is
    named in this request or the conservative predicate finds no artifacts for it.
    Anything else retains them, and status names them.

    checker and readme keep the retain-and-report precedent instead. The asymmetry
    is behavioral: a checker left behind does nothing until something calls it, while
    a skill left behind is advertised to every model that scans the root, and the
    checker path in its body may by then point at nothing.
    """
    snapshot = manifest.load()
    remaining = [
        t for t in AGENT_TARGETS if t not in targets and target_present(t, snapshot)
    ]
    if remaining:
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

In `plan_remove_targets`, delete the `codex skill` and `codex setup skill` legs and the
`opencode skill` and `opencode setup skill` legs, then append at the very end of the function:

```python
    # Last, because apply_plan stops at the first error: a shared removal placed
    # earlier would strand a target with its own artifacts installed and its skill gone.
    plan_shared_removal(targets, force, planned, refusals)
```

In `uninstall_command`, widen the retained-payload note:

```python
    rc = apply_plan(planned)
    if targets and rc == 0:
        print(
            f"note: the published payloads under "
            f"{manifest.semlf_data_dir()} are shared and retained; "
            "`semlf status` reports leftovers."
        )
    return rc
```

- [ ] **Step 4: Print the same note from the checkout door**

In `scripts/install.py`, `uninstall`, replace the final `return lifecycle.apply_plan(planned)` with:

```python
    rc = lifecycle.apply_plan(planned)
    if targets and rc == 0:
        print(
            f"note: the published payloads under "
            f"{manifest.semlf_data_dir()} are shared and retained; "
            "`semlf status` reports leftovers."
        )
    return rc
```

`manifest` is already imported there;
if it is not, add `from semlf import manifest` beside the existing `lifecycle` import.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_semlf_install.py tests/test_installer.py -q`
Expected: PASS

- [ ] **Step 6: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add cli/semlf/lifecycle.py scripts/install.py tests/
git commit -m "feat(uninstall): drop shared skills with the last consumer

A skill is shared now, so no single target owns its removal. It goes
when this request covers every target that still has artifacts, and is
retained and reported otherwise.

The removals are planned last because apply_plan stops at the first
error and has no rollback: placed earlier, a failure would leave a
target installed with its skill already gone, while placed last the
same failure leaves the skills intact and a re-run converges. Both
doors now print the retained-payload note, which only the package door
did and only for codex."
```

---

### Task 8: Legacy uninstall

An upgraded machine can be uninstalled before it is ever installed under the new layout.

**Files:**
- Modify: `cli/semlf/lifecycle.py` (`plan_remove_targets`)
- Test: `tests/test_migration.py`

**Interfaces:**
- Consumes: `lifecycle.plan_legacy_cleanup` (5).
- Produces: no new names.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_migration.py`:

```python
def test_uninstall_clears_legacy_copies_without_a_new_install(tmp_path):
    """Upgrading the package and uninstalling immediately is a reachable path.

    Without this the old skill survives an uninstall that reported success, and
    because opencode scans its own root it stays advertised.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "opencode"], env)
    legacy = tmp_path / "xdg" / "opencode" / "skills" / "semantic-linefeeds"
    legacy.mkdir(parents=True, exist_ok=True)
    body = "---\nname: semantic-linefeeds\n---\n\nold\n"
    (legacy / "SKILL.md").write_text(body, encoding="utf-8")
    records = tmp_path / "state" / "semlf" / "artifacts"
    (records / "opencode-skill.json").write_text(
        json.dumps(
            {
                "path": str(legacy / "SKILL.md"),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "version": check_linefeeds.__version__,
            }
        ),
        encoding="utf-8",
    )

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    assert not (legacy / "SKILL.md").exists()
    assert not (records / "opencode-skill.json").exists()


def test_uninstall_keeps_a_legacy_record_it_could_not_remove(tmp_path):
    """A refused removal must not forget its record.

    On a joined root with another consumer still installed the shared file survives
    correctly, but its only proof is that retired record. Forgetting it would leave
    a file no record proves, and the next install would refuse without --force.
    """
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex", "opencode"], env)
    skills = tmp_path / "xdg" / "opencode" / "skills"
    if skills.exists():
        shutil.rmtree(skills)
    skills.symlink_to(tmp_path / "home" / ".agents" / "skills", target_is_directory=True)
    records = tmp_path / "state" / "semlf" / "artifacts"
    entry = json.loads((records / "skill.json").read_text())
    (records / "opencode-skill.json").write_text(
        json.dumps(dict(entry, path=str(skills / "semantic-linefeeds" / "SKILL.md"))),
        encoding="utf-8",
    )

    r = run_semlf(["uninstall", "opencode"], env)
    assert r.returncode == 0, r.stderr
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    assert shared.is_file()
    assert (records / "opencode-skill.json").exists()

    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
```

Add `import shutil` to `tests/test_migration.py` if absent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_migration.py -k "legacy_copies or could_not_remove" -q`
Expected: FAIL — the legacy file survives the uninstall

- [ ] **Step 3: Call the cleanup from the removal plan**

In `cli/semlf/lifecycle.py`, `plan_remove_targets`, inside the `if "opencode" in targets:` block,
after the existing legs and before the shared removal:

```python
        # An upgraded machine can be uninstalled before it is ever installed under
        # this layout, and the pre-change copies would otherwise survive an uninstall
        # that reported success.
        plan_legacy_cleanup(planned, refusals)
```

`plan_legacy_cleanup` already keeps a record it could not remove:
a joined-root path takes the `continue` branch, which plans nothing and forgets nothing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_migration.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add cli/semlf/lifecycle.py tests/test_migration.py
git commit -m "fix(uninstall): clear pre-change copies too

Upgrading the package and uninstalling immediately never runs an
install under the new layout, so the old skill survived an uninstall
that reported success, and opencode kept advertising it.

A removal the joined-root guard refuses keeps its record rather than
forgetting it. The shared file survives correctly in that case, and
that retired record is its only proof: cleared, the next install would
find a file nothing proves and refuse without --force."
```

---

### Task 9: The `doctor` competitor check

**Files:**
- Modify: `cli/semlf/doctor.py`
- Test: `tests/test_doctor.py`

**Interfaces:**
- Consumes: `manifest.same_file` (1), `manifest.opencode_skills_dir` (4).
- Produces: `doctor._opencode_competitor_check() -> int`, the failure count, called from `run`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_doctor.py`, following that file's existing environment helper:

```python
def test_doctor_is_quiet_when_the_opencode_path_is_the_shared_file(tmp_path):
    """A joined root is the supported topology, not a fault.

    Enumerating opencode's skills root and failing on whatever is there would fail
    every joined-root machine, since that root holds the shared skills by
    construction plus every other tool's.
    """
    env = doctor_env(tmp_path)
    run_semlf(["install", "codex"], env)
    skills = tmp_path / "xdg" / "opencode" / "skills"
    skills.parent.mkdir(parents=True, exist_ok=True)
    skills.symlink_to(tmp_path / "home" / ".agents" / "skills", target_is_directory=True)

    r = run_semlf(["doctor"], env)
    assert "competes" not in r.stdout


def test_doctor_fails_on_a_competing_file_with_different_bytes(tmp_path):
    env = doctor_env(tmp_path)
    run_semlf(["install", "codex"], env)
    d = tmp_path / "xdg" / "opencode" / "skills" / "semantic-linefeeds"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: semantic-linefeeds\n---\n\nold\n", encoding="utf-8")

    r = run_semlf(["doctor"], env)
    assert r.returncode == 1
    assert "competes" in r.stdout
    assert str(d / "SKILL.md") in r.stdout


def test_doctor_warns_on_a_competing_file_with_identical_bytes(tmp_path):
    env = doctor_env(tmp_path)
    run_semlf(["install", "codex"], env)
    shared = tmp_path / "home" / ".agents" / "skills" / "semantic-linefeeds" / "SKILL.md"
    d = tmp_path / "xdg" / "opencode" / "skills" / "semantic-linefeeds"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_bytes(shared.read_bytes())

    r = run_semlf(["doctor"], env)
    assert "warn" in r.stdout
    assert "competes" in r.stdout


def test_doctor_is_quiet_when_opencodes_skills_root_is_absent(tmp_path):
    env = doctor_env(tmp_path)
    run_semlf(["install", "codex"], env)
    r = run_semlf(["doctor"], env)
    assert "competes" not in r.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_doctor.py -k competitor -q`
Expected: FAIL — nothing prints "competes"

- [ ] **Step 3: Implement the check**

Add to `cli/semlf/doctor.py`:

```python
def _opencode_competitor_check():
    """Report a file at opencode's own skill path that is not the shared file.

    opencode scans its own skills root as well as the shared one, and a copy there
    usually wins the name race, so this is the state that makes it answer with last
    release's skill. Nothing else doctor runs can see it.

    Four rules, each a way to get this wrong:
    it compares two specific paths rather than enumerating a root, because a joined
    root holds the shared skills by construction; resolving to the shared file is
    healthy and silent; identical bytes are a warning, since that file competes for
    the name but serves the same content and is residue for migration to clear;
    and when the shared file is absent nothing is being competed with, so the report
    says install has not run instead.

    "Competes" rather than "shadows": precedence is a race, so a second copy usually
    wins but is not guaranteed to, and a message promising determinism would describe
    a rule opencode does not publish.
    """
    skills_dir = manifest.opencode_skills_dir()
    if skills_dir is None:
        return 0
    destinations = lifecycle.payload_destinations()
    failures = 0
    for folder, live in (("semantic-linefeeds", "skill"), ("setup-semlf", "setup-skill")):
        candidate = skills_dir / folder / "SKILL.md"
        if not os.path.lexists(str(candidate)):
            continue
        shared = destinations.get(live)
        if shared is None or not os.path.lexists(str(shared)):
            print(
                f"opencode skills: FAIL — {candidate} exists but no shared "
                f"{live} is published; run `semlf install`"
            )
            failures += 1
            continue
        if manifest.same_file(candidate, shared):
            continue
        here = manifest.read_regular_bytes(candidate, manifest.CLASSIFY_LIMIT)
        there = manifest.read_regular_bytes(shared, manifest.CLASSIFY_LIMIT)
        if here is not None and here == there:
            print(
                f"opencode skills: warn — {candidate} competes with the shared "
                "copy but carries the same bytes; `semlf install` clears it"
            )
            continue
        print(
            f"opencode skills: FAIL — {candidate} competes with the shared copy "
            "and differs from it; `semlf install` clears it"
        )
        failures += 1
    return failures
```

Call it from `run`, adding its return value to the failure count exactly as the other checks are added.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_doctor.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add cli/semlf/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): report a skill competing with the shared copy

opencode scans its own skills root as well as the shared one, and a copy
there usually wins the name race. That is the state that makes it answer
with an old skill, and nothing doctor ran could see it.

It compares two paths rather than enumerating a root, because a joined
root holds the shared skills by construction and enumerating would fail
every such machine. Resolving to the shared file is healthy and silent,
identical bytes warn, and differing bytes fail."
```

---

### Task 10: Documentation and the changelog

**Files:**
- Modify: `README.md`, `adapters/opencode/INSTALL.md`, `scripts/install.py`, `CHANGELOG.md`
- Modify: `docs/plans/active/2026-08-15-shared-skills-root.md` (status line)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: Fix the manual install instructions**

`adapters/opencode/INSTALL.md` step 2 currently tells a reader to copy the skill into
`~/.config/opencode/skills/`, which is the state `doctor` now reports and migration removes.
Replace step 2 with:

```markdown
2. Copy `skills/semantic-linefeeds/` into `~/.agents/skills/`.
   opencode reads that directory natively, as does Codex CLI,
   so one copy serves both and nothing needs to go under `~/.config/opencode/skills/`.
   A copy there would compete with this one for the skill's name.

   Requires opencode 1.18.18 or newer.
   `OPENCODE_DISABLE_EXTERNAL_SKILLS` turns that scan off;
   with it set, no copy in `~/.agents/skills` is visible to opencode at all.
```

- [ ] **Step 2: Update the README destinations and add the version floor**

In the section listing what install writes,
replace the two per-target skill rows with one shared row at `~/.agents/skills/semantic-linefeeds/SKILL.md`.
Do the same for `setup-semlf`.
Add, in the opencode part of that section:

```markdown
The skill is published once, to `~/.agents/skills`, which Codex CLI and opencode both read.
opencode 1.18.18 or newer is required, and `OPENCODE_DISABLE_EXTERNAL_SKILLS` disables that scan —
with it set, opencode sees no skill regardless of where it is installed.
```

- [ ] **Step 3: Update the checkout door's help text**

In `scripts/install.py`, the `--codex` and `--opencode` help strings are now wrong.
They describe Codex as the owner of the skill, the checker and the README.
Reword both to say the checker, README and skills are shared and published for either target.
Rename the compatibility export `codex_skill_dest` to `skill_dest`.
Keep the old name as an alias only if `tests/` references it, and otherwise delete it.

Run `grep -rn "codex_skill_dest\|opencode_skill_dest\|codex-skill\|opencode-skill" --include='*.py' .`
and resolve every hit before continuing.

- [ ] **Step 4: Write the changelog entry**

Add to `CHANGELOG.md` under the unreleased heading.
User-facing language only: no ADR numbers, no row ids, no internal names.

```markdown
### Changed

- The `semantic-linefeeds` and `setup-semlf` skills are now installed once, to
  `~/.agents/skills`, instead of once per agent. Codex CLI and opencode both read that
  directory, so one copy serves both.
- Installing for opencode alone now also publishes the checker and README under
  `~/.local/share/semlf`, because the single skill points there. Uninstalling opencode
  leaves them in place, and `semlf status` names them if you want them gone.
- Installing no longer refuses when your agents' skill directories are linked together.
  A shared skills folder — one directory that every agent reads through a symlink — is
  now the arrangement it expects rather than one it rejects.
- Upgrading removes the older per-agent copies. Without that, opencode would keep
  loading the copy in its own directory, which takes precedence over the shared one.
- `semlf doctor` now reports a skill file sitting in opencode's own directory that
  competes with the shared copy.

### Requirements

- opencode 1.18.18 or newer. Setting `OPENCODE_DISABLE_EXTERNAL_SKILLS` hides the shared
  skill from opencode entirely.
```

- [ ] **Step 5: Mark the design as implemented**

Change the design document's status line to
`**Status:** implemented` and move both it and this plan to `docs/plans/done/`.

- [ ] **Step 6: Self-check every touched Markdown file**

Run:

```bash
python3 scripts/check_linefeeds.py --file README.md CHANGELOG.md \
  adapters/opencode/INSTALL.md \
  docs/plans/done/2026-08-15-shared-skills-root.md \
  docs/plans/done/2026-08-15-shared-skills-root-implementation.md
```

Expected: exit 0, zero `fused` and zero `wrap` findings.
`long` findings are advisories to judge, not obey.

- [ ] **Step 7: Run the full suite and lint**

Run: `python3 -m pytest tests/ -q && uv run ruff check . && uv run ruff format --check .`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add README.md CHANGELOG.md adapters/opencode/INSTALL.md scripts/install.py docs/
git commit -m "docs: describe the shared skills root

The manual install instructions told readers to copy the skill into
opencode's own directory, which is exactly the copy that competes with
the shared one and that upgrading now removes.

Records the opencode version floor and the environment variable that
turns off the scan the shared copy depends on, since both produce a
machine that has lost the skill and reports nothing."
```

---

## Live Verification, After the Suite Is Green

The suite cannot reach any of this.
Run it from the checkout, on a machine with both agents:

- [ ] `semlf install codex opencode`, then restart opencode.
  A running opencode holds its skills in memory and never retracts one,
  so a check made without restarting reports the state before the install.
- [ ] Ask a real Codex and a real opencode to load the `semantic-linefeeds` skill and quote a rule back.
- [ ] `opencode debug skill | python3 -c "import json,sys; d=json.load(sys.stdin); print([x['location'] for x in d if x['name']=='semantic-linefeeds'])"`
  and confirm exactly one entry, pointing into `~/.agents/skills`.
- [ ] `semlf doctor` exits 0.
- [ ] Repeat the whole sequence on a machine whose `~/.config/opencode/skills` links to `~/.agents/skills`.
  That is the arrangement that used to be refused outright.

## Self-Review

**Spec coverage.**
Every section of the design maps to a task:
the shared owner and selection to 2, collision to 3, the registry and record projection to 4,
migration to 5, the removal predicate to 6, last-consumer removal and both doors' note to 7,
legacy uninstall to 8, `doctor` to 9, and every documentation item to 10.
The `same_file` rule that runs through all of them is Task 1.

**Deliberate omissions.**
Two design items have no task, and both are recorded there as carve-outs rather than work:
project-level `.opencode/skill` and `.opencode/skills` are never inspected,
and bind-mount joins are handled by `same_file` rather than given their own detection.

**Type consistency.**
`selects`, `expected_by`, `same_file`, `target_present`, `project_retired`,
`plan_legacy_cleanup`, `plan_shared_removal` and `_opencode_competitor_check` complete that list.
Each is defined once and referenced afterwards with the same name and arity.
Row ids `skill` and `setup-skill` are used consistently from Task 4 onward,
and the retired names appear only in `manifest.RETIRED` and `RETIRED_FOR`.
