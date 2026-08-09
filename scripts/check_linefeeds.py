#!/usr/bin/env python3
"""Detect violations of the semantic linefeeds convention in code comments, doc comments, and docstrings,
covering Go, C-family, Rust, Python, shell, SQL, Ruby, and more, plus Markdown prose.

Three heuristics, tuned for precision over recall — the agent judges, this only flags suspicion:
"fused" is two independent sentences on one line,
"wrap" is a line that ends mid-clause with the sentence continuing on the next line,
and "long" is a line over the threshold that appears to contain a clause boundary to split at.

Two modes.
"--hook [claude|codex]" reads a PostToolUse JSON payload on stdin (agent defaults to claude),
checks only the text just written,
and reports findings to stderr, exiting 2 if any are found.
"--file PATH... [--json]" checks whole files and reports to stdout as text or, with --json, as JSON,
exiting 1 if any fused/wrap violations are found;
long findings are advisory only and never affect the exit code.

Exits 64 on a usage error, such as bad or missing arguments.
"""

import argparse
import collections
import json
import os
import re
import sys
import tempfile

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


SKIP_DIRS = {"vendor", "node_modules", "testdata", "fixtures",
             ".git", "dist", "build", "tmp"}

LICENSE_RE = re.compile(
    r"SPDX-License-Identifier|Copyright \(c\)|Copyright \d{4}|©|All rights reserved",
    re.IGNORECASE,
)

DOC_OPEN_RE = re.compile(r"^[rRuUbB]{0,2}(\"\"\"|''')")
SIG_RE = re.compile(r"^(async\s+def|def|class)\b")

# A line may legitimately end without terminal punctuation when the break
# lands before a conjunction or relative/subordinate clause on the next line.
CONNECTORS = {
    "and", "but", "so", "or", "nor", "yet",
    "which", "that", "where", "who", "whose", "whom",
    "when", "while", "because", "although", "though",
    "unless", "until", "if", "as",
}

# Characters that can legitimately end a semantically broken line.
OK_LINE_ENDERS = tuple(".!?;:,—-–)”\"'`")

# Sentence end followed by a new sentence on the same line.  Requires two or
# more lowercase letters before the terminal punctuation so that "e.g." and
# "i.e." do not match.
FUSED_RE = re.compile(r"\b[a-z]{2,}[.!?][\"')\]]*\s+[A-Z]")

# A bare "and" is usually a compound object (not a boundary); require the
# comma-led form, or strong punctuation, before advising a split.
BOUNDARY_HINT_RE = re.compile(
    r"[;:—]|\s–\s|, (?:and|but|so|which|that|where)\b"
)

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
          blocks=[("<#", "#>")],
          directives=[r"^#!", r"^#[rR]equires",
                      r"^#(?i:endregion|region)\b"]),
    _lang("rlang", [".r", ".R"], line="#", doc_lines=["#'"],
          directives=[r"^#!"]),
    _lang("haskell", [".hs"], line="--", blocks=[("{-", "-}")]),
    _lang("elixir", [".ex", ".exs"], line="#", directives=[r"^#!"]),
    _lang("zig", [".zig"], line="//", doc_lines=["///", "//!"]),
]


def is_markdown(path):
    return path.endswith((".md", ".markdown", ".mdx"))


def skip_path(path):
    """Return True if path should be skipped by hook mode.

    Compares path components after normalizing separators,
    so vendor/doc.go (repo-relative), /abs/vendor/doc.go (absolute),
    ./vendor/doc.go (relative), and C:\\repo\\vendor\\doc.go (Windows)
    all match.
    Anything under the platform temp directory is skipped:
    agent scratch files are never deliverables.
    """
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if any(part in SKIP_DIRS for part in p.split("/")):
        return True
    tmp_root = (tempfile.gettempdir() or "").replace("\\", "/").rstrip("/")
    return bool(tmp_root) and p.startswith(tmp_root + "/")


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
    if body.startswith(("#", "|", ">", "<", "@", "\\")):
        # Markdown headers/tables/quotes, HTML, javadoc/jsdoc/doxygen tags.
        return None
    if re.match(r"^\.[A-Za-z]+(\s|$)", body):
        # PowerShell comment-based-help keywords (.SYNOPSIS, .PARAMETER
        # Path), structurally the same as an @-prefixed doc tag.
        return None
    return body


def prose_lines_markdown(text):
    """Yield (lineno, raw_line, prose) for checkable Markdown lines.

    Yields (lineno, None, None) for lines that break paragraph continuity.
    """
    in_fence = False
    in_frontmatter = False
    after_refdef = False
    for i, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if i == 1 and stripped == "---":
            in_frontmatter = True
            yield i, None, None
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            yield i, None, None
            continue
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            yield i, None, None
            continue
        if in_fence:
            yield i, None, None
            continue
        if raw.startswith(("    ", "\t")):
            yield i, None, None
            continue
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
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("|")
            or "://" in stripped
            or stripped.startswith("<")
        ):
            yield i, None, None
            continue
        # Strip list markers and blockquote markers for content analysis.
        prose = re.sub(r"^(?:>\s*)?(?:[-*+]\s+|\d+[.)]\s+)?", "", stripped)
        yield i, raw, prose


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
    in_doc = False
    doc_quote = ""
    doc_base = 0
    expect_doc = lang.docstrings  # a module docstring may open the file
    sig_pending = False
    sig_depth = 0

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
            if lang.docstrings and stripped:
                # A "#" after whitespace in a string default (def f(x="a #b"):) makes the tracker miss that docstring
                # A "#"-led line inside a multi-line string literal is misread as a comment
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
                        expect_doc = False
                    else:
                        expect_doc = code.endswith(":")
                else:
                    expect_doc = False
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

PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$")
PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$")


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


def check(text, path):
    """Return a list of (lineno, kind, message, excerpt) findings."""
    lines = prose_stream(text, path)
    if lines is None:
        return []
    if not is_markdown(path):
        lang = lang_for_path(path)
        cut = license_header_extent(text, lang) if lang else 0
        if cut:
            lines = ((n, raw if n > cut else None, p if n > cut else None)
                     for n, raw, p in lines)

    findings = []
    limit = active_long_limit()
    prev = None  # (lineno, prose) of previous prose line in the same paragraph
    for lineno, raw, prose in lines:
        if prose is None:
            prev = None
            continue

        if FUSED_RE.search(prose):
            findings.append((
                lineno, "fused",
                "two sentences on one line — one sentence per line",
                prose,
            ))

        if prev is not None:
            prev_no, prev_prose = prev
            first_word = re.match(r"[a-z]+", prose)
            if (
                not prev_prose.endswith(OK_LINE_ENDERS)
                and first_word
                and first_word.group(0) not in CONNECTORS
            ):
                findings.append((
                    prev_no, "wrap",
                    "ends mid-clause (column-wrapped?) — break at sentence or clause boundaries, not at a column",
                    prev_prose,
                ))

        if limit and len(raw) > limit and BOUNDARY_HINT_RE.search(prose):
            findings.append((
                lineno, "long",
                f"advisory: {len(raw)} chars with a possible clause boundary — scan from ~{limit} rightward for ';' ':' '—' or an independent-clause 'and/but/so' / 'which/that/where', else backward; split only at a boundary where both sides stand alone, else leave the line long",
                prose,
            ))

        prev = (lineno, prose)
    findings.sort(key=lambda f: f[0])
    return findings


def format_findings(findings, path, snippet):
    where = "the text just written to" if snippet else ""
    lines = [f"semantic-linefeeds: {len(findings)} issue(s) in {where} {path}:".replace("  ", " ")]
    for lineno, kind, msg, excerpt in findings:
        label = f"line {lineno} of your edit" if snippet else f"line {lineno}"
        if len(excerpt) > 60:
            excerpt = excerpt[:57] + "..."
        lines.append(f'  [{kind}] {label}: {msg}\n         > {excerpt}')
    lines.append(
        f"Fix these in the block you just wrote: one sentence per line; "
        f"split sentences over ~{active_long_limit() or DEFAULT_LONG_LINE} chars at a real clause boundary (both sides must stand alone); "
        f"never break URLs, directives, or example code. "
        f"A finding can be a false positive (e.g. an 'and' joining a compound object is not a boundary) — "
        f"judge each one; leave the line alone if the break would sever a clause. "
        f"If unsure of the rules, load the semantic-linefeeds skill."
    )
    return "\n".join(lines)


def run_hook_claude():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not (is_markdown(path) or lang_for_path(path) is not None):
        return 0
    if skip_path(path):
        return 0
    text = tool_input.get("new_string") or tool_input.get("content") or ""
    if not text:
        return 0
    findings = check(text, path)
    if not findings:
        return 0
    print(format_findings(findings, path, snippet=True), file=sys.stderr)
    return 2


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


def main():
    ap = argparse.ArgumentParser(prog="check_linefeeds", description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--hook", nargs="?", const="claude",
                      choices=["claude", "codex"], default=None,
                      help="read a PostToolUse JSON payload on stdin and check only the "
                           "text just written; report findings to stderr, exit 2 if any "
                           "(default agent: claude)")
    mode.add_argument("--file", nargs="+", default=None, metavar="PATH",
                      help="check whole files and report to stdout; exit 1 on any "
                           "fused/wrap violation (long findings are advisory only)")
    ap.add_argument("--json", action="store_true",
                    help="with --file, emit findings as JSON instead of text")
    ap.add_argument("--long-limit", type=int, default=None, metavar="N",
                    help="long-line advisory threshold in chars; 0 disables "
                         "(default: $SEMBR_LONG_LINE or 120)")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(0 if e.code == 0 else 64)
    if args.long_limit is not None:
        if args.long_limit < 0:
            print("check_linefeeds: --long-limit must be >= 0", file=sys.stderr)
            sys.exit(64)
        global CLI_LONG_LIMIT
        CLI_LONG_LIMIT = args.long_limit
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


if __name__ == "__main__":
    main()
