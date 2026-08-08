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

GO_DIRECTIVE_RE = re.compile(r"^//[a-zA-Z0-9_+-]+:")

# A bare "and" is usually a compound object (not a boundary); require the
# comma-led form, or strong punctuation, before advising a split.
BOUNDARY_HINT_RE = re.compile(
    r"[;:—]|\s–\s|, (?:and|but|so|which|that|where)\b"
)


def is_markdown(path):
    return path.endswith((".md", ".markdown", ".mdx"))


def is_go(path):
    return path.endswith(".go")


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


def prose_lines_go(text):
    """Yield (lineno, raw_line, prose) for checkable Go comment lines.

    Yields (lineno, None, None) for lines that break paragraph continuity.
    """
    in_block = False
    for i, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if in_block:
            end = "*/" in stripped
            body = stripped.split("*/")[0].strip(" *")
            if end:
                in_block = False
            if body and "://" not in body:
                yield i, raw, body
            else:
                yield i, None, None
            continue
        if stripped.startswith("/*"):
            in_block = "*/" not in stripped
            yield i, None, None
            continue
        if not stripped.startswith("//"):
            yield i, None, None
            continue
        if GO_DIRECTIVE_RE.match(stripped):
            yield i, None, None
            continue
        body = stripped[2:]
        if body.startswith("\t") or body.startswith("    "):
            # Indented godoc example code.
            yield i, None, None
            continue
        body = body.strip()
        if not body or "://" in body:
            yield i, None, None
            continue
        yield i, raw, body


def check(text, path):
    """Return a list of (lineno, kind, message, excerpt) findings."""
    if is_markdown(path):
        lines = prose_lines_markdown(text)
    elif is_go(path):
        first = text.splitlines()[0] if text.strip() else ""
        if "Code generated" in first:
            return []
        lines = prose_lines_go(text)
    else:
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
                f"{len(raw)} chars with a possible clause boundary — scan from ~{LONG_LINE} rightward for ';' ':' '—' or an independent-clause 'and/but/so' / 'which/that/where', else backward; split there if found",
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
    if not (is_markdown(path) or is_go(path)):
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
    total = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            print(f"semantic-linefeeds: cannot read {path}: {e}", file=sys.stderr)
            continue
        findings = check(text, path)
        if findings:
            total += len(findings)
            print(format_findings(findings, path, snippet=False))
    return 1 if total else 0


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
