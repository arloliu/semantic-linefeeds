# Hook Scope, Long-Limit Config, and New Languages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the hooks from flagging agent scratch files under temp directories,
make the long-line advisory threshold configurable,
and extend comment checking to ten more languages plus new C-family extensions.

**Architecture:** All three changes land in the single stdlib core `scripts/check_linefeeds.py`:
`skip_path()` grows a temp-root check used by both hook modes,
the `LONG_LINE` constant becomes a resolved limit (CLI flag over env var over default 120, 0 disables),
and the declarative `LANGUAGES` table gains new entries and extensions.
The adapters need no changes — they all delegate to the core.

**Tech Stack:** Python 3.9+ stdlib only; pytest with the existing marker-fixture corpus.

## Global Constraints

- `scripts/check_linefeeds.py` stays one file, stdlib imports only, Python 3.9+.
- Precision over recall: a missed finding is acceptable, a false positive is a bug.
- `skip_path()` applies to hook modes only;
  `--file` mode never skips paths the user named explicitly.
- Exit codes unchanged: hook 0/2, `--file` 0/1, usage errors 64, `--help` 0.
- All Markdown written or modified must pass
  `python3 scripts/check_linefeeds.py --file <file>` with zero fused/wrap findings.
- Commits follow `.agents/rules/600-git-conventions.md`:
  Conventional Commits, header ≤ 50 chars, body ≤ 72, no attribution trailers.
- Run the full test suite (`python3 -m pytest tests/ -q`) before every commit.
- Version bumps to 0.4.0 only in the final task.

## File Structure (end state)

```
scripts/check_linefeeds.py    # temp skip, long-limit resolution, new LANGUAGES entries
tests/test_cli.py             # temp-skip and long-limit CLI/hook tests appended
tests/test_detector.py        # extension-dispatch test appended
tests/conftest.py             # ALLOWED_SUFFIXES gains the new fixture extensions
tests/fixtures/<lang>/        # bad_/good_ fixture pairs for each new language
README.md                     # languages list + configuration section
CHANGELOG.md                  # [0.4.0] entry
.claude-plugin/plugin.json    # version 0.4.0
```

---

### Task 1: Skip temp and scratch paths in hook mode

**Files:**
- Modify: `scripts/check_linefeeds.py` (imports, `SKIP_DIRS`, `skip_path`)
- Modify: `tests/test_cli.py` (append tests)

**Interfaces:**
- Consumes: `skip_path(path)` as called by `run_hook_claude` and `run_hook_codex`
  (both already call it; no call-site changes).
- Produces: `skip_path` returning True for any path under `tempfile.gettempdir()`
  or containing a `tmp` component.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
def test_skip_path_temp_roots(monkeypatch):
    monkeypatch.setattr(check_linefeeds.tempfile, "tempdir", "/var/folders/zz/T")
    assert check_linefeeds.skip_path("/var/folders/zz/T/prompt.md")
    assert check_linefeeds.skip_path("/var/folders/zz/T/deep/nested/note.md")
    assert not check_linefeeds.skip_path("/var/folders-other/doc.md")


def test_skip_path_tmp_component():
    assert check_linefeeds.skip_path("/tmp/claude/v1_review_prompt.md")
    assert check_linefeeds.skip_path("tmp/PROGRESS.md")
    assert check_linefeeds.skip_path("./tmp/notes.md")
    assert not check_linefeeds.skip_path("docs/tmpl/notes.md")


def test_hook_ignores_temp_markdown():
    import tempfile as _tf
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {
            "file_path": _tf.gettempdir() + "/agent_prompt.md",
            "content": "Bad break here. Another sentence follows.\n",
        },
    })
    r = run_cli(["--hook"], payload)
    assert r.returncode == 0
    assert r.stderr == ""


def test_file_mode_still_checks_temp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(check_linefeeds.tempfile, "tempdir", str(tmp_path))
    bad = tmp_path / "doc.md"
    bad.write_text("One sentence. Two sentences fused.\n", encoding="utf-8")
    assert check_linefeeds.run_files([str(bad)]) == 1
```

Note the last test calls `run_files` directly (unit level)
to prove `--file` mode never consults `skip_path`.

- [ ] **Step 2: Run the tests, expect FAIL**

Run: `python3 -m pytest tests/test_cli.py -q -k "temp or tmp_component"`
Expected: the three new skip tests fail (`skip_path` knows nothing of temp roots);
the `--file` test passes already (guards against a wrong implementation).

- [ ] **Step 3: Implement**

In `scripts/check_linefeeds.py`:
add `import tempfile` to the imports (keep the import block sorted),
add `"tmp"` to `SKIP_DIRS`,
and extend `skip_path`:

```python
SKIP_DIRS = {"vendor", "node_modules", "testdata", "fixtures",
             ".git", "dist", "build", "tmp"}
```

```python
def skip_path(path):
    """Return True if path should be skipped by hook mode.

    Compares path components after normalizing separators,
    so vendor/doc.go (repo-relative), /abs/vendor/doc.go (absolute),
    ./vendor/doc.go (relative), and C:\\repo\\vendor\\doc.go (Windows)
    all match.  Anything under the platform temp directory is also
    skipped: agent scratch files are never deliverables.
    """
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if any(part in SKIP_DIRS for part in p.split("/")):
        return True
    tmp_root = (tempfile.gettempdir() or "").replace("\\", "/").rstrip("/")
    return bool(tmp_root) and p.startswith(tmp_root + "/")
```

- [ ] **Step 4: Run the tests, expect PASS; full suite green**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/check_linefeeds.py tests/test_cli.py
git commit -m "fix: skip temp and scratch paths in hook mode"
```

---

### Task 2: Configurable long-line limit

**Files:**
- Modify: `scripts/check_linefeeds.py`
  (`DEFAULT_LONG_LINE`, `CLI_LONG_LIMIT`, `active_long_limit()`, `check()`, `format_findings()`, `main()`)
- Modify: `tests/test_cli.py` (append tests)

**Interfaces:**
- Consumes: the `long` advisory branch in `check()` and the footer text in `format_findings()`.
- Produces: `active_long_limit() -> int` with precedence
  `--long-limit N` flag > `SEMBR_LONG_LINE` env var > default 120;
  0 disables the advisory entirely;
  module global `CLI_LONG_LIMIT` (None when the flag is absent).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
LONGISH = ("This clause runs on and on past sixty characters, "
           "and the tail keeps going to make the point.\n")


def test_long_limit_flag_lowers_threshold(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    r = run_cli(["--file", str(doc), "--long-limit", "60"])
    assert r.returncode == 0
    assert "[long]" in r.stdout


def test_long_limit_zero_disables_advisory(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("x" * 200 + ", and more text here.\n", encoding="utf-8")
    r = run_cli(["--file", str(doc), "--long-limit", "0"])
    assert r.returncode == 0
    assert "[long]" not in r.stdout


def test_long_limit_env_var(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    env = os.environ.copy()
    env["SEMBR_LONG_LINE"] = "60"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(doc)],
        capture_output=True, text=True, env=env,
    )
    assert "[long]" in r.stdout


def test_long_limit_flag_beats_env(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    env = os.environ.copy()
    env["SEMBR_LONG_LINE"] = "60"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(doc), "--long-limit", "1000"],
        capture_output=True, text=True, env=env,
    )
    assert "[long]" not in r.stdout


def test_long_limit_bad_env_falls_back(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(LONGISH, encoding="utf-8")
    env = os.environ.copy()
    env["SEMBR_LONG_LINE"] = "banana"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--file", str(doc)],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0
    assert "[long]" not in r.stdout  # 95 chars is under the 120 default


def test_long_limit_negative_is_usage_error(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("fine\n", encoding="utf-8")
    assert run_cli(["--file", str(doc), "--long-limit", "-5"]).returncode == 64
```

These tests need `import os` and `import sys` plus `SCRIPT` in `tests/test_cli.py`;
add `import os`, `import sys`, and extend the conftest import line to
`from conftest import PAYLOADS, FIXTURES, run_cli, load_fixture, REPO, SCRIPT`
(`SCRIPT` already exists in `tests/conftest.py`).

- [ ] **Step 2: Run the tests, expect FAIL**

Run: `python3 -m pytest tests/test_cli.py -q -k long_limit`
Expected: `--long-limit` is rejected by argparse today, so every flag test exits 64.

- [ ] **Step 3: Implement**

In `scripts/check_linefeeds.py`,
replace the `LONG_LINE = 120` constant with:

```python
DEFAULT_LONG_LINE = 120
CLI_LONG_LIMIT = None  # set by --long-limit in main()


def active_long_limit():
    """Resolve the long-line advisory threshold; 0 disables it.

    Precedence: --long-limit flag, then $SEMBR_LONG_LINE, then 120.
    A malformed or negative env value falls back to the default.
    """
    if CLI_LONG_LIMIT is not None:
        return CLI_LONG_LIMIT
    raw = os.environ.get("SEMBR_LONG_LINE", "")
    if raw:
        try:
            value = int(raw)
            if value >= 0:
                return value
        except ValueError:
            pass
    return DEFAULT_LONG_LINE
```

`import os` is already present after Task 1 (add it here if not).

In `check()`, replace the advisory branch:

```python
        limit = active_long_limit()
        if limit and len(raw) > limit and BOUNDARY_HINT_RE.search(prose):
            findings.append((
                lineno, "long",
                f"advisory: {len(raw)} chars with a possible clause boundary — scan from ~{limit} rightward for ';' ':' '—' or an independent-clause 'and/but/so' / 'which/that/where', else backward; split only at a boundary where both sides stand alone, else leave the line long",
                prose,
            ))
```

Hoist `limit = active_long_limit()` above the loop (one resolution per check call).

In `format_findings()`, the footer sentence
`"split sentences over ~120 chars at a real clause boundary"`
becomes an f-string using the active limit:

```python
        f"split sentences over ~{active_long_limit() or DEFAULT_LONG_LINE} chars at a real clause boundary "
```

In `main()`, add the flag and validation:

```python
    ap.add_argument("--long-limit", type=int, default=None, metavar="N",
                    help="long-line advisory threshold in chars; 0 disables "
                         "(default: $SEMBR_LONG_LINE or 120)")
```

and after argument parsing, before mode dispatch:

```python
    if args.long_limit is not None:
        if args.long_limit < 0:
            print("check_linefeeds: --long-limit must be >= 0", file=sys.stderr)
            sys.exit(64)
        global CLI_LONG_LIMIT
        CLI_LONG_LIMIT = args.long_limit
```

(`main()` needs no `global` today; add the declaration at the top of `main()`.)

- [ ] **Step 4: Run the tests, expect PASS; full suite green**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/check_linefeeds.py tests/test_cli.py
git commit -m "feat: configurable long-line limit"
```

---

### Task 3: Ten new languages and new C-family extensions

**Files:**
- Modify: `scripts/check_linefeeds.py` (`LANGUAGES` table only)
- Modify: `tests/conftest.py` (`ALLOWED_SUFFIXES`)
- Modify: `tests/test_detector.py` (append dispatch test)
- Create: fixture pairs under `tests/fixtures/<lang>/` as listed below

**Interfaces:**
- Consumes: the `Language` namedtuple and `_lang()` helper;
  block delimiters are matched before line markers,
  and line/doc markers are matched longest-first
  (so `--[[` beats `--`, and `'''` beats `'`).
- Produces: `lang_for_path` resolving the new extensions;
  no signature changes anywhere.

- [ ] **Step 1: Extend `ALLOWED_SUFFIXES`** in `tests/conftest.py`:

```python
ALLOWED_SUFFIXES = {".go", ".md", ".java", ".ts", ".rs", ".py", ".sh", ".c",
                    ".kt", ".vb", ".sql", ".lua", ".rb", ".pl", ".ps1", ".r",
                    ".hs", ".ex", ".zig"}
```

- [ ] **Step 2: Write the failing dispatch test** (append to `tests/test_detector.py`)

```python
@pytest.mark.parametrize("ext,name", [
    (".kt", "cfamily"), (".kts", "cfamily"), (".swift", "cfamily"),
    (".scala", "cfamily"), (".dart", "cfamily"), (".m", "cfamily"),
    (".mm", "cfamily"), (".php", "cfamily"), (".groovy", "cfamily"),
    (".gradle", "cfamily"),
    (".vb", "vbnet"), (".sql", "sql"), (".lua", "lua"),
    (".rb", "ruby"), (".rake", "ruby"), (".pl", "perl"), (".pm", "perl"),
    (".ps1", "powershell"), (".psm1", "powershell"), (".psd1", "powershell"),
    (".r", "rlang"), (".R", "rlang"), (".hs", "haskell"),
    (".ex", "elixir"), (".exs", "elixir"), (".zig", "zig"),
])
def test_new_extension_dispatch(ext, name):
    lang = check_linefeeds.lang_for_path(f"example{ext}")
    assert lang is not None and lang.name == name
```

- [ ] **Step 3: Create the fixture pairs**

Each `bad_` fixture carries `{fused}` or `{wrap}` markers on the offending lines;
each `good_` fixture must yield zero findings.
Create exactly these files:

`tests/fixtures/kotlin/bad_comments.kt`

```kotlin
// Parses the manifest. It caches results. {fused}
fun parse() = Unit
```

`tests/fixtures/kotlin/good_comments.kt`

```kotlin
/** Parses the manifest. */
fun parse() = Unit
```

`tests/fixtures/vbnet/bad_comments.vb`

```vb
''' Renders the report. Callers must dispose it. {fused}
Sub Render()
```

`tests/fixtures/vbnet/good_comments.vb`

```vb
''' <summary>
''' Renders the report.
''' </summary>
Sub Render()
```

`tests/fixtures/sql/bad_comments.sql`

```sql
-- Counts users. It excludes bots. {fused}
SELECT 1;
```

`tests/fixtures/sql/good_comments.sql`

```sql
-- Counts active users.
-- Rows older than a year are ignored.
SELECT 1;
```

`tests/fixtures/lua/bad_comments.lua`

```lua
-- This helper trims the cache. It also rebuilds the index. {fused}
-- The rebuild walks every entry and {wrap}
-- compacts the freelist.
local function trim() end
```

`tests/fixtures/lua/good_comments.lua`

```lua
--[[ Trims the cache.
Compacts the freelist. ]]
local function trim() end
```

`tests/fixtures/ruby/bad_comments.rb`

```ruby
# frozen_string_literal: true
# The importer batches rows and {wrap}
# retries transient failures.
def import; end
```

`tests/fixtures/ruby/good_comments.rb`

```ruby
# frozen_string_literal: true

# The importer batches rows
# and retries transient failures.
def import; end
```

`tests/fixtures/perl/bad_comments.pl`

```perl
# Reads the manifest. It skips symlinks. {fused}
print 1;
```

`tests/fixtures/perl/good_comments.pl`

```perl
#!/usr/bin/perl
# Reads the manifest.
# Missing files abort the run.
print 1;
```

`tests/fixtures/powershell/bad_comments.ps1`

```powershell
# Loads settings. It merges defaults. {fused}
function Load {}
```

`tests/fixtures/powershell/good_comments.ps1`

```powershell
<# Loads settings.
   Returns a hashtable. #>
function Load {}
```

`tests/fixtures/rlang/bad_comments.r`

```r
# Fits the model. It scales inputs. {fused}
fit <- function(x) x
```

`tests/fixtures/rlang/good_comments.r`

```r
#' Fits the model.
#' @param x input matrix
fit <- function(x) x
```

`tests/fixtures/haskell/bad_comments.hs`

```haskell
-- Parses the config. It validates keys. {fused}
main = pure ()
```

`tests/fixtures/haskell/good_comments.hs`

```haskell
{- This module parses configs.
   It stays dependency free. -}
main = pure ()
```

`tests/fixtures/elixir/bad_comments.ex`

```elixir
# Starts the worker. It links to the caller. {fused}
def start, do: :ok
```

`tests/fixtures/elixir/good_comments.ex`

```elixir
# Starts the worker.
# It links to the caller.
def start, do: :ok
```

`tests/fixtures/zig/bad_comments.zig`

```zig
/// Allocates the pool. The caller owns it. {fused}
pub fn init() void {}
```

`tests/fixtures/zig/good_comments.zig`

```zig
//! Pool allocator.
/// Allocates the pool.
/// The caller owns it.
pub fn init() void {}
```

- [ ] **Step 4: Run the tests, expect FAIL**

Run: `python3 -m pytest tests/test_detector.py -q`
Expected: the dispatch parametrizations fail (unknown extensions),
and every new `bad_` fixture fails
because `check()` returns no findings for an unknown language.

- [ ] **Step 5: Implement — extend the `LANGUAGES` table**

In `scripts/check_linefeeds.py`,
extend the cfamily extension list and append the new entries,
so the table reads:

```python
LANGUAGES = [
    _lang("go", [".go"], line="//", blocks=[("/*", "*/")],
          directives=[r"^//[a-zA-Z0-9_+-]+:"]),
    _lang("cfamily",
          [".c", ".h", ".cc", ".cpp", ".hpp", ".hh", ".java",
           ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".cs",
           ".kt", ".kts", ".swift", ".scala", ".dart", ".m", ".mm",
           ".php", ".groovy", ".gradle"],
          line="//", doc_lines=["///"], blocks=[("/*", "*/")], block_prefix="*",
          directives=[r"^//[a-zA-Z0-9_+-]+:",
                      r"^//\s*(eslint|prettier|biome|@ts-|tslint|NOLINT|noinspection|istanbul)"]),
    _lang("rust", [".rs"], line="//", doc_lines=["///", "//!"],
          blocks=[("/*", "*/")], block_prefix="*"),
    _lang("python", [".py", ".pyi"], line="#", docstrings=True,
          directives=[r"^#!",
                      r"^#\s*-\*-",
                      r"^#\s*(noqa|type:|pylint:|ruff:|flake8:|fmt:|isort:|mypy:|pragma:)",
                      r"^#[a-zA-Z0-9_+-]+:"]),
    _lang("shell", [".sh", ".bash"], line="#",
          directives=[r"^#!", r"^#\s*shellcheck"]),
    _lang("vbnet", [".vb"], line="'", doc_lines=["'''"]),
    _lang("sql", [".sql"], line="--", blocks=[("/*", "*/")], block_prefix="*"),
    _lang("lua", [".lua"], line="--", blocks=[("--[[", "]]")],
          directives=[r"^---@"]),
    _lang("ruby", [".rb", ".rake"], line="#",
          directives=[r"^#!",
                      r"^#\s*(frozen_string_literal|rubocop|encoding|typed):"]),
    _lang("perl", [".pl", ".pm"], line="#", directives=[r"^#!"]),
    _lang("powershell", [".ps1", ".psm1", ".psd1"], line="#",
          blocks=[("<#", "#>")], directives=[r"^#[rR]equires"]),
    _lang("rlang", [".r", ".R"], line="#", doc_lines=["#'"]),
    _lang("haskell", [".hs"], line="--", blocks=[("{-", "-}")]),
    _lang("elixir", [".ex", ".exs"], line="#", directives=[r"^#!"]),
    _lang("zig", [".zig"], line="//", doc_lines=["///", "//!"]),
]
```

The entry name is `rlang` (not `r`) purely for grep-ability;
`lang_for_path` matches on extensions, never names.

- [ ] **Step 6: Run the tests, expect PASS; full suite green**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 7: Commit**

```bash
git add scripts/check_linefeeds.py tests/conftest.py tests/test_detector.py tests/fixtures/
git commit -m "feat: support ten more comment languages"
```

---

### Task 4: Docs, CHANGELOG, v0.4.0

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`
- Check (modify only if they state a fixed 120 or an old language list):
  `skills/semantic-linefeeds/SKILL.md`, `adapters/agentsmd/SNIPPET.md`,
  `.claude-plugin/plugin.json` description

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: the released 0.4.0 surface.

- [ ] **Step 1: Update README.md**

Where the README names the supported languages
(intro and/or a languages section — locate with `grep -n "Rust\|C-family" README.md`),
extend the list to:
Go, C-family (C, C++, Java, JavaScript/TypeScript, C#, Kotlin, Swift, Scala, Dart, Objective-C, PHP, Groovy),
Rust, Python, shell, VB.NET, SQL, Lua, Ruby, Perl, PowerShell, R, Haskell, Elixir, Zig, and Markdown.

Add a `## Configuration` section after the install matrix:

```markdown
## Configuration

The long-line advisory threshold defaults to 120 characters.
Set it per run with `--long-limit N` (0 disables the advisory),
or per environment with `SEMBR_LONG_LINE=N`;
the flag wins over the environment variable.
Fused and wrap findings are never affected — only the advisory moves.

Hook mode skips paths under the platform temp directory and any
`tmp/` component, so agent scratch files are never flagged.
`--file` mode always checks exactly the paths you name.
```

- [ ] **Step 2: Sweep for stale "120" and language-list mentions**

Run: `grep -rn "120" README.md skills/ adapters/agentsmd/ .claude-plugin/plugin.json`
Update any text that presents 120 as a fixed value,
so it reads "configurable, default 120" (keep it to one clause).
Update the plugin.json `description` language list to include the new names
(one sentence, no full enumeration needed — "and more" after the headline names is fine).

- [ ] **Step 3: CHANGELOG.md** — add above the `[0.3.0]` entry:

```markdown
## [0.4.0] - 2026-08-09

### Added

- Ten new comment languages:
  VB.NET, SQL, Lua, Ruby, Perl, PowerShell, R, Haskell, Elixir, and Zig,
  plus new C-family extensions
  (Kotlin, Swift, Scala, Dart, Objective-C, PHP, Groovy/Gradle).
- Configurable long-line advisory threshold:
  `--long-limit N` flag and `SEMBR_LONG_LINE` env var, 0 disables;
  default stays 120.

### Fixed

- Hook mode no longer flags files under the platform temp directory
  or any `tmp/` path component,
  so agent-generated scratch and prompt files pass untouched.
```

- [ ] **Step 4: `.claude-plugin/plugin.json`** — set `"version": "0.4.0"`.

- [ ] **Step 5: Self-check every touched Markdown file**

```bash
python3 scripts/check_linefeeds.py --file README.md CHANGELOG.md \
  docs/plans/2026-08-09-scope-config-langs.md
```

plus any skill/snippet file modified in Step 2.
Expected: exit 0, zero fused/wrap.

- [ ] **Step 6: Full suite green, commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "docs: prepare the v0.4.0 release"
```

---

### Task 5: install.sh bootstrapper

**Files:**
- Create: `install.sh` (repo root)
- Modify: `tests/test_installer.py` (append bootstrapper tests)

**Interfaces:**
- Consumes: `scripts/install.py`'s CLI surface (`--codex`, `--opencode`, `--agentsmd`, `--dry-run`, `--force`, no-args status).
- Produces: a POSIX-sh bootstrapper that fetches or updates the repo into `$SEMBR_HOME`
  and delegates every remaining argument to `install.py`;
  overrides `SEMBR_REPO`/`--repo`, `SEMBR_HOME`/`--home`, `SEMBR_REF`/`--ref`.

Behavior contract:

- Defaults: repo `https://github.com/arloliu/semantic-linefeeds.git`,
  home `${XDG_DATA_HOME:-$HOME/.local/share}/semantic-linefeeds`, ref empty (remote default branch).
- Flags `--repo`, `--home`, `--ref` are consumed by the script;
  every other argument passes through to `install.py` verbatim
  (POSIX single-quote escaping via an `eval "set -- $pass"` rebuild).
- Self-checkout detection: when `$0` ends in `install.sh`
  and `scripts/check_linefeeds.py` exists beside it
  and neither `--repo` nor `SEMBR_REPO` was given,
  use that checkout directly and skip fetching entirely.
  A piped run (`curl … | sh`) has `$0 = sh`, so it never self-detects.
- Fetch path: `git clone` (with `--branch "$ref"` when a ref is given) into `$SEMBR_HOME`
  when `$SEMBR_HOME/.git` is absent.
  On rerun without a ref: `git -C "$SEMBR_HOME" pull --ff-only`.
  On rerun with a ref: `git -C "$SEMBR_HOME" fetch origin "$ref"`
  then `git -C "$SEMBR_HOME" checkout --detach FETCH_HEAD` —
  never an unconditional pull, which fails on a detached pinned checkout.
- Friendly errors (exit 1, stderr) when `git` or `python3` is missing.
- Ends with `exec python3 "$home_dir/scripts/install.py" "$@"`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_installer.py`)

```python
INSTALL_SH = REPO / "install.sh"


def make_source_repo(tmp_path):
    """A minimal git repo carrying just what install.py needs."""
    src = tmp_path / "source-repo"
    src.mkdir()
    shutil.copytree(REPO / "scripts", src / "scripts")
    shutil.copytree(REPO / "adapters", src / "adapters")
    git = ["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    return src


def run_install_sh(args, env_overrides, cwd=None):
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        ["sh", str(INSTALL_SH)] + args,
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def test_install_sh_clones_and_installs_codex(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    r = run_install_sh(["--repo", str(src), "--home", str(home), "--codex"],
                       isolated_env(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (home / "scripts" / "install.py").exists()
    assert codex_hooks_path(tmp_path).exists()


def test_install_sh_rerun_pulls_and_is_idempotent(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = isolated_env(tmp_path)
    run_install_sh(["--repo", str(src), "--home", str(home), "--codex"], env)
    r = run_install_sh(["--repo", str(src), "--home", str(home), "--codex"], env)
    assert r.returncode == 0, r.stderr
    assert "already" in r.stdout.lower()


def test_install_sh_env_repo_and_dry_run(tmp_path):
    src = make_source_repo(tmp_path)
    home = tmp_path / "sembr-home"
    env = isolated_env(tmp_path)
    env["SEMBR_REPO"] = str(src)
    env["SEMBR_HOME"] = str(home)
    r = run_install_sh(["--codex", "--dry-run"], env)
    assert r.returncode == 0, r.stderr
    assert not codex_hooks_path(tmp_path).exists()
    assert "dry-run" in r.stdout.lower()


def test_install_sh_uses_own_checkout_without_repo(tmp_path):
    never = tmp_path / "never-created"
    env = isolated_env(tmp_path)
    env["SEMBR_HOME"] = str(never)
    r = run_install_sh([], env)
    assert r.returncode == 0, r.stderr
    assert "codex:" in r.stdout
    assert not never.exists()
```

- [ ] **Step 2: Run the tests, expect FAIL**

Run: `python3 -m pytest tests/test_installer.py -q -k install_sh`
Expected: FAIL — `install.sh` does not exist.

- [ ] **Step 3: Write `install.sh`** implementing the behavior contract above,
  with a header comment showing the curl one-liner and the private-mirror form.
  Mark it executable (`chmod +x install.sh`).

- [ ] **Step 4: Run the tests, expect PASS; full suite green**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 5: Commit**

```bash
git add install.sh tests/test_installer.py
git commit -m "feat: curl-able install.sh bootstrapper"
```

---

### Task 6: User-facing README rewrite

**Files:**
- Rewrite: `README.md`
- Modify: `CHANGELOG.md` (extend the 0.4.0 Added section)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–5 plus the 0.3.0 installer.
- Produces: the release-facing README.

Required structure (content guidance, not verbatim copy):

1. Title + a short pitch: what the kit does and the concrete benefit
   (one-line diffs, reviewable blame, prose that survives agent editing).
2. A "why semantic line breaks" concept section, linking https://sembr.org,
   showing a two-or-three-line before/after diff example.
3. A "why a prompt rule is not enough" section,
   which keeps the three-layer explanation (hook, skill, detector) from the current README.
4. Quick start: the curl one-liner first,
   then the per-agent matrix where every row links to its guide —
   `adapters/codex/INSTALL.md`, `adapters/opencode/INSTALL.md`,
   `adapters/agentsmd/SNIPPET.md` — and the Claude Code marketplace block.
5. A "private network" subsection: curl the raw `install.sh` from the mirror,
   pass the mirror via `--repo` or `SEMBR_REPO`;
   Claude Code side covered by `claude plugin marketplace add <private remote>`.
6. Configuration, Supported languages, CLAUDE.md companion, Testing —
   carried over from the current README, updated where Task 5 changes them.

Constraints: SemBr from the first draft (one sentence per line);
plain direct prose — no filler phrases, no rhetorical setups,
active voice, concrete examples over abstractions.

- [ ] **Step 1: Rewrite README.md** per the structure above.
- [ ] **Step 2: Extend the changelog** —
  add the `install.sh` bootstrapper and the README rewrite to the `[0.4.0]` Added section.
- [ ] **Step 3: Self-check**

```bash
python3 scripts/check_linefeeds.py --file README.md CHANGELOG.md
```

Expected: exit 0, zero fused/wrap.

- [ ] **Step 4: Full suite green, commit**

```bash
python3 -m pytest tests/ -q
git add README.md CHANGELOG.md
git commit -m "docs: rewrite README around the install story"
```

---

## Verification checklist (run after the final task)

- `python3 -m pytest tests/ -q` — all green.
- Hook smoke: pipe a Write payload targeting `$(python3 -c "import tempfile;print(tempfile.gettempdir())")/x.md`
  with fused text into `python3 scripts/check_linefeeds.py --hook` — exit 0, silent.
- `python3 scripts/check_linefeeds.py --file README.md --long-limit 0` — no `[long]` lines.
- `SEMBR_LONG_LINE=60 python3 scripts/check_linefeeds.py --file README.md` — advisories appear, exit 0.
- `grep -E "^import|^from" scripts/check_linefeeds.py` — stdlib only.
- `python3 scripts/check_linefeeds.py --file $(git ls-files '*.md' ':!tests/')` — exit 0.
