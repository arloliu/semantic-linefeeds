#!/usr/bin/env python3
"""Detect violations of the semantic linefeeds convention in Go comments and Markdown prose.

Three heuristics, tuned for precision over recall (the agent judges; this only flags suspicion):

  fused  two independent sentences on one line
  wrap   a line that ends mid-clause with the sentence continuing on the next line
  long   a line over the threshold that appears to contain a clause boundary to split at

Modes:
  --hook          read a Claude Code PostToolUse JSON payload on stdin,
                  check only the text that was just written, report via stderr + exit 2
  --file PATH...  check whole files, report to stdout, exit 1 if findings
"""

import collections
import json
import re
import sys

LONG_LINE = 120

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
]


def is_markdown(path):
    return path.endswith((".md", ".markdown", ".mdx"))


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


def prose_lines_markdown(text):
    """Yield (lineno, raw_line, prose) for checkable Markdown lines.

    Yields (lineno, None, None) for lines that break paragraph continuity.
    """
    in_fence = False
    in_frontmatter = False
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


def check(text, path):
    """Return a list of (lineno, kind, message, excerpt) findings."""
    lines = prose_stream(text, path)
    if lines is None:
        return []

    findings = []
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

        if len(raw) > LONG_LINE and BOUNDARY_HINT_RE.search(prose):
            findings.append((
                lineno, "long",
                f"advisory: {len(raw)} chars with a possible clause boundary — scan from ~{LONG_LINE} rightward for ';' ':' '—' or an independent-clause 'and/but/so' / 'which/that/where', else backward; split only at a boundary where both sides stand alone, else leave the line long",
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
        "Fix these in the block you just wrote: one sentence per line; "
        "split sentences over ~120 chars at a real clause boundary (both sides must stand alone); "
        "never break URLs, directives, or example code. "
        "A finding can be a false positive (e.g. an 'and' joining a compound object is not a boundary) — "
        "judge each one; leave the line alone if the break would sever a clause. "
        "If unsure of the rules, load the semantic-linefeeds skill."
    )
    return "\n".join(lines)


def run_hook():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not (is_markdown(path) or lang_for_path(path) is not None):
        return 0
    if "/vendor/" in path or "/node_modules/" in path:
        return 0
    text = tool_input.get("new_string") or tool_input.get("content") or ""
    if not text:
        return 0
    findings = check(text, path)
    if not findings:
        return 0
    print(format_findings(findings, path, snippet=True), file=sys.stderr)
    return 2


def run_files(paths):
    # "long" findings are advisories (120 is a guide, not a gate): they are
    # printed for the judgment pass but never fail the run on their own.
    violations = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            print(f"semantic-linefeeds: cannot read {path}: {e}", file=sys.stderr)
            continue
        findings = check(text, path)
        if findings:
            violations += sum(1 for f in findings if f[1] != "long")
            print(format_findings(findings, path, snippet=False))
    return 1 if violations else 0


def main():
    args = sys.argv[1:]
    if args and args[0] == "--hook":
        sys.exit(run_hook())
    if args and args[0] == "--file":
        sys.exit(run_files(args[1:]))
    print(__doc__, file=sys.stderr)
    sys.exit(64)


if __name__ == "__main__":
    main()
