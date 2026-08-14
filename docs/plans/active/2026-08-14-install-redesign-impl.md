# Install UX Redesign Implementation Plan

**Status:** reviewed; ready for execution
(three external reviewers, five rounds, final confirmatory round zero findings)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `semlf` the single install entry point:
the package installs the tool,
`semlf install` publishes every integration through one payload registry and one three-axis classifier,
and the checkout door becomes a thin parser over the same shared operations.

**Architecture:** A declarative payload registry (`cli/semlf/registry.py`) feeds the wheel build,
the zipapp build, the installer, and the identity checks.
A three-axis artifact classifier (`cli/semlf/classify.py`) decides admission for every single-file artifact.
A lifecycle module (`cli/semlf/lifecycle.py`) runs request-wide preflight then ordered apply,
and both doors — `semlf install` and `scripts/install.py` — call it,
so the two doors produce byte-identical artifacts everywhere.
Hooks and skills point at the neutral root `${XDG_DATA_HOME:-~/.local/share}/semlf/`.

**Tech Stack:** Python 3.9+, stdlib only, setuptools (build-time only), pytest.

**Spec:** `docs/plans/active/2026-08-14-install-redesign-design.md` is the single source of truth.
Every decision in it was adjudicated by the maintainer;
do not re-litigate any of them.
In particular: "hook calls the semlf CLI" was analyzed and rejected — do not reopen it.

## Global Constraints

- Python floor is 3.9; everything under `cli/semlf/` and `scripts/` imports stdlib only.
- The core stays one file: `scripts/check_linefeeds.py` is never split, and no task here touches its behavior.
- Nothing packaging-only is ever committed: payload members exist in build trees and artifacts only.
- The neutral payload root is `${XDG_DATA_HOME:-~/.local/share}/semlf/`, holding `check_linefeeds.py` and `README.md`.
- The installed codex hook command shape stays `python3 <path ending in check_linefeeds.py> --hook codex`.
- Exit codes: 0 success or no-op, 1 refusal or error, 64 usage; `--dry-run` always exits 0 and never writes or prompts.
- During INSTALL admission, `--force` never overrides an object-state refusal
  (symlink, directory, special file, unreadable, occupied backup slot).
  Uninstall keeps ADR-0014's removal semantics unchanged,
  where `--force` may unlink a symlink, special, or unreadable single file —
  the two matrices are different verbs and must not be conflated (see Task 9).
- Claude Code stays on the marketplace pair; `semlf` never touches it.
- Every Markdown file touched must pass `python3 scripts/check_linefeeds.py --file <file>` with zero `fused`/`wrap` findings before commit.
- Write all prose (plan docs, ADRs, README, comments) with semantic linefeeds from the first draft.
- Validation before calling any task done: `python3 -m pytest tests/ -q`;
  add `bun test adapters/opencode/` if adapter TypeScript changed.
- Commit per task;
  Conventional Commits, header ≤ 50 chars, body lines ≤ 72;
  no attribution trailers;
  never cite plan step numbers, review rounds, or `tmp/` paths in messages.
- Push nothing without being told to.
- Accepted ADRs are never edited beyond status and superseded-by pointers;
  the redesign ships as one new superseding record.

## File Structure

| Path | Responsibility |
|---|---|
| `cli/semlf/registry.py` (new) | The declarative payload registry: rows with destinations, renderings, and identity flags; embedded-byte access; transforms; build-tree staging |
| `cli/semlf/classify.py` (new) | The three-axis artifact classifier and version ordering |
| `cli/semlf/lifecycle.py` (new) | Shared operations: preflight-then-apply engine, install/status/uninstall commands, detection, consent |
| `cli/semlf/manifest.py` | Grows `checker`/`readme` names, the data-root helper, record preflight, the owned-hook scanner |
| `cli/semlf/cli.py` | Routes `install`/`status`/`uninstall` subcommands to lifecycle |
| `cli/semlf/doctor.py` | Grows the published-payload identity check and the zipapp migration report |
| `scripts/install.py` | Checkout door: thin parser over lifecycle operations; keeps the zipapp build and cli verbs |
| `setup.py` (new) | Wheel build hook: stages registry payloads into the build tree |
| `MANIFEST.in` (new) | Puts canonical payload sources into the sdist so wheels built from it stage correctly |
| `adapters/codex/hooks.json` | Placeholder becomes `__CHECKER__` carrying the full checker path |
| `tests/test_registry.py` (new) | Registry rows, byte access, transforms, staging |
| `tests/test_classify.py` (new) | The full classifier matrix |
| `tests/test_lifecycle.py` (new) | Engine-level preflight/apply, interleavings, half-state |
| `tests/test_semlf_install.py` (new) | The `semlf install`/`status`/`uninstall` command surface |
| `tests/test_migration.py` (new) | Package-door verbs over checkout-rendered artifacts |
| `docs/decisions/0016-*.md` (new) | The superseding ADR |

Dependency order: Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12; Tasks 13–15 close the slice.

---

### Task 1: Manifest growth — data root, new names, record preflight, hook scanner

**Files:**

- Modify: `cli/semlf/manifest.py`
- Modify: `cli/semlf/doctor.py` (only the `_codex_hook_check` scan collapses onto the new helper)
- Test: `tests/test_manifest.py` (append)

**Interfaces:**

- Consumes: nothing new.
- Produces:
  - `KNOWN = ("cli", "checker", "readme", "codex-skill", "opencode-plugin", "opencode-checker")`.
  - `semlf_data_dir() -> Path | None` — `${XDG_DATA_HOME:-~/.local/share}/semlf`, None when no home resolves.
  - `record_preflight(name) -> str | None` — None when the record can be written, else a refusal string;
    admission covers shape AND writability (`os.access`) of the record side.
  - `owned_codex_hooks(data) -> list[list[str]]` —
    every managed hook argv in a parsed hooks.json, `[]` for any shape trouble.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_manifest.py`
(ensure `import os`, `import stat`, and `import pytest` are present at its top;
add whichever are missing):

```python
def test_known_grows_the_neutral_payload_names():
    assert "checker" in manifest.KNOWN
    assert "readme" in manifest.KNOWN
    assert manifest.artifact_state_path("checker") is not None


def test_semlf_data_dir_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert manifest.semlf_data_dir() == tmp_path / "xdg" / "semlf"


def test_semlf_data_dir_falls_back_to_local_share(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert manifest.semlf_data_dir() == (
        tmp_path / ".local" / "share" / "semlf")


def test_record_preflight_accepts_a_writable_root(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert manifest.record_preflight("checker") is None


def test_record_preflight_refuses_a_directory_at_the_record_path(
        monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = manifest.artifact_state_path("checker")
    path.mkdir(parents=True)
    refusal = manifest.record_preflight("checker")
    assert refusal is not None and "not a regular file" in refusal


def test_record_preflight_refuses_a_file_blocking_the_parent(
        monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "semlf").write_text("in the way")
    refusal = manifest.record_preflight("checker")
    assert refusal is not None and "not a directory" in refusal


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root ignores permission bits")
def test_record_preflight_refuses_an_unwritable_state_tree(
        monkeypatch, tmp_path):
    """A writable destination plus a read-only artifacts directory must
    refuse at preflight, not publish and then fail the record write."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    artifacts = tmp_path / "state" / "semlf" / "artifacts"
    artifacts.mkdir(parents=True)
    artifacts.chmod(0o555)
    try:
        refusal = manifest.record_preflight("checker")
        assert refusal is not None and "writ" in refusal
    finally:
        artifacts.chmod(0o755)


def test_owned_codex_hooks_finds_only_managed_entries():
    data = {"hooks": {"PostToolUse": [
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": 'python3 "/x/check_linefeeds.py" --hook codex'},
            {"type": "command", "command": "echo unrelated"}]},
        {"matcher": "shell", "hooks": [
            {"type": "command",
             "command": 'python3 "/x/check_linefeeds.py" --hook codex'}]},
    ]}}
    owned = manifest.owned_codex_hooks(data)
    assert owned == [["python3", "/x/check_linefeeds.py",
                      "--hook", "codex"]]


def test_owned_codex_hooks_is_total_over_hostile_shapes():
    for data in (None, [], {"hooks": []}, {"hooks": {"PostToolUse": {}}},
                 {"hooks": {"PostToolUse": [None, {"hooks": "x"}]}}):
        assert manifest.owned_codex_hooks(data) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_manifest.py -q`
Expected: FAIL — `AttributeError` on the new names, `ValueError` for `checker` in `artifact_state_path`.

- [ ] **Step 3: Implement**

In `cli/semlf/manifest.py`:

Change the `KNOWN` line:

```python
KNOWN = ("cli", "checker", "readme", "codex-skill",
         "opencode-plugin", "opencode-checker")
```

Add after `cli_bin_dest`:

```python
def semlf_data_dir():
    """${XDG_DATA_HOME:-~/.local/share}/semlf, or None when no home resolves.

    The neutral payload root:
    installed hooks and skills point here, whatever channel semlf
    itself arrived by, so a hook survives a channel switch, a venv
    rebuild, or a CLI uninstall untouched.
    """
    if os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / "semlf"
    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".local" / "share" / "semlf"


def record_preflight(name):
    """None when name's record can be written here, else a refusal string.

    Preflight admits the provenance side before the first destination is
    touched: the state root must resolve, the record leaf must be absent
    or a regular file, and the nearest existing ancestor of its parent
    must be a directory — a file squatting on the semlf state directory
    would otherwise fail the record write after publication, leaving the
    half-state a preflight exists to prevent.
    """
    state = artifact_state_path(name)
    if state is None:
        return "no state root resolves (no home directory)"
    try:
        if os.path.lexists(state) and not stat.S_ISREG(os.lstat(state).st_mode):
            return (f"record path {state} exists and is "
                    "not a regular file")
        probe = state.parent
        while not os.path.lexists(probe):
            if probe.parent == probe:
                break
            probe = probe.parent
        if os.path.lexists(probe):
            if not probe.is_dir():
                return (f"record parent {probe} exists and is not a "
                        "directory")
            # record() creates missing directories, stages a temp file,
            # and os.replace()s it into the parent — all of which need
            # write+search permission on the nearest existing ancestor.
            if not os.access(str(probe), os.W_OK | os.X_OK):
                return f"record parent {probe} is not writable"
    except OSError as exc:
        return f"cannot inspect the record path {state}: {exc}"
    return None


def owned_codex_hooks(data):
    """Every managed hook argv in a parsed hooks.json; [] on any trouble.

    The one structural scan doctor, status, and the installer share,
    so "installed" can never mean different things to different verbs.
    """
    if not isinstance(data, dict):
        return []
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return []
    post = hooks.get("PostToolUse", [])
    if not isinstance(post, list):
        return []
    out = []
    for block in post:
        if isinstance(block, dict) and isinstance(block.get("hooks"), list):
            for h in block["hooks"]:
                argv = parse_managed_codex_hook(block.get("matcher"), h)
                if argv is not None:
                    out.append(argv)
    return out
```

In `cli/semlf/doctor.py`, replace the owned-entry accumulation loop inside `_codex_hook_check`
(the `owned = []` block scanning `post`) with:

```python
    owned = manifest.owned_codex_hooks(data)
    if not owned:
        print("codex hook: not installed")
        return 0
```

Keep the preceding unreadable-JSON FAIL and the "not installed" absent-file path exactly as they are;
delete only the now-redundant manual scan and the `isinstance(post, list)` pre-check it duplicated.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_manifest.py tests/test_doctor.py tests/test_installer.py -q`
Expected: PASS.
`test_doctor.py` guards the refactored scan;
if any doctor test fails, the scan collapse changed behavior —
fix the collapse, not the test.

- [ ] **Step 5: Commit**

```bash
git add cli/semlf/manifest.py cli/semlf/doctor.py tests/test_manifest.py
git commit -m "feat(cli): grow manifest for the neutral root" \
  -m "The provenance vocabulary gains the checker and readme names,
the XDG data-root helper, a record-side preflight, and one shared
structural scan for owned codex hook entries."
```

---

### Task 2: The payload registry module

One declarative table drives the wheel build, the zipapp build, the installer, and the identity checks.
Members embed at `semlf/payloads/<id>`; transforms fail loud on a wrong match count.

**Files:**

- Create: `cli/semlf/registry.py`
- Create: `tests/test_registry.py`
- Modify: `adapters/codex/hooks.json` (placeholder `__REPO__` → `__CHECKER__`)
- Modify: `adapters/codex/INSTALL.md` (only if it names `__REPO__`; check with grep)

**Interfaces:**

- Consumes: canonical repository files only.
- Consumes: `manifest.semlf_data_dir`, `manifest.codex_home`,
  `manifest.opencode_plugins_dir`, `manifest.codex_skill_dest` (Task 1) for the row destination closures.
- Produces:
  - `PayloadRow` namedtuple with fields `id, source, member, owner, order, recorded, identity, dest, render`.
    `dest` is a zero-argument callable returning `Path | None`
    (None-returning exactly when no home resolves),
    or the literal None for the agentsmd row, whose path is user-named and never derived.
    `render` is a callable `(data_dir: Path) -> bytes` for the five single-file rows
    (byte rows ignore the argument),
    and None for the two shared-file rows,
    which render through `render_codex_hook_entry` and the sentinel splice instead.
    `identity` is True for the three digest-identity payloads
    (`checker`, `readme`, `opencode-checker`) that status and doctor compare by guarded bytes.
    Every downstream consumer — staging, destinations, renderings, apply order,
    consumer expectedness, identity iteration — derives from `ROWS`;
    no second mapping exists anywhere.
  - `ROWS: tuple[PayloadRow]` in apply order; `BY_ID: dict[str, PayloadRow]`.
  - `payload_bytes(row_id) -> bytes` —
    embedded dir beside the module, else the enclosing zipapp member, else the checkout canonical path.
  - `stage_payloads(build_root, repo=None) -> None` — writes every member under `build_root`.
  - `render_codex_skill(data_dir: Path) -> str` — three exactly-once rewrites;
    raises `ValueError` when `data_dir` is None.
  - `render_codex_hook_entry(data_dir: Path) -> dict` —
    the one PostToolUse entry, `__CHECKER__` substituted exactly once;
    raises `ValueError` when `data_dir` is None.
  - `TransformError(ValueError)` raised on any wrong match count.
  - `CHECKER_NAME = "check_linefeeds.py"`.

- [ ] **Step 1: Change the canonical hook template placeholder**

The design requires `__CHECKER__` carrying the full checker path,
because substituting a directory into the old `__REPO__/scripts/...` shape would bake a stray `/scripts/` segment into the command.
Edit `adapters/codex/hooks.json` line 9 to:

```json
            "command": "python3 \"__CHECKER__\" --hook codex"
```

Run `grep -rn "__REPO__" adapters/ README.md` and update any prose that names the old placeholder
(describe the merge in terms of `__CHECKER__` and the neutral checker path).
Scope the sweep to `adapters/` and `README.md` only:
the matches under `docs/plans/done/` and `docs/research/` are historical records
and must never be edited.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_registry.py`:

```python
"""tests/test_registry.py — one registry, no second mapping anywhere."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

from semlf import registry


EXPECTED_IDS = ["checker", "readme", "codex-hook-template", "codex-skill",
                "opencode-plugin", "opencode-checker", "agentsmd-snippet"]


def test_rows_carry_the_designed_ids_in_apply_order():
    assert [r.id for r in registry.ROWS] == EXPECTED_IDS
    assert [r.order for r in registry.ROWS] == sorted(r.order for r in registry.ROWS)


def test_member_paths_follow_the_id():
    for row in registry.ROWS:
        assert row.member == f"semlf/payloads/{row.id}"


def test_owners_match_the_design_table():
    owners = {r.id: r.owner for r in registry.ROWS}
    assert owners == {"checker": "codex", "readme": "codex",
                      "codex-hook-template": "codex", "codex-skill": "codex",
                      "opencode-plugin": "opencode",
                      "opencode-checker": "opencode",
                      "agentsmd-snippet": "agentsmd"}


def test_the_two_no_record_rows_are_marked():
    unrecorded = {r.id for r in registry.ROWS if not r.recorded}
    assert unrecorded == {"codex-hook-template", "agentsmd-snippet"}


def test_identity_marks_exactly_the_digest_compared_payloads():
    assert {r.id for r in registry.ROWS if r.identity} == {
        "checker", "readme", "opencode-checker"}


def test_every_consumer_field_is_complete(monkeypatch, tmp_path):
    """The no-second-mapping invariant: every recorded single-file row
    resolves a destination and renders bytes from the one table."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    data_dir = tmp_path / "data" / "semlf"
    for row in registry.ROWS:
        if row.recorded:
            assert callable(row.dest), row.id
            assert row.dest() is not None, row.id
            assert callable(row.render), row.id
            assert isinstance(row.render(data_dir), bytes), row.id
        elif row.id == "codex-hook-template":
            assert row.dest() is not None
            assert row.render is None
        else:  # agentsmd-snippet: user-named, never derived
            assert row.dest is None and row.render is None


def test_render_refuses_a_none_data_dir():
    with pytest.raises(ValueError):
        registry.render_codex_skill(None)
    with pytest.raises(ValueError):
        registry.render_codex_hook_entry(None)


def test_payload_bytes_serves_canonical_bytes_in_a_checkout():
    assert registry.payload_bytes("checker") == (
        REPO / "scripts" / "check_linefeeds.py").read_bytes()
    assert registry.payload_bytes("opencode-checker") == (
        REPO / "scripts" / "check_linefeeds.py").read_bytes()
    assert registry.payload_bytes("readme") == (REPO / "README.md").read_bytes()


def test_stage_payloads_places_every_member(tmp_path):
    registry.stage_payloads(tmp_path, repo=REPO)
    for row in registry.ROWS:
        staged = tmp_path / Path(*row.member.split("/"))
        assert staged.read_bytes() == (REPO / row.source).read_bytes()


def test_payload_bytes_prefers_a_staged_dir_beside_the_module(tmp_path, monkeypatch):
    # Simulate a wheel install: copy the package and stage payloads beside it.
    pkg = tmp_path / "site" / "semlf"
    pkg.mkdir(parents=True)
    for src in (REPO / "cli" / "semlf").glob("*.py"):
        (pkg / src.name).write_bytes(src.read_bytes())
    registry.stage_payloads(tmp_path / "site", repo=REPO)
    import subprocess, sys as _sys
    code = ("import sys; sys.path.insert(0, %r); "
            "from semlf import registry; "
            "sys.stdout.buffer.write(registry.payload_bytes('checker'))"
            % str(tmp_path / "site"))
    out = subprocess.run([_sys.executable, "-c", code], capture_output=True)
    assert out.returncode == 0
    assert out.stdout == (REPO / "scripts" / "check_linefeeds.py").read_bytes()


def test_render_codex_hook_entry_substitutes_exactly_once(tmp_path):
    entry = registry.render_codex_hook_entry(tmp_path / "data" / "semlf")
    assert entry["matcher"] == "apply_patch"
    command = entry["hooks"][0]["command"]
    assert command == ('python3 "%s" --hook codex'
                      % (tmp_path / "data" / "semlf" / "check_linefeeds.py"))
    assert "__CHECKER__" not in command


def test_render_codex_skill_pins_all_three_rewrites(tmp_path):
    data_dir = tmp_path / "data" / "semlf"
    body = registry.render_codex_skill(data_dir)
    assert ('python3 "%s" --file <files>'
            % (data_dir / "check_linefeeds.py")) in body
    assert str(data_dir / "README.md") in body
    assert "CLAUDE_PLUGIN_ROOT" not in body
    assert "../../scripts/check_linefeeds.py" not in body
    assert "../../README.md" not in body


def test_a_wrong_match_count_fails_loud():
    with pytest.raises(registry.TransformError):
        registry._replace_exactly_once("no match here", "__CHECKER__", "x",
                                       "codex hook template")
    with pytest.raises(registry.TransformError):
        registry._replace_exactly_once("__X__ and __X__", "__X__", "x", "twice")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'semlf.registry'`
(the collection error counts; every test errors out).

- [ ] **Step 4: Write the registry module**

Create `cli/semlf/registry.py`:

```python
"""The payload registry: one declarative table for every packaging and
lifecycle consumer (the redesign ADR).

Each row names a logical id (also its provenance record name where one
exists), the canonical repository path, the embedded member path in both
wheel and zipapp, the owning install target, and its apply-order position.
The wheel build hook, the zipapp builder, the installer, and the identity
checks all import this table;
no consumer invents a second mapping.
Members carry canonical bytes;
transforms run on the installing machine, and every transform fails loud
when its match count is wrong, so a canonical-source edit can never
silently disable a rewrite.
"""
import json
import zipfile
from collections import namedtuple
from pathlib import Path

from semlf import manifest

PayloadRow = namedtuple("PayloadRow",
                        ["id", "source", "member", "owner", "order",
                         "recorded", "identity", "dest", "render"])

CHECKER_NAME = "check_linefeeds.py"


def _in(base, name):
    """base / name, or None when the base itself does not resolve."""
    return None if base is None else base / name


def _data_path(name):
    return _in(manifest.semlf_data_dir(), name)


# The row lambdas reference render functions defined further down;
# module-level names resolve at call time, so the forward references
# are safe, and the table stays one readable block.
ROWS = (
    PayloadRow("checker", "scripts/check_linefeeds.py",
               "semlf/payloads/checker", "codex", 0, True, True,
               lambda: _data_path(CHECKER_NAME),
               lambda data_dir: payload_bytes("checker")),
    PayloadRow("readme", "README.md",
               "semlf/payloads/readme", "codex", 1, True, True,
               lambda: _data_path("README.md"),
               lambda data_dir: payload_bytes("readme")),
    PayloadRow("codex-hook-template", "adapters/codex/hooks.json",
               "semlf/payloads/codex-hook-template", "codex", 2,
               False, False,
               lambda: _in(manifest.codex_home(), "hooks.json"),
               None),
    PayloadRow("codex-skill", "skills/semantic-linefeeds/SKILL.md",
               "semlf/payloads/codex-skill", "codex", 3, True, False,
               manifest.codex_skill_dest,
               lambda data_dir: render_codex_skill(
                   data_dir).encode("utf-8")),
    PayloadRow("opencode-plugin",
               "adapters/opencode/semantic-linefeeds.ts",
               "semlf/payloads/opencode-plugin", "opencode", 4, True,
               False,
               lambda: _in(manifest.opencode_plugins_dir(),
                           "semantic-linefeeds.ts"),
               lambda data_dir: payload_bytes("opencode-plugin")),
    PayloadRow("opencode-checker", "scripts/check_linefeeds.py",
               "semlf/payloads/opencode-checker", "opencode", 5, True,
               True,
               lambda: _in(manifest.opencode_plugins_dir(),
                           CHECKER_NAME),
               lambda data_dir: payload_bytes("opencode-checker")),
    PayloadRow("agentsmd-snippet", "adapters/agentsmd/SNIPPET.md",
               "semlf/payloads/agentsmd-snippet", "agentsmd", 6,
               False, False, None, None),
)

BY_ID = {row.id: row for row in ROWS}


class TransformError(ValueError):
    """A registry transform's match count came out wrong.

    Raised instead of rendering silently:
    a canonical-source edit that breaks a rewrite must break the install,
    never ship an artifact with the rewrite quietly skipped.
    """


def _replace_exactly_once(text, old, new, what):
    count = text.count(old)
    if count != 1:
        raise TransformError(
            f"{what}: expected exactly one match, found {count}")
    return text.replace(old, new)


def _repo_root():
    """The enclosing checkout's root, or None when not running from one."""
    root = Path(__file__).resolve().parents[2]
    if (root / "scripts" / CHECKER_NAME).is_file():
        return root
    return None


def payload_bytes(row_id):
    """The canonical bytes for one row, wherever this artifact came from.

    Three sources, tried in order:
    a staged payloads directory beside this module (a wheel install),
    the enclosing zipapp archive (a pyz install),
    and the checkout's canonical file (the development tree, where
    nothing packaging-only is ever committed).
    """
    row = BY_ID[row_id]
    here = Path(__file__).resolve().parent
    staged = here / "payloads" / row.id
    if staged.is_file():
        return staged.read_bytes()
    archive = here.parent
    if archive.is_file() and zipfile.is_zipfile(str(archive)):
        with zipfile.ZipFile(str(archive)) as z:
            return z.read(row.member)
    root = _repo_root()
    if root is not None:
        return (root / row.source).read_bytes()
    raise FileNotFoundError(
        f"payload {row_id!r} is neither embedded nor in a checkout")


def stage_payloads(build_root, repo=None):
    """Place every registry payload at its member path under build_root.

    The one shared staging step:
    the wheel's build hook and the zipapp builder both call it, and it
    writes into a build tree only — never into the repository.
    With repo given, bytes come from that checkout's canonical files;
    without it, from payload_bytes, so a wheel-installed artifact can
    stage a zipapp-shaped tree too.
    """
    build_root = Path(build_root)
    for row in ROWS:
        if repo is not None:
            data = (Path(repo) / row.source).read_bytes()
        else:
            data = payload_bytes(row.id)
        dest = build_root / Path(*row.member.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


# The three exact literal edits the installed codex skill needs:
# the fenced command line points at the neutral checker path,
# the CLAUDE_PLUGIN_ROOT fallback sentence is removed,
# and the relative suppression-section link is rewritten to the
# neutral README path, so it resolves on air-gapped machines too.
SKILL_COMMAND_OLD = (
    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" '
    '--file <files>'
)
SKILL_FALLBACK_LINE = (
    "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at "
    "`../../scripts/check_linefeeds.py` relative to this SKILL.md.)\n\n"
)
SKILL_README_LINK_OLD = "../../README.md"


def render_codex_skill(data_dir):
    """The installed skill body, pinned to the neutral root."""
    if data_dir is None:
        raise ValueError("data_dir cannot be None: no data root "
                         "resolves here")
    data_dir = Path(data_dir)
    text = payload_bytes("codex-skill").decode("utf-8")
    checker = data_dir / CHECKER_NAME
    text = _replace_exactly_once(
        text, SKILL_COMMAND_OLD,
        f'python3 "{checker}" --file <files>', "codex-skill command")
    text = _replace_exactly_once(
        text, SKILL_FALLBACK_LINE, "", "codex-skill fallback line")
    return _replace_exactly_once(
        text, SKILL_README_LINK_OLD, str(data_dir / "README.md"),
        "codex-skill readme link")


def render_codex_hook_entry(data_dir):
    """The one PostToolUse entry the installer merges."""
    if data_dir is None:
        raise ValueError("data_dir cannot be None: no data root "
                         "resolves here")
    data_dir = Path(data_dir)
    text = payload_bytes("codex-hook-template").decode("utf-8")
    checker = data_dir / CHECKER_NAME
    text = _replace_exactly_once(text, "__CHECKER__", str(checker),
                                 "codex hook template")
    return json.loads(text)["hooks"]["PostToolUse"][0]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_registry.py tests/test_installer.py -q`
Expected: `test_registry.py` PASSES.
`test_installer.py` must still pass — the template placeholder change must not break it
(the current installer builds its command in code and never reads the template; verify, don't assume).

- [ ] **Step 6: Full suite and commit**

Run: `python3 -m pytest tests/ -q` — all green.
Run the checker on any touched Markdown.

```bash
git add cli/semlf/registry.py tests/test_registry.py adapters/codex/hooks.json adapters/codex/INSTALL.md
git commit -m "feat(cli): add the declarative payload registry" \
  -m "One table drives packaging, install rendering, and identity
checks, so no consumer invents a second payload mapping.
The codex hook template's placeholder becomes __CHECKER__ carrying
the full checker path; every transform fails loud when its match
count is wrong."
```

---

### Task 3: The three-axis artifact classifier

Admission for every single-file artifact:
object state × provenance state × execution mode,
with adoption, downgrade-refuse-unless-`--force`,
and object-state refusals `--force` never overrides.
This matrix governs INSTALL admission only;
uninstall keeps ADR-0014's removal semantics unchanged (Task 9),
where `--force` may still unlink a symlink, special, or unreadable file.

**Files:**

- Create: `cli/semlf/classify.py`
- Create: `tests/test_classify.py`

**Interfaces:**

- Consumes: `manifest.read_regular_bytes`, `manifest.classify_entry`, `manifest.CLASSIFY_LIMIT`, `manifest.sha256_bytes`.
- Produces:
  - `Verdict` namedtuple: `state, action, detail, snapshot` (snapshot defaults to None; carries the classified bytes for the backup path).
  - `state` ∈ `absent, exact, managed-older, managed-newer, managed-equal, managed-unorderable, edited, unrecorded, symlink, directory, special, unreadable`.
  - `action` ∈ `write, adopt, replace, backup-replace, refuse`.
  - `parse_version(text) -> tuple[int, ...] | None` — dot-separated non-negative integers only.
  - `object_state(dest) -> str` — `absent | regular | symlink | directory | special | unreadable` from one lstat.
  - `classify_artifact(entry, dest, rendered, version, force) -> Verdict` —
    `entry` is the manifest snapshot's entry (or None), `rendered` the exact bytes this machine's transform produces, `version` the running artifact's version string.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_classify.py`:

```python
"""tests/test_classify.py — every cell of the admission matrix, per axis."""
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

from semlf import classify, manifest

RENDERED = b"current rendering\n"
VERSION = "0.7.0"


def entry_for(path, data, version):
    return {"path": str(path), "sha256": manifest.sha256_bytes(data),
            "version": version}


def verdict(dest, entry=None, rendered=RENDERED, version=VERSION,
            force=False):
    return classify.classify_artifact(entry, dest, rendered, version, force)


# --- version ordering -------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("0.7.0", (0, 7, 0)), ("1.0", (1, 0)), ("10", (10,)),
    ("0.7.0rc1", None), ("", None), ("1..2", None), ("-1.0", None),
    (None, None), ("a.b", None),
])
def test_versions_order_as_dot_separated_integer_tuples(text, expected):
    assert classify.parse_version(text) == expected


# --- object-state axis ------------------------------------------------------

def test_absent_writes(tmp_path):
    v = verdict(tmp_path / "a")
    assert (v.state, v.action) == ("absent", "write")


def test_symlink_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.symlink_to(tmp_path / "elsewhere")
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("symlink", "refuse")


def test_directory_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.mkdir()
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("directory", "refuse")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
def test_special_file_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    os.mkfifo(dest)
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("special", "refuse")


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root ignores permission bits")
def test_unreadable_file_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"content\n")
    dest.chmod(0o000)
    try:
        for force in (False, True):
            v = verdict(dest, force=force)
            assert (v.state, v.action) == ("unreadable", "refuse")
    finally:
        dest.chmod(0o644)


def test_oversized_file_is_unreadable_even_with_force(tmp_path, monkeypatch):
    """Over CLASSIFY_LIMIT reads as None through the guarded primitive,
    so the classifier must refuse it as unreadable, force or not."""
    dest = tmp_path / "a"
    dest.write_bytes(b"x" * 32)
    monkeypatch.setattr(manifest, "CLASSIFY_LIMIT", 16)
    for force in (False, True):
        v = verdict(dest, force=force)
        assert (v.state, v.action) == ("unreadable", "refuse")


# --- provenance axis (readable regular file) --------------------------------

def test_exact_rendering_adopts(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(RENDERED)
    v = verdict(dest)
    assert (v.state, v.action) == ("exact", "adopt")


@pytest.mark.parametrize("force", [False, True])
def test_force_does_not_change_the_permissive_cells(tmp_path, force):
    """The design table marks absent, exact, managed-older, and
    managed-equal as `same` under --force: pin all four both ways."""
    dest = tmp_path / "a"
    assert verdict(dest, force=force).action == "write"
    dest.write_bytes(RENDERED)
    assert verdict(dest, force=force).action == "adopt"
    dest.write_bytes(b"older managed bytes\n")
    e = entry_for(dest, b"older managed bytes\n", "0.6.0")
    assert verdict(dest, entry=e, force=force).action == "replace"
    dest.write_bytes(b"equal-version other build\n")
    e = entry_for(dest, b"equal-version other build\n", VERSION)
    assert verdict(dest, entry=e, force=force).action == "replace"


def test_managed_older_replaces_without_force(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"older bytes\n")
    e = entry_for(dest, b"older bytes\n", "0.6.0")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-older", "replace")


def test_managed_newer_refuses_then_forces_a_downgrade(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"newer bytes\n")
    e = entry_for(dest, b"newer bytes\n", "0.8.0")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-newer", "refuse")
    assert "newer than this artifact" in v.detail
    assert "--force" in v.detail
    forced = verdict(dest, entry=e, force=True)
    assert (forced.state, forced.action) == ("managed-newer", "replace")


def test_managed_equal_version_different_bytes_replaces(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"same version other build\n")
    e = entry_for(dest, b"same version other build\n", VERSION)
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-equal", "replace")


def test_managed_unorderable_refuses_then_forces(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"who knows\n")
    e = entry_for(dest, b"who knows\n", "v0.6-beta")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("managed-unorderable", "refuse")
    assert "cannot order" in v.detail
    forced = verdict(dest, entry=e, force=True)
    assert forced.action == "replace"


def test_edited_refuses_then_forces_a_backup_replace(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"hand-patched\n")
    e = entry_for(dest, b"what was recorded\n", "0.6.0")
    v = verdict(dest, entry=e)
    assert (v.state, v.action) == ("edited", "refuse")
    forced = verdict(dest, entry=e, force=True)
    assert (forced.state, forced.action) == ("edited", "backup-replace")
    assert forced.snapshot == b"hand-patched\n"


def test_unrecorded_refuses_then_forces_a_backup_replace(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"no record of this\n")
    v = verdict(dest)
    assert (v.state, v.action) == ("unrecorded", "refuse")
    forced = verdict(dest, force=True)
    assert forced.action == "backup-replace"


def test_occupied_backup_slot_refuses_even_with_force(tmp_path):
    dest = tmp_path / "a"
    dest.write_bytes(b"diverged\n")
    dest.with_name("a.bak").write_bytes(b"already here")
    forced = verdict(dest, force=True)
    assert forced.action == "refuse"
    assert ".bak" in forced.detail
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_classify.py -q`
Expected: collection FAIL — `No module named 'semlf.classify'`.

- [ ] **Step 3: Write the classifier**

Create `cli/semlf/classify.py`:

```python
"""The three-axis artifact classifier (the redesign ADR).

Admission is decided on three independent axes for every single-file
artifact: object state, provenance state, and execution mode.
Force widens the provenance axis only — it never overrides an
object-state refusal, and an occupied backup slot refuses uniformly.
Adoption in the exact-rendering row is deliberate:
publication and record are separate files, so a correct copy with a
missing record must converge to managed on the next run.
The classifier fails closed:
a recorded version that does not parse as dot-separated integers is
unorderable, refused rather than guessed at.
"""
import os
import stat
from collections import namedtuple

from semlf import manifest

Verdict = namedtuple("Verdict", ["state", "action", "detail", "snapshot"])
Verdict.__new__.__defaults__ = (None, None)


def parse_version(text):
    """A dot-separated non-negative integer tuple, or None."""
    if not isinstance(text, str) or not text:
        return None
    parts = text.split(".")
    if not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def object_state(dest):
    """absent | regular | symlink | directory | special | unreadable."""
    try:
        st = os.lstat(dest)
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unreadable"
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    if stat.S_ISDIR(st.st_mode):
        return "directory"
    if not stat.S_ISREG(st.st_mode):
        return "special"
    return "regular"


def classify_artifact(entry, dest, rendered, version, force):
    """One artifact's verdict for this run, read-only.

    entry is the caller's one manifest snapshot's entry for this name
    (or None); rendered is the exact bytes this machine's transform
    produces; version is the running artifact's own version string.
    """
    state = object_state(dest)
    if state == "absent":
        return Verdict("absent", "write", None)
    if state != "regular":
        return Verdict(state, "refuse",
                       f"{dest} is a {state}; move it aside and re-run "
                       "(--force never overrides this)")
    current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
    if current is None:
        return Verdict("unreadable", "refuse",
                       f"{dest} exists but is not a readable regular "
                       "file (--force never overrides this)")
    if current == rendered:
        return Verdict("exact", "adopt", None, current)
    prov = manifest.classify_entry(entry, dest)
    if prov == "managed":
        recorded = parse_version(entry["version"])
        running = parse_version(version)
        if recorded is None or running is None:
            if force:
                return Verdict("managed-unorderable", "replace", None,
                               current)
            return Verdict("managed-unorderable", "refuse",
                           f"{dest}: cannot order the recorded version "
                           f"({entry['version']}) against this "
                           f"artifact's ({version}); rerun with --force "
                           "to replace it")
        if recorded > running:
            if force:
                return Verdict("managed-newer", "replace", None, current)
            return Verdict("managed-newer", "refuse",
                           f"{dest}: published is newer than this "
                           "artifact — rerun with `--force` to "
                           "downgrade")
        state = "managed-older" if recorded < running else "managed-equal"
        return Verdict(state, "replace", None, current)
    # prov is "edited" or "unrecorded"
    if not force:
        return Verdict(prov, "refuse",
                       f"{dest}: its content differs from what this kit "
                       f"installed ({prov}); rerun with --force to back "
                       "it up and replace it")
    bak = dest.with_name(dest.name + ".bak")
    if os.path.lexists(bak):
        return Verdict(prov, "refuse",
                       f"refusing to overwrite {bak}: a backup already "
                       "exists; move it aside and re-run")
    return Verdict(prov, "backup-replace", None, current)
```

Note `dest` must be a `pathlib.Path` for `with_name`; the engine guarantees it.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_classify.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

```bash
git add cli/semlf/classify.py tests/test_classify.py
git commit -m "feat(cli): add the three-axis artifact classifier" \
  -m "Object state, provenance state, and execution mode decide every
single-file admission: adoption on exact rendering, managed
replacement without backups, downgrade refusal unless forced, and
object-state refusals force never overrides."
```

---

### Task 4: Both artifacts embed the registry's payloads

The wheel's build hook and the zipapp builder call the same staging step;
the packaging tests inspect both finished artifacts against the registry.

**Files:**

- Create: `setup.py`
- Create: `MANIFEST.in`
- Modify: `scripts/install.py` (`build_pyz` stages payloads; `PYZ_REQUIRED_MEMBERS` grows from the registry)
- Test: `tests/test_packaging.py` (append)

**Interfaces:**

- Consumes: `registry.ROWS`, `registry.stage_payloads`.
- Produces: wheels and zipapps carrying `semlf/payloads/<id>` members, byte-identical to canonical sources.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packaging.py`:

```python
import io
import os
import shutil
import subprocess
import zipfile

sys.path.insert(0, str(REPO / "cli"))
from semlf import registry


def test_the_pyz_embeds_every_registry_member(tmp_path):
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib
    install = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install.build_pyz(pyz)
    with zipfile.ZipFile(pyz) as z:
        names = set(z.namelist())
        assert {r.member for r in registry.ROWS} <= names
        for row in registry.ROWS:
            assert z.read(row.member) == (REPO / row.source).read_bytes()


def test_pyz_required_members_cover_the_registry():
    import importlib
    sys.path.insert(0, str(REPO / "scripts"))
    install = importlib.import_module("install")
    assert {r.member for r in registry.ROWS} <= install.PYZ_REQUIRED_MEMBERS


def test_payload_bytes_reads_from_inside_a_zipapp(tmp_path):
    """The rendering source works from a pyz install, not only a
    checkout: the archive itself lands on sys.path via zipimport."""
    sys.path.insert(0, str(REPO / "scripts"))
    import importlib
    install = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install.build_pyz(pyz)
    code = ("import sys; sys.path.insert(0, %r); "
            "from semlf import registry; "
            "sys.stdout.buffer.write(registry.payload_bytes('checker'))"
            % str(pyz))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == (REPO / "scripts" / "check_linefeeds.py").read_bytes()


def _setuptools_at_least_61():
    try:
        import setuptools
        return int(setuptools.__version__.split(".")[0]) >= 61
    except Exception:
        return False


def _pip_available():
    r = subprocess.run([sys.executable, "-m", "pip", "--version"],
                       capture_output=True)
    return r.returncode == 0


WHEEL_PREREQS = pytest.mark.skipif(
    not (_setuptools_at_least_61() and _pip_available()),
    reason="wheel build needs pip and setuptools>=61")


# Skips guard only genuinely absent prerequisites, probed up front.
# Once a build starts, ANY backend failure is a test failure —
# a broken setup.py hook or a MANIFEST.in gap must never pass as a skip.
@WHEEL_PREREQS
def test_the_wheel_embeds_every_registry_member(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(REPO), "--no-deps",
         "--no-build-isolation", "-w", str(tmp_path)],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    wheels = list(tmp_path.glob("semlf-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as z:
        names = set(z.namelist())
        assert {r_.member for r_ in registry.ROWS} <= names
        for row in registry.ROWS:
            assert z.read(row.member) == (REPO / row.source).read_bytes()
    # Nothing packaging-only was left in the repository.
    assert not (REPO / "cli" / "semlf" / "payloads").exists()


@WHEEL_PREREQS
def test_a_wheel_built_from_the_sdist_carries_the_members(tmp_path):
    """MANIFEST.in must put every canonical payload source into the
    sdist, or a wheel built from it stages nothing."""
    r = subprocess.run(
        [sys.executable, "setup.py", "sdist", "--dist-dir",
         str(tmp_path)],
        cwd=str(REPO), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    sdists = list(tmp_path.glob("semlf-*.tar.gz"))
    assert len(sdists) == 1
    r = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(sdists[0]),
         "--no-deps", "--no-build-isolation", "-w",
         str(tmp_path / "from-sdist")],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    wheels = list((tmp_path / "from-sdist").glob("semlf-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as z:
        names = set(z.namelist())
        assert {row.member for row in registry.ROWS} <= names
        for row in registry.ROWS:
            assert z.read(row.member) == (REPO / row.source).read_bytes()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_packaging.py -q`
Expected: the pyz test FAILS (members missing);
the wheel test FAILS or skips depending on the environment —
it must fail where setuptools ≥ 61 is present.

- [ ] **Step 3: Implement**

Create `setup.py`:

```python
"""Wheel build hook: stage registry payloads into the build tree.

setuptools reads pyproject.toml for everything declarative;
this file exists only to run the shared staging step after build_py,
so the wheel embeds every semlf/payloads/<id> member without a
packaging copy ever being committed to the repository.
"""
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "cli"))


class build_py_with_payloads(build_py):
    def run(self):
        super().run()
        from semlf import registry
        registry.stage_payloads(Path(self.build_lib), repo=REPO)


setup(cmdclass={"build_py": build_py_with_payloads})
```

Create `MANIFEST.in` (the sdist must carry every canonical payload source so a wheel built from it stages correctly):

```
# Canonical payload sources: the build hook stages these into
# semlf/payloads/<id>, so the sdist must carry every registry source
# even though none of them import as Python code.
include scripts/check_linefeeds.py
include README.md
include LICENSE
include adapters/codex/hooks.json
include adapters/opencode/semantic-linefeeds.ts
include adapters/agentsmd/SNIPPET.md
include skills/semantic-linefeeds/SKILL.md
```

In `scripts/install.py`:

Add `from semlf import registry` beside the existing `from semlf import manifest` import.
Change `PYZ_REQUIRED_MEMBERS` to grow from the registry
(this must come after the import block; move the constant below the imports if needed):

```python
PYZ_REQUIRED_MEMBERS = frozenset(
    {"__main__.py", "check_linefeeds.py",
     "semlf/__init__.py", "semlf/cli.py",
     "semlf/providers.py", "semlf/doctor.py",
     "semlf/manifest.py", "semlf/registry.py",
     "semlf/classify.py"}
    | {row.member for row in registry.ROWS})
```

Copy this block verbatim — it deliberately does NOT list `semlf/lifecycle.py`,
because that module arrives only in Task 5,
and `_snapshot_runnable` requires every listed member to exist
(a member listed before its module exists fails every pyz runnable check).
Task 5 appends `"semlf/lifecycle.py"` to this set as one of its own steps.

In `build_pyz`, after the loop copying `CLI_PKG` sources, add:

```python
        registry.stage_payloads(stage, repo=REPO)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_packaging.py tests/test_installer.py tests/test_doctor.py -q`
Expected: PASS (the doctor tests build pyzs; the grown member set must not break them).

- [ ] **Step 5: Full suite, proof replay, and commit**

Run: `python3 -m pytest tests/ -q` and `sh docs/proofs/zipapp-packaging/verify.sh`.

```bash
git add setup.py MANIFEST.in scripts/install.py tests/test_packaging.py
git commit -m "feat(build): embed registry payloads in both artifacts" \
  -m "A shared staging step reads the registry and places each
canonical source at its member path in the build tree only; the
wheel's build hook and the zipapp builder both call it, and the
packaging tests inspect both finished artifacts against the
registry. No packaging copy is ever committed."
```

---

### Task 5: The lifecycle engine — publisher, preflight, ordered apply

Request-wide preflight then ordered apply,
idempotent rerun, no rollback, no locking;
the published-but-not-recorded half-state is reported by name.

**Files:**

- Create: `cli/semlf/lifecycle.py`
- Create: `tests/test_lifecycle.py`
- Modify: `scripts/install.py`
  (`PYZ_REQUIRED_MEMBERS` gains `semlf/lifecycle.py`;
  `_publish_new`/`_exclusive_backup` become aliases of the moved lifecycle functions)

**Interfaces:**

- Consumes: `classify.classify_artifact`, `classify.Verdict`, `manifest.*` (Task 1 additions included), `registry.*`.
- Produces:
  - `Planned` namedtuple: `label, name, dest, verdict, do, done` —
    `do` is a zero-argument callable or None for a no-op note;
    `done` (optional, defaults None) is the completion line `apply_plan` prints in place of `label`,
    for legs whose pinned disclosure and completion wordings differ.
  - `artifact_version() -> str` — the version of this artifact's own embedded checker payload.
  - `payload_destinations() -> dict[str, Path | None]` —
    keys `checker, readme, codex-skill, opencode-plugin, opencode-checker`.
  - `rendered_bytes(name) -> bytes` — the exact bytes `name`'s transform produces on this machine.
  - `publish_bytes(dest, data)` — same-directory temp file and `os.replace`.
  - `publish_exclusive(staged, dest) -> bool` and `exclusive_backup(src, bak, data)` —
    moved verbatim from `scripts/install.py` (`_publish_new`, `_exclusive_backup`);
    install.py rewires its call sites onto import aliases in this same task, keeping no duplicate.
  - `plan_file(name, force, snapshot, destinations, planned, refusals)` —
    classify one registry single-file artifact into the plan.
  - `apply_file(name, dest, rendered, verdict) -> str | None` —
    publish and record; a non-None return is the half-state note.
  - `apply_plan(planned) -> int` — ordered apply with per-artifact reporting.
  - `describe_plan(planned, refusals, prefix="")` —
    the shared read-only report for the dry run (`prefix="[dry-run] "`),
    the consent prompt, and the full-verdict refusal report.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lifecycle.py`:

```python
"""tests/test_lifecycle.py — preflight admits everything or nothing;
apply converges under any interruption."""
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

from semlf import classify, lifecycle, manifest, registry


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    (tmp_path / "home").mkdir()
    return tmp_path


def plan_names(targets, force=False):
    planned, refusals = [], []
    snapshot = manifest.load()
    destinations = lifecycle.payload_destinations()
    for name in targets:
        lifecycle.plan_file(name, force, snapshot, destinations,
                            planned, refusals)
    return planned, refusals


def test_artifact_version_matches_the_core(home):
    import check_linefeeds
    assert lifecycle.artifact_version() == check_linefeeds.__version__


def test_fresh_apply_publishes_and_records(home, capsys):
    planned, refusals = plan_names(["checker", "readme"])
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    data_dir = manifest.semlf_data_dir()
    assert ((data_dir / "check_linefeeds.py").read_bytes()
            == registry.payload_bytes("checker"))
    assert (data_dir / "README.md").read_bytes() == registry.payload_bytes("readme")
    assert manifest.classify("checker", data_dir / "check_linefeeds.py") == "managed"
    assert manifest.classify("readme", data_dir / "README.md") == "managed"


def test_rerun_is_idempotent_and_adopts_a_missing_record(home, capsys):
    planned, _ = plan_names(["checker"])
    lifecycle.apply_plan(planned)
    dest = manifest.semlf_data_dir() / "check_linefeeds.py"
    manifest.forget("checker")
    planned, refusals = plan_names(["checker"])
    assert refusals == []
    before = dest.read_bytes()
    assert lifecycle.apply_plan(planned) == 0
    assert dest.read_bytes() == before
    assert manifest.classify("checker", dest) == "managed"


def test_one_refusing_artifact_aborts_before_any_write(home, capsys):
    data_dir = manifest.semlf_data_dir()
    data_dir.mkdir(parents=True)
    (data_dir / "README.md").mkdir()  # object-state refusal on readme
    planned, refusals = plan_names(["checker", "readme"])
    assert refusals
    # The engine's caller must not apply when refusals exist;
    # assert nothing was written during planning itself.
    assert not (data_dir / "check_linefeeds.py").exists()


def test_record_side_preflight_refuses_before_any_write(home, capsys):
    state_dir = Path(os.environ["XDG_STATE_HOME"])
    state_dir.mkdir(parents=True)
    (state_dir / "semlf").write_text("a file squatting on the state root")
    planned, refusals = plan_names(["checker"])
    assert refusals and "not a directory" in refusals[0]


def test_half_state_is_reported_by_name_and_a_rerun_converges(
        home, capsys, monkeypatch):
    planned, _ = plan_names(["checker"])
    real_record = manifest.record

    def boom(*args, **kwargs):
        raise OSError("record write failed")

    monkeypatch.setattr(manifest, "record", boom)
    rc = lifecycle.apply_plan(planned)
    err = capsys.readouterr().err
    assert rc == 1
    assert "published" in err and "not record" in err.replace("recorded", "record")
    dest = manifest.semlf_data_dir() / "check_linefeeds.py"
    assert dest.read_bytes() == registry.payload_bytes("checker")
    monkeypatch.setattr(manifest, "record", real_record)
    planned, refusals = plan_names(["checker"])
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert manifest.classify("checker", dest) == "managed"


def test_crossed_interleavings_fail_closed(home):
    """Destination and record written by different runs classify as
    edited — degraded classification, never a silent overwrite."""
    dest = manifest.semlf_data_dir()
    dest.mkdir(parents=True)
    checker = dest / "check_linefeeds.py"
    # (a) destination replaced, record stale.
    checker.write_bytes(b"new bytes the record does not describe\n")
    manifest.record("checker", checker, "0.6.0",
                    manifest.sha256_bytes(b"what an old run staged\n"))
    v = classify.classify_artifact(manifest.load()["checker"], checker,
                                   b"rendered\n", "0.7.0", False)
    assert (v.state, v.action) == ("edited", "refuse")
    # (b) record refreshed, destination old.
    manifest.record("checker", checker, "0.7.0",
                    manifest.sha256_bytes(b"rendered\n"))
    v = classify.classify_artifact(manifest.load()["checker"], checker,
                                   b"rendered but dest still old\n", "0.7.0", False)
    assert (v.state, v.action) == ("edited", "refuse")


def test_forced_replace_of_an_edited_file_takes_an_exclusive_backup(
        home, capsys):
    dest_dir = manifest.semlf_data_dir()
    dest_dir.mkdir(parents=True)
    checker = dest_dir / "check_linefeeds.py"
    checker.write_bytes(b"hand-patched\n")
    planned, refusals = plan_names(["checker"], force=True)
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert checker.read_bytes() == registry.payload_bytes("checker")
    assert (dest_dir / "check_linefeeds.py.bak").read_bytes() == b"hand-patched\n"


def test_a_failed_publication_after_backup_keeps_the_rerun_convergent(
        home, capsys, monkeypatch):
    """A forced backup-replace whose publication fails must not leave
    an occupied backup slot behind: the rerun would refuse forever."""
    dest_dir = manifest.semlf_data_dir()
    dest_dir.mkdir(parents=True)
    checker = dest_dir / "check_linefeeds.py"
    checker.write_bytes(b"hand-patched\n")
    planned, refusals = plan_names(["checker"], force=True)
    assert refusals == []
    real_publish = lifecycle.publish_bytes

    def boom(dest, data):
        raise OSError("publication failed")

    monkeypatch.setattr(lifecycle, "publish_bytes", boom)
    assert lifecycle.apply_plan(planned) == 1
    assert checker.read_bytes() == b"hand-patched\n"
    assert not (dest_dir / "check_linefeeds.py.bak").exists()
    monkeypatch.setattr(lifecycle, "publish_bytes", real_publish)
    planned, refusals = plan_names(["checker"], force=True)
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert checker.read_bytes() == registry.payload_bytes("checker")
    assert (dest_dir / "check_linefeeds.py.bak").read_bytes() == \
        b"hand-patched\n"


def test_adoption_record_failure_reports_the_half_state(
        home, capsys, monkeypatch):
    """Exact rendering with a failing record write is the
    published-but-not-recorded half-state, not a generic error."""
    planned, _ = plan_names(["checker"])
    lifecycle.apply_plan(planned)
    manifest.forget("checker")
    planned, refusals = plan_names(["checker"])
    assert refusals == []

    def boom(*args, **kwargs):
        raise OSError("record failed")

    monkeypatch.setattr(manifest, "record", boom)
    rc = lifecycle.apply_plan(planned)
    err = capsys.readouterr().err
    assert rc == 1
    assert "already correct" in err


def test_managed_replace_skips_the_backup(home, capsys):
    planned, _ = plan_names(["checker"])
    lifecycle.apply_plan(planned)
    dest = manifest.semlf_data_dir() / "check_linefeeds.py"
    # Simulate an older managed release at the destination.
    dest.write_bytes(b"an older managed rendering\n")
    manifest.record("checker", dest, "0.0.1",
                    manifest.sha256_bytes(b"an older managed rendering\n"))
    planned, refusals = plan_names(["checker"])
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert dest.read_bytes() == registry.payload_bytes("checker")
    assert not (manifest.semlf_data_dir() / "check_linefeeds.py.bak").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: collection FAIL — `No module named 'semlf.lifecycle'`.

- [ ] **Step 3: Write the module**

Create `cli/semlf/lifecycle.py`:

```python
"""Shared lifecycle operations behind both doors (the redesign ADR).

`semlf install` and `scripts/install.py` are thin parsers over the
operations here, so the two doors produce byte-identical artifacts
everywhere.
The engine is request-wide preflight then ordered apply:
every artifact of the whole request is classified read-only first, any
refusal aborts the run before the first write, apply follows the
registry's order, provenance is recorded immediately after each
artifact's publication, and the published-but-not-recorded half-state
is reported by name.
Rollback is deliberately not offered; a rerun converges.
Concurrent lifecycle commands stay out of scope (ADR-0014's boundary).
"""
import os
import re
import shutil
import stat
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

from semlf import classify, manifest, registry

Planned = namedtuple("Planned",
                     ["label", "name", "dest", "verdict", "do", "done"])
Planned.__new__.__defaults__ = (None,)
# label is the DISCLOSURE line (plans, prompts, dry runs);
# done, when set, is the COMPLETION line apply_plan prints instead —
# a leg whose pinned outputs differ between "would install" and
# "installed" carries both, and a leg with one voice sets only label.

_VERSION_RE = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


def artifact_version():
    """The version of this artifact's own embedded checker payload.

    Read textually so nothing is imported;
    on the checkout door this is the canonical core file, so both doors
    agree by construction.
    """
    text = registry.payload_bytes("checker").decode("utf-8")
    match = _VERSION_RE.search(text)
    return match.group(1) if match else "unknown"


def payload_destinations():
    """Each recorded single-file artifact's destination, or None entries.

    Derived from the registry rows — never a hand-maintained mapping.
    """
    return {row.id: row.dest() for row in registry.ROWS if row.recorded}


def rendered_bytes(name):
    """The exact bytes name's transform produces on this machine.

    Callers refuse a None destination before rendering, and every
    row whose rendering needs the data root has a destination that
    resolves exactly when the data root does, so the ValueError the
    codex-skill renderer raises on a None data root marks a caller
    bug, not a user-facing path.
    """
    return registry.BY_ID[name].render(manifest.semlf_data_dir())


# --- publication primitives -------------------------------------------------
# publish_exclusive and exclusive_backup move here verbatim from
# scripts/install.py (_publish_new, _exclusive_backup), docstrings
# included; install.py imports them back so the cli verb keeps its
# exact behavior.


def publish_bytes(dest, data):
    """Atomic complete-file publication: same-directory temp, os.replace."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)
    except BaseException:
        os.unlink(tmp)
        raise


def _describe(name, dest, verdict):
    if verdict.action == "write":
        return f"{name}: install {dest}"
    if verdict.action == "adopt":
        return f"{name}: up to date ({dest})"
    if verdict.action == "backup-replace":
        return f"{name}: back up and replace {dest} ({verdict.state})"
    return f"{name}: replace {dest} ({verdict.state})"


def plan_file(name, force, snapshot, destinations, planned, refusals):
    """Classify one registry single-file artifact into the plan."""
    dest = destinations[name]
    if dest is None:
        refusals.append(f"refusing to install {name}: cannot determine "
                        "a home directory to install it under.")
        return
    rendered = rendered_bytes(name)
    verdict = classify.classify_artifact(snapshot.get(name), dest,
                                         rendered, artifact_version(),
                                         force)
    if verdict.action == "refuse":
        refusals.append(verdict.detail)
        return
    record_trouble = manifest.record_preflight(name)
    if record_trouble is not None:
        refusals.append(f"refusing to install {name}: {record_trouble}")
        return

    def _do(name=name, dest=dest, rendered=rendered, verdict=verdict):
        return apply_file(name, dest, rendered, verdict)

    planned.append(Planned(_describe(name, dest, verdict), name, dest,
                           verdict, _do))


def apply_file(name, dest, rendered, verdict):
    """Publish one classified artifact and record it.

    Returns None on success, or the published-but-not-recorded
    half-state note when the record write failed after publication —
    the destination is correct, and a rerun adopts the missing record.
    """
    if verdict.action == "adopt":
        try:
            manifest.record(name, dest, artifact_version(),
                            manifest.sha256_bytes(rendered))
        except OSError as exc:
            return (f"{name}: {dest} is already correct, but its "
                    f"provenance could not be recorded: {exc}; "
                    "a re-run records it")
        return None
    if verdict.action == "backup-replace":
        bak = dest.with_name(dest.name + ".bak")
        exclusive_backup(dest, bak, verdict.snapshot)
        try:
            publish_bytes(dest, rendered)
        except BaseException:
            # This attempt's backup must not poison the slot: the
            # destination is unchanged (publication failed before its
            # os.replace), so removing the backup keeps the rerun
            # convergent instead of refusing on an occupied slot.
            os.unlink(bak)
            raise
    elif verdict.action == "write":
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, staged_name = tempfile.mkstemp(dir=str(dest.parent),
                                           prefix=dest.name)
        with os.fdopen(fd, "wb") as fh:
            fh.write(rendered)
        if not publish_exclusive(Path(staged_name), dest):
            raise OSError(f"{dest} appeared after classification; "
                          "re-run so it can be classified")
    else:
        publish_bytes(dest, rendered)
    try:
        manifest.record(name, dest, artifact_version(),
                        manifest.sha256_bytes(rendered))
    except OSError as exc:
        return (f"{name}: published {dest} but could not record its "
                f"provenance: {exc}; a re-run records it")
    return None


def apply_plan(planned):
    """Ordered apply with per-artifact reporting; 0 clean, 1 otherwise."""
    had_error = False
    completed = []
    for i, item in enumerate(planned):
        if item.do is None:
            print(item.label)
            continue
        try:
            note = item.do()
        except OSError as exc:
            remaining = [p.label for p in planned[i + 1:]
                         if p.do is not None]
            print(f"error while applying {item.label}: {exc}",
                  file=sys.stderr)
            print("applied: "
                  + (", ".join(completed) if completed else "(nothing)"),
                  file=sys.stderr)
            print("not applied: " + ", ".join([item.label] + remaining),
                  file=sys.stderr)
            print("a re-run converges: completed artifacts no-op, "
                  "incomplete ones are attempted again.", file=sys.stderr)
            return 1
        if note:
            print(note, file=sys.stderr)
            had_error = True
        else:
            print(item.done or item.label)
        completed.append(item.label)
    return 1 if had_error else 0


def describe_plan(planned, refusals, prefix=""):
    """The read-only report every disclosure path shares.

    The dry run passes prefix="[dry-run] " so scripts keep a stable
    marker to grep for; the consent prompt and the refusal report
    print the same lines bare.
    A refusing request reports every artifact's verdict, not only the
    refusals — the admissible legs are part of the disclosure.
    """
    for item in planned:
        print(prefix + item.label)
    for refusal in refusals:
        print(f"{prefix}would refuse: {refusal}")
```

Move `_publish_new` and `_exclusive_backup` from `scripts/install.py` into this module
as `publish_exclusive` and `exclusive_backup` (bodies and docstrings verbatim, names updated),
and delete the originals from `scripts/install.py` in the same edit,
replacing them with aliases so every existing call site —
and the tests that monkeypatch `install._exclusive_backup` —
keeps working unchanged:

```python
from semlf.lifecycle import (  # noqa: E402
    exclusive_backup as _exclusive_backup,
    publish_exclusive as _publish_new,
)
```

Place the import beside the existing `from semlf import manifest` block;
no duplicate implementation survives this task.

Add `"semlf/lifecycle.py"` to `PYZ_REQUIRED_MEMBERS` in `scripts/install.py`
(Task 4 deliberately left it out because this module did not exist yet).

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_lifecycle.py tests/test_packaging.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

```bash
git add cli/semlf/lifecycle.py tests/test_lifecycle.py scripts/install.py
git commit -m "feat(cli): add the shared lifecycle engine" \
  -m "Request-wide preflight then ordered apply over classifier
verdicts: any refusal aborts before the first write, provenance is
recorded immediately after each publication, and the
published-but-not-recorded half-state is reported by name so a
rerun converges. No rollback, no locking (ADR-0014's boundary)."
```

---

### Task 6: The codex hook and agentsmd snippet plans

The two shared-file artifacts keep their own admission rules —
structural for the hook, sentinel-block for the snippet —
folded into the same preflight-then-apply engine.

**Files:**

- Modify: `cli/semlf/lifecycle.py`
- Test: `tests/test_lifecycle.py` (append)

**Interfaces:**

- Consumes: `registry.render_codex_hook_entry`, `manifest.owned_codex_hooks`, `manifest.read_state_json`, `publish_bytes`.
- Produces:
  - `SENTINEL_OPEN`, `SENTINEL_CLOSE` — moved from `scripts/install.py`.
  - `TRUST_NOTE` — moved from `scripts/install.py`.
  - `plan_codex_hook(planned, refusals)` — merge or update the PostToolUse entry, read-only planning.
  - `plan_agentsmd(target: Path, planned, refusals)` — sentinel-block splice, read-only planning.
  - `agents_block() -> str` — the sentinel-wrapped snippet body from the registry payload.
  - `bak_sibling_ok(path) -> bool` — moved from `scripts/install.py` (`_bak_sibling_ok`).
  - `publish_shared(path, text)` —
    the shared-merged-file publisher, ported from install.py's `atomic_write`:
    backs an existing regular file up to `<name>.bak` (last-run-wins) before replacing,
    raises `OSError` when the slot holds a non-regular object.
    The managed-replacements-skip-backups rule covers provenance-managed single files only;
    shared merged files keep their backup, exactly as today.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lifecycle.py`:

```python
def hook_path():
    return Path(os.environ["CODEX_HOME"]) / "hooks.json"


def plan_hook():
    planned, refusals = [], []
    lifecycle.plan_codex_hook(planned, refusals)
    return planned, refusals


def test_hook_plan_creates_a_fresh_hooks_json(home, capsys):
    planned, refusals = plan_hook()
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    import json
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    owned = manifest.owned_codex_hooks(data)
    assert len(owned) == 1
    checker = str(manifest.semlf_data_dir() / "check_linefeeds.py")
    assert owned[0][1] == checker


def test_hook_plan_updates_a_stale_path_and_preserves_foreign_entries(
        home, capsys):
    import json
    hook_path().parent.mkdir(parents=True)
    hook_path().write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "shell",
         "hooks": [{"type": "command", "command": "echo hi"}]},
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": 'python3 "/old/clone/scripts/check_linefeeds.py"'
                        ' --hook codex'}]},
    ]}}), encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals == []
    lifecycle.apply_plan(planned)
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    commands = [h["hooks"][0]["command"]
                for h in data["hooks"]["PostToolUse"]]
    assert commands[0] == "echo hi"
    assert "/old/clone/" not in commands[1]
    assert str(manifest.semlf_data_dir()) in commands[1]


def test_hook_plan_noops_when_current(home, capsys):
    planned, _ = plan_hook()
    lifecycle.apply_plan(planned)
    before = hook_path().read_text(encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals == []
    assert all(item.do is None for item in planned)
    lifecycle.apply_plan(planned)
    assert hook_path().read_text(encoding="utf-8") == before


def test_hook_plan_refuses_unparseable_json(home):
    hook_path().parent.mkdir(parents=True)
    hook_path().write_text("{not json", encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals and "hand" in refusals[0]


def test_hook_plan_is_total_over_hostile_parseable_shapes(home, capsys):
    """{"hooks": 7} and a non-dict block must be planned around and
    preserved exactly, never raise TypeError mid-preflight."""
    import json
    hook_path().parent.mkdir(parents=True)
    hostile = {"hooks": {"PostToolUse": [
        None, {"hooks": 7}, {"matcher": "apply_patch"}]}}
    hook_path().write_text(json.dumps(hostile), encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals == []
    lifecycle.apply_plan(planned)
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    post = data["hooks"]["PostToolUse"]
    assert post[:3] == hostile["hooks"]["PostToolUse"]
    assert len(manifest.owned_codex_hooks(data)) == 1


def test_an_up_to_date_hook_ignores_a_hostile_backup_slot(home, capsys):
    """A no-op writes nothing, so a symlink squatting on hooks.json.bak
    must not break clean idempotence."""
    planned, _ = plan_hook()
    lifecycle.apply_plan(planned)
    bak = hook_path().with_name("hooks.json.bak")
    if bak.exists():
        bak.unlink()
    bak.symlink_to(hook_path().parent / "elsewhere")
    planned, refusals = plan_hook()
    assert refusals == []
    assert all(item.do is None for item in planned)
    # A stale hook with the same hostile slot still refuses.
    import json
    data = json.loads(hook_path().read_text(encoding="utf-8"))
    data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] = (
        'python3 "/old/check_linefeeds.py" --hook codex')
    hook_path().write_text(json.dumps(data), encoding="utf-8")
    planned, refusals = plan_hook()
    assert refusals and ".bak" in refusals[0]


def test_hook_merge_backs_up_the_shared_file(home, capsys):
    """Shared merged files keep their .bak — the skip-backups rule is
    for provenance-managed single files only."""
    import json
    hook_path().parent.mkdir(parents=True)
    hook_path().write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "shell",
         "hooks": [{"type": "command", "command": "echo hi"}]}]}}),
        encoding="utf-8")
    before = hook_path().read_bytes()
    planned, _ = plan_hook()
    lifecycle.apply_plan(planned)
    bak = hook_path().with_name("hooks.json.bak")
    assert bak.read_bytes() == before


def test_agentsmd_plan_writes_and_reruns_clean(home, tmp_path, capsys):
    target = tmp_path / "AGENTS.md"
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    assert refusals == []
    lifecycle.apply_plan(planned)
    text = target.read_text(encoding="utf-8")
    assert lifecycle.SENTINEL_OPEN in text and lifecycle.SENTINEL_CLOSE in text
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    assert refusals == []
    assert all(item.do is None for item in planned)


def test_agentsmd_plan_refuses_a_broken_sentinel_pair(home, tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(lifecycle.SENTINEL_OPEN + "\nno close",
                      encoding="utf-8")
    planned, refusals = [], []
    lifecycle.plan_agentsmd(target, planned, refusals)
    assert refusals and "sentinel" in refusals[0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: FAIL — `plan_codex_hook`/`plan_agentsmd` do not exist yet.

- [ ] **Step 3: Implement**

Add to `cli/semlf/lifecycle.py` (port the logic from `scripts/install.py`,
split into read-only planning and an apply closure; key differences called out):

```python
SENTINEL_OPEN = "<!-- semantic-linefeeds -->"
SENTINEL_CLOSE = "<!-- /semantic-linefeeds -->"

TRUST_NOTE = ("note: Codex hashes unmanaged hooks; on your next "
              "interactive codex run it will ask you to trust this "
              "hook — accept it once.")


def bak_sibling_ok(path):
    """Whether path's .bak sibling is absent or a plain regular file."""
    bak = path.with_name(path.name + ".bak")
    try:
        return (not os.path.lexists(bak)
                or stat.S_ISREG(os.lstat(bak).st_mode))
    except OSError:
        return False


def plan_codex_hook(planned, refusals):
    """Plan the PostToolUse merge into $CODEX_HOME/hooks.json.

    Structural admission, no provenance record:
    ownership is parse_managed_codex_hook over the shared file, never
    per-file bytes, and foreign entries are preserved exactly.
    """
    import json
    home = manifest.codex_home()
    data_dir = manifest.semlf_data_dir()
    if home is None or data_dir is None:
        refusals.append("refusing to install the codex hook: cannot "
                        "determine a home directory to install it under.")
        return
    entry = registry.render_codex_hook_entry(data_dir)
    command = entry["hooks"][0]["command"]
    path = home / "hooks.json"
    if not os.path.lexists(path):
        data = {"hooks": {"PostToolUse": [entry]}}
        label = f"codex hook: create {path}"
    else:
        data = manifest.read_state_json(path)
        if data is None or not isinstance(data, dict):
            refusals.append(f"refusing to touch {path}: cannot read or "
                            "parse it; merge the entry from the codex "
                            "adapter template by hand.")
            return
        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            refusals.append(f"refusing to touch {path}: cannot parse "
                            "it; repair it by hand.")
            return
        post = hooks.setdefault("PostToolUse", [])
        if not isinstance(post, list):
            refusals.append(f"refusing to touch {path}: cannot parse "
                            "it; repair it by hand.")
            return
        # Guard every nested level before iterating: a parseable but
        # hostile shape ({"hooks": 7}, a non-dict block) must plan
        # around the garbage, never raise TypeError mid-preflight.
        ours = [h for block in post if isinstance(block, dict)
                and isinstance(block.get("hooks"), list)
                for h in block["hooks"]
                if isinstance(h, dict)
                and manifest.parse_managed_codex_hook(
                    block.get("matcher"), h) is not None]
        if ours and all(h["command"] == command for h in ours):
            # The no-op is decided BEFORE backup-slot admission:
            # an up-to-date hook writes nothing, so a hostile unused
            # .bak must not turn clean idempotence into a refusal.
            planned.append(Planned(
                f"codex hook: up to date ({path})",
                "codex-hook", path, None, None))
            return
        if not bak_sibling_ok(path):
            bak = path.with_name(path.name + ".bak")
            refusals.append(f"refusing to touch {path}: its backup slot "
                            f"{bak} exists and is not a regular file; "
                            "move it aside and re-run.")
            return
        if ours:
            for h in ours:
                h["command"] = command
            label = f"codex hook: update the checker path in {path}"
        else:
            post.append(entry)
            label = f"codex hook: append the PostToolUse entry to {path}"
    text = json.dumps(data, indent=2) + "\n"

    def _do(path=path, text=text):
        publish_shared(path, text)
        print(TRUST_NOTE)
        return None

    planned.append(Planned(label, "codex-hook", path, None, _do))
```

Add the shared-file publisher the hook and snippet plans both use
(the design's managed-replacements-skip-backups rule covers provenance-managed single-file artifacts only,
so shared merged files keep today's backup semantics):

```python
def publish_shared(path, text):
    """atomic_write for a shared merged file (hooks.json, AGENTS.md).

    Ported from install.py's atomic_write with semantics unchanged:
    an existing regular file is first copied to <name>.bak —
    last-run-wins, because the next run re-merges the shared file,
    so the backup is never the only copy of anything — and a
    non-regular object in the slot raises OSError instead of being
    written through.
    Publication is the same-directory temp file and os.replace.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_name(path.name + ".bak")
        try:
            bak_mode = os.lstat(bak).st_mode
        except FileNotFoundError:
            bak_mode = None
        if bak_mode is not None and not stat.S_ISREG(bak_mode):
            raise OSError(f"backup slot {bak} exists and is not a "
                          "regular file; move it aside and re-run")
        shutil.copy2(path, bak)
    publish_bytes(path, text.encode("utf-8"))
```

Then port `install_agentsmd` + `_plan_agentsmd` into one read-only planner:

```python
def agents_block():
    body = registry.payload_bytes("agentsmd-snippet").decode("utf-8")
    return f"{SENTINEL_OPEN}\n{body.rstrip()}\n{SENTINEL_CLOSE}\n"


def plan_agentsmd(target, planned, refusals):
    """Plan the sentinel-block splice into the user-named file.

    Sentinel admission in a user-owned file:
    force never overrides a refusal here, and every malformed-sentinel
    shape is a repair-by-hand refusal, exactly as before.
    """
    ...
```

The body reproduces `install_agentsmd`'s admission chain
(lexists → `read_regular_bytes` → UTF-8 decode → sentinel pairing/count/order checks → build `new` text),
appending refusal strings for each refusing branch
and a `Planned` whose `do` closure calls `publish_shared(target, new)`.
An up-to-date block appends a `Planned` with `do=None` and label `f"agentsmd: already up to date ({target})"`.
An absent file plans `new = agents_block()`.
Copy the exact splice arithmetic from `install_agentsmd`
(the `pre + block + post` reconstruction and the trailing-newline handling)
so installed output stays byte-identical.
Port `_semlf_note` too — the `do` closure and the up-to-date branch both end by printing it —
with its command updated for the package-first story
(the "not on PATH" phrase is pinned by an existing test and stays):

```python
def _semlf_note():
    if shutil.which("semlf") is None:
        print("note: semlf is not on PATH; the snippet's check "
              "command needs it. install it with `uv tool install "
              "semlf` (or `pipx install semlf`).")
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

```bash
git add cli/semlf/lifecycle.py tests/test_lifecycle.py
git commit -m "feat(cli): plan hook merge and snippet splice" \
  -m "The codex hook keeps structural admission over the shared
hooks.json and the agentsmd snippet keeps sentinel admission in a
user-owned file, both folded into the preflight-then-apply engine.
Shared merged files keep their .bak backup and the occupied-slot
guard still refuses a hostile backup slot; planning is total over
hostile parseable shapes."
```

---

### Task 7: The `semlf install` command

Detection, plan disclosure, consent, `--dry-run` dominance,
the PATH shim warning, and the Claude Code trailer.

**Files:**

- Modify: `cli/semlf/lifecycle.py` (commands and helpers)
- Modify: `cli/semlf/cli.py` (routing and USAGE)
- Create: `tests/test_semlf_install.py`

**Interfaces:**

- Consumes: everything from Tasks 5–6.
- Produces:
  - `run(command, argv) -> int` —
    dispatch for `install`, `status`, `uninstall` (status and uninstall bodies land in Tasks 8–9; until then `run` routes only `install` and returns 64 otherwise).
  - `install_command(argv) -> int`.
  - `detect_agents() -> list[tuple[str, str]]` — moved verbatim from `scripts/install.py`.
  - `plan_install(targets, agentsmd_path, force) -> (planned, refusals)` —
    targets in registry order, neutral payloads first.
  - `claude_code_trailer()` — prints the marketplace pair when `claude` is on PATH or `~/.claude` exists.
  - `shim_warning()` — warns when `semlf` on PATH is not the running artifact.
  - `_parse_targets(argv, verb, allowed_flags)` —
    shared by install and uninstall; returns `(targets, agentsmd_path, flags)` or None after printing a usage error.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_semlf_install.py`:

```python
"""tests/test_semlf_install.py — the package door's command surface."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

BOOTSTRAP = ("import sys; sys.path[:0] = [%r, %r]; "
             "from semlf.cli import main; sys.exit(main(sys.argv[1:]))"
             % (str(REPO / "cli"), str(REPO / "scripts")))


def isolated_env(tmp_path, path=""):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"HOME": str(home),
            "CODEX_HOME": str(tmp_path / "codex"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "PATH": path}


def run_semlf(args, env_overrides, stdin_text=""):
    env = os.environ.copy()
    env["PATH"] = ""
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", BOOTSTRAP] + args,
                          input=stdin_text, capture_output=True,
                          text=True, env=env, timeout=60)


def data_root(tmp_path):
    return tmp_path / "data" / "semlf"


def test_named_target_is_consent_and_applies(tmp_path):
    r = run_semlf(["install", "codex"], isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (data_root(tmp_path) / "check_linefeeds.py").read_bytes() == (
        REPO / "scripts" / "check_linefeeds.py").read_bytes()
    assert (data_root(tmp_path) / "README.md").exists()
    hooks = json.loads((tmp_path / "codex" / "hooks.json").read_text())
    command = hooks["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert str(data_root(tmp_path) / "check_linefeeds.py") in command
    skill = tmp_path / "home" / ".agents" / "skills" / \
        "semantic-linefeeds" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert str(data_root(tmp_path) / "check_linefeeds.py") in body
    assert str(data_root(tmp_path) / "README.md") in body


def test_apply_order_puts_neutral_payloads_first(tmp_path):
    r = run_semlf(["install", "codex"], isolated_env(tmp_path))
    out = r.stdout
    assert out.index("checker") < out.index("codex hook")


def test_non_tty_detection_without_yes_prints_plan_and_exits_one(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "codex").mkdir()  # codex detected by directory evidence
    r = run_semlf(["install"], env)
    assert r.returncode == 1
    assert "--yes" in r.stdout + r.stderr
    assert not data_root(tmp_path).exists()


def test_yes_applies_in_detection_mode(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "codex").mkdir()
    r = run_semlf(["install", "--yes"], env)
    assert r.returncode == 0, r.stderr
    assert (data_root(tmp_path) / "check_linefeeds.py").exists()


def test_zero_detection_is_an_explicit_noop(tmp_path):
    r = run_semlf(["install"], isolated_env(tmp_path))
    assert r.returncode == 0
    assert "no supported agents detected" in r.stdout.lower()


def test_dry_run_dominates_and_writes_nothing(tmp_path):
    env = isolated_env(tmp_path)
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert not data_root(tmp_path).exists()
    assert not (tmp_path / "codex" / "hooks.json").exists()


def test_dry_run_reports_a_would_be_refusal_at_exit_zero(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched",
                                             encoding="utf-8")
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert "would refuse" in r.stdout
    assert (root / "check_linefeeds.py").read_text(
        encoding="utf-8") == "hand-patched"


def test_a_refusal_without_dry_run_aborts_the_whole_request(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched",
                                             encoding="utf-8")
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert not (tmp_path / "codex" / "hooks.json").exists()
    assert not (root / "README.md").exists()


def test_force_replaces_with_an_exclusive_backup(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("hand-patched",
                                             encoding="utf-8")
    r = run_semlf(["install", "codex", "--force"], env)
    assert r.returncode == 0, r.stderr
    assert (root / "check_linefeeds.py.bak").read_text(
        encoding="utf-8") == "hand-patched"


def test_agentsmd_requires_an_explicit_path(tmp_path):
    r = run_semlf(["install", "agentsmd"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_agentsmd_with_a_path_is_first_class(tmp_path):
    target = tmp_path / "AGENTS.md"
    r = run_semlf(["install", "agentsmd", str(target)],
                  isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "semantic-linefeeds" in target.read_text(encoding="utf-8")


def test_unknown_target_is_a_usage_error(tmp_path):
    r = run_semlf(["install", "codey"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_shim_mismatch_is_warned_about(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "semlf"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    env = isolated_env(tmp_path, path=str(bindir))
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0
    assert "resolves to" in r.stdout + r.stderr


def test_claude_trailer_appears_last_when_claude_is_present(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0
    tail = r.stdout.strip().splitlines()[-3:]
    assert any("marketplace" in line for line in tail)


def test_trailer_ends_dry_run_and_refusal_outputs_too(tmp_path):
    env = isolated_env(tmp_path)
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0 and "marketplace" in r.stdout
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("x", encoding="utf-8")
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1 and "marketplace" in r.stdout


def test_a_refusing_request_still_names_every_verdict(tmp_path):
    env = isolated_env(tmp_path)
    root = data_root(tmp_path)
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("x", encoding="utf-8")
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    # The admissible legs are disclosed alongside the refusal.
    assert "readme" in r.stdout and "codex hook" in r.stdout


def test_dry_run_output_carries_the_dry_run_marker(tmp_path):
    r = run_semlf(["install", "codex", "--dry-run"],
                  isolated_env(tmp_path))
    assert "[dry-run] " in r.stdout


def test_subcommand_help_prints_usage_and_exits_zero(tmp_path):
    for cmd in ("install", "status", "uninstall"):
        r = run_semlf([cmd, "--help"], isolated_env(tmp_path))
        assert r.returncode == 0, cmd
        assert "usage: semlf" in r.stdout
```

Add in-process TTY-consent tests to `tests/test_lifecycle.py`:

```python
@pytest.mark.parametrize("name", ["checker", "readme", "codex-skill",
                                  "opencode-plugin",
                                  "opencode-checker"])
def test_every_registry_row_reaches_the_classifier(home, name, capsys):
    """Each recorded row classifies through its own registry
    destination and rendering — edited refuses, managed-older
    replaces, exact adopts — so no row can bypass the matrix."""
    targets = ["codex", "opencode"]
    planned, refusals = lifecycle.plan_install(targets, None, False)
    assert refusals == []
    lifecycle.apply_plan(planned)
    dest = lifecycle.payload_destinations()[name]
    dest.write_bytes(b"hand-patched\n")
    manifest.forget(name)
    planned, refusals = lifecycle.plan_install(targets, None, False)
    assert any(str(dest) in r for r in refusals)
    manifest.record(name, dest, "0.0.1",
                    manifest.sha256_bytes(b"hand-patched\n"))
    planned, refusals = lifecycle.plan_install(targets, None, False)
    assert refusals == []
    assert lifecycle.apply_plan(planned) == 0
    assert dest.read_bytes() == lifecycle.rendered_bytes(name)
    assert manifest.classify(name, dest) == "managed"


def test_tty_prompt_answered_n_declines(home, capsys, monkeypatch):
    (Path(os.environ["CODEX_HOME"])).mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    rc = lifecycle.install_command([])
    assert rc == 1
    assert not (manifest.semlf_data_dir() / "check_linefeeds.py").exists()


def test_tty_prompt_eof_declines(home, capsys, monkeypatch):
    (Path(os.environ["CODEX_HOME"])).mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert lifecycle.install_command([]) == 1


def test_tty_prompt_y_applies(home, capsys, monkeypatch):
    (Path(os.environ["CODEX_HOME"])).mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert lifecycle.install_command([]) == 0
    assert (manifest.semlf_data_dir() / "check_linefeeds.py").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_semlf_install.py tests/test_lifecycle.py -q`
Expected: FAIL — `install` is not a `semlf` subcommand yet.

- [ ] **Step 3: Implement**

In `cli/semlf/cli.py`, add after the `doctor` dispatch:

```python
    if argv[:1] and argv[0] in ("install", "status", "uninstall"):
        if argv[1:2] and argv[1] in ("--help", "-h"):
            print(USAGE, end="")
            return 0
        from semlf import lifecycle
        return lifecycle.run(argv[0], argv[1:])
```

(`semlf install --help` must print usage and exit 0,
not fall into `_parse_targets` and die with a 64 on an "unknown flag".)

Extend `USAGE` with the new modes and the consent rule stated plainly:

```
  install [TARGET...]    detect agents, list every path the plan writes, ask y/N;
                         naming a target (codex, opencode, agentsmd PATH) applies it immediately
  status [agentsmd PATH] report every discoverable or recorded artifact's state
  uninstall TARGET...    preflight-then-apply removal of a target's artifacts
options: install takes --yes, --dry-run, --force; uninstall takes --dry-run, --force
```

In `cli/semlf/lifecycle.py`, add `detect_agents` (moved verbatim from `scripts/install.py`) and:

```python
def _parse_targets(argv, verb, allowed_flags):
    """(ordered targets, agentsmd_path, flags) or None after a usage error."""
    targets = []
    agentsmd_path = None
    flags = {"yes": False, "dry_run": False, "force": False}
    by_flag = {"--yes": "yes", "--dry-run": "dry_run", "--force": "force"}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in by_flag and by_flag[arg] in allowed_flags:
            flags[by_flag[arg]] = True
        elif arg in ("codex", "opencode"):
            if arg not in targets:
                targets.append(arg)
        elif arg == "agentsmd":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                print(f"semlf {verb}: agentsmd requires an explicit "
                      "path; refusing to default one.", file=sys.stderr)
                return None
            i += 1
            agentsmd_path = Path(argv[i])
        else:
            print(f"semlf {verb}: unknown target or flag {arg!r}",
                  file=sys.stderr)
            return None
        i += 1
    return targets, agentsmd_path, flags


def plan_install(targets, agentsmd_path, force):
    """The whole request's plan, walked in the registry's own order.

    The apply order comes from the rows' order field —
    the neutral checker and readme first, then each integration's own
    files — never from a hand-maintained call sequence here.
    """
    planned, refusals = [], []
    snapshot = manifest.load()
    destinations = payload_destinations()
    for row in registry.ROWS:
        if row.recorded and row.owner in targets:
            plan_file(row.id, force, snapshot, destinations,
                      planned, refusals)
        elif row.id == "codex-hook-template" and "codex" in targets:
            plan_codex_hook(planned, refusals)
        elif (row.id == "agentsmd-snippet"
                and agentsmd_path is not None):
            plan_agentsmd(agentsmd_path, planned, refusals)
    return planned, refusals


def claude_code_trailer():
    """The marketplace pair, visually set off as the last block."""
    home = os.path.expanduser("~")
    has_dir = home != "~" and (Path(home) / ".claude").exists()
    if not (shutil.which("claude") or has_dir):
        return
    print("")
    print("Claude Code is managed by its own plugin marketplace — "
          "semlf never touches it:")
    print("  claude plugin marketplace add "
          "https://github.com/arloliu/semantic-linefeeds")
    print("  claude plugin install semantic-linefeeds@semantic-linefeeds")


def shim_warning():
    """Warn when `semlf` on PATH is not the artifact that ran this."""
    resolved = shutil.which("semlf")
    if resolved is None:
        return
    try:
        if os.path.realpath(resolved) != os.path.realpath(sys.argv[0]):
            print(f"warning: `semlf` on PATH resolves to {resolved}, "
                  "not this artifact; a pre-redesign zipapp or a second "
                  "channel may be shadowing it. remove it with the "
                  "checkout door (install.py --uninstall --cli) or the "
                  "other package manager.")
    except OSError:
        pass


def _finish(rc):
    """Every valid install/status outcome ends with the trailer.

    The design pins the marketplace block as the LAST block of the
    output, so success, dry run, refusal, and a declined prompt all
    route through here; only usage errors (64) skip it.
    """
    claude_code_trailer()
    return rc


def install_command(argv):
    parsed = _parse_targets(argv, "install",
                            ("yes", "dry_run", "force"))
    if parsed is None:
        return 64
    targets, agentsmd_path, flags = parsed
    named = bool(targets or agentsmd_path is not None)
    if not named:
        detected = detect_agents()
        for agent, evidence in detected:
            print(f"{agent}: detected ({evidence})")
        if not detected:
            print("semlf install: no supported agents detected; "
                  "nothing to do.")
            return _finish(0)
        targets = [agent for agent, _ in detected]
    planned, refusals = plan_install(targets, agentsmd_path,
                                     flags["force"])
    if flags["dry_run"]:
        describe_plan(planned, refusals, prefix="[dry-run] ")
        return _finish(0)
    if refusals:
        # A refusing request reports every artifact's verdict,
        # not only the refusals (the design's disclosure rule).
        describe_plan(planned, [])
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return _finish(1)
    if not named and not flags["yes"]:
        describe_plan(planned, refusals)
        if not sys.stdin.isatty():
            print("semlf install: not a terminal; re-run with --yes "
                  "to apply this plan.", file=sys.stderr)
            return _finish(1)
        try:
            answer = input("apply this plan? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            print("")
            return _finish(1)
        if answer.strip().lower() not in ("y", "yes"):
            return _finish(1)
    rc = apply_plan(planned)
    shim_warning()
    return _finish(rc)


def run(command, argv):
    if command == "install":
        return install_command(argv)
    if command == "status":
        return status_command(argv)
    if command == "uninstall":
        return uninstall_command(argv)
    return 64
```

Until Tasks 8–9 land, add stubs so `run` stays importable:

```python
def status_command(argv):
    print("semlf status: not implemented yet", file=sys.stderr)
    return 64


def uninstall_command(argv):
    print("semlf uninstall: not implemented yet", file=sys.stderr)
    return 64
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_semlf_install.py tests/test_lifecycle.py tests/test_semlf_cli.py -q`
Expected: PASS (`test_semlf_cli.py` guards that routing did not disturb check/git/hook modes).

- [ ] **Step 5: Full suite and commit**

```bash
git add cli/semlf/lifecycle.py cli/semlf/cli.py tests/test_semlf_install.py tests/test_lifecycle.py
git commit -m "feat(cli): add the semlf install command" \
  -m "Detection prints its evidence, the plan names every path it
would write, naming a target is consent, --yes covers scripts, and
--dry-run dominates everything: it never prompts, writes nothing,
reports would-be refusals, and exits 0. A non-TTY run without --yes
fails loud instead of reporting green over an install that never
happened."
```

---

### Task 8: The `semlf status` command

Report every discoverable or recorded artifact's state,
including published-payload lag and no-consumer leftovers.

**Files:**

- Modify: `cli/semlf/lifecycle.py`
- Test: `tests/test_semlf_install.py` (append)

**Interfaces:**

- Consumes: Tasks 5–7.
- Produces:
  - `status_command(argv) -> int` — replaces the Task 7 stub.
  - `installed_consumers() -> set[str]` —
    `codex` when an owned hook entry OR the installed skill file exists
    (the skill references the neutral payloads too,
    so removing only the hook must not downgrade them to leftovers);
    `opencode` when the plugin file exists.
  - `payload_identity(name) -> tuple[str, str]` —
    `(state, human line)`; state ∈ `ok, missing, edited, lagging, ahead, same-version-different-bytes, unorderable, unreadable`.
    Status and doctor route ALL THREE identity payloads
    (`checker`, `readme`, `opencode-checker` — the registry's `identity` rows) through this one function;
    the generic classifier vocabulary never appears on a payload line.
  - `snippet_state(target: Path) -> str` — `present`, `absent`, `malformed`, or `unreadable`;
    malformed uses the SAME pairing, count, and order predicate the install plan enforces,
    so a repeated or reversed sentinel pair never reports `present`.
  - Status labels, decided here once so Task 11 can enumerate test updates against them:
    `payload <id>: …` for identity payloads,
    `codex hook: …`, `codex skill: …` (space, as today), `opencode plugin: …`,
    integration lines print the classifier state verbatim
    (`exact`, `edited`, `unrecorded`, `managed-older`, …).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_semlf_install.py`:

```python
def test_status_reports_a_healthy_install(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    out = r.stdout.lower()
    assert "checker" in out and "readme" in out
    assert "codex" in out


def test_status_reports_payload_lag_by_version_label(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    checker = data_root(tmp_path) / "check_linefeeds.py"
    stale = checker.read_text(encoding="utf-8").replace(
        '__version__ = "', '__version__ = "0.0.', 1)
    checker.write_text(stale, encoding="utf-8")
    # Make the stale copy managed so the state is lagging, not edited.
    import hashlib
    record = {"path": str(checker),
              "sha256": hashlib.sha256(
                  stale.encode("utf-8")).hexdigest(),
              "version": "0.0.1"}
    state = tmp_path / "state" / "semlf" / "artifacts" / "checker.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(record), encoding="utf-8")
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "lag" in r.stdout.lower()
    assert "semlf install" in r.stdout


def test_status_names_no_consumer_leftovers_in_one_line(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    run_semlf(["uninstall", "codex"], env)
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    out = r.stdout
    assert "no remaining" in out.lower() or "leftover" in out.lower()
    assert str(data_root(tmp_path)) in out


def test_status_excludes_agentsmd_without_a_path(tmp_path):
    r = run_semlf(["status"], isolated_env(tmp_path))
    assert "agentsmd" not in r.stdout.lower()


def test_status_agentsmd_reports_the_named_file(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    run_semlf(["install", "agentsmd", str(target)], env)
    r = run_semlf(["status", "agentsmd", str(target)], env)
    assert r.returncode == 0
    assert "present" in r.stdout.lower()
    r = run_semlf(["status", "agentsmd", str(tmp_path / "other.md")], env)
    assert "absent" in r.stdout.lower()


def test_status_agentsmd_reports_malformed_sentinels(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    target.write_text("<!-- semantic-linefeeds -->\nno close\n",
                      encoding="utf-8")
    r = run_semlf(["status", "agentsmd", str(target)], env)
    assert "malformed" in r.stdout.lower()
    target.write_text(
        "<!-- /semantic-linefeeds -->\nreversed\n"
        "<!-- semantic-linefeeds -->\n", encoding="utf-8")
    r = run_semlf(["status", "agentsmd", str(target)], env)
    assert "malformed" in r.stdout.lower()


def test_status_names_a_recorded_payload_whose_file_vanished(tmp_path):
    """Status reports every discoverable OR RECORDED artifact: a valid
    record with a missing file is missing, never silently omitted."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    run_semlf(["uninstall", "codex"], env)
    (data_root(tmp_path) / "check_linefeeds.py").unlink()
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "checker" in r.stdout and "missing" in r.stdout.lower()


def test_a_skill_only_machine_keeps_payloads_expected(tmp_path):
    """Removing only the hook must not downgrade the neutral payloads
    to leftovers — the installed skill still references them."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    (tmp_path / "codex" / "hooks.json").write_text(
        '{"hooks": {"PostToolUse": []}}', encoding="utf-8")
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "no remaining" not in r.stdout.lower()
```

Also append the identity-state matrix to `tests/test_lifecycle.py`
(in-process, using its `home` fixture):

```python
@pytest.mark.parametrize("name", ["checker", "readme",
                                  "opencode-checker"])
def test_payload_identity_states_per_payload(home, name, capsys):
    planned, refusals = lifecycle.plan_install(["codex", "opencode"],
                                               None, False)
    assert refusals == []
    lifecycle.apply_plan(planned)
    dest = lifecycle.payload_destinations()[name]
    version = lifecycle.artifact_version()
    assert lifecycle.payload_identity(name)[0] == "ok"

    dest.unlink()
    assert lifecycle.payload_identity(name)[0] == "missing"

    dest.write_bytes(b"edited by hand\n")
    manifest.forget(name)
    assert lifecycle.payload_identity(name)[0] == "edited"

    def managed(version_str, data=b"managed bytes\n"):
        dest.write_bytes(data)
        manifest.record(name, dest, version_str,
                        manifest.sha256_bytes(data))

    managed("0.0.1")
    assert lifecycle.payload_identity(name)[0] == "lagging"
    managed("999.0")
    assert lifecycle.payload_identity(name)[0] == "ahead"
    managed(version)
    assert (lifecycle.payload_identity(name)[0]
            == "same-version-different-bytes")
    managed("not-a-version")
    assert lifecycle.payload_identity(name)[0] == "unorderable"
```

Note: `test_status_names_no_consumer_leftovers_in_one_line` needs Task 9's uninstall;
mark it `@pytest.mark.xfail(reason="needs semlf uninstall", strict=False)` now
and drop the mark in Task 9.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_semlf_install.py -q`
Expected: the new status tests FAIL (stub exits 64).

- [ ] **Step 3: Implement**

Replace the `status_command` stub in `cli/semlf/lifecycle.py`:

```python
def installed_consumers():
    """Integrations whose own artifacts are present on this machine.

    codex counts as installed when EITHER its hook entry or its
    installed skill file is present: the skill references the neutral
    checker and README too, so removing only the hook must not
    downgrade required payloads to leftovers.
    """
    found = set()
    home = manifest.codex_home()
    if home is not None:
        data = manifest.read_state_json(home / "hooks.json")
        if manifest.owned_codex_hooks(data):
            found.add("codex")
    skill = manifest.codex_skill_dest()
    if skill is not None and os.path.lexists(str(skill)):
        found.add("codex")
    d = manifest.opencode_plugins_dir()
    if d is not None and os.path.lexists(str(d / "semantic-linefeeds.ts")):
        found.add("opencode")
    return found


def payload_identity(name):
    """(state, human line) for one published payload.

    Guarded bytes decide the state, never the version string alone:
    two builds can differ under one version, and on a downgrade the
    published copy is ahead, not behind.
    The version is the human-facing label in the line.
    """
    dest = payload_destinations()[name]
    if dest is None:
        return "missing", f"{name}: no destination resolves here"
    state = classify.object_state(dest)
    if state == "absent":
        return "missing", f"{name}: not published ({dest})"
    if state != "regular":
        return "unreadable", f"{name}: {dest} is a {state}"
    current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
    if current is None:
        return "unreadable", f"{name}: {dest} is unreadable"
    if current == rendered_bytes(name):
        return "ok", f"{name}: current ({dest})"
    entry = manifest.load().get(name)
    prov = manifest.classify_entry(entry, dest)
    running = artifact_version()
    if prov != "managed":
        return "edited", (f"{name}: edited or unrecorded ({dest}); "
                          "rerun `semlf install` with --force to replace it")
    recorded = entry["version"]
    rv, cv = (classify.parse_version(recorded),
              classify.parse_version(running))
    if rv is None or cv is None:
        return "unorderable", (f"{name}: managed, but the recorded "
                               f"version ({recorded}) cannot be ordered "
                               f"against this artifact's ({running})")
    if rv < cv:
        return "lagging", (f"{name}: published v{recorded} lags this "
                           f"artifact (v{running}); run `semlf install` "
                           "to refresh it")
    if rv > cv:
        return "ahead", (f"{name}: published v{recorded} is ahead of "
                         f"this artifact (v{running})")
    return "same-version-different-bytes", (
        f"{name}: published v{recorded} matches this artifact's "
        "version but not its bytes; run `semlf install` to refresh it")


def snippet_state(target):
    if not os.path.lexists(target):
        return "absent"
    data = manifest.read_regular_bytes(target, manifest.CLASSIFY_LIMIT)
    if data is None:
        return "unreadable"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "unreadable"
    has_open = SENTINEL_OPEN in text
    has_close = SENTINEL_CLOSE in text
    if not has_open and not has_close:
        return "absent"
    # The same pairing, count, and order predicate the install plan
    # enforces: a repeated or reversed pair is malformed, not present.
    if (has_open != has_close
            or text.count(SENTINEL_OPEN) != 1
            or text.count(SENTINEL_CLOSE) != 1
            or text.index(SENTINEL_OPEN) > text.index(SENTINEL_CLOSE)):
        return "malformed"
    return "present"


def status_command(argv):
    if argv[:1] == ["agentsmd"]:
        if len(argv) != 2:
            print("semlf status: agentsmd requires an explicit path.",
                  file=sys.stderr)
            return 64
        target = Path(argv[1])
        print(f"agentsmd: block {snippet_state(target)} in {target}")
        return 0
    if argv:
        print(f"semlf status: unknown argument {argv[0]!r}",
              file=sys.stderr)
        return 64
    consumers = installed_consumers()
    snapshot = manifest.load()
    leftovers = False
    # Every identity payload — both checker copies and the readme —
    # reports through payload_identity; the classifier vocabulary
    # never appears on a payload line.
    for row in registry.ROWS:
        if not row.identity:
            continue
        state, line = payload_identity(row.id)
        if (state == "missing" and row.owner not in consumers
                and snapshot.get(row.id) is None):
            # Only a payload with neither a consumer nor a valid
            # provenance record is irrelevant here: status reports
            # every discoverable OR RECORDED artifact, so a recorded
            # payload whose file vanished is named as missing.
            continue
        print(f"payload {line}")
        if state != "missing" and row.owner not in consumers:
            leftovers = True
    home = manifest.codex_home()
    data_dir = manifest.semlf_data_dir()
    if home is None or data_dir is None:
        # CODEX_HOME may resolve while no data root does; rendering
        # the wanted command needs both, so guard both (a bare
        # render_codex_hook_entry(None) would raise instead of report).
        print("codex hook: no home to check")
    else:
        hooks_path = home / "hooks.json"
        data = manifest.read_state_json(hooks_path)
        owned = manifest.owned_codex_hooks(data)
        if not os.path.lexists(str(hooks_path)):
            print(f"codex hook: not installed ({hooks_path})")
        elif data is None:
            print(f"codex hook: unreadable ({hooks_path})")
        elif not owned:
            print(f"codex hook: not installed ({hooks_path})")
        else:
            entry = registry.render_codex_hook_entry(data_dir)
            import shlex as _shlex
            wanted = _shlex.split(entry["hooks"][0]["command"])
            if all(argv_ == wanted for argv_ in owned):
                print(f"codex hook: installed ({hooks_path})")
            else:
                print("codex hook: installed (stale checker path; "
                      "re-run `semlf install codex`)")
    # The skill and the plugin are integration artifacts, not
    # identity payloads: they report the classifier state verbatim
    # (the one manifest snapshot above serves this loop too).
    destinations = payload_destinations()
    for name, label in (("codex-skill", "codex skill"),
                        ("opencode-plugin", "opencode plugin")):
        dest = destinations[name]
        if dest is None:
            print(f"{label}: no home to check")
            continue
        state = classify.object_state(dest)
        if state == "absent":
            print(f"{label}: not installed ({dest})")
            continue
        verdict = classify.classify_artifact(
            snapshot.get(name), dest, rendered_bytes(name),
            artifact_version(), False)
        print(f"{label}: {verdict.state} ({dest})")
    if leftovers:
        print(f"payloads: no remaining consumer; remove "
              f"{manifest.semlf_data_dir()} by hand if unwanted.")
    shim_warning()
    return _finish(0)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_semlf_install.py -q`
Expected: PASS (the leftover test still xfails until Task 9).

- [ ] **Step 5: Full suite and commit**

```bash
git add cli/semlf/lifecycle.py tests/test_semlf_install.py
git commit -m "feat(cli): add the semlf status command" \
  -m "Status reports every discoverable or recorded artifact through
the classifier, labels payload lag by version while guarded bytes
decide it, names no-consumer leftovers in one line, and keeps the
agentsmd snippet behind an explicit path."
```

---

### Task 9: The `semlf uninstall` command

Preflight-then-apply removal, ADR-0014 semantics unchanged;
the neutral payloads are deliberately retained.

**Files:**

- Modify: `cli/semlf/lifecycle.py`
- Test: `tests/test_semlf_install.py` (append; drop the Task 8 xfail mark)

**Interfaces:**

- Consumes: Tasks 5–8.
- Produces:
  - `uninstall_command(argv) -> int` — replaces the Task 7 stub.
  - `plan_remove_file(label, dest, name, force, planned, refusals, prune_parent=False)` —
    ported from install.py's `_plan_file`, reference bytes from `rendered_bytes(name)`.
  - `plan_remove_codex_hook(planned, refusals)` — ported from `_plan_codex_hook`.
  - `plan_remove_agentsmd(target, planned, refusals)` — ported from `_plan_agentsmd`.
  - `_forget_note(dest, name)` and `_prune_empty_parent(dest)` —
    MOVED from `scripts/install.py` into lifecycle in this task
    (the removal planners call them, so leaving them behind would `NameError`);
    install.py keeps aliases beside the Task 5 import block
    (`from semlf.lifecycle import _forget_note, _prune_empty_parent`)
    because its retained `_plan_cli` calls them too.
  - Removal apply reuses `apply_plan` (`do` closures unlink and forget, or splice and publish).
  - Force semantics here are ADR-0014's, NOT the install classifier's:
    `--force` may unlink a symlink, special, or unreadable single file
    (an unlink is not a content write),
    directories still refuse,
    and the agentsmd splice-out is never force-overridable.
    The existing checkout-door tests pinning forced symlink and unreadable removal stay green.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_semlf_install.py`:

```python
def test_uninstall_without_a_target_is_a_usage_error(tmp_path):
    r = run_semlf(["uninstall"], isolated_env(tmp_path))
    assert r.returncode == 64


def test_uninstall_codex_removes_hook_and_skill_but_keeps_payloads(
        tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    r = run_semlf(["uninstall", "codex"], env)
    assert r.returncode == 0, r.stderr
    hooks = json.loads((tmp_path / "codex" / "hooks.json").read_text())
    from semlf import manifest as m  # path inserted at module top
    assert m.owned_codex_hooks(hooks) == []
    skill = tmp_path / "home" / ".agents" / "skills" / \
        "semantic-linefeeds" / "SKILL.md"
    assert not skill.exists()
    assert (data_root(tmp_path) / "check_linefeeds.py").exists()
    assert (data_root(tmp_path) / "README.md").exists()


def test_uninstall_refuses_an_edited_skill_without_force(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    skill = tmp_path / "home" / ".agents" / "skills" / \
        "semantic-linefeeds" / "SKILL.md"
    skill.write_text("hand-patched", encoding="utf-8")
    # Clear its record so admission can only come from byte identity.
    (tmp_path / "state" / "semlf" / "artifacts" /
     "codex-skill.json").unlink()
    r = run_semlf(["uninstall", "codex"], env)
    assert r.returncode == 1
    assert skill.exists()
    r = run_semlf(["uninstall", "codex", "--force"], env)
    assert r.returncode == 0
    assert not skill.exists()


def test_uninstall_agentsmd_requires_and_uses_the_path(tmp_path):
    env = isolated_env(tmp_path)
    target = tmp_path / "AGENTS.md"
    target.write_text("# mine\n", encoding="utf-8")
    run_semlf(["install", "agentsmd", str(target)], env)
    r = run_semlf(["uninstall", "agentsmd"], env)
    assert r.returncode == 64
    r = run_semlf(["uninstall", "agentsmd", str(target)], env)
    assert r.returncode == 0
    text = target.read_text(encoding="utf-8")
    assert "semantic-linefeeds" not in text
    assert "# mine" in text


def test_uninstall_dry_run_removes_nothing(tmp_path):
    env = isolated_env(tmp_path)
    run_semlf(["install", "opencode"], env)
    plugin = tmp_path / "xdg" / "opencode" / "plugins" / \
        "semantic-linefeeds.ts"
    assert plugin.exists()
    r = run_semlf(["uninstall", "opencode", "--dry-run"], env)
    assert r.returncode == 0
    assert plugin.exists()


def test_uninstall_dry_run_reports_a_would_be_refusal_at_exit_zero(
        tmp_path):
    """Dry-run dominates refusals on uninstall exactly as on install:
    report, write nothing, exit 0."""
    env = isolated_env(tmp_path)
    run_semlf(["install", "codex"], env)
    skill = tmp_path / "home" / ".agents" / "skills" / \
        "semantic-linefeeds" / "SKILL.md"
    skill.write_text("hand-patched", encoding="utf-8")
    (tmp_path / "state" / "semlf" / "artifacts" /
     "codex-skill.json").unlink()
    r = run_semlf(["uninstall", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert "would refuse" in r.stdout
    assert skill.read_text(encoding="utf-8") == "hand-patched"
```

The opencode dry-run test needs `semlf install opencode` to work with no opencode present;
naming the target is consent, and the plans create the plugins directory —
this matches the design's "naming a target is consent: apply directly".

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_semlf_install.py -q`
Expected: the uninstall tests FAIL (stub exits 64 for every invocation, including valid ones).

- [ ] **Step 3: Implement**

Port the three planners from `scripts/install.py` into `cli/semlf/lifecycle.py`,
with these adaptations and nothing else:

- `plan_remove_file` is `_plan_file` with `reference_bytes` computed as `rendered_bytes(name)`
  and the `Planned` tuple in place of `(label, callable)` pairs
  (`do` returns the `_forget_note` string, which `apply_plan` already treats as a partial-failure note).
- `plan_remove_codex_hook` is `_plan_codex_hook` with `_write_shared` replaced by
  `publish_shared(path, text)` —
  the shared-file rewrite keeps its `.bak`, exactly as install-side merges do (Task 6).
- `plan_remove_agentsmd` is `_plan_agentsmd` unchanged in logic (force never overrides it),
  with the same `publish_shared` substitution.
- `_forget_note` and `_prune_empty_parent` MOVE from `scripts/install.py` into lifecycle
  (the planners above call them);
  install.py gains `from semlf.lifecycle import _forget_note, _prune_empty_parent` beside the Task 5 aliases,
  because its retained `_plan_cli` calls them too.
- Force admission here is ADR-0014's, ported unchanged:
  a symlink, special, or unreadable single file IS removable with `--force`
  (the existing checkout tests pin this), a directory never is,
  and the sentinel splice-out is never force-overridable.
  Do not substitute the install classifier's force-never-overrides rule into these planners.

Then:

```python
def uninstall_command(argv):
    parsed = _parse_targets(argv, "uninstall", ("dry_run", "force"))
    if parsed is None:
        return 64
    targets, agentsmd_path, flags = parsed
    if not targets and agentsmd_path is None:
        print("semlf uninstall: name a target (codex, opencode, "
              "agentsmd PATH).", file=sys.stderr)
        return 64
    planned, refusals = [], []
    if "codex" in targets:
        plan_remove_codex_hook(planned, refusals)
        plan_remove_file("codex skill",
                         payload_destinations()["codex-skill"],
                         "codex-skill", flags["force"], planned,
                         refusals, prune_parent=True)
    if "opencode" in targets:
        destinations = payload_destinations()
        plan_remove_file("opencode plugin",
                         destinations["opencode-plugin"],
                         "opencode-plugin", flags["force"], planned,
                         refusals)
        plan_remove_file("opencode checker",
                         destinations["opencode-checker"],
                         "opencode-checker", flags["force"], planned,
                         refusals)
    if agentsmd_path is not None:
        plan_remove_agentsmd(agentsmd_path, planned, refusals)
    if flags["dry_run"]:
        # Dry-run dominates everything: it reports the would-be
        # refusals instead of taking them, and exits 0 (the design's
        # fixed precedence covers the whole command surface).
        for item in planned:
            print(item.label if item.do is None
                  else f"[dry-run] would remove {item.label}")
        for refusal in refusals:
            print(f"[dry-run] would refuse: {refusal}")
        return 0
    if refusals:
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1
    rc = apply_plan(planned)
    if "codex" in targets and rc == 0:
        print(f"note: the published payloads under "
              f"{manifest.semlf_data_dir()} are shared and retained; "
              "`semlf status` reports leftovers.")
    return rc
```

Drop the Task 8 xfail mark from `test_status_names_no_consumer_leftovers_in_one_line`.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_semlf_install.py tests/test_lifecycle.py -q`
Expected: PASS, xfail now passing as a normal test.

- [ ] **Step 5: Full suite and commit**

```bash
git add cli/semlf/lifecycle.py tests/test_semlf_install.py
git commit -m "feat(cli): add the semlf uninstall command" \
  -m "Preflight-then-apply removal with ADR-0014 semantics: byte or
provenance admission per file, structural hook unmerge, sentinel
splice-out that force never overrides, and a usage error when no
target is named. The neutral payloads are deliberately retained and
status names them."
```

---

### Task 10: Doctor fails on expected-payload mismatch

Staleness is a digest question conditioned on installed consumers:
doctor fails on an expected-payload mismatch,
warns on no-consumer leftovers,
and repeats the zipapp migration report.

**Files:**

- Modify: `cli/semlf/doctor.py`
- Test: `tests/test_doctor.py` (append)

**Interfaces:**

- Consumes: `lifecycle.payload_identity`, `lifecycle.installed_consumers`, `lifecycle.payload_destinations`, `lifecycle.shim_warning`.
- Produces: `_payload_identity_check() -> int` — the number of failed checks, folded into `run`'s `failures`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_doctor.py`
(reuse the file's existing `installed_pyz`/`run_doctor` helpers;
the new tests drive the package-door state with the same isolated env shape as `tests/test_semlf_install.py`):

```python
def _install_codex_via_semlf(tmp_path, env):
    bootstrap = ("import sys; sys.path[:0] = [%r, %r]; "
                 "from semlf.cli import main; "
                 "sys.exit(main(sys.argv[1:]))"
                 % (str(REPO / "cli"), str(REPO / "scripts")))
    r = subprocess.run([sys.executable, "-c", bootstrap,
                        "install", "codex"],
                       capture_output=True, text=True, env=env,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    return r


def test_doctor_passes_with_current_payloads(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    _install_codex_via_semlf(tmp_path, env)
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "payload" in r.stdout


def test_doctor_fails_on_an_expected_payload_mismatch(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    _install_codex_via_semlf(tmp_path, env)
    checker = Path(env["XDG_DATA_HOME"]) / "semlf" / "check_linefeeds.py"
    checker.write_text(checker.read_text(encoding="utf-8") + "# edited\n",
                       encoding="utf-8")
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 1
    assert "payload" in r.stdout and "FAIL" in r.stdout


def test_doctor_fails_an_installed_hook_with_no_published_payload(
        tmp_path):
    """An owned hook makes the payloads expected; a machine that has
    the hook but never published them is the migration half-state
    doctor exists to flag."""
    pyz, env = installed_pyz(tmp_path)
    hooks = Path(env["CODEX_HOME"]) / "hooks.json"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    checker = Path(env["XDG_DATA_HOME"]) / "semlf" / "check_linefeeds.py"
    hooks.write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": f'python3 "{checker}" --hook codex'}]}]}}),
        encoding="utf-8")
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 1
    assert "payload" in r.stdout and "FAIL" in r.stdout


def test_doctor_warns_but_passes_on_no_consumer_leftovers(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    _install_codex_via_semlf(tmp_path, env)
    # Remove the consumer but keep the payloads (the uninstall verb's
    # deliberate leftover policy).
    hooks = Path(env["CODEX_HOME"]) / "hooks.json"
    hooks.write_text('{"hooks": {"PostToolUse": []}}', encoding="utf-8")
    skill = Path(env["HOME"]) / ".agents" / "skills" / \
        "semantic-linefeeds" / "SKILL.md"
    if skill.exists():
        skill.unlink()
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout
    assert "warn" in r.stdout.lower()
    assert str(Path(env["XDG_DATA_HOME"]) / "semlf") in r.stdout


def test_doctor_passes_on_a_machine_with_no_integrations(tmp_path):
    pyz, env = installed_pyz(tmp_path)
    r = run_doctor(pyz, env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
```

Extend the existing `installed_pyz` helper's env with
`"XDG_DATA_HOME": str(tmp_path / "data")` — this is mandatory, not conditional:
`tests/test_doctor.py` does not set it today,
and the new tests index `env["XDG_DATA_HOME"]` directly.

One existing doctor test changes behavior by design:
`test_doctor_replays_an_installed_codex_hook` plants an owned hook without ever publishing payloads,
which after this task is an expected-consumer-with-missing-payload machine —
exactly the migration half-state doctor must flag —
so its healthy-path assertion would fail.
Update that test to publish the payloads first
(run `semlf install codex` through `_install_codex_via_semlf` before asserting exit 0),
and pin the flagging behavior explicitly in the new
`test_doctor_fails_on_an_expected_payload_mismatch` family below
(add a case: owned hook present, payload never published → exit 1 with a `payload: FAIL` line).

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_doctor.py -q`
Expected: the new tests FAIL — no payload lines in doctor output yet.

- [ ] **Step 3: Implement**

In `cli/semlf/doctor.py`:

Add the imports:

```python
from semlf import lifecycle, registry
```

Replace `_expected_destinations` with a delegation that adds the cli entry
(the provenance loop must know where `checker` and `readme` install,
or their records would be mislabeled "no destination resolves here"):

```python
def _expected_destinations():
    """Each known artifact's current expected location, or None entries."""
    destinations = lifecycle.payload_destinations()
    destinations["cli"] = manifest.cli_bin_dest()
    return destinations
```

Add the identity check and call it from `run` right after `_codex_hook_check()`:

```python
def _payload_identity_check():
    """Expected-payload mismatches fail; no-consumer leftovers warn.

    Expectedness is conditioned on consumers:
    an installed integration makes its payloads expected, a payload
    with no remaining consumer is a warning with the manual-removal
    pointer, a machine with no integrations passes, and a codex-only
    machine is never failed over the absent opencode copy.
    """
    failures = 0
    consumers = lifecycle.installed_consumers()
    leftover_dir = None
    # The identity set and its consumer expectedness both come from
    # the registry rows — no hand-maintained name tuple here.
    for row in registry.ROWS:
        if not row.identity:
            continue
        expected = row.owner in consumers
        state, line = lifecycle.payload_identity(row.id)
        if state == "missing" and not expected:
            continue
        if expected and state != "ok":
            print(f"payload: FAIL — {line}")
            failures += 1
        elif not expected:
            print(f"payload: warn — {line} (no remaining consumer)")
            if row.id in ("checker", "readme"):
                leftover_dir = manifest.semlf_data_dir()
        else:
            print(f"payload: {line}")
    if leftover_dir is not None:
        print(f"payload: warn — remove {leftover_dir} by hand if "
              "unwanted")
    return failures
```

In `run`, after `failures += _codex_hook_check()`, add:

```python
    failures += _payload_identity_check()
```

The existing `path:` line in `run` already warns when `semlf` on PATH is not the running artifact;
extend its wording with the checkout-door removal pointer so the migration case is actionable:

```python
    elif os.path.realpath(resolved) != os.path.realpath(artifact):
        print(f"path: warn — `semlf` resolves to {resolved}, not the "
              "artifact running doctor; a pre-redesign zipapp may be "
              "shadowing it (remove with install.py --uninstall --cli)")
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_doctor.py -q`
Expected: PASS.
A no-integration machine gains payload lines only when payloads or consumers exist,
so the remaining legacy tests stay green without edits —
the ONE sanctioned exception is `test_doctor_replays_an_installed_codex_hook`,
updated in Step 1 because an owned hook with no published payload is now the expected-payload-missing failure by design.
Any other legacy failure means the conditioning logic is wrong;
fix the logic, not the test.

- [ ] **Step 5: Full suite and commit**

```bash
git add cli/semlf/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): fail on expected-payload mismatch" \
  -m "Every published payload is compared against the running
artifact's embedded set by guarded bytes, never version strings
alone. An installed integration makes its payloads expected and a
mismatch there fails; leftovers with no consumer warn and name the
directory for manual removal."
```

---

### Task 11: The checkout door becomes a thin parser

`scripts/install.py` keeps its whole flag vocabulary over the shared operations;
the behavior deltas the design enumerates land here, with their tests.

**Files:**

- Modify: `scripts/install.py`
- Modify: `tests/test_installer.py`

**Interfaces:**

- Consumes: `lifecycle.plan_install`, `lifecycle.apply_plan`, `lifecycle.describe_plan`, `lifecycle.uninstall_command`-style planners, `lifecycle.status_command`, `lifecycle.detect_agents`, `lifecycle.publish_exclusive`, `lifecycle.exclusive_backup`.
- Produces: the same CLI surface `install.sh` already forwards to, unchanged flags, so `install.sh` needs zero changes.

- [ ] **Step 1: Update the installer tests for the enumerated deltas**

The refactor breaks roughly 37 existing tests in `tests/test_installer.py`,
in four mechanical categories.
Every one is enumerated here,
so "the rest keep working" is literally true once these edits land;
do not weaken any assertion beyond what an item names.
`isolated_env` gains `"XDG_DATA_HOME": str(tmp_path / "data")` first —
several categories depend on it.

**Category A — direct calls to deleted functions.**
These tests call `install_module.<fn>` in-process and would crash with `AttributeError`:

1. `test_install_codex_refuses_without_a_resolvable_home`,
   `test_install_codex_skill_refuses_without_a_resolvable_home`,
   `test_install_opencode_refuses_without_a_resolvable_home`:
   rewrite each against the shared planner —
   monkeypatch `expanduser` as today,
   call `lifecycle.plan_install(["codex"], None, False)` (or `["opencode"]`),
   and assert the no-home refusal string lands in `refusals` and nothing was written.
2. `test_status_reports_no_home_to_check` and
   `test_status_reports_no_home_on_every_path_without_env_overrides`:
   keep calling `install_module.status()` —
   the composed status survives (Category D) —
   and update the expected labels to the Task 8 set:
   `codex hook: no home to check`, `codex skill: no home to check`,
   `opencode plugin: no home to check`, and `cli: no home to check` retained.
3. `test_agents_block_carries_no_absolute_path`: call `lifecycle.agents_block()`.
4. `test_agentsmd_warns_when_semlf_is_missing`:
   drive through `run_install(["--agentsmd", str(target)], env)`;
   the pinned "not on PATH" phrase survives (Task 6 kept it).
5. `test_publish_new_refuses_a_destination_that_appeared`,
   `test_a_failed_backup_releases_the_slot`,
   `test_a_failed_backup_fails_install_cli_cleanly`:
   the Task 5 aliases (`install._publish_new`, `install._exclusive_backup`)
   keep direct calls AND monkeypatching working —
   verify these three pass unchanged before touching them.
6. The seventeen direct `install.install_cli` calls
   (the CLI unit tests around `tests/test_installer.py:1096-1216`
   and the isolated-module tests around `:1341-1402`, `:1532-1549`, `:1968-1986`)
   stay green through the compatibility wrapper Step 3 defines;
   the planner labels reuse the old message strings,
   so their substring assertions hold —
   verify all seventeen before editing any of them.
7. Both minimal-checkout constructors
   (`make_source_repo` at `tests/test_installer.py:380`
   and `make_self_checkout_repo` at `:550`)
   gain `shutil.copy(REPO / "README.md", src / "README.md")` —
   the registry's `readme` row reads `root / "README.md"` on the checkout path,
   so a clone without it fails every `--codex` install.
   Guard the property for future rows too:

```python
def test_generated_checkout_fixtures_carry_every_registry_source(
        tmp_path):
    from semlf import registry
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for src in (make_source_repo(tmp_path / "a"),
                make_self_checkout_repo(tmp_path / "b")):
        for row in registry.ROWS:
            assert (src / row.source).is_file(), (src, row.source)
```

**Category B — output wording, against the labels Task 8 decided.**

6. Rerun no-ops assert `"up to date"` instead of `"already"`:
   `test_codex_rerun_is_a_noop`, `test_opencode_rerun_is_a_noop`,
   `test_codex_skill_rerun_is_a_noop`, `test_install_sh_rerun_pulls_and_is_idempotent`.
7. Dry-run marker tests keep passing unchanged —
   `describe_plan`'s `[dry-run] ` prefix preserves the `"dry-run"` substring:
   `test_codex_dry_run_writes_nothing`, `test_opencode_dry_run_writes_nothing`,
   `test_codex_skill_dry_run_writes_nothing`, `test_install_sh_env_repo_and_dry_run`.
   Verify; edit only if an exact-match assertion surfaces.
8. Skill-content assertions move from `str(REPO)` to the neutral data-root path:
   `test_codex_install_writes_the_native_skill`,
   `test_codex_skill_force_overwrites_and_backs_up`.
9. Hook-path assertions move from `str(REPO)` to the neutral checker path,
   and `test_codex_fresh_install_creates_hooks_json` additionally asserts the neutral checker and readme with canonical bytes:
   `test_codex_fresh_install_creates_hooks_json`,
   `test_codex_stale_path_is_updated_in_place`.
10. Status-label updates to the Task 8 set
    (`codex hook:`, `codex skill:`, `opencode plugin:`,
    classifier states verbatim — a recordless hand-made copy is `unrecorded`, not `diverged`):
    `test_status_reports_all_targets_and_claude_guidance`,
    `test_status_sees_installed_targets`,
    `test_status_handles_a_malformed_hooks_shape_without_crashing`,
    `test_status_reports_codex_skill_states`,
    `test_status_and_rerun_detect_a_crlf_converted_skill`,
    `test_status_reports_unreadable_for_a_fifo_skill_destination`,
    `test_status_reports_unreadable_for_a_dangling_symlink_opencode_destination`,
    `test_install_sh_uses_own_checkout_without_repo`,
    `test_install_sh_status_mode_is_safe_with_home_truly_unset`.
11. Status stops probing `./AGENTS.md`:
    every status test asserting an `agentsmd:` line now asserts its absence.
    Four probe tests become obsolete — delete all four
    (`semlf status agentsmd PATH` owns that surface and Task 8 tested it):
    `test_status_reports_agentsmd_against_a_resolved_path`,
    `test_status_handles_undecodable_agentsmd`,
    `test_status_handles_a_fifo_agentsmd_target_without_hanging`,
    `test_status_handles_a_symlink_cycle_at_agentsmd_without_a_traceback`.

**Category C — behavior-delta additions (these tests do not exist yet; add them).**

12. Dry-run over a diverged skill reports the would-be refusal at exit 0 and writes nothing
    (today's behavior — exit 1 — was never pinned by a test; the new behavior gets one now):

```python
def test_dry_run_reports_a_diverged_skill_at_exit_zero(tmp_path):
    env = isolated_env(tmp_path)
    r = run_install(["--codex"], env)
    assert r.returncode == 0
    skill = (tmp_path / "home" / ".agents" / "skills" /
             "semantic-linefeeds" / "SKILL.md")
    skill.write_text("hand-patched", encoding="utf-8")
    (tmp_path / "state" / "semlf" / "artifacts" /
     "codex-skill.json").unlink()
    r = run_install(["--codex", "--dry-run"], env)
    assert r.returncode == 0
    assert "would refuse" in r.stdout
    assert skill.read_text(encoding="utf-8") == "hand-patched"
```

13. A manifest-managed older skill and opencode file upgrade without `--force` and without a backup
    (one test per artifact: write older bytes, record them via `manifest.record`,
    run the plain install, assert replacement and no `.bak`).
14. An occupied backup slot refuses uniformly for the skill and opencode paths,
    with and without `--force`
    (`test_codex_skill_force_overwrites_and_backs_up` and
    `test_opencode_force_overwrites_and_backs_up` keep passing —
    a FREE slot still takes the exclusive backup; only the occupied slot changes).
15. `test_codex_merge_preserves_existing_entries` keeps its `hooks.json.bak` assertion —
    shared merged files keep their backup (Task 6's `publish_shared`).
16. `test_codex_refuses_a_hooks_bak_symlink_without_following` keeps passing:
    `publish_shared` raises on a non-regular slot exactly as `atomic_write` did.
17. `test_help_mentions_the_skill_and_the_widened_force_scope` keeps its pinned strings:
    extend the `--codex` help text for the neutral-root publishing
    without dropping "native semantic-linefeeds skill" or "codex-skill".

**Category D — the composed request and the composed status.**

18. Add mixed-refusal composition tests, both directions —
    one selected leg refusing must abort the whole request before any write:

```python
def test_a_refusing_codex_leg_aborts_the_cli_leg_too(tmp_path):
    env = isolated_env(tmp_path)
    root = tmp_path / "data" / "semlf"
    root.mkdir(parents=True)
    (root / "check_linefeeds.py").write_text("diverged",
                                             encoding="utf-8")
    r = run_install(["--codex", "--cli"], env)
    assert r.returncode == 1
    assert not (tmp_path / "home" / ".local" / "bin" / "semlf").exists()
    assert not (tmp_path / "codex" / "hooks.json").exists()


def test_a_refusing_cli_leg_aborts_the_codex_leg_too(tmp_path):
    env = isolated_env(tmp_path)
    bin_dir = tmp_path / "home" / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "semlf").symlink_to(bin_dir / "elsewhere")
    r = run_install(["--codex", "--cli"], env)
    assert r.returncode == 1
    assert not (tmp_path / "codex" / "hooks.json").exists()
    assert not (tmp_path / "data").exists()
```

19. Add the two-door byte-identity test.
    Create each isolated root BEFORE calling `isolated_env` on it
    (the helper's `home.mkdir(exist_ok=True)` has no `parents=True`),
    and drive the package door through a BUILT ZIPAPP,
    not the checkout's import path,
    so the rendering-from-an-installed-artifact requirement is actually established:

```python
def test_both_doors_render_identical_artifacts(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    env_a = isolated_env(tmp_path / "a")
    r = run_install(["--codex"], env_a)
    assert r.returncode == 0, r.stderr
    # The package door runs from a built zipapp, not the checkout.
    import importlib
    install_module_ = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install_module_.build_pyz(pyz)
    env_b = isolated_env(tmp_path / "b")
    full_env = os.environ.copy()
    full_env.update(env_b)
    r = subprocess.run([sys.executable, str(pyz), "install", "codex"],
                       capture_output=True, text=True, env=full_env,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    root_a = str(tmp_path / "a" / "data").encode()
    root_b = str(tmp_path / "b" / "data").encode()
    for rel in (("data", "semlf", "check_linefeeds.py"),
                ("data", "semlf", "README.md"),
                ("home", ".agents", "skills", "semantic-linefeeds",
                 "SKILL.md"),
                ("codex", "hooks.json")):
        a = Path(tmp_path, "a", *rel).read_bytes()
        b = Path(tmp_path, "b", *rel).read_bytes()
        assert a.replace(root_a, b"ROOT") == b.replace(root_b, b"ROOT"), rel
```

20. The composed status keeps the cli line:
    `test_a_fifo_at_the_cli_destination_refuses_install_and_status_reports_not_runnable`
    and `test_status_handles_an_encrypted_member_pyz_at_the_cli_destination`
    stay green because `install.py status()` is the cli section
    plus `lifecycle.status_command([])` (Step 3) —
    verify both, do not edit them.

- [ ] **Step 2: Run to verify the updated tests fail**

Run: `python3 -m pytest tests/test_installer.py -q`
Expected: the updated tests FAIL against the old installer behavior.

- [ ] **Step 3: Refactor install.py**

Rewire `scripts/install.py`:

- The import block already carries the Task 5 aliases
  (`_publish_new`, `_exclusive_backup`)
  and the Task 9 helper imports (`_forget_note`, `_prune_empty_parent`);
  add `from semlf import lifecycle` beside them if not already present.
- Delete: `install_codex`, `install_codex_skill`, `codex_skill_body`,
  `CODEX_SKILL_COMMAND_OLD`, `CODEX_SKILL_FALLBACK_LINE`, `CODEX_SKILL_README_LINK_OLD`,
  `install_opencode`, `install_agentsmd`, `agents_block`, `_semlf_note`,
  `SENTINEL_OPEN`, `SENTINEL_CLOSE`, `TRUST_NOTE`, `desired_codex_command`,
  `detect_agents`, `_plan_codex_hook`, `_plan_file`, `_plan_opencode`, `_plan_agentsmd`,
  `_write_shared`, `_bak_sibling_ok`, `_apply`, `atomic_write`, `_guarded_atomic_write`,
  and `_BackupSlotRefused`.
- Keep: `core_version`, `build_pyz`, `pyz_state`, `_snapshot_runnable`,
  `guarded_pyz_state`, `pyz_runnable`, `_path_note`, `_adopt_current_cli`,
  `_plan_cli`, `_plan_cli_bak_note`,
  and `install_cli` — which becomes a thin compatibility wrapper (below):
  seventeen existing tests call `install.install_cli` directly
  and monkeypatch its seams (`build_pyz`, `_exclusive_backup`),
  so the API must survive the refactor.
- Split `install_cli`'s BODY into a checkout-only planner and its apply closure,
  so the cli leg joins the one request-wide plan:

```python
def _plan_cli_install(planned, refusals, force):
    """install_cli's admission, read-only, as one plan leg.

    The decision table is install_cli's own, unchanged:
    a None destination or a symlink refuses;
    an unreadable object refuses;
    identity match with the fresh build plans an adopt no-op;
    a manifest-managed copy plans an upgrade without a backup;
    anything else refuses without --force,
    and with --force plans the exclusive backup unless the slot is
    occupied, which still refuses.
    The apply closure carries the remaining install_cli body:
    stage a fresh build in dest's directory, back up if planned,
    publish (exclusively for a fresh install), and record.
    planned may be empty on entry — a bare `--cli` run is exactly
    that — and this leg simply appends to whatever it is handed.
    """
```

  Carve both halves out of today's `install_cli` code —
  the admission reads (`guarded_pyz_state`, `manifest.classify`, the `.bak` probe)
  become the planner,
  and the mutation block (staging, `_exclusive_backup`, `os.replace`,
  `_publish_new`, `manifest.record`, `_path_note`) becomes the `do` closure.
  Mutating branches construct with all six fields —
  `Planned(label, "cli", dest, None, do, done)` —
  so `apply_plan` prints the completion wording;
  only the adopt no-op relies on the `done=None` default,
  keeping its pinned `"already installed"` line for both modes.
  Two carving rules the "verbatim" instruction alone would miss:
  the already-installed branch is an adopt no-op with a NON-None `do`
  that runs `_path_note(dest)` then `_adopt_current_cli(dest, snapshot)` —
  the PATH note and the converge-to-managed re-record are that branch's side effects today
  and must survive the split;
  and the closure's failure protocol is `apply_plan`'s, not `install_cli`'s —
  where the old body printed to stderr and `return 1`
  (an occupied backup slot at apply time, a `_publish_new` refusal),
  the closure performs the same staged-file cleanup
  and RETURNS the diagnostic string as its note
  (a truthy note is the engine's failure channel; a literal `return 1` would read as success).
  The planner reuses install_cli's existing message strings verbatim,
  split across the two `Planned` label slots
  because the old dry-run and apply wordings differ:
  `label` carries the disclosure strings
  (`would install …`, `would upgrade … (managed install)`, `would back up and replace …`,
  `cli: already installed (…)` for the no-op),
  and `done` carries the completion string (`cli: installed (…)`),
  so a real apply never prints a future-tense `would install` line
  and both pinned contracts
  (`test_install_cli_places_semlf_on_local_bin`'s `"installed"` after apply,
  `test_install_cli_dry_run_writes_nothing`'s `"would install"` under dry-run)
  hold from the one plan leg.
  Add one assertion to the apply test:
  its stdout does NOT contain `"would install"`.
  And pin the cli-leg adopt re-record
  (the design's converge-to-managed, currently proven only at the lifecycle level):

```python
def test_cli_adopt_recreates_a_deleted_record(tmp_path, monkeypatch):
    env = isolated_env(tmp_path)
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    shutil.rmtree(tmp_path / "state" / "semlf")
    r = run_install(["--cli"], env)
    assert r.returncode == 0
    record = (tmp_path / "state" / "semlf" / "artifacts" / "cli.json")
    assert record.is_file()
```
  Then define the compatibility wrapper over the pair:

```python
def install_cli(dry, force):
    """Compatibility wrapper over the split pair.

    The direct-call tests and their monkeypatch seams stay green;
    the composed request path uses the planner directly.
    """
    planned, refusals = [], []
    _plan_cli_install(planned, refusals, force)
    if dry:
        lifecycle.describe_plan(planned, refusals,
                                prefix="[dry-run] ")
        return 0
    if refusals:
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1
    return lifecycle.apply_plan(planned)
```

  The cli-leg wording and precedence ripples, each named:
  `test_dry_run_force_reports_an_occupied_backup_slot` now expects exit 0 with a would-refuse line
  (dry-run dominates the cli leg too);
  `test_dry_run_force_with_a_free_slot_reports_and_writes_nothing` keeps exit 0
  and its literal `"would back up and replace"` (the label survives verbatim);
  `test_dry_run_over_an_already_current_cli_does_not_create_a_state_entry`,
  `test_install_cli_is_idempotent_and_still_notes_path`, and
  `test_status_reports_the_cli_states` keep `"already installed"` and `"not runnable"`
  (the cli leg deliberately keeps its old labels, unlike the lifecycle rows' "up to date");
  `test_managed_upgrade_ignores_an_occupied_backup_slot` keeps its `"managed"` dry-run wording.
- Refactor `_plan_cli` (the uninstall planner) and `_plan_cli_bak_note` to append `lifecycle.Planned` tuples,
  replacing their `(label, fn)` pairs
  (a no-op note keeps `do=None`),
  so `lifecycle.apply_plan` and the dry-run description can consume them —
  the shared engine dereferences `.label` and `.do`.
- `main` composes ONE request across every selected leg and applies once —
  a refusing codex leg aborts the cli leg and vice versa:

```python
def _run_request(targets, agentsmd_path, cli, dry, force):
    """One preflight-then-apply request across every selected leg.

    A checkout flag is an explicit action, so it is consent:
    no prompt, exactly like naming a target on the package door.
    """
    planned, refusals = lifecycle.plan_install(targets, agentsmd_path,
                                               force)
    if cli:
        _plan_cli_install(planned, refusals, force)
    if dry:
        lifecycle.describe_plan(planned, refusals, prefix="[dry-run] ")
        return 0
    if refusals:
        lifecycle.describe_plan(planned, [])
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1
    return lifecycle.apply_plan(planned)
```

Inside `main`, the mode dispatch becomes:

```python
    codes = []
    if args.auto:
        detected = dict(lifecycle.detect_agents())
        for agent in ("codex", "opencode"):
            if agent in detected:
                print(f"{agent}: detected ({detected[agent]})")
            else:
                print(f"{agent}: not detected; skipped")
        targets = [a for a in ("codex", "opencode") if a in detected]
        codes.append(_run_request(targets, None, cli=True,
                                  dry=args.dry_run, force=args.force))
        lifecycle.claude_code_trailer()
    else:
        targets = [a for a, on in (("codex", args.codex),
                                   ("opencode", args.opencode)) if on]
        agentsmd = (Path(args.agentsmd)
                    if args.agentsmd is not None else None)
        if targets or agentsmd is not None or args.cli:
            codes.append(_run_request(targets, agentsmd, cli=args.cli,
                                      dry=args.dry_run,
                                      force=args.force))
    if not codes:
        codes.append(status())
    sys.exit(max(codes))
```

  Note the trailer call is bare —
  `claude_code_trailer` self-gates on the binary or `~/.claude`,
  so no `shutil.which("claude")` wrapper narrows it.
- `--uninstall` composes the same way,
  and the module-level `uninstall(args)` function SURVIVES with this composed body
  (an existing test calls `install.uninstall(args)` in-process with a `Namespace`;
  the name and its `args` contract stay):
  build one `planned`/`refusals` pair from
  `lifecycle.plan_remove_codex_hook`, `lifecycle.plan_remove_file`
  (codex skill with `prune_parent=True`, both opencode files),
  `_plan_cli` for `--cli`, and `lifecycle.plan_remove_agentsmd`,
  then apply the SAME precedence as `lifecycle.uninstall_command`:
  dry-run first (would-remove and would-refuse lines, exit 0),
  then refuse-all-or-apply through `lifecycle.apply_plan`.
- The no-flag status composes the cli section with the shared body:

```python
def status():
    """The checkout door's no-flag report.

    The cli/zipapp section is checkout-owned and prints first;
    everything else is the shared status body, which already ends
    with the shim warning and the Claude Code trailer.
    """
    _print_cli_status()
    return lifecycle.status_command([])
```

  `_print_cli_status()` is today's `status()` cli block
  (the `cli_bin_dest` / `guarded_pyz_state` / `_snapshot_runnable` section)
  extracted verbatim;
  the codex/skill/opencode/agentsmd sections of the old `status()` are deleted with it.
- Update the module docstring:
  the installed hook points at the neutral root,
  `--codex` publishes the checker and readme payloads there,
  no-flag status no longer probes `./AGENTS.md`,
  and every flag combination preflights as one request.
  Extend the `--codex` argparse help for the neutral-root publishing
  WITHOUT dropping the pinned strings
  ("native semantic-linefeeds skill" in `--codex`'s help,
  "codex-skill" in `--force`'s help).

- [ ] **Step 4: Run to verify everything passes**

Run: `python3 -m pytest tests/test_installer.py tests/test_lifecycle.py tests/test_semlf_install.py tests/test_doctor.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite and commit**

Run: `python3 -m pytest tests/ -q` and `sh docs/proofs/zipapp-packaging/verify.sh`.

```bash
git add scripts/install.py tests/test_installer.py
git commit -m "refactor(install): thin parser over shared lifecycle" \
  -m "install.py keeps its whole flag vocabulary while every verb
routes through the shared operations, so both doors render
byte-identical artifacts. Deltas under the unchanged flags: hooks
target the neutral root, --codex publishes the checker and readme,
dry-run reports refusals at exit 0, managed files upgrade without
--force and without backups, and an occupied backup slot refuses
uniformly."
```

---

### Task 12: Migration coverage

Tests begin from current checkout-rendered artifacts and existing provenance records,
then exercise the package door over them.

**Files:**

- Create: `tests/test_migration.py`

**Interfaces:**

- Consumes: the full command surface; no new production code —
  any behavior gap these tests expose is fixed in the module that owns it.

- [ ] **Step 1: Write the tests**

Create `tests/test_migration.py`:

```python
"""tests/test_migration.py — the package door over a pre-redesign
machine: checkout-rendered artifacts, old records, leftover zipapp."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "scripts"))

import check_linefeeds

BOOTSTRAP = ("import sys; sys.path[:0] = [%r, %r]; "
             "from semlf.cli import main; sys.exit(main(sys.argv[1:]))"
             % (str(REPO / "cli"), str(REPO / "scripts")))


def isolated_env(tmp_path, path=""):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"HOME": str(home),
            "CODEX_HOME": str(tmp_path / "codex"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "PATH": path}


def run_semlf(args, env_overrides, stdin_text=""):
    env = os.environ.copy()
    env["PATH"] = ""
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", BOOTSTRAP] + args,
                          input=stdin_text, capture_output=True,
                          text=True, env=env, timeout=60)


def old_checkout_state(tmp_path):
    """A machine the pre-redesign checkout door installed:
    hook pointing into the checkout, skill rendered with checkout
    paths, records written the way the old installer wrote them."""
    env = isolated_env(tmp_path)
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True)
    hooks.write_text(json.dumps({"hooks": {"PostToolUse": [
        {"matcher": "apply_patch", "hooks": [
            {"type": "command",
             "command": f'python3 "{REPO}/scripts/check_linefeeds.py"'
                        ' --hook codex'}]}]}}, indent=2) + "\n",
        encoding="utf-8")
    skill_src = (REPO / "skills" / "semantic-linefeeds" /
                 "SKILL.md").read_text(encoding="utf-8")
    old_body = skill_src.replace(
        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" '
        '--file <files>',
        f'python3 "{REPO}/scripts/check_linefeeds.py" --file <files>')
    old_body = old_body.replace(
        "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at "
        "`../../scripts/check_linefeeds.py` relative to this "
        "SKILL.md.)\n\n", "")
    old_body = old_body.replace("../../README.md", f"{REPO}/README.md")
    skill = (tmp_path / "home" / ".agents" / "skills" /
             "semantic-linefeeds" / "SKILL.md")
    skill.parent.mkdir(parents=True)
    skill.write_text(old_body, encoding="utf-8")
    record = {"path": str(skill),
              "sha256": hashlib.sha256(
                  old_body.encode("utf-8")).hexdigest(),
              "version": check_linefeeds.__version__}
    state = tmp_path / "state" / "semlf" / "artifacts" / \
        "codex-skill.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(record, indent=2) + "\n",
                     encoding="utf-8")
    return env, hooks, skill


def test_install_migrates_a_checkout_rendered_machine(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0, r.stderr
    data_dir = tmp_path / "data" / "semlf"
    command = json.loads(hooks.read_text(encoding="utf-8"))[
        "hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert str(data_dir / "check_linefeeds.py") in command
    assert str(REPO) not in command
    body = skill.read_text(encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in body
    assert str(REPO) not in body
    assert not skill.with_name("SKILL.md.bak").exists()


def test_dry_run_over_the_old_machine_writes_nothing(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    before_hooks = hooks.read_bytes()
    before_skill = skill.read_bytes()
    r = run_semlf(["install", "codex", "--dry-run"], env)
    assert r.returncode == 0
    assert hooks.read_bytes() == before_hooks
    assert skill.read_bytes() == before_skill


def _built_pyz(tmp_path):
    import importlib
    install = importlib.import_module("install")
    pyz = tmp_path / "semlf.pyz"
    install.build_pyz(pyz)
    return pyz


def test_status_survives_the_old_machine(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["status"], env)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr


def test_doctor_flags_the_old_machine_through_a_real_artifact(tmp_path):
    """Doctor replays through a BUILT zipapp — its replay child derives
    from sys.argv[0], so the checkout bootstrap would prove nothing.
    The old machine has an owned hook but no published payloads:
    doctor must flag exactly that, deterministically."""
    env, hooks, skill = old_checkout_state(tmp_path)
    pyz = _built_pyz(tmp_path)
    full_env = os.environ.copy()
    full_env["PATH"] = ""
    full_env.update(env)
    r = subprocess.run([sys.executable, str(pyz), "doctor"],
                       capture_output=True, text=True, env=full_env,
                       cwd=str(tmp_path), timeout=120)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "payload" in r.stdout and "FAIL" in r.stdout
    assert "Traceback" not in r.stderr


def test_forced_migration_replaces_an_unrecorded_old_skill(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    # Without its record the old rendering is unrecorded: refuse
    # without force, exclusive backup then replace with it.
    (tmp_path / "state" / "semlf" / "artifacts" /
     "codex-skill.json").unlink()
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 1
    assert str(REPO) in skill.read_text(encoding="utf-8")
    r = run_semlf(["install", "codex", "--force"], env)
    assert r.returncode == 0, r.stderr
    assert str(tmp_path / "data" / "semlf") in skill.read_text(
        encoding="utf-8")
    assert skill.with_name("SKILL.md.bak").exists()


def test_uninstall_admits_the_old_recorded_skill(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    r = run_semlf(["uninstall", "codex"], env)
    assert r.returncode == 0, r.stderr
    assert not skill.exists()
    data = json.loads(hooks.read_text(encoding="utf-8"))
    from semlf import manifest
    assert manifest.owned_codex_hooks(data) == []


def test_leftover_zipapp_on_path_is_warned_about(tmp_path):
    env, hooks, skill = old_checkout_state(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # The design names a REAL pre-redesign zipapp as the collision;
    # a shell stub would only prove generic path-mismatch wording.
    shim = bindir / "semlf"
    import importlib
    importlib.import_module("install").build_pyz(shim)
    env["PATH"] = str(bindir)
    r = run_semlf(["install", "codex"], env)
    assert r.returncode == 0
    assert "resolves to" in r.stdout + r.stderr
    r = run_semlf(["status"], env)
    out = r.stdout + r.stderr
    assert "resolves to" in out
    # The migration report carries the checkout-door removal pointer.
    assert "install.py --uninstall --cli" in out


def _pip_and_setuptools_ok():
    try:
        import setuptools
        if int(setuptools.__version__.split(".")[0]) < 61:
            return False
    except Exception:
        return False
    r = subprocess.run([sys.executable, "-m", "pip", "--version"],
                       capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _pip_and_setuptools_ok(),
                    reason="needs pip and setuptools>=61")
def test_a_wheel_installed_semlf_renders_the_codex_artifacts(tmp_path):
    """The design requires rendering proof from a wheel INSTALL,
    not only member inspection: build, install into a venv, run
    `semlf install codex` from the installed entry point."""
    r = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(REPO), "--no-deps",
         "--no-build-isolation", "-w", str(tmp_path)],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    wheel = next(tmp_path.glob("semlf-*.whl"))
    venv_dir = tmp_path / "venv"
    r = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    r = subprocess.run([str(venv_dir / "bin" / "pip"), "install",
                        "--no-deps", str(wheel)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    env = isolated_env(tmp_path, path=str(venv_dir / "bin"))
    full_env = os.environ.copy()
    full_env.update(env)
    r = subprocess.run([str(venv_dir / "bin" / "semlf"),
                        "install", "codex"],
                       capture_output=True, text=True, env=full_env,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    data_dir = tmp_path / "data" / "semlf"
    assert (data_dir / "check_linefeeds.py").read_bytes() == (
        REPO / "scripts" / "check_linefeeds.py").read_bytes()
    assert (data_dir / "README.md").read_bytes() == (
        REPO / "README.md").read_bytes()
    skill = (tmp_path / "home" / ".agents" / "skills" /
             "semantic-linefeeds" / "SKILL.md")
    body = skill.read_text(encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in body
    hooks_text = (tmp_path / "codex" / "hooks.json").read_text(
        encoding="utf-8")
    assert str(data_dir / "check_linefeeds.py") in hooks_text
```

The unforced-upgrade path in `test_install_migrates_a_checkout_rendered_machine` depends on the old skill being manifest-managed at the recorded version;
that is exactly what the design's managed-equal row replaces without `--force`
(same version, different rendering).
The hook needs no record at all — structural ownership admits it.

- [ ] **Step 2: Run, fix behavior gaps, and commit**

Run: `python3 -m pytest tests/test_migration.py -q`.
Any failure here is a real migration gap;
fix it in the owning module (`classify`, `lifecycle`, or `doctor`), never by weakening the test.
Then the full suite:

```bash
python3 -m pytest tests/ -q
git add tests/test_migration.py
git commit -m "test: cover package-door runs over old installs" \
  -m "Migration coverage starts from checkout-rendered artifacts and
old provenance records: unforced managed upgrades, dry-run
inertness, verbs that survive the old machine, and the leftover
zipapp PATH warning."
```

---

### Task 13: The superseding ADR and the living documents

One new record supersedes the affected parts of ADR-0004, ADR-0014, and ADR-0015;
accepted records gain only status and superseded-by pointers;
rule 100 and the decisions index amend in the same commit.

**Files:**

- Create: `docs/decisions/0016-one-entry-point-and-the-payload-registry.md`
- Modify: `docs/decisions/0004-portable-core-and-repository-cli.md` (pointers only)
- Modify: `docs/decisions/0014-lifecycle-verbs-and-the-provenance-manifest.md` (pointers only)
- Modify: `docs/decisions/0015-distribution-channels.md` (pointers only)
- Modify: `docs/decisions/README.md`
- Modify: `.agents/rules/100-project-map.md`

- [ ] **Step 1: Read the neighbors**

Read `docs/decisions/README.md` for the index format and the supersede policy wording,
and ADR-0014/0015 in full —
the new record must cover their superseded claims in its own evidence and rejected-alternatives sections,
since they are never edited in place.

- [ ] **Step 2: Write ADR-0016**

Create `docs/decisions/0016-one-entry-point-and-the-payload-registry.md` following the house ADR format,
with the required coverage below
(each item is in the design's ADR-impact sweep; the design doc supplies the rationale text to adapt):

- **Decision:** `semlf` (pipx/uv) is the single entry point;
  `semlf install/status/uninstall` are package-door verbs;
  payloads embed via one declarative registry with member paths `semlf/payloads/<id>`;
  hooks and skills target the neutral root `${XDG_DATA_HOME:-~/.local/share}/semlf/`;
  admission is the three-axis classifier with adoption and downgrade refusal;
  installs are request-wide preflight then ordered apply with no rollback and no locking;
  staleness is a digest comparison conditioned on installed consumers, and doctor fails on it;
  the zipapp stays behind the checkout door;
  PyPI becomes the package channel's primary source, git-URL retained for mirrors.
- **Supersedes:** ADR-0014's decision, evidence, and rejected-alternatives claims
  (payload embedding removes the "no payload to copy from" premise;
  the lifecycle verbs move behind `semlf`);
  ADR-0015's wheel/zipapp contents, primary channel, and collision story;
  ADR-0004's amendment header, decision parenthetical, and lifecycle-verb sentence.
- **Carries over unchanged:** preflight-then-apply, the provenance manifest,
  structural hook ownership, doctor's replay contract,
  the maintainer-act publishing boundary, and the no-fork mapping rule;
  the managed-upgrade rule is extended by the classifier, not weakened.
- **Rejected alternatives:** routing hooks through the `semlf` command
  (PATH fragility, CLI as a survival dependency, forked hook shape against ADR-0004);
  hook-time lag warnings in the core (lifecycle knowledge does not belong in findings);
  a package-door `cli` target (a `semlf uninstall cli --force` could unlink its own shim);
  a Node/npm channel (skills-only, cannot install the hook).
- **Evidence:** the byte-identity, rendering, classifier-matrix, preflight, migration,
  and identity test families, named by test file.

- [ ] **Step 3: Add the pointers and amend the living documents**

In each of 0004, 0014, 0015: update only the status line
(e.g. `Accepted → Superseded in part by [ADR-0016](0016-one-entry-point-and-the-payload-registry.md)`)
and, where the house format has one, the superseded-by header field —
matching however ADR-0002-style supersessions are already marked in this repo;
copy the existing convention exactly.

In `docs/decisions/README.md`:
add the 0016 index row,
and update any verb-assignment or distribution summary the index restates.

In `.agents/rules/100-project-map.md`:
the layout block gains `cli/semlf/registry.py`, `cli/semlf/classify.py`, `cli/semlf/lifecycle.py`
with one-line responsibilities;
the installer bullet's verb assignment moves install/uninstall/status behind `semlf`;
`scripts/install.py` becomes the checkout door over shared operations, citing ADR-0016.

- [ ] **Step 4: Check and commit**

Run the checker over every touched Markdown file:

```bash
python3 scripts/check_linefeeds.py --file \
  docs/decisions/0016-one-entry-point-and-the-payload-registry.md \
  docs/decisions/0004-portable-core-and-repository-cli.md \
  docs/decisions/0014-lifecycle-verbs-and-the-provenance-manifest.md \
  docs/decisions/0015-distribution-channels.md \
  docs/decisions/README.md .agents/rules/100-project-map.md
git add docs/decisions/ .agents/rules/100-project-map.md
git commit -m "docs(adr): record the install redesign" \
  -m "One superseding record covers the semlf entry point, the
payload registry, the neutral root, the three-axis classifier, and
the PyPI channel; the affected records gain only status pointers,
and the project map amends in the same commit."
```

---

### Task 14: README restructure and payload-source copy

Two tiers: a 60-second quickstart on top,
exhaustive channel detail in an appendix,
and a component matrix naming exactly what an install touches.

**Files:**

- Modify: `README.md`
- Modify: `adapters/agentsmd/SNIPPET.md` (fallback install line)
- Modify: `adapters/codex/INSTALL.md`, `adapters/opencode/INSTALL.md` (only where they name the old install path or flags)

- [ ] **Step 1: Restructure README.md**

Reorder into the design's five tiers, keeping current section text where it already fits:

1. What it is and the diff argument (current opening, trimmed).
2. **Quickstart:**

```bash
uv tool install semlf        # or: pipx install semlf
semlf install                # detects agents, lists every path it would write, asks y/N
semlf doctor                 # replays the payloads end to end
```

   plus the Claude Code marketplace pair,
   plus a per-agent table (codex / opencode / agentsmd / Claude Code → one command each).
   A channel-conflict note sits here:
   one channel per machine, and `semlf doctor` names a collision when it sees one.
3. **What gets installed** — a matrix: component × location × purpose × who needs it.
   State the CLI's optionality per channel:
   on the package channel the `semlf` package is the installer and cannot be skipped,
   but its check commands remain optional;
   a guardrail-only machine with no CLI at all is the checkout door's offer
   (`install.sh --codex`, no `--cli`).
   Locations use the literal paths: `${XDG_DATA_HOME:-~/.local/share}/semlf/check_linefeeds.py`,
   `$CODEX_HOME/hooks.json`, `~/.agents/skills/semantic-linefeeds/SKILL.md`,
   the opencode plugins directory, and the user-named AGENTS.md.
4. The layers, suppression, configuration, and git-modes sections, as today.
5. **Appendix** — air-gapped and mirror installs
   (`install.sh`, `SEMLF_REPO`, the zipapp channel), lifecycle detail
   (upgrade pair `uv tool upgrade semlf && semlf install`, leftovers, `--force` semantics), testing.
   Mention the Vercel `skills` CLI only as a skill-only supplement,
   with the it-cannot-install-the-hook caveat stated.

The quickstart flips to `uv tool install semlf` in this rewrite;
the release-gate task ships it in the same release that first publishes to PyPI,
and nothing is pushed before then, so the constraint holds by construction.

- [ ] **Step 2: Update the snippet's fallback line**

In `adapters/agentsmd/SNIPPET.md`, the fallback install parenthetical becomes:

```markdown
(If `semlf` is not installed:
`uv tool install semlf`, or the equivalent `pipx install semlf`.)
```

The snippet is a registry payload, so its rendering tests keep passing bytes-for-bytes;
only re-run the suite to confirm nothing pinned the old wording.

- [ ] **Step 3: Sweep the adapter INSTALL.md files**

Grep them for `install.py`, `--cli`, and checkout paths;
update the manual-install narratives to lead with `semlf install <target>`
and keep the checkout door as the air-gapped alternative.
The codex INSTALL.md's manual merge instructions name the `__CHECKER__` placeholder
and the neutral checker path (begun in Task 2; finish the prose here).

- [ ] **Step 4: Check and commit**

```bash
python3 scripts/check_linefeeds.py --file README.md \
  adapters/agentsmd/SNIPPET.md adapters/codex/INSTALL.md \
  adapters/opencode/INSTALL.md
python3 -m pytest tests/ -q
git add README.md adapters/
git commit -m "docs: two-tier install README with component matrix" \
  -m "The quickstart is three lines plus the Claude Code marketplace
pair; a matrix names every component, location, purpose, and
audience; channel detail moves to an appendix; the snippet's
fallback line names the package install."
```

---

### Task 15: Release gate — first PyPI publish

The first PyPI publish is a required, closing step of this slice.
Publishing stays a maintainer release act;
repository automation never builds or uploads a PyPI artifact.

**Files:**

- Modify: `CHANGELOG.md`
- Modify: `scripts/check_linefeeds.py` (version bump only, one line)
- Move: `docs/plans/active/2026-08-14-install-redesign-design.md` → `docs/plans/done/`,
  and this plan alongside it, once the release ships.

- [ ] **Step 1: Write the CHANGELOG entry**

Add the release section (user-facing wording only — no slice codenames, no ADR codes,
no process talk; say what changed for someone installing or upgrading).
It must cover:

- `semlf` installs from PyPI; `semlf install` / `status` / `uninstall` / `doctor` are the lifecycle surface.
- Hooks and skills now point at `~/.local/share/semlf/` (or `$XDG_DATA_HOME/semlf/`);
  the upgrade command is the pair `uv tool upgrade semlf && semlf install`.
- The checkout-door behavior deltas, each in plain words:
  the installed hook's target path moved out of the checkout;
  `--dry-run` on a diverged file reports instead of failing;
  files this kit installed upgrade without `--force` and without backups;
  an existing backup file now blocks a forced replace instead of being overwritten;
  `--codex` also publishes the checker and README to the shared root;
  bare `install.py` status no longer probes `./AGENTS.md` (`semlf status agentsmd PATH` replaces it).

- [ ] **Step 2: Bump the version**

Ask the maintainer which number this release carries
(the ADR-0011 gate review sits at the v0.6→v0.7 boundary and its scheduling is their call);
then set `__version__` in `scripts/check_linefeeds.py` accordingly.
Everything else derives from it — pyproject reads it dynamically,
and both doors label artifacts with it —
so the bump must land BEFORE Step 3's validation and Step 4's builds,
or the locally verified artifacts embed the wrong version string.

- [ ] **Step 3: Run the full release validation**

```bash
python3 -m pytest tests/ -q
bun test adapters/opencode/
sh docs/proofs/zipapp-packaging/verify.sh
python3 scripts/check_linefeeds.py --file README.md CHANGELOG.md
```

All green before anything else happens.

- [ ] **Step 4: Build and verify the distribution locally**

```bash
python3 -m build          # sdist + wheel; install `build` via pipx run if absent
python3 -m venv /tmp/semlf-rel && /tmp/semlf-rel/bin/pip install dist/semlf-*.whl
/tmp/semlf-rel/bin/semlf --version
/tmp/semlf-rel/bin/semlf install --dry-run
/tmp/semlf-rel/bin/semlf doctor || true   # inspect output by eye
```

Also verify the sdist path: `pip install dist/semlf-*.tar.gz` into a second venv,
confirming the payload members made it through MANIFEST.in.

- [ ] **Step 5: Hand the maintainer the publish steps**

Publishing is the maintainer's act; present, do not run:

1. Verify the `semlf` name is (still) available or owned on PyPI — this is the release gate.
2. `twine upload dist/*` (or `uv publish`), with their credentials.
3. Tag and push per their release routine.

The README quickstart that names `uv tool install semlf` ships in this same release —
nothing here is pushed or published until the maintainer says so.

- [ ] **Step 6: Close the slice**

After the release ships:
move the design doc and this plan to `docs/plans/done/`,
and commit the move with the release housekeeping.

```bash
git add CHANGELOG.md scripts/check_linefeeds.py
git commit -m "chore(release): prepare the semlf PyPI release" \
  -m "Changelog covers the package-door lifecycle surface, the
neutral payload root, the upgrade pair, and every checkout-door
behavior delta in user-facing words."
```

---

## Self-Review Checklist

Run this after writing code for the final task, before calling the slice done:

1. **Spec coverage.**
   Walk the design doc section by section
   (entry point, neutral root, registry, classifier, preflight/apply, command surface,
   staleness/doctor, zipapp door, two doors, channels, PyPI, README, ADR impact, non-goals, testing)
   and point at the task that implements each;
   any gap becomes a new task.
2. **Byte identity and installed rendering.**
   `test_both_doors_render_identical_artifacts` (checkout vs a built zipapp),
   `test_a_wheel_installed_semlf_renders_the_codex_artifacts` (a venv-installed wheel),
   and the packaging member inspections (direct wheel, sdist-built wheel, pyz)
   are all green.
3. **The classifier matrix.**
   Every design-table cell has a test:
   absent, exact+adopt, managed older/newer/equal/unorderable, edited, unrecorded,
   occupied backup slot,
   and all of symlink, directory, special, and unreadable under both force modes —
   and the uninstall planners were NOT converted to that matrix
   (ADR-0014's force-removal semantics stay pinned by the legacy tests).
4. **Exit codes and precedence.**
   0 success or no-op, 1 refusal or error (including the non-TTY unconfirmed plan),
   64 usage;
   dry-run exits 0 and dominates refusals on BOTH `install` and `uninstall`,
   on both doors —
   grep the tests for each.
5. **One table.**
   `payload_destinations`, `rendered_bytes`, `plan_install`'s walk,
   status and doctor's identity iteration, and both builders all read `registry.ROWS`;
   `test_every_consumer_field_is_complete` guards the invariant.
6. **The Task 11 enumeration is complete.**
   Run `python3 -m pytest tests/test_installer.py -q` after Task 11
   and confirm zero failures outside the enumerated categories;
   any survivor goes into the task list, never into a weakened assertion.
7. **No re-litigated decisions.**
   No code path routes a hook through the `semlf` command,
   auto-installs the agentsmd snippet or the zipapp, adds a package-door `cli` target,
   or edits an accepted ADR's body.
