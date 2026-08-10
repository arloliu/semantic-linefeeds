# Multi-Agent, Multi-Language Semantic Linefeeds Implementation Plan

> **For agentic workers:** implement this plan task-by-task, with a review checkpoint after each task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Widen the semantic-linefeeds plugin along three axes:
agents (Claude Code → also Codex CLI and opencode),
languages (Go + Markdown → also C/C++, Java, JS/TS, C#, Rust, Python, shell, and docstrings),
and tests (bash script → pytest golden fixtures).

**Architecture:** One stdlib-only single-file Python core (`scripts/check_linefeeds.py`),
restructured around a Vale-style per-language table feeding a shared comment extractor and a language-agnostic checker.
Thin per-agent adapters on top:
the existing Claude plugin,
a Codex `hooks.json` (Codex ships Claude-style hooks, stable and default-on),
and a ~40-line opencode TypeScript plugin that shells out to the core.
Tests move to pytest:
markdownlint-style inline expectation markers for the detector,
Vale-style JSON goldens for the extractor,
and recorded hook payloads for the adapters.

**Tech Stack:** Python 3.9+ stdlib only (core + tests via pytest);
TypeScript for the opencode adapter (tested with `bun test`);
no runtime dependencies anywhere.

**Review status:** four external review rounds were run against this plan before implementation.
The findings they produced are incorporated below rather than summarized here;
the P0s concerned the Codex payload field name, patch-parser handling of renames and disjoint hunks,
and repo-relative path matching in `skip_path`.

**Design rationale:** grounded in `docs/research/2026-08-08-widening-scope.md`.
Key decisions locked in from that research:

- **Single-file core, not a package.**
  The "copy one file, runs on bare python3" property is what makes every adapter trivial:
  the opencode plugin ships the script next to itself,
  and Codex points a hooks.json at it.
  Split into a package only if the file exceeds ~1000 lines.
- **Table-driven regex state machine, not tree-sitter.**
  Vale affords tree-sitter because it ships a compiled binary;
  `py-tree-sitter` would end the zero-dependency install story.
  Even Vale needs a regex layer to clean comment bodies.
  The known failure mode (comment markers inside string literals) is capped:
  the hook sees only freshly written text and findings are advisory.
- **Adapters reuse the Claude contract.**
  Codex loads Claude-schema `hooks.json` with identical exit-2/stderr semantics
  (verified in `codex-rs/hooks/src/events/post_tool_use.rs`);
  only the tool vocabulary differs:
  the tool is `apply_patch`, and the patch text arrives as `tool_input.command`
  (verified in `codex-rs/core/src/tools/handlers/apply_patch.rs:439` and `hook_names.rs:24`).
  opencode has no subprocess hooks,
  so its TS plugin builds a Claude-shaped payload and pipes it to `--hook claude`;
  its `edit`/`write` arg names are verified against `packages/opencode/src/tool/edit.ts:42`,
  `write.ts:18`, and `packages/plugin/src/index.ts:265`.
- **Two golden styles at two seams.**
  Inline `{fused}`/`{wrap}`/`{long}` markers in detector fixtures
  (markdownlint pattern: the expectation sits next to the offending line);
  JSON goldens for the extractor (Vale pattern: positional data in structured files);
  recorded payloads for adapters.
- **MCP and AGENTS.md are distribution extras, not the backbone.**
  An AGENTS.md snippet covers agents with no hook surface;
  MCP is deliberately out of scope for enforcement.

## Global Constraints

- Core stays ONE file:
  `scripts/check_linefeeds.py`, Python 3.9+, stdlib imports only (`argparse collections json re sys`).
- Precision over recall everywhere:
  the checker flags suspicion, the agent judges;
  when a heuristic is uncertain, skip the line.
  A miss is acceptable; a false positive is a bug.
- Hook modes check ONLY the text just written, never the whole file;
  `--file` mode checks whole files, and its `long` findings never affect the exit code.
- Exit codes: `--file` 0 clean / 1 violations-or-unreadable-input;
  `--hook` 0 clean-or-not-applicable / 2 findings with stderr feedback;
  64 usage error;
  `--help` exits 0.
  `--json` is valid only with `--file`.
- `LONG_LINE = 120` stays;
  the `CONNECTORS`, `OK_LINE_ENDERS`, `FUSED_RE`, and `BOUNDARY_HINT_RE` heuristics keep their current semantics.
- All Markdown prose written for this repo (plan, README, SKILL.md) must itself pass `--file` with zero fused/wrap findings.
- Never add `Co-Authored-By` or any attribution trailer to commits (user's global rule).
- Run the full test suite (`python3 -m pytest tests/ -q`) before every commit;
  a task is not done with red tests.
- Detector fixtures need not compile;
  they exist to exercise the regex extractor.
- Version bumps to 0.2.0 only in the final task.

## File Structure (end state)

```
scripts/check_linefeeds.py        # single-file core: table, extractor, checker, CLI, payload parsers
hooks/hooks.json                  # Claude adapter (command gains explicit "claude" agent arg)
skills/semantic-linefeeds/SKILL.md
adapters/codex/hooks.json         # Codex adapter template
adapters/codex/INSTALL.md
adapters/opencode/semantic-linefeeds.ts   # opencode plugin (runtime-import-free; type-only import)
adapters/opencode/semantic-linefeeds.test.ts
adapters/opencode/INSTALL.md
adapters/agentsmd/SNIPPET.md      # AGENTS.md paragraph for hook-less agents
tests/conftest.py                 # marker parsing, golden helpers, --update-golden
tests/test_detector.py            # parametrized over tests/fixtures/**
tests/test_extractor.py           # Vale-style in/out goldens
tests/test_cli.py                 # subprocess tests replaying tests/payloads/*.json
tests/fixtures/{go,markdown,cfamily,rust,python,shell}/   # bad_*/good_* files with inline markers
tests/extractor/in/  tests/extractor/out/
tests/payloads/*.json
```

---

### Task 1: Pytest harness replacing the bash tests

**Files:**
- Create: `tests/conftest.py`, `tests/test_detector.py`, `tests/test_cli.py`
- Create: `tests/payloads/claude_edit_bad.json`,
  `tests/payloads/claude_edit_good.json`,
  `tests/payloads/claude_other_file.json`
- Move: `tests/fixtures/*.{go,md}` into `tests/fixtures/go/` and `tests/fixtures/markdown/`,
  adding inline markers to the bad fixtures
- Delete: `tests/run_tests.sh`, `scripts/__pycache__/`

**Interfaces:**
- Consumes: `check(text, path) -> list[(lineno, kind, message, excerpt)]` from `scripts/check_linefeeds.py` (already exists).
- Produces: `load_fixture(path) -> (stripped_text, expected)` in `conftest.py`,
  where `expected` is `[(lineno, kind), ...]`;
  `run_cli(args, stdin_text) -> CompletedProcess` in `conftest.py`;
  `ALLOWED_SUFFIXES` in `conftest.py`.
  Later tasks add fixtures and payloads into the same directories and get picked up automatically.

- [ ] **Step 1: Write conftest.py**

```python
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_linefeeds.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PAYLOADS = Path(__file__).resolve().parent / "payloads"

sys.path.insert(0, str(REPO / "scripts"))

# The full set of extensions the fixture corpus may use; anything else in
# tests/fixtures/ is a mistake and fails test_fixture_corpus_is_intentional.
ALLOWED_SUFFIXES = {".go", ".md", ".java", ".ts", ".rs", ".py", ".sh", ".c"}

# A marker like "{fused}" on a line asserts one finding of that kind on that
# line; markers are stripped before the text is checked.  A line may carry
# several markers.
MARKER_RE = re.compile(r"\s*\{(fused|wrap|long)\}")


def load_fixture(path):
    """Return (text_without_markers, [(lineno, kind), ...])."""
    expected, out_lines = [], []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in MARKER_RE.finditer(line):
            expected.append((i, m.group(1)))
        out_lines.append(MARKER_RE.sub("", line))
    return "\n".join(out_lines) + "\n", expected


def run_cli(args, stdin_text=""):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        input=stdin_text, capture_output=True, text=True,
    )


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true",
                     help="rewrite extractor golden files from current output")
```

- [ ] **Step 2: Write test_detector.py**

```python
import pytest
from conftest import ALLOWED_SUFFIXES, FIXTURES, load_fixture

import check_linefeeds

ALL_FIXTURES = sorted(p for p in FIXTURES.rglob("*") if p.is_file())


def test_fixture_corpus_is_intentional():
    for path in ALL_FIXTURES:
        assert path.suffix in ALLOWED_SUFFIXES, f"unexpected fixture type: {path}"
        assert path.name.startswith(("bad_", "good_", "advisory_")), \
            f"fixture name must declare intent: {path}"


@pytest.mark.parametrize("path", ALL_FIXTURES,
                         ids=lambda p: f"{p.parent.name}/{p.name}")
def test_fixture(path):
    text, expected = load_fixture(path)
    got = [(f[0], f[1]) for f in check_linefeeds.check(text, str(path))]
    assert sorted(got) == sorted(expected)


def test_good_fixtures_have_no_markers():
    for path in ALL_FIXTURES:
        if path.name.startswith("good_"):
            _, expected = load_fixture(path)
            assert expected == [], f"{path} is a good_ fixture but carries markers"
```

Note: `check()` keys off the path suffix,
and fixture paths keep their real extensions,
so passing the fixture's own path exercises the right language.
The fixture-directory paths contain `/fixtures/`,
which Task 6 adds to the hook-mode path filter;
that filter is never consulted by `check()`, so these tests are unaffected.

- [ ] **Step 3: Write payload fixtures**

The payloads carry the full field set of a real Claude Code PostToolUse event
(the official schema documents `session_id`, `transcript_path`, `cwd`, `hook_event_name`,
`tool_name`, `tool_input`, `tool_response`),
so the adapter is tested against the shape it actually receives.
Provenance (review requirement):
these fixtures are AUTHORED from the cited schema, not captured from a live session;
Task 10's release gate therefore includes a live end-to-end validation per agent,
and any divergence found there must be folded back into these fixtures.

`tests/payloads/claude_edit_bad.json`:

```json
{"session_id": "s1", "transcript_path": "/tmp/t.jsonl", "cwd": "/x", "hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/x/doc.go", "old_string": "old", "new_string": "// Package cache provides caches. A cache\n// holds a bounded number of entries here\n// and evicts old ones.", "replace_all": false}, "tool_response": {"filePath": "/x/doc.go"}}
```

`tests/payloads/claude_edit_good.json`:

```json
{"session_id": "s1", "transcript_path": "/tmp/t.jsonl", "cwd": "/x", "hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/x/doc.go", "old_string": "old", "new_string": "// Package cache provides fixed-capacity, in-memory key/value caches.\n// A cache holds a bounded number of entries.", "replace_all": false}, "tool_response": {"filePath": "/x/doc.go"}}
```

`tests/payloads/claude_other_file.json`:

```json
{"session_id": "s1", "transcript_path": "/tmp/t.jsonl", "cwd": "/x", "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": "/x/main.xyz", "content": "wrapped prose. More prose\nthat would be flagged in md."}, "tool_response": {"filePath": "/x/main.xyz"}}
```

The non-target extension is `.xyz`, not `.py`:
Python becomes a target language in Task 5, and this fixture must stay non-target.

- [ ] **Step 4: Write test_cli.py** (ports every bash assertion)

```python
from conftest import PAYLOADS, FIXTURES, run_cli, load_fixture


def hook(payload_name):
    return run_cli(["--hook"], (PAYLOADS / payload_name).read_text())


def test_hook_bad_edit_blocks():
    r = hook("claude_edit_bad.json")
    assert r.returncode == 2
    assert "[fused]" in r.stderr
    assert "[wrap]" in r.stderr
    assert "semantic-linefeeds skill" in r.stderr


def test_hook_good_edit_passes():
    assert hook("claude_edit_good.json").returncode == 0


def test_hook_non_target_file_ignored():
    assert hook("claude_other_file.json").returncode == 0


def test_hook_malformed_json_never_crashes():
    assert run_cli(["--hook"], "not json").returncode == 0


def test_file_mode_bad_fixture_exits_1(tmp_path):
    text, _ = load_fixture(FIXTURES / "go" / "bad_wrapped.go")
    f = tmp_path / "bad_wrapped.go"
    f.write_text(text)
    assert run_cli(["--file", str(f)]).returncode == 1


def test_file_mode_long_is_advisory(tmp_path):
    text, _ = load_fixture(FIXTURES / "markdown" / "advisory_long.md")
    f = tmp_path / "advisory_long.md"
    f.write_text(text)
    r = run_cli(["--file", str(f)])
    assert r.returncode == 0
    assert "[long]" in r.stdout
```

- [ ] **Step 5: Move fixtures and add markers**

```bash
mkdir -p tests/fixtures/go tests/fixtures/markdown
git mv tests/fixtures/bad_wrapped.go tests/fixtures/good_sembr.go tests/fixtures/go/
git mv tests/fixtures/bad_wrapped.md tests/fixtures/good_sembr.md tests/fixtures/advisory_long.md tests/fixtures/markdown/
```

Then run the current checker over the three bad fixtures to learn the exact linenos:

```bash
python3 scripts/check_linefeeds.py --file \
  tests/fixtures/go/bad_wrapped.go \
  tests/fixtures/markdown/bad_wrapped.md \
  tests/fixtures/markdown/advisory_long.md
```

For every reported finding, append ` {kind}` to the end of that exact line in the fixture
(a line reported as `[fused] line 4` gets ` {fused}` appended).
The known totals to place:
`bad_wrapped.go` 3× `{fused}` + 2× `{wrap}`,
`bad_wrapped.md` 1× `{fused}` + 2× `{wrap}`,
`advisory_long.md` 1× `{long}`.
Caution: a `wrap` finding is reported on the line that ends mid-clause (the upper line),
so its marker goes on the reported lineno, not on the continuation line.

- [ ] **Step 6: Run pytest, expect all green**

Run: `python3 -m pytest tests/ -q`
Expected: all pass.
If a detector test fails, a marker is on the wrong line;
re-check against the `--file` output linenos.

- [ ] **Step 7: Delete the bash harness and stale cache**

```bash
git rm tests/run_tests.sh
rm -rf scripts/__pycache__
echo "__pycache__/" >> .gitignore
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "test: replace bash harness with pytest inline-marker fixtures"
```

---

### Task 2: Table-driven extractor (Go via the table, plus column coalescing)

**Files:**
- Modify: `scripts/check_linefeeds.py`
  (replace `prose_lines_go` with a `Language` table + `prose_lines_code`; add `prose_stream` dispatch)
- Create: `tests/fixtures/go/good_columns.go`, `tests/fixtures/go/good_generated.go`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  `Language` namedtuple `(name, extensions, line, doc_lines, blocks, block_prefix, directives, docstrings)`;
  `LANGUAGES` list;
  `lang_for_path(path) -> Language | None`;
  `prose_lines_code(text, lang)` generator yielding `(lineno, raw, prose)` or `(lineno, None, None)`;
  `comment_body(body) -> str | None` (stateless never-flag rules);
  a `body_prose` closure inside `prose_lines_code` (stateful fence/pre tracking around `comment_body`);
  `prose_stream(text, path) -> generator | None`.
  Tasks 4–6 extend `LANGUAGES` and `comment_body`;
  Task 3 goldens call `prose_stream`.

- [ ] **Step 1: Write the failing fixtures**

`tests/fixtures/go/good_columns.go` — two directly consecutive own-line comments at different indent columns.
Today's extractor joins them into one paragraph and flags the first as `wrap`
(it ends bare, and the second starts with a lowercase non-connector);
Vale's column-coalescing rule treats the column change as a paragraph break instead.
No markers: zero findings expected.

```go
package pool

func (p *Pool) Put(c *Conn) {
	if c == nil {
		// nil conns are dropped without touching the freelist
	// the freelist keeps at most Cap idle conns
	}
	_ = c
}
```

`tests/fixtures/go/good_generated.go` — regression proof for the generated-file rule
(the current code only checks line 1 for `Code generated`; the new rule scans the first five lines):

```go
package gen

// Code generated by protoc-gen-go. DO NOT EDIT.

// this wrapped junk would normally be flagged but the file
// is generated and must be skipped entirely
var X = 1
```

- [ ] **Step 2: Run pytest, expect the new fixtures to FAIL**

Run: `python3 -m pytest tests/test_detector.py -q -k "good_columns or good_generated"`
Expected: both FAIL —
`good_columns.go` with a spurious `(5, "wrap")`,
`good_generated.go` with a spurious `wrap` because `Code generated` is not on line 1.

- [ ] **Step 3: Implement the table and generic extractor**

Replace `GO_DIRECTIVE_RE` and `prose_lines_go` in `scripts/check_linefeeds.py` with:

```python
import collections

Language = collections.namedtuple(
    "Language",
    "name extensions line doc_lines blocks block_prefix directives docstrings",
)


def _lang(name, extensions, line=None, doc_lines=(), blocks=(), block_prefix="",
          directives=(), docstrings=False):
    return Language(name, tuple(extensions), line, tuple(doc_lines),
                    tuple(blocks), block_prefix,
                    tuple(re.compile(p) for p in directives), docstrings)


LANGUAGES = [
    _lang("go", [".go"], line="//", blocks=[("/*", "*/")],
          directives=[r"^//[a-zA-Z0-9_+-]+:"]),
]


def lang_for_path(path):
    for lang in LANGUAGES:
        if path.endswith(lang.extensions):
            return lang
    return None


def comment_body(body):
    """Stateless never-flag rules; return cleaned prose or None."""
    body = body.strip()
    if not body or "://" in body:
        return None
    return body


def prose_lines_code(text, lang):
    """Yield (lineno, raw, prose) for prose comment lines.

    Yields (lineno, None, None) for lines that break paragraph continuity.
    Consecutive line comments continue one paragraph only when they start at
    the same indentation column (Vale's coalescing rule); a column change
    emits a break before the new line's prose.  Fence (```), <pre>, and
    doctest state is scoped to one comment run and resets at EVERY scope
    exit, including one-line scopes; every block-comment exit also emits a
    paragraph break so prose on a closing line can never coalesce with a
    following comment.
    """
    in_block = False
    block_close = ""
    block_base = 0
    prev_col = None
    fence = False
    pre = False
    doctest = False

    def reset_scope():
        nonlocal fence, pre, doctest
        fence = pre = doctest = False

    def body_prose(body):
        # Stateful never-flag layer: doctest regions, markdown fences, and
        # HTML <pre> blocks inside doc comments, then indented example
        # code, then the stateless comment_body rules.
        nonlocal fence, pre, doctest
        s = body.strip()
        if s.startswith(">>>"):
            doctest = True  # region runs until the next blank line
            return None
        if doctest:
            if not s:
                doctest = False
            return None
        if s.startswith(("```", "~~~")):
            fence = not fence
            return None
        low = s.lower()
        if low.startswith("<pre"):
            pre = True
            return None
        if "</pre" in low:
            pre = False
            return None
        if fence or pre or not s:
            return None
        if body.startswith(("\t", "    ")):
            return None  # indented example code
        return comment_body(s)

    for i, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()

        if in_block:
            body = raw
            closing = block_close in body
            if closing:
                body = body.split(block_close)[0]
            s = body.strip()
            if lang.block_prefix and s.startswith(lang.block_prefix):
                body = s[len(lang.block_prefix):]
            else:
                # Undecorated block: keep indentation relative to the block
                # opener so indented example code stays recognizable.
                lead = len(body) - len(body.lstrip())
                body = body[min(lead, block_base):]
            prose = body_prose(body)
            if prose:
                yield i, raw, prose
            else:
                yield i, None, None
            if closing:
                in_block = False
                reset_scope()
                yield i, None, None  # scope exit is a paragraph break
            continue

        opened = False
        for open_d, close_d in lang.blocks:
            if stripped.startswith(open_d):
                rest = stripped[len(open_d):]
                one_line = close_d in rest
                if one_line:
                    rest = rest.split(close_d)[0]
                else:
                    in_block = True
                    block_close = close_d
                    block_base = len(raw) - len(raw.lstrip())
                reset_scope()
                prev_col = None
                yield i, None, None  # block entry is a paragraph break
                prose = body_prose(rest.lstrip("*!").strip())
                if prose:
                    yield i, raw, prose
                if one_line:
                    reset_scope()  # a one-line scope exits immediately
                    yield i, None, None
                opened = True
                break
        if opened:
            continue

        marker = None
        markers = lang.doc_lines + ((lang.line,) if lang.line else ())
        for m in sorted(markers, key=len, reverse=True):
            if stripped.startswith(m):
                marker = m
                break
        if marker is None:
            prev_col = None
            reset_scope()
            yield i, None, None
            continue
        if any(d.match(stripped) for d in lang.directives):
            prev_col = None
            reset_scope()
            yield i, None, None
            continue

        col = len(raw) - len(raw.lstrip())
        if prev_col is not None and col != prev_col:
            reset_scope()
            yield i, None, None  # column change: new paragraph
        prev_col = col

        prose = body_prose(stripped[len(marker):])
        if prose:
            yield i, raw, prose
        else:
            yield i, None, None


GENERATED_RE = re.compile(r"Code generated|@generated|DO NOT EDIT")


def prose_stream(text, path):
    """Return the prose-line generator for path, or None if not a target."""
    if is_markdown(path):
        return prose_lines_markdown(text)
    lang = lang_for_path(path)
    if lang is None:
        return None
    head = "\n".join(text.splitlines()[:5])
    if GENERATED_RE.search(head):
        return iter(())
    return prose_lines_code(text, lang)
```

Rewrite the top of `check()` to use the dispatch,
keeping the findings loop unchanged:

```python
def check(text, path):
    """Return a list of (lineno, kind, message, excerpt) findings."""
    lines = prose_stream(text, path)
    if lines is None:
        return []
    # ... (the existing findings loop, unchanged from here on)
```

Delete `is_go()`,
and update `run_hook`'s target test from `is_markdown(path) or is_go(path)`
to `is_markdown(path) or lang_for_path(path) is not None`.

Two behavior notes worth a code comment:
the column-break and block-opener cases yield TWO items for the same lineno
(a break, then the prose),
which the checker's loop handles because a `prose is None` item just resets `prev`;
and text on a block comment's opening line IS extracted
(the review's license-opener case requires it),
preceded by an explicit paragraph break.

- [ ] **Step 4: Run the full suite, expect all green**

Run: `python3 -m pytest tests/ -q`
Expected: PASS for the two new fixtures and every pre-existing fixture;
the refactor must not change Go or Markdown findings on the existing corpus.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: table-driven comment extractor with column coalescing"
```

---

### Task 3: Extractor golden tests (Vale pattern)

**Files:**
- Create: `tests/test_extractor.py`,
  `tests/extractor/in/0.go`, `tests/extractor/in/1.md`,
  `tests/extractor/out/0.json`, `tests/extractor/out/1.json`

**Interfaces:**
- Consumes: `prose_stream(text, path)` from Task 2; `--update-golden` from Task 1.
- Produces: the golden harness;
  Tasks 4–6 drop new `in/N.<ext>` files and run `--update-golden` to mint goldens.

- [ ] **Step 1: Write the golden inputs**

`tests/extractor/in/0.go`:

```go
// Package demo shows extraction.
// It has two sentences on two lines.
package demo

//go:generate stringer -type=Kind

// Frob frobnicates.
//
//	frob(x) // indented example code
//
// See https://example.com/frob for background.
func Frob() {}
```

`tests/extractor/in/1.md`:

````markdown
---
title: demo
---

# Heading

Prose line one.
Prose line two.

| a | b |
|---|---|

```go
code in fence
```

Tail prose.
````

- [ ] **Step 2: Write test_extractor.py**

```python
import json

import pytest
from conftest import REPO

import check_linefeeds

IN_DIR = REPO / "tests" / "extractor" / "in"
OUT_DIR = REPO / "tests" / "extractor" / "out"


def extract(path):
    stream = check_linefeeds.prose_stream(path.read_text(encoding="utf-8"), str(path))
    assert stream is not None, f"{path} must be a target file type"
    return [{"line": n, "prose": p} for n, _raw, p in stream if p is not None]


@pytest.mark.parametrize("in_path", sorted(IN_DIR.iterdir()), ids=lambda p: p.name)
def test_extractor_golden(in_path, request):
    golden = OUT_DIR / (in_path.stem + ".json")
    got = extract(in_path)
    if request.config.getoption("--update-golden"):
        golden.write_text(json.dumps(got, indent=2) + "\n", encoding="utf-8")
    assert got == json.loads(golden.read_text(encoding="utf-8"))
```

- [ ] **Step 3: Mint the goldens and eyeball them**

Run: `python3 -m pytest tests/test_extractor.py -q --update-golden && cat tests/extractor/out/*.json`
Expected for `0.json`:
exactly the two package-doc lines and the `Frob frobnicates.` line;
not the directive, not the indented example, not the URL line.
Expected for `1.json`:
the three prose lines and nothing from front matter, heading, table, or fence.
Fix the extractor before proceeding if the goldens disagree.

- [ ] **Step 4: Run the full suite, expect green; commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "test: Vale-style extraction goldens with --update-golden refresh"
```

---

### Task 4: C-family and Rust support

**Files:**
- Modify: `scripts/check_linefeeds.py` (two `LANGUAGES` entries; `comment_body` markup skips)
- Create: `tests/fixtures/cfamily/bad_wrapped.java`,
  `tests/fixtures/cfamily/good_javadoc.java`,
  `tests/fixtures/cfamily/good_directives.ts`,
  `tests/fixtures/cfamily/good_pre_block.java`,
  `tests/fixtures/cfamily/good_scope_edges.c`
- Create: `tests/fixtures/rust/bad_wrapped.rs`, `tests/fixtures/rust/good_rustdoc.rs`
- Create: `tests/extractor/in/2.rs`, `tests/extractor/in/3.java`, `tests/extractor/in/5.c`
  (+ goldens via `--update-golden`)

**Interfaces:**
- Consumes: `_lang`, `LANGUAGES`, `comment_body`, `prose_lines_code` from Task 2.
- Produces:
  extensions `.c .h .cc .cpp .hpp .hh .java .js .jsx .ts .tsx .mjs .cjs .cs` and `.rs` become target types;
  `comment_body` additionally returns None for bodies starting with `# | > < @ \`.

- [ ] **Step 1: Write the failing fixtures**

`tests/fixtures/cfamily/bad_wrapped.java`
(the first doc line earns both markers:
`fused` for the two sentences, and `wrap` because it ends bare with a lowercase continuation below):

```java
/**
 * Returns the cached value for the key. The cache {fused} {wrap}
 * evicts the oldest entry when full and the {wrap}
 * caller must not mutate the returned list.
 */
public List<String> get(String key) { return null; }
```

`tests/fixtures/cfamily/good_javadoc.java`:

```java
/**
 * Returns the cached value for the key.
 * The cache evicts the oldest entry when it is full.
 *
 * <p>HTML paragraph tags are never checked.
 *
 * @param key the lookup key, which must not be null
 * @return the cached list, or null when the key is absent
 */
public List<String> get(String key) { return null; }
```

`tests/fixtures/cfamily/good_pre_block.java`
(code inside `<pre>...</pre>` must be invisible even though it looks like wrapped prose):

```java
/**
 * Usage example follows.
 *
 * <pre>
 * cache.put(key, value) with no punctuation at the end
 * cache.get(key) returning the stored value
 * </pre>
 */
public class Cache {}
```

`tests/fixtures/cfamily/good_scope_edges.c`
(review-mandated scope-boundary cases,
each one-liner followed IMMEDIATELY by observable prose
so a leaked state cannot be masked by the next scope's entry reset —
a v3 causality finding.
Prose on a block's closing line must not coalesce with a following line comment,
and the undecorated block's four-space example must stay invisible,
which only the `block_base` indentation preservation guarantees):

```c
/* ``` */
// Extracted despite the fence marker in the one-liner above.

/* <pre> */
// Extracted despite the pre marker in the one-liner above.

/*
Frobs the widget without any punctuation at the end */
// lowercase words here must open a new paragraph, not continue the block

/*
Example usage:

    frob(x) with no punctuation and lowercase words

Closing sentence stays checked. */
int x;
```

`tests/fixtures/cfamily/good_directives.ts`:

```typescript
// eslint-disable-next-line no-console
// prettier-ignore
// @ts-expect-error legacy shim without types
// biome-ignore lint: intentional
console.log("directives above are never prose");
```

`tests/fixtures/rust/bad_wrapped.rs` (same double-marker pattern on the first line):

```rust
/// Reads the whole file into memory. The buffer {fused} {wrap}
/// grows geometrically and the read stops at EOF {wrap}
/// without retrying short reads.
pub fn read_all() {}
```

`tests/fixtures/rust/good_rustdoc.rs`:

````rust
//! Crate-level docs use inner doc comments.
//! One sentence per line keeps diffs reviewable.

/// # Examples
///
/// ```
/// let x = read_all();
/// assert!(x.is_empty());
/// ```
///
/// Fenced code above is never checked, and this closing sentence is fine.
pub fn read_all() {}
````

- [ ] **Step 2: Run pytest, expect the new fixtures to FAIL**

Run: `python3 -m pytest tests/test_detector.py -q -k "cfamily or rust"`
Expected: FAIL.
`.java`/`.ts`/`.rs` are not yet target types,
so `check()` returns `[]` while the bad fixtures expect findings.

- [ ] **Step 3: Implement**

Add to `LANGUAGES`:

```python
    _lang("cfamily",
          [".c", ".h", ".cc", ".cpp", ".hpp", ".hh", ".java",
           ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".cs"],
          line="//", doc_lines=["///"], blocks=[("/*", "*/")], block_prefix="*",
          directives=[r"^//[a-zA-Z0-9_+-]+:",
                      r"^//\s*(eslint|prettier|biome|@ts-|tslint|NOLINT|noinspection|istanbul)"]),
    _lang("rust", [".rs"], line="//", doc_lines=["///", "//!"],
          blocks=[("/*", "*/")], block_prefix="*"),
```

Extend `comment_body`:

```python
def comment_body(body):
    """Stateless never-flag rules; return cleaned prose or None."""
    body = body.strip()
    if not body or "://" in body:
        return None
    if body.startswith(("#", "|", ">", "<", "@", "\\")):
        # Markdown headers/tables/quotes, HTML, javadoc/jsdoc/doxygen tags.
        return None
    return body
```

The fence and `<pre>` handling already lives in Task 2's `body_prose`,
so no extractor change is needed here beyond the table rows.

- [ ] **Step 4: Run pytest; mint the new extractor goldens**

Write `tests/extractor/in/2.rs` with the content of `good_rustdoc.rs`,
`tests/extractor/in/3.java` with the content of `good_javadoc.java`,
and `tests/extractor/in/5.c` with the content of `good_scope_edges.c`.
Run: `python3 -m pytest tests/ -q --update-golden`
Eyeball the goldens:
`2.json` must exclude everything between the doc-comment fences and the `# Examples` header;
`3.json` must exclude the `@param`/`@return`/`<p>` lines and include the two prose sentences;
`5.json` must include the standalone comment sentence after EACH one-liner
(an absence means that one-liner's fence or `<pre>` state leaked —
the mutation this golden exists to catch),
the first block's closing-line sentence,
and the last block's `Example usage:` and closing sentences,
while excluding the four-space `frob(x)` line
(its presence means undecorated-block indentation preservation was lost).

- [ ] **Step 5: Full suite green, commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "feat: C-family and Rust comment support with doc-tag and fence skips"
```

---

### Task 5: Python support (# comments + docstrings) and shell comments

**Files:**
- Modify: `scripts/check_linefeeds.py`
  (python and shell `LANGUAGES` entries; docstring states in `prose_lines_code`)
- Create: `tests/fixtures/python/bad_docstring.py`,
  `tests/fixtures/python/good_python.py`,
  `tests/fixtures/python/good_doctest.py`,
  `tests/fixtures/python/good_sig_states.py`,
  `tests/extractor/in/4.py` (+ golden)

**Interfaces:**
- Consumes: everything from Tasks 2 and 4.
- Produces: `.py`/`.pyi`/`.sh`/`.bash` become target types;
  `prose_lines_code` gains docstring extraction gated on `lang.docstrings`,
  with paren-depth signature tracking.

- [ ] **Step 1: Write the failing fixtures**

`tests/fixtures/python/bad_docstring.py`
(first docstring line: `fused` plus `wrap`, because it ends bare before a lowercase continuation):

```python
def fetch(url):
    """Fetch the URL and return its body. Retries are {fused} {wrap}
    performed with exponential backoff and the caller {wrap}
    sees only the final result.
    """
    return url


# A trailing comment sentence that wraps mid-clause is also {wrap}
# caught by the line-comment path.
X = 1
```

`tests/fixtures/python/good_python.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Module docstring: one sentence per line keeps diffs reviewable.
Each sentence gets its own line.
"""

import os  # noqa: F401


def fetch(url):
    """Fetch the URL and return its body.
    Retries use exponential backoff,
    and the caller sees only the final result.
    """
    s = "// this is a string literal, not a comment. Never flagged."
    d = """just a string expression,
        not a docstring because it does not follow a def or class"""
    return url, s, d, os
```

`tests/fixtures/python/good_doctest.py`
(doctest lines, fenced code, and deeper-indented examples inside a docstring are never prose):

```python
def sample():
    """Summary line is checked normally.

    >>> sample() # doctest lines are skipped. Even with two sentences.
    'x'

        indented example block with no punctuation at all
        and a lowercase continuation that must stay invisible

    ```
    fenced example with no punctuation at all
    ```

    Closing sentence after the examples is checked again.
    """
    return "x"


def fence_one_liner():
    """```"""
    # This comment sits directly after a one-line docstring with a fence marker.
    # It must be extracted as prose, and it is clean.
    return 1


def pre_one_liner():
    """<pre>"""
    # This comment sits directly after a one-line docstring with a pre marker.
    # It must be extracted as prose, and it is clean.
    return 2
```

The two one-liner sections are v3/v4 causality fixtures:
a recognized one-line docstring toggles fence or `<pre>` state inside `body_prose`,
and only the post-close `reset_scope()` keeps the following comments extractable.
The comments sit DIRECTLY after the docstring line —
before any code line, whose own path also resets scope and would mask the mutation
(v4 finding).

`tests/fixtures/python/good_sig_states.py`
(regression fixtures for the review's signature-state findings:
a one-line suite must NOT leave a pending docstring expectation,
a trailing comment after the colon must not defeat a real docstring,
and a multi-line signature must carry the expectation to the closing colon):

```python
def one_liner(): pass


for item in [1]:
    """this string follows a for loop. It must not be treated as a docstring."""


def with_comment():  # pragma: no cover
    """A real docstring despite the trailing comment on the signature.
    It is checked and it is clean.
    """


def multi_line(
    a,
    b,
):
    """Docstrings after multi-line signatures are found too.
    Both sentences here are clean.
    """
```

- [ ] **Step 2: Run pytest, expect FAIL**

Run: `python3 -m pytest tests/test_detector.py -q -k python`
Expected: FAIL — `.py` is not a target type yet.

- [ ] **Step 3: Implement**

Add to `LANGUAGES`:

```python
    _lang("python", [".py", ".pyi"], line="#", docstrings=True,
          directives=[r"^#!",
                      r"^#\s*-\*-",
                      r"^#\s*(noqa|type:|pylint:|ruff:|flake8:|fmt:|isort:|mypy:|pragma:)",
                      r"^#[a-zA-Z0-9_+-]+:"]),
    _lang("shell", [".sh", ".bash"], line="#",
          directives=[r"^#!", r"^#\s*shellcheck"]),
```

(The shell entry rides along in this task because it is one table row;
its fixtures come in Task 6.)

Module-level constants:

```python
DOC_OPEN_RE = re.compile(r"^[rRuUbB]{0,2}(\"\"\"|''')")
SIG_RE = re.compile(r"^(async\s+def|def|class)\b")
```

New state in `prose_lines_code`, beside the existing state variables:

```python
    in_doc = False
    doc_quote = ""
    doc_base = 0
    expect_doc = lang.docstrings  # a module docstring may open the file
    sig_pending = False
    sig_depth = 0
```

At the top of the loop body, before the block-comment branch:

```python
        if in_doc:
            col = len(raw) - len(raw.lstrip())
            body = stripped
            closing = doc_quote in body
            if closing:
                body = body.split(doc_quote)[0].strip()
            if body and (col - doc_base) >= 4:
                prose = None  # example code indented within the docstring
            else:
                prose = body_prose(body)
            if prose:
                yield i, raw, prose
            else:
                yield i, None, None
            if closing:
                in_doc = False
                reset_scope()
                yield i, None, None  # scope exit is a paragraph break
            continue

        if lang.docstrings and expect_doc:
            m = DOC_OPEN_RE.match(stripped)
            if m:
                doc_quote = m.group(1)
                doc_base = len(raw) - len(raw.lstrip())
                rest = stripped[m.end():]
                expect_doc = False
                reset_scope()
                one_line = doc_quote in rest
                if one_line:
                    prose = body_prose(rest.split(doc_quote)[0])
                else:
                    in_doc = True
                    prose = body_prose(rest)
                if prose:
                    yield i, raw, prose
                else:
                    yield i, None, None
                if one_line:
                    reset_scope()  # a one-line scope exits immediately
                    yield i, None, None
                continue
```

In the fall-through code-line branch (`marker is None`),
replace the plain reset with signature tracking.
The tracker counts parentheses,
so a multi-line signature carries the expectation to the line whose closing `):` ends it,
and it strips a trailing `#` comment so `def f():  # pragma` still counts:

```python
        if marker is None:
            prev_col = None
            reset_scope()
            if lang.docstrings and stripped:
                code = re.sub(r"\s#.*$", "", stripped).rstrip()
                if sig_pending:
                    sig_depth += code.count("(") - code.count(")")
                    if sig_depth <= 0:
                        sig_pending = False
                        expect_doc = code.endswith(":")
                elif SIG_RE.match(code):
                    sig_depth = code.count("(") - code.count(")")
                    if sig_depth > 0:
                        sig_pending = True
                    else:
                        expect_doc = code.endswith(":")
                else:
                    expect_doc = False
            yield i, None, None
            continue
```

Behavior this buys, mapped to the fixtures:
`def one_liner(): pass` ends with `pass`, so `expect_doc` stays False and never leaks;
`for item in [1]:` is not a signature, so the string after it is not a docstring;
`def with_comment():  # pragma: no cover` strips the comment and ends with `:`;
the multi-line signature keeps `sig_pending` until `):`.
Accepted precision limitations, each a comment in the code:
a whitespace-then-`#` inside a string default (`def f(x="a #b"):`) makes the tracker miss that one docstring (a miss, never a false positive),
and a `#`-led line inside a multi-line string literal is misread as a comment
(the string-literal blind spot the design consciously accepts).

- [ ] **Step 4: Run pytest; mint the extractor golden**

Write `tests/extractor/in/4.py` with the content of `good_doctest.py`, then:
Run: `python3 -m pytest tests/ -q --update-golden`
Eyeball `4.json`:
the summary line and closing sentence appear;
the doctest line, its output line, the indented block, and the fenced block do not;
and all four comment sentences sitting directly after the one-line docstrings appear
(an absence means one-line docstring state leaked —
the mutation those sections exist to catch,
and their placement BEFORE any code line is what makes the proof causal).

- [ ] **Step 5: Full suite green, commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "feat: Python comment and docstring support plus shell comments"
```

---

### Task 6: Never-flag hardening (license headers, Markdown gaps, path skips)

**Files:**
- Modify: `scripts/check_linefeeds.py`
  (`drop_license_header`; Markdown indented-code and reference-definition rules; shared `skip_path`)
- Create: `tests/fixtures/go/good_license.go`,
  `tests/fixtures/go/good_license_multiparagraph.go`,
  `tests/fixtures/go/bad_license_then_doc.go`,
  `tests/fixtures/cfamily/good_license.c`,
  `tests/fixtures/cfamily/bad_license_then_block.c`,
  `tests/fixtures/markdown/good_refdefs.md`,
  `tests/fixtures/markdown/good_indented_code.md`,
  `tests/fixtures/shell/good_shell.sh`,
  `tests/fixtures/shell/bad_shell.sh`

**Interfaces:**
- Consumes: `prose_stream` and `check` internals from Task 2.
- Produces: `skip_path(path) -> bool` used by all hook modes
  (component-based, so it matches absolute, repo-relative, and backslash paths);
  `check()` drops a license-smelling first comment block in code files.

- [ ] **Step 1: Write the failing fixtures**

`tests/fixtures/go/good_license.go`
(today the header produces a `fused` on line 1 and a `wrap` on line 2;
the license filter must silence both):

```go
// Copyright 2026 Arlo Liu. Licensed under the Apache License,
// Version 2.0; you may not use this file except in compliance
// with the License.

// Package demo is documented properly.
package demo
```

`tests/fixtures/cfamily/good_license.c`
(the license keyword appears ONLY on the block-comment opening line —
the review's case that requires opener text extraction):

```c
/* Copyright 2026 Arlo Liu. This file may be freely
   used under the MIT license terms described in LICENSE. */
int x;
```

`tests/fixtures/go/good_license_multiparagraph.go`
(a license spanning blank `//` lines is one leading comment scope;
a paragraph-based filter would drop only the first paragraph and leak a `wrap` from lines 5–6):

```go
// Copyright 2026 Arlo Liu.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at some location and the
// text continues wrapped like old files often are

// Package demo is documented properly.
package demo
```

`tests/fixtures/go/bad_license_then_doc.go`
(the negative guard:
the license scope ends at the first blank line,
so the package doc AFTER it must still be checked):

```go
// Copyright 2026 Arlo Liu. All rights reserved.

// Package demo is documented badly. It has two sentences. {fused}
package demo
```

`tests/fixtures/cfamily/bad_license_then_block.c`
(v3 finding: a line-comment license followed WITHOUT a blank line by a block comment counts as two scopes,
and a scanner that merges them would silence the block's real violation):

```c
// Copyright 2026 Arlo Liu. All rights reserved.
/*
This block doc is checked. It has two sentences. {fused}
*/
int x;
```

`tests/fixtures/markdown/good_refdefs.md`
(the `[note]` definition has no URL scheme,
so only a reference-definition rule can exempt it;
today its two-sentence title trips `fused`.
The variants cover no space after the colon,
an image-style definition,
a title continued on a two-space-indented next line
(two spaces on purpose — four would be intercepted by the indented-code rule
and make the continuation case vacuous, a review finding),
a destination continued on the next line,
and tail prose proving the continuation state resets):

```markdown
Prose referring to [the spec][spec] stays on one line.

[spec]: https://sembr.org/
[note]: ./notes.md "See the notes. They explain the tradeoff."
[raw]:./no-space.md
![img]: ./image-def.png "Two sentences in here. Still exempt."
[cont]: ./continued.md
  "a title on its own continuation line. Two sentences here."
[dest]:
  ./destination-on-next-line.md
[both]:
  ./destination-line.md
  "then a title line. With two sentences in it."

Tail prose after the definitions proves the state resets.
```

The `[both]` case is a v3 finding:
a destination continuation must KEEP the definition open for one optional title line,
or the title leaks out as prose and its two sentences trip `fused`.

`tests/fixtures/markdown/good_indented_code.md`:

```markdown
Intro prose line.

    indented code block with no punctuation at all
    and a lowercase continuation that must stay invisible

Tail prose.
```

`tests/fixtures/shell/bad_shell.sh`
(first comment line: `fused` plus `wrap`, as in Tasks 4–5):

```bash
#!/usr/bin/env bash
# Rotates the log files. The rotation keeps seven {fused} {wrap}
# days of history and the oldest file is {wrap}
# deleted first.
echo rotate
```

`tests/fixtures/shell/good_shell.sh`:

```bash
#!/usr/bin/env bash
# shellcheck disable=SC2086
# Rotates the log files.
# The rotation keeps seven days of history,
# and the oldest file is deleted first.
echo rotate
```

- [ ] **Step 2: Run pytest, expect the new fixtures to FAIL**

Run: `python3 -m pytest tests/test_detector.py -q -k "license or refdefs or indented or shell"`

- [ ] **Step 3: Implement**

In `prose_lines_markdown`, three additions.
First, an indented-code skip before any stripping
(CommonMark treats 4-space/tab-indented blocks as code;
deeply indented list prose is sacrificed to precision, per the global constraint):

```python
        if raw.startswith(("    ", "\t")):
            yield i, None, None
            continue
```

Second, reference definitions —
link or image style, with or without a space after the colon —
plus their continuation lines.
A quote/paren-led continuation is a title and CLOSES the definition;
a single whitespace-free token is a destination and keeps the definition open,
because CommonMark allows a title line to follow a destination line (v3 finding).
The single-token rule can at worst skip one-word prose lines after a definition,
which is a miss, never a false positive:

```python
        if re.match(r"^!?\[[^\]]+\]:", stripped):
            after_refdef = True
            yield i, None, None
            continue
        if after_refdef:
            if stripped.startswith(('"', "'", "(", "<")):
                after_refdef = False  # a title ends the definition
                yield i, None, None
                continue
            if stripped and " " not in stripped:
                yield i, None, None  # a destination; a title may follow
                continue
            after_refdef = False
```

(`after_refdef = False` initialized before the loop.
A blank or ordinary-prose line clears the state,
and it falls through to the existing skip conditions unchanged.)

Third — no change needed for fences/front matter; they already exist.

Add the license filter and wire it into `check()`.
It scans RAW text, not the extracted prose stream,
so blank `//` lines inside a multi-paragraph license cannot end the region early
(a paragraph-based filter drops only the first paragraph — review finding).
The region is the leading run of comment lines,
ended by the first truly blank line or the first code line;
it is dropped only when some line in it matches `LICENSE_RE`:

```python
LICENSE_RE = re.compile(
    r"SPDX-License-Identifier|Copyright \(c\)|Copyright \d{4}|©|All rights reserved",
    re.IGNORECASE,
)


def license_header_extent(text, lang):
    """Return the last lineno of a leading license comment region, else 0.

    The region is the file's leading comment scope: consecutive line
    comments (blank-bodied ones included) OR one block comment — never
    both.  It ends at the first blank line outside a block, the first
    code line, the block comment's close, or a style transition (a block
    opener after line comments), whichever comes first.  A multi-
    paragraph license separated by truly blank lines keeps only its
    first chunk — a documented precision tradeoff.
    """
    end = 0
    licensey = False
    in_block = False
    close = ""
    style = None  # "line" or "block", fixed by the first comment line
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if in_block:
            end = i
            if LICENSE_RE.search(s):
                licensey = True
            if close in s:
                break
            continue
        if not s:
            break  # a blank line ends the leading comment region
        opened = False
        transition = False
        for od, cd in lang.blocks:
            if s.startswith(od):
                if style == "line":
                    transition = True  # a second scope begins here
                else:
                    style = "block"
                    in_block = cd not in s[len(od):]
                    close = cd
                    opened = True
                break
        if transition:
            break
        if not opened:
            if not (lang.line and s.startswith(lang.line)):
                break  # first code line ends the region
            style = style or "line"
        end = i
        if LICENSE_RE.search(s):
            licensey = True
        if opened and not in_block:
            break  # one-line block comment closes the region
    return end if licensey else 0
```

In `check()`, for code files only,
blank every prose item inside the region before the findings loop:

```python
    lines = prose_stream(text, path)
    if lines is None:
        return []
    if not is_markdown(path):
        lang = lang_for_path(path)
        cut = license_header_extent(text, lang) if lang else 0
        if cut:
            lines = ((n, raw if n > cut else None, p if n > cut else None)
                     for n, raw, p in lines)
```

Add the shared path filter and use it in the hook mode
(replacing the inline vendor check).
It compares path COMPONENTS after normalizing separators,
so `vendor/doc.go` (Codex sends repo-relative paths),
`/abs/vendor/doc.go`, `./vendor/doc.go`, and `C:\repo\vendor\doc.go` all match:

```python
SKIP_DIRS = {"vendor", "node_modules", "testdata", "fixtures",
             ".git", "dist", "build"}


def skip_path(path):
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return any(part in SKIP_DIRS for part in p.split("/"))
```

`fixtures` and `testdata` are skipped because test corpora contain intentional violations,
including this repo's own;
a hook that nags while editing bad fixtures blocks the very work the fixtures exist for.
`skip_path` guards hook modes only;
`--file` mode checks whatever paths it is given.

- [ ] **Step 4: Add path-filter unit tests** (append to `tests/test_cli.py`)

```python
import check_linefeeds


def test_skip_path_relative_and_absolute():
    assert check_linefeeds.skip_path("vendor/doc.go")
    assert check_linefeeds.skip_path("/abs/vendor/doc.go")
    assert check_linefeeds.skip_path("./fixtures/bad.go")
    assert check_linefeeds.skip_path("a/b/node_modules/c.ts")
    assert check_linefeeds.skip_path("C:\\repo\\testdata\\x.go")
    assert not check_linefeeds.skip_path("src/vendored/doc.go")
    assert not check_linefeeds.skip_path("distance/notes.md")
```

- [ ] **Step 5: Full suite green (goldens unchanged), commit**

Run: `python3 -m pytest tests/ -q`
The Task 3 goldens must not change
(`1.md` contains no indented code or reference definitions by design).

```bash
git add -A
git commit -m "feat: license-header, markdown, and path-skip never-flag rules"
```

---

### Task 7: CLI surface — `--hook <agent>`, `--json`, error semantics

**Files:**
- Modify: `scripts/check_linefeeds.py`
  (argparse CLI; `--hook` takes an optional agent; `--json` for `--file`; defined error behavior)
- Modify: `hooks/hooks.json` (command gains explicit `claude` agent)
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `check`, `format_findings`, `skip_path`.
- Produces:
  CLI contract `--hook [claude|codex]` where bare `--hook` means claude (preserving installed hooks);
  `--file PATH... [--json]`;
  JSON schema `[{"path": ..., "findings": [{"line", "kind", "message", "excerpt"}]}]`;
  exit 1 when any requested file is unreadable;
  `--help` exits 0; usage errors exit 64.
  Task 8 fills in the codex branch behind the same flag;
  Task 9's opencode plugin calls `--hook claude`.
  A Claude `edits`-array payload is deliberately NOT supported:
  the official Edit schema is `file_path`/`old_string`/`new_string`/`replace_all` with no `edits` member,
  and inventing parsers for payloads no agent produces is contract fiction
  (review finding; revisit only when a real producer exists).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
import json


def test_hook_accepts_explicit_claude_agent():
    r = run_cli(["--hook", "claude"], (PAYLOADS / "claude_edit_bad.json").read_text())
    assert r.returncode == 2


def test_file_json_output(tmp_path):
    text, expected = load_fixture(FIXTURES / "go" / "bad_wrapped.go")
    f = tmp_path / "bad_wrapped.go"
    f.write_text(text)
    r = run_cli(["--file", str(f), "--json"])
    assert r.returncode == 1
    data = json.loads(r.stdout)
    got = [(x["line"], x["kind"]) for x in data[0]["findings"]]
    assert sorted(got) == sorted(expected)


def test_file_json_clean_file_emits_empty_list(tmp_path):
    f = tmp_path / "clean.go"
    f.write_text("// One clean sentence.\npackage x\n")
    r = run_cli(["--file", str(f), "--json"])
    assert r.returncode == 0
    assert json.loads(r.stdout) == []


def test_file_json_long_only_still_exits_zero(tmp_path):
    text, _ = load_fixture(FIXTURES / "markdown" / "advisory_long.md")
    f = tmp_path / "advisory_long.md"
    f.write_text(text)
    r = run_cli(["--file", str(f), "--json"])
    assert r.returncode == 0
    assert json.loads(r.stdout)[0]["findings"][0]["kind"] == "long"


def test_unreadable_file_exits_1(tmp_path):
    r = run_cli(["--file", str(tmp_path / "missing.go")])
    assert r.returncode == 1
    assert "cannot read" in r.stderr


def test_help_exits_zero():
    assert run_cli(["--help"]).returncode == 0


def test_conflicting_modes_exit_64():
    assert run_cli(["--hook", "claude", "--file", "x.go"]).returncode == 64


def test_json_without_file_mode_exits_64():
    assert run_cli(["--hook", "claude", "--json"], "{}").returncode == 64


def test_no_mode_exits_64():
    assert run_cli([]).returncode == 64
```

- [ ] **Step 2: Run pytest, expect the new tests to FAIL**

Run: `python3 -m pytest tests/test_cli.py -q`

- [ ] **Step 3: Implement**

Replace `main()` with argparse:

```python
import argparse


def main():
    ap = argparse.ArgumentParser(prog="check_linefeeds", description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--hook", nargs="?", const="claude",
                      choices=["claude", "codex"], default=None)
    mode.add_argument("--file", nargs="+", default=None, metavar="PATH")
    ap.add_argument("--json", action="store_true")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(0 if e.code == 0 else 64)
    if args.json and not args.file:
        print("check_linefeeds: --json requires --file", file=sys.stderr)
        sys.exit(64)
    if args.hook == "claude":
        sys.exit(run_hook_claude())
    if args.hook == "codex":
        sys.exit(run_hook_codex())
    if args.file:
        sys.exit(run_files(args.file, as_json=args.json))
    ap.print_usage(sys.stderr)
    sys.exit(64)
```

The `except SystemExit` preserves argparse's exit 0 for `--help`
and converts only parse failures to the documented 64.
In this task, `run_hook_codex` is a stub returning 0 with a `# Task 8` comment,
so the choices list stays honest.

Rename `run_hook` to `run_hook_claude`,
and swap its inline vendor check for `skip_path(path)`.
Its text extraction stays `new_string` or `content` — nothing else.

Rewrite `run_files` with JSON output and defined read-error behavior:

```python
def run_files(paths, as_json=False):
    violations = 0
    read_errors = 0
    reports = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            print(f"semantic-linefeeds: cannot read {path}: {e}", file=sys.stderr)
            read_errors += 1
            continue
        findings = check(text, path)
        if findings:
            violations += sum(1 for f in findings if f[1] != "long")
            if as_json:
                reports.append({"path": path, "findings": [
                    {"line": n, "kind": k, "message": m, "excerpt": e}
                    for n, k, m, e in findings]})
            else:
                print(format_findings(findings, path, snippet=False))
    if as_json:
        print(json.dumps(reports, indent=2))
    return 1 if (violations or read_errors) else 0
```

Update `hooks/hooks.json`'s command to end with `--hook claude`;
bare `--hook` still works for already-installed copies.

- [ ] **Step 4: Full suite green, commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "feat: explicit hook agents, JSON output, defined CLI error semantics"
```

---

### Task 8: Codex CLI adapter

**Files:**
- Modify: `scripts/check_linefeeds.py` (implement `run_hook_codex` + `added_text_by_file`)
- Create: `adapters/codex/hooks.json`, `adapters/codex/INSTALL.md`
- Create: `tests/payloads/codex_apply_patch_bad.json`,
  `tests/payloads/codex_apply_patch_good.json`,
  `tests/payloads/codex_apply_patch_other.json`,
  `tests/payloads/codex_apply_patch_rename.json`,
  `tests/payloads/codex_apply_patch_two_runs.json`,
  `tests/payloads/codex_apply_patch_multifile.json`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `check`, `format_findings`, `skip_path`, the `--hook codex` branch stubbed in Task 7.
- Produces: `added_text_by_file(patch) -> dict[path, text]`
  where disjoint addition runs are separated by blank lines
  and `*** Move to:` renames re-key to the destination path;
  exit-2 stderr feedback matching the Claude wording so the shared skill instructions apply.

**Contract note (review-verified)**:
the current Codex stable payload carries the patch as `tool_input.command`
(`codex-rs/core/src/tools/handlers/apply_patch.rs:439`),
the serialized tool name is `apply_patch` (`hook_names.rs:24`),
and the apply-patch grammar places `*** Move to:` between the `*** Update File:` line and its hunks
(`codex-rs/core/prompt_with_apply_patch_instructions.md:426`).
`input`/`patch` are retained as read-only fallbacks for older payload shapes,
documented as best-effort compatibility with no support window.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
def codex_hook(name):
    return run_cli(["--hook", "codex"], (PAYLOADS / name).read_text())


def test_codex_bad_patch_blocks():
    r = codex_hook("codex_apply_patch_bad.json")
    assert r.returncode == 2
    assert "[fused]" in r.stderr


def test_codex_good_patch_passes():
    assert codex_hook("codex_apply_patch_good.json").returncode == 0


def test_codex_non_target_patch_ignored():
    assert codex_hook("codex_apply_patch_other.json").returncode == 0


def test_codex_rename_dispatches_on_destination():
    # notes.txt would be ignored; the Move to: pkg/doc.go rename makes it Go.
    r = codex_hook("codex_apply_patch_rename.json")
    assert r.returncode == 2
    assert "[fused]" in r.stderr


def test_codex_disjoint_hunks_do_not_fuse():
    # Two separate addition runs in one file must not form one paragraph;
    # fusing them would fabricate a wrap finding.
    assert codex_hook("codex_apply_patch_two_runs.json").returncode == 0


def test_codex_multifile_patch_reports_each_target():
    r = codex_hook("codex_apply_patch_multifile.json")
    assert r.returncode == 2
    assert "a.go" in r.stderr
    assert "b.rs" in r.stderr


def test_codex_malformed_never_crashes():
    assert run_cli(["--hook", "codex"], "not json").returncode == 0
```

Payload fixtures — envelope fields mirror `codex-rs/hooks/src/events/post_tool_use.rs`,
and the patch lives in `tool_input.command`.
Provenance: authored from the cited source, not captured;
Task 10's live Codex validation is the capture-grounded check,
and any divergence found there must be folded back into these fixtures.

`tests/payloads/codex_apply_patch_bad.json`:

```json
{"session_id": "s1", "turn_id": "t1", "transcript_path": "/tmp/t", "cwd": "/x", "hook_event_name": "PostToolUse", "model": "gpt-5.6-codex", "permission_mode": "default", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: pkg/doc.go\n@@\n+// Package cache provides caches. A cache\n+// holds a bounded number of entries here\n+// and evicts old ones.\n context line untouched\n*** End Patch"}, "tool_response": {"output": "Done"}, "tool_use_id": "call_1"}
```

`tests/payloads/codex_apply_patch_good.json`:

```json
{"session_id": "s1", "turn_id": "t1", "transcript_path": "/tmp/t", "cwd": "/x", "hook_event_name": "PostToolUse", "model": "gpt-5.6-codex", "permission_mode": "default", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: pkg/doc.go\n@@\n+// Package cache provides fixed-capacity, in-memory key/value caches.\n+// A cache holds a bounded number of entries.\n*** End Patch"}, "tool_response": {"output": "Done"}, "tool_use_id": "call_1"}
```

`tests/payloads/codex_apply_patch_other.json`:

```json
{"session_id": "s1", "turn_id": "t1", "transcript_path": "/tmp/t", "cwd": "/x", "hook_event_name": "PostToolUse", "model": "gpt-5.6-codex", "permission_mode": "default", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: notes.txt\n@@\n+wrapped prose. Two sentences here\n*** End Patch"}, "tool_response": {"output": "Done"}, "tool_use_id": "call_1"}
```

`tests/payloads/codex_apply_patch_rename.json`:

```json
{"session_id": "s1", "turn_id": "t1", "transcript_path": "/tmp/t", "cwd": "/x", "hook_event_name": "PostToolUse", "model": "gpt-5.6-codex", "permission_mode": "default", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: notes.txt\n*** Move to: pkg/doc.go\n@@\n+// Package doc has stuff. It is fused here.\n*** End Patch"}, "tool_response": {"output": "Done"}, "tool_use_id": "call_1"}
```

`tests/payloads/codex_apply_patch_two_runs.json`:

```json
{"session_id": "s1", "turn_id": "t1", "transcript_path": "/tmp/t", "cwd": "/x", "hook_event_name": "PostToolUse", "model": "gpt-5.6-codex", "permission_mode": "default", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: pkg/doc.go\n@@\n+// Frob adjusts the frobnicator\n unchanged context line\n+// caller-facing docs start lowercase here\n*** End Patch"}, "tool_response": {"output": "Done"}, "tool_use_id": "call_1"}
```

`tests/payloads/codex_apply_patch_multifile.json`:

```json
{"session_id": "s1", "turn_id": "t1", "transcript_path": "/tmp/t", "cwd": "/x", "hook_event_name": "PostToolUse", "model": "gpt-5.6-codex", "permission_mode": "default", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: a.go\n@@\n+// First file is fused. Two sentences.\n*** Add File: b.rs\n+/// Second file is fused too. Also two sentences.\n*** End Patch"}, "tool_response": {"output": "Done"}, "tool_use_id": "call_1"}
```

- [ ] **Step 2: Run pytest, expect the codex tests to FAIL**

Run: `python3 -m pytest tests/test_cli.py -q -k codex`
Expected: the blocking tests fail because the stub returns 0.

- [ ] **Step 3: Implement**

```python
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$")
PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$")


def added_text_by_file(patch):
    """Map file path -> added text from an apply_patch body.

    Disjoint addition runs (separated by context, deletions, or hunk
    markers) are joined with blank lines so they can never merge into one
    paragraph and fabricate a wrap finding.  A `*** Move to:` rename
    re-keys the entry to the destination path, whose extension decides
    language dispatch.
    """
    files = {}   # path -> list of runs, each run a list of added lines
    current = None
    in_run = False
    for line in patch.splitlines():
        m = PATCH_FILE_RE.match(line)
        if m:
            current = m.group(1).strip()
            files.setdefault(current, [])
            in_run = False
            continue
        mv = PATCH_MOVE_RE.match(line)
        if mv and current is not None:
            dest = mv.group(1).strip()
            files[dest] = files.pop(current)
            current = dest
            in_run = False
            continue
        if line.startswith("*** "):
            current = None  # Delete File / End Patch
            in_run = False
            continue
        if current is None:
            continue
        if line.startswith("+"):
            if not in_run:
                files[current].append([])
                in_run = True
            files[current][-1].append(line[1:])
        else:
            in_run = False  # context, deletion, or @@ ends the run
    return {p: "\n\n".join("\n".join(r) for r in runs)
            for p, runs in files.items() if runs}


def run_hook_codex():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if payload.get("tool_name") != "apply_patch":
        return 0
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, str):
        patch = tool_input
    else:
        tool_input = tool_input or {}
        # "command" is the current stable contract; "input"/"patch" are
        # best-effort fallbacks for older payload shapes.
        patch = (tool_input.get("command") or tool_input.get("input")
                 or tool_input.get("patch") or "")
    blocked = False
    for path, text in sorted(added_text_by_file(patch).items()):
        if skip_path(path):
            continue
        findings = check(text, path)
        if findings:
            blocked = True
            print(format_findings(findings, path, snippet=True), file=sys.stderr)
            print("(line numbers are approximate positions within the added "
                  "lines of your patch; locate findings by the quoted excerpts)",
                  file=sys.stderr)
    return 2 if blocked else 0
```

`adapters/codex/hooks.json` (template; `__REPO__` is replaced at install time):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "apply_patch",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"__REPO__/scripts/check_linefeeds.py\" --hook codex"
          }
        ]
      }
    ]
  }
}
```

`adapters/codex/INSTALL.md`:

```markdown
# Codex CLI install

Codex loads Claude-style lifecycle hooks from `hooks.json` (stable, on by default).

1. Clone this repo somewhere stable, e.g. `~/tools/semantic-linefeeds`.
2. Copy `adapters/codex/hooks.json` to `~/.codex/hooks.json` (user scope)
   or `<project>/.codex/hooks.json` (project scope),
   replacing `__REPO__` with the absolute repo path:

       sed "s|__REPO__|$HOME/tools/semantic-linefeeds|" adapters/codex/hooks.json > ~/.codex/hooks.json

   If you already have a `hooks.json`, merge the `PostToolUse` entry instead of overwriting.
3. Codex asks you to trust the hook on first run
   (unmanaged hooks are hashed and must be approved);
   accept it.
4. Optional: copy `adapters/agentsmd/SNIPPET.md` into your `~/.codex/AGENTS.md`
   so the model knows the convention before the hook fires.
```

- [ ] **Step 4: Full suite green, commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "feat: Codex CLI adapter parsing apply_patch command payloads"
```

---

### Task 9: opencode adapter

**Files:**
- Create: `adapters/opencode/semantic-linefeeds.ts`,
  `adapters/opencode/semantic-linefeeds.test.ts`,
  `adapters/opencode/INSTALL.md`
- Modify: `tests/test_cli.py` (one gated bun test hook)

**Interfaces:**
- Consumes: the core CLI's `--hook claude` contract;
  opencode payloads are translated into Claude-shaped ones.
  Arg names verified against upstream:
  `edit` args are `filePath`/`oldString`/`newString`/`replaceAll`,
  `write` args are `filePath`/`content`,
  and `tool.execute.after` receives `(input: {tool, sessionID, callID, args}, output: {title, output, metadata})`.
- Produces: exported `buildPayload(tool, args)` (pure)
  and the plugin export registering `tool.execute.after`;
  BOTH are unit-tested — the after-hook closure is invoked with a fake shell,
  so output mutation and exit-2 handling have real coverage.
  Defined failure behavior (review requirement):
  only exit 2 mutates the tool output;
  any other exit code, a missing interpreter, or a throwing shell leaves the output untouched —
  an advisory tool must never break the agent it advises.

- [ ] **Step 1: Write the plugin**

`adapters/opencode/semantic-linefeeds.ts`:

```typescript
// opencode plugin: enforce semantic linefeeds on edit/write via the core CLI.
// Install: copy this file AND scripts/check_linefeeds.py into
// ~/.config/opencode/plugins/ (they must sit side by side), or set
// SEMANTIC_LINEFEEDS_CHECK to the script's absolute path.
import type { Plugin } from "@opencode-ai/plugin"

export function buildPayload(
  tool: string,
  args: Record<string, unknown>,
): string | null {
  if (tool !== "edit" && tool !== "write") return null
  const filePath = args.filePath as string | undefined
  const text = (tool === "edit" ? args.newString : args.content) as
    | string
    | undefined
  if (!filePath || !text) return null
  return JSON.stringify({
    tool_name: "Edit",
    tool_input: { file_path: filePath, new_string: text },
  })
}

export const SemanticLinefeeds: Plugin = async ({ $ }) => {
  const script =
    process.env.SEMANTIC_LINEFEEDS_CHECK ??
    new URL("./check_linefeeds.py", import.meta.url).pathname
  return {
    "tool.execute.after": async (input, output) => {
      const args = (input as { args?: Record<string, unknown> }).args ?? {}
      const payload = buildPayload(input.tool, args)
      if (!payload) return
      let proc
      try {
        proc = await $`printf '%s' ${payload} | python3 ${script} --hook claude`
          .quiet()
          .nothrow()
      } catch {
        return // advisory tool: a broken checker must never break the agent
      }
      if (proc.exitCode === 2) {
        output.output += `\n\n${proc.stderr.toString().trim()}`
      }
    },
  }
}

export default SemanticLinefeeds
```

- [ ] **Step 2: Write the bun unit tests** (payload builder AND hook closure)

`adapters/opencode/semantic-linefeeds.test.ts`:

```typescript
import { expect, test } from "bun:test"
import SemanticLinefeeds, { buildPayload } from "./semantic-linefeeds"

test("edit tool produces a Claude-shaped payload", () => {
  const p = buildPayload("edit", { filePath: "/x/doc.go", newString: "// hi" })
  expect(JSON.parse(p!)).toEqual({
    tool_name: "Edit",
    tool_input: { file_path: "/x/doc.go", new_string: "// hi" },
  })
})

test("write tool uses content", () => {
  const p = buildPayload("write", { filePath: "/x/a.md", content: "Prose." })
  expect(JSON.parse(p!).tool_input.new_string).toBe("Prose.")
})

test("other tools and empty args are ignored", () => {
  expect(buildPayload("bash", { command: "ls" })).toBeNull()
  expect(buildPayload("edit", {})).toBeNull()
})

// A fake Bun shell: a template tag whose result supports .quiet().nothrow().
function fakeShell(exitCode: number, stderr: string) {
  const result = { exitCode, stderr, stdout: "" }
  const chain = {
    quiet: () => chain,
    nothrow: () => Promise.resolve(result),
  }
  const calls: unknown[][] = []
  const $ = (...a: unknown[]) => {
    calls.push(a)
    return chain
  }
  return { $, calls }
}

async function runAfterHook(exitCode: number, stderr: string, tool = "edit") {
  const { $, calls } = fakeShell(exitCode, stderr)
  const hooks = await SemanticLinefeeds({ $ } as never)
  const output = { title: "", output: "original output", metadata: {} }
  await hooks["tool.execute.after"]!(
    {
      tool,
      sessionID: "s",
      callID: "c",
      args: { filePath: "/x/doc.go", newString: "// text" },
    } as never,
    output as never,
  )
  return { output, calls }
}

test("after-hook appends stderr to tool output on exit 2", async () => {
  const { output } = await runAfterHook(2, "semantic-linefeeds: 1 issue(s)")
  expect(output.output).toContain("original output")
  expect(output.output).toContain("semantic-linefeeds: 1 issue(s)")
})

test("after-hook leaves output alone on exit 0", async () => {
  const { output } = await runAfterHook(0, "")
  expect(output.output).toBe("original output")
})

test("after-hook never spawns for non-target tools", async () => {
  const { output, calls } = await runAfterHook(2, "should not appear", "bash")
  expect(output.output).toBe("original output")
  expect(calls.length).toBe(0)
})

test("non-0/non-2 subprocess exits leave output alone", async () => {
  const { output } = await runAfterHook(127, "python3: command not found")
  expect(output.output).toBe("original output")
})

test("a throwing shell is swallowed", async () => {
  const $ = () => {
    throw new Error("spawn failed")
  }
  const hooks = await SemanticLinefeeds({ $ } as never)
  const output = { title: "", output: "original output", metadata: {} }
  await hooks["tool.execute.after"]!(
    {
      tool: "edit",
      sessionID: "s",
      callID: "c",
      args: { filePath: "/x/doc.go", newString: "// hi" },
    } as never,
    output as never,
  )
  expect(output.output).toBe("original output")
})
```

- [ ] **Step 3: Gate it into pytest** (append to `tests/test_cli.py`)

```python
import shutil
import subprocess

import pytest
from conftest import REPO


@pytest.mark.skipif(shutil.which("bun") is None, reason="bun not installed")
def test_opencode_plugin_unit_tests():
    r = subprocess.run(["bun", "test", "adapters/opencode/"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
```

The skipif keeps CI portable,
but this gate is NOT allowed to skip for a release:
Task 10's checklist requires a green `bun test` run before 0.2.0 ships.
Type-checking against `@opencode-ai/plugin` is deliberately not part of CI;
the import is type-only and erased at runtime,
so bun runs the file without the package installed.

- [ ] **Step 4: Run and verify**

Run: `bun test adapters/opencode/` (if bun is installed locally),
then `python3 -m pytest tests/ -q`.

- [ ] **Step 5: Write INSTALL.md**

`adapters/opencode/INSTALL.md`:

```markdown
# opencode install

opencode plugins are in-process TypeScript; this one shells out to the same core CLI.

1. Copy `adapters/opencode/semantic-linefeeds.ts` and `scripts/check_linefeeds.py`
   into `~/.config/opencode/plugins/` (global) or `<project>/.opencode/plugins/` —
   the two files must sit side by side
   (or export `SEMANTIC_LINEFEEDS_CHECK=/abs/path/to/check_linefeeds.py` instead of copying the script).
2. The skill needs no port:
   opencode reads `.claude/skills/` and `~/.claude/skills/` natively,
   so if the Claude plugin is installed the skill is already visible.
   Otherwise copy `skills/semantic-linefeeds/` into `~/.config/opencode/skills/`.
3. Findings appear appended to the edit/write tool output
   (advisory, same wording as the Claude hook).
```

- [ ] **Step 6: Commit**

```bash
python3 -m pytest tests/ -q
git add -A
git commit -m "feat: opencode plugin adapter shelling out to the core checker"
```

---

### Task 10: Docs, skill scope, AGENTS.md snippet, version 0.2.0

**Files:**
- Create: `adapters/agentsmd/SNIPPET.md`
- Modify: `skills/semantic-linefeeds/SKILL.md` (description + scope wording for new languages)
- Modify: `README.md` (multi-agent install matrix, language matrix, test instructions)
- Modify: `.claude-plugin/plugin.json` (version 0.2.0)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–9.
- Produces: the released 0.2.0 surface.

- [ ] **Step 1: Write the AGENTS.md snippet**

`adapters/agentsmd/SNIPPET.md`:

```markdown
## Semantic linefeeds

When writing or editing prose in code comments, doc comments, docstrings, or Markdown:
break lines by meaning, not by column.
One sentence per line;
a sentence longer than ~120 characters splits only at a real clause boundary
(`;`, `:`, `—`, or a conjunction where both sides stand alone).
Never break URLs, compiler/lint directives, example code, or table rows.
Never rewrap existing text you are not otherwise editing.
Check your work with:

    python3 <repo>/scripts/check_linefeeds.py --file <files you touched>
```

- [ ] **Step 2: Update SKILL.md scope wording**

Replace the frontmatter `description` with:

```yaml
description: Use when writing or editing code comments, doc comments (godoc, javadoc, JSDoc, rustdoc, docstrings), or Markdown prose (README, CHANGELOG, docs, specs, rule files), and when a linefeeds hook reports fused, wrap, or long findings on text just written.
```

Update the body's "Never break" section to add:
javadoc/JSDoc/doxygen tag lines (`@param`, `\param`),
license headers,
fenced code and `<pre>` blocks inside doc comments,
doctest lines,
and Markdown link reference definitions.
Keep every other section unchanged.

- [ ] **Step 3: Update README.md**

Rewrite the install section as a per-agent matrix:
Claude Code keeps the existing marketplace instructions;
Codex CLI points to `adapters/codex/INSTALL.md`;
opencode points to `adapters/opencode/INSTALL.md`;
anything else points to `adapters/agentsmd/SNIPPET.md` plus `--file` in CI.
Add a "Supported languages" table
(Go, C/C++, Java, JS/TS, C#, Rust, Python, shell, Markdown).
Add a "Testing" section:
`python3 -m pytest tests/ -q`,
the `--update-golden` workflow,
and the fixture-marker convention.

- [ ] **Step 4: Bump the version**

In `.claude-plugin/plugin.json`, set `"version": "0.2.0"`.

- [ ] **Step 5: Release gate — run every suite for real**

Run, and require green (installing bun first if absent — the opencode gate may not skip here):

```bash
python3 -m pytest tests/ -q
bun test adapters/opencode/
```

- [ ] **Step 5b: Release gate — live end-to-end validation per agent**

The payload fixtures are authored from cited schemas (Tasks 1 and 8);
this step is the capture-grounded proof the review requires,
and it needs a human or an agent session per harness:

1. Claude Code: in a live session with the plugin installed,
   Edit a scratch `.go` file introducing a fused sentence;
   confirm the hook blocks with `[fused]` feedback.
2. Codex CLI: with `adapters/codex/hooks.json` installed,
   run one `codex exec` task that writes a violating comment;
   confirm the exit-2 stderr feedback appears in the transcript.
3. opencode: with the plugin installed,
   make one violating edit;
   confirm the findings are appended to the tool output.

If any agent's real payload diverges from the authored fixtures,
capture the real payload (sanitized), replace the fixture, and re-run the suites.

- [ ] **Step 6: Self-check every prose file with the checker itself**

Run:

```bash
python3 scripts/check_linefeeds.py --file \
  README.md skills/semantic-linefeeds/SKILL.md \
  adapters/codex/INSTALL.md adapters/opencode/INSTALL.md adapters/agentsmd/SNIPPET.md \
  docs/plans/done/2026-08-08-multi-agent-scope.md
```

Expected: exit 0;
fix any fused/wrap findings
(long advisories are judged, not obeyed).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "docs: multi-agent install matrix, wider skill scope, v0.2.0"
```

---

## Verification checklist (run after the final task)

- `python3 -m pytest tests/ -q` — all green.
- `bun test adapters/opencode/` — all green (release gate; may not be skipped).
- `python3 scripts/check_linefeeds.py --file $(git ls-files '*.md' ':!tests/')` — exit 0
  (`tests/` is excluded because its `bad_*` fixtures are intentional violations).
- Manual smoke:
  pipe `tests/payloads/claude_edit_bad.json` into `--hook claude` (expect exit 2),
  and `tests/payloads/codex_apply_patch_bad.json` into `--hook codex` (expect exit 2).
- Every `good_*` fixture carries zero markers (enforced by `test_good_fixtures_have_no_markers`).
- The live per-agent validation of Task 10 Step 5b has been performed,
  with any payload divergence folded back into the fixtures.
- No imports beyond the stdlib in the core
  (`grep -E "^import|^from" scripts/check_linefeeds.py`).
