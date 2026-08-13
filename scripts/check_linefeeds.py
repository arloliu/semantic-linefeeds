#!/usr/bin/env python3
"""Detect violations of the semantic linefeeds convention in code comments, doc comments, and docstrings,
covering Go, C-family, Rust, Python, shell, SQL, Ruby, and more, plus Markdown prose.

Three heuristics, tuned for precision over recall — the agent judges, this only flags suspicion:
"fused" is two independent sentences on one line,
"wrap" is a line that ends mid-clause with the sentence continuing on the next line,
and "long" is a line over the threshold that appears to contain a clause boundary to split at.

Two modes.
"--hook [claude|codex]" reads a PostToolUse JSON payload on stdin (agent defaults to claude)
and reads a stable snapshot of the edited file to report real line numbers,
falling back to checking only the payload's own text when the edit cannot be mapped to it exactly.
A fused finding blocks the edit: exit 2, with the report on stderr.
A wrap finding reaches the model only when SEMLF_EXPERIMENTAL_WRAP is set, and never blocks.
A result carrying only advisories exits 0 instead,
delivering them as one JSON object on stdout under hookSpecificOutput.additionalContext,
which is the shape both hosts make visible to the model.
"--file PATH... [--json]" checks whole files and reports to stdout as text or, with --json, as JSON,
exiting 1 if any fused/wrap violations are found;
long findings are advisory only and never affect the exit code.

Exits 64 on a usage error, such as bad or missing arguments.
"""

import argparse
import collections
import configparser
import fnmatch
import json
import os
import re
import sys
import tempfile

__version__ = "0.5.0"

DEFAULT_LONG_LINE = 120
CLI_LONG_LIMIT = None  # set by --long-limit in main()
CONFIG_FILENAME = ".semlf.ini"


def active_long_limit(path=None):
    """Resolve the long-line advisory threshold; 0 disables it.

    Precedence: --long-limit flag, then $SEMLF_LONG_LINE,
    then the project config discovered from path's directory, then 120.
    A malformed or negative env value falls back to the next leg.
    Discovery starts at the nearest existing ancestor directory,
    so a path whose directory vanished from the worktree keeps its policy.
    Discovery runs fresh on every call — no memo —
    because diagnose() and check() are called directly by tests and adapters,
    and a hidden cache a caller must know to reset would trade
    a few stat calls for a correctness trap.
    """
    if CLI_LONG_LIMIT is not None:
        return CLI_LONG_LIMIT
    raw = os.environ.get("SEMLF_LONG_LINE", "")
    if raw:
        try:
            value = int(raw)
            if value >= 0:
                return value
        except ValueError:
            pass
    if path is not None:
        cfg = load_config(_existing_start(path))
        if "long_limit" in cfg:
            return cfg["long_limit"]
    return DEFAULT_LONG_LINE


def _config_and_root(start_dir):
    """(parsed config dict, real directory owning the config).

    ({}, None) when no config was found or the file was unusable.
    The walk is physical: start_dir is resolved through symlinks once,
    then parents are taken lexically from the resolved path,
    so candidates, parents, and boundary checks share one representation.
    It stops at the first directory holding .semlf.ini or a .git entry
    (file or directory — worktrees use a file),
    because configuration must not leak across a repository boundary;
    in the directory holding both, the config wins,
    which is what permits a repository-root config.
    A start_dir that is not an existing directory returns ({}, None)
    without walking.
    No section supplies a key through defaults inheritance:
    every parser default is stripped through the public API right after
    the file is read, before any section is consulted,
    because ConfigParser.defaults() would otherwise inherit into [semlf]
    from a default section whose name hostile input can always spell.
    File-level trouble — unreadable, undecodable, parser error —
    drops the whole file;
    an invalid value drops only its own key,
    so one bad long-limit cannot silence a good exclude beside it.
    """
    cur = os.path.realpath(start_dir)
    if not os.path.isdir(cur):
        return {}, None
    found = None
    while True:
        candidate = os.path.join(cur, CONFIG_FILENAME)
        if os.path.isfile(candidate):
            found = candidate
            break
        if os.path.exists(os.path.join(cur, ".git")):
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if found is None:
        return {}, None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(found, encoding="utf-8") as fh:
            parser.read_file(fh)
        for option in list(parser.defaults()):
            parser.remove_option(configparser.DEFAULTSECT, option)
        raw_limit = parser.get("semlf", "long-limit", fallback=None)
        raw_exclude = parser.get("semlf", "exclude", fallback=None)
    except (OSError, UnicodeDecodeError, configparser.Error):
        return {}, None
    cfg = {}
    if raw_limit is not None:
        try:
            value = int(raw_limit.strip())
        except ValueError:
            value = -1
        if value >= 0:
            cfg["long_limit"] = value
    if raw_exclude is not None:
        patterns = []
        for line in raw_exclude.replace("\\", "/").splitlines():
            pattern = line.strip().lstrip("/")
            if pattern:
                patterns.append(pattern)
        if patterns:
            cfg["exclude"] = patterns
    return cfg, cur


def load_config(start_dir):
    """Project configuration discovered from start_dir upward.

    The walk and its boundary rules live on _config_and_root;
    this wrapper keeps the public shape every v0.6a caller uses.
    Returns {"long_limit": int} and/or {"exclude": [str, ...]} for a
    valid file, else {} — a config file can tune the checker but must
    never break it, and an invalid value drops only its own key.
    """
    return _config_and_root(start_dir)[0]


def _existing_start(path):
    """The nearest existing ancestor directory of path.

    The worktree-policy anchor: a staged file whose parent directory
    was removed from the worktree is still governed by the configs
    that do exist above it (ADR-0013's one-policy-source ruling).
    load_config keeps its own contract — a nonexistent start_dir handed
    to it directly returns {} without walking; the ascent lives here,
    in the callers that own a path rather than a directory.
    """
    cur = os.path.dirname(os.path.abspath(path))
    while cur and not os.path.isdir(cur):
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return cur


def _segments_match(parts, patterns):
    """Segment-wise glob equality: same length, every segment matches its pattern."""
    return (len(parts) == len(patterns)
            and all(fnmatch.fnmatchcase(part, pattern)
                    for part, pattern in zip(parts, patterns)))


def _exclude_match(rel, patterns):
    """Whether a /-normalized relative path matches any exclude pattern.

    Grammar (ADR-0013), one load-bearing rule first:
    separators are boundaries — * and ? never cross a slash,
    so every comparison is per path segment, never whole-string
    (raw fnmatch would let * roam across separators).
    A trailing "/" names folders:
    with an inner "/" the segment chain is anchored at the config
    root and matches only what lives under it — never a plain file
    whose own path spells the chain;
    without one the folder name excludes at any depth.
    A pattern without a trailing "/" is a glob:
    with a "/" it must match the whole relative path segment-by-segment,
    without one it may match any single path component.
    fnmatchcase everywhere: a rule that changed meaning between
    platforms would make the same commit clean on one machine
    and flagged on another.
    """
    parts = rel.split("/")
    for pattern in patterns:
        if pattern.endswith("/"):
            chain = pattern.rstrip("/").split("/")
            if len(chain) > 1:
                if len(parts) > len(chain) and _segments_match(parts[:len(chain)], chain):
                    return True
            elif any(fnmatch.fnmatchcase(part, chain[0]) for part in parts[:-1]):
                return True
        elif "/" in pattern:
            if _segments_match(parts, pattern.split("/")):
                return True
        elif any(fnmatch.fnmatchcase(part, pattern) for part in parts):
            return True
    return False


def excluded(path):
    """Whether the project config excludes path from discovery.

    Discovery-only: hook mode and the semlf git modes consult this
    filter; an explicitly named --file path never does — naming a path
    is the judgment call excludes exist to encode (ADR-0010's
    principle), and overriding it silently would hide a finding the
    user asked for.
    Fails open like every config path: no config, a config the parser
    rejects, or a path outside the config's tree excludes nothing.
    A false exclusion is a missed finding — the acceptable direction;
    a crash or a changed finding kind is not.
    """
    cfg, root = _config_and_root(_existing_start(path))
    patterns = cfg.get("exclude")
    if not patterns or root is None:
        return False
    try:
        rel = os.path.relpath(os.path.realpath(path), root)
    except (OSError, ValueError):
        # ValueError is Windows' cross-drive relpath; both fail open.
        return False
    rel = rel.replace(os.sep, "/").replace("\\", "/")
    if rel == "." or rel == ".." or rel.startswith("../"):
        return False
    return _exclude_match(rel, patterns)


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

# Abbreviations that end mid-sentence rather than ending a sentence.
# Derived from the rule below rather than from a general list of abbreviations.
# "Fig.", "No.", "Eq.", "e.g." and "i.e." cannot match that rule at all,
# so listing them would widen the exclusion the day the rule changes,
# without narrowing anything today.
# "etc." and "resp." are left out for the opposite reason:
# both commonly do end a sentence.
MID_SENTENCE_ABBREVIATIONS = ("cf", "esp", "viz", "vs")

# Sentence end followed by a new sentence on the same line.
# Two or more lowercase letters are required before the terminal punctuation,
# which is what keeps "e.g." and "i.e." from matching.
# A code span may stand where the final word does,
# because a closing backtick is unambiguous:
# it closes the span, and the punctuation after it belongs to the sentence.
# Emphasis marks may stand between the punctuation and the space,
# where they close a sentence written wholly inside emphasis.
# The next sentence opens on an uppercase letter,
# or on a code span that something in the same sentence follows;
# a span the line merely ends on is a fragment rather than a sentence.
FUSED_RE = re.compile(
    r"(?:\b(?!(?:" + "|".join(MID_SENTENCE_ABBREVIATIONS) + r")\.)"
    r"[a-z]{2,}|`[^`]+`)"
    r"[.!?][\"')\]*_~]*"
    r"\s+(?:[A-Z]|`[^`]+`\s*\w)")

# Emphasis delimiters standing between the terminal punctuation and the end of the line,
# where they hide that punctuation from the wrap check.
# The backtick is deliberately absent.
# It already ends a line legitimately,
# so peeling it would expose whatever punctuation the code span happens to contain.
CLOSING_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3}|~{1,2})$")

# A code span that closes the line it sits on.
# The backtick is a legitimate line ender, so a line ending in a span is never a wrap
# and the clause the span was attached to is never read at all.
TRAILING_CODE_SPAN_RE = re.compile(r"`[^`]+`$")

# A comment line holding nothing but code punctuation.
# Commented-out code written as line comments rather than as an indented block
# reaches the extractor as prose, and a lone closing brace then forms a boundary
# with whatever line follows it.
# The set is deliberately narrow: no English sentence is built from these alone,
# so nothing that reads as prose can match.
CODE_PUNCTUATION_RE = re.compile(r"^[{}()\[\];,\s]+$")

# A rule of repeated punctuation used to divide one section of a comment from the next.
# The divider is not prose, and the label under it is not a continuation of it.
# Three characters minimum, so an em dash standing on its own line is not swallowed.
DIVIDER_RE = re.compile(r"^([^\w\s])\1{2,}$")

# One blockquote marker: up to three leading spaces, ">", and at most one space after it.
QUOTE_MARKER_RE = re.compile(r"^ {0,3}> ?")

# A list marker, and the space that must follow it before the item's content.
LIST_ITEM_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")

# The delimiter row under a table header.
# A row may omit its leading and trailing pipes, so the first character marks nothing,
# and a row of prose cells reaches the checker looking exactly like a paragraph.
# The delimiter row is the one part of the syntax that cannot be read as prose.
# A pipe is still required in it, so a setext underline stays a setext underline.
TABLE_DELIMITER_RE = re.compile(r"^\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?$")

# A code fence, which only a run of its own mark and at least its own length closes.
# One flag for both marks let a tilde run inside a backtick block close it,
# and a fence long enough to quote a shorter one was closed by the one it quoted.
# Either inverts every fence after that point,
# so prose is skipped and the code in the next block is read as prose.
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# An HTML block whose content is code.
# The opening tag is skipped for starting with a bracket,
# and without a state the lines under it are read as prose.
PRE_OPEN_RE = re.compile(r"<pre\b|<pre>", re.IGNORECASE)

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
          # gofail failpoints are written with a space (`// gofail: var x T`),
          # so the unspaced marker pattern never reaches them.
          directives=[r"^//[a-zA-Z0-9_+-]+:", r"^//\s*\+build\b",
                      r"^//\s*gofail:"]),
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
    try:
        tmp_root = (tempfile.gettempdir() or "").replace("\\", "/").rstrip("/")
    except OSError:
        # A host with no usable temp directory loses the exclusion,
        # which costs a few findings on scratch files.
        # Raising here would cost the agent its edit,
        # and an advisory guardrail never gets to do that.
        # Only filesystem failure is caught:
        # a TypeError here would be this file's own bug, and hiding it helps nobody.
        return False
    return bool(tmp_root) and p.startswith(tmp_root + "/")


def _after_directive_preamble(lines, lang):
    """The index where the leading comment region starts, past any build directives.

    A build constraint is not a comment scope of its own.
    Reading it as one ends the region at the blank line the language requires
    under a Go build tag, which leaves the licence below it judged as prose.
    Only a run that actually opens with a directive is stepped over,
    so a file whose first line is a blank or a comment is read exactly as before.
    """
    if not lang.directives:
        return 0
    start = 0
    seen = False
    for i, raw in enumerate(lines):
        s = raw.strip()
        if any(rx.match(s) for rx in lang.directives):
            seen = True
        elif not (seen and not s):
            break
        start = i + 1
    return start if seen else 0


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
    lines = text.splitlines()
    start = _after_directive_preamble(lines, lang)
    for i, raw in enumerate(lines[start:], start + 1):
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
    if CODE_PUNCTUATION_RE.match(body):
        # A closing brace standing alone in a comment is commented-out code.
        return None
    if DIVIDER_RE.match(body):
        # A rule of dashes divides sections; it continues no sentence.
        return None
    return body


def peel_emphasis(prose):
    """Strip closing emphasis delimiters so the line-ender test sees the punctuation.

    Only a delimiter something opened is peeled.
    A lone "*" at the end of a line is a multiplication sign or a typo,
    and treating it as emphasis would hide a real wrap behind it.
    """
    while True:
        match = CLOSING_EMPHASIS_RE.search(prose)
        if not match:
            return prose
        head = prose[:match.start()]
        if match.group(1) not in head:
            return prose
        prose = head


def peel_code_span(prose):
    """Remove a code span that closes the line, so the clause in front of it can be read.

    This is not the emphasis peel.
    That one strips a delimiter to reveal the punctuation standing behind it,
    and the punctuation was always the line's own.
    A code span carries punctuation of its own that says nothing about the sentence,
    so the whole span goes and the question becomes what the span was attached to.

    A line that is nothing but a code span keeps its ending.
    Code alone is not a clause, so there is no clause end to look for behind it.
    """
    match = TRAILING_CODE_SPAN_RE.search(prose)
    if not match:
        return prose
    return prose[:match.start()].rstrip() or prose


def line_ending(prose):
    """What a line ends with, once the trailing markup that hides it is removed."""
    return peel_emphasis(peel_code_span(peel_emphasis(prose)))


# A changed span is where an edit landed in the after-state text.
# Half-open over code points, except that a deleted newline leaves no
# after-state text at all, so a boundary is carried as a zero-width span.
# "mapping" records whether the adapter located the edit exactly or fell
# back to something coarser; the hook, not the core, decides what a
# degraded mapping forfeits.
def normalize_span(span):
    if not isinstance(span, dict):
        raise ValueError(f"span must be a mapping: {span!r}")
    unknown = set(span) - {"at", "start", "end", "mapping"}
    if unknown:
        raise ValueError(f"span carries unknown keys: {span!r}")
    if "at" in span:
        if "start" in span or "end" in span:
            raise ValueError(f"span mixes 'at' with a range: {span!r}")
        start = end = span["at"]
    elif "start" in span and "end" in span:
        start, end = span["start"], span["end"]
    else:
        raise ValueError(f"span needs 'at' or 'start' and 'end': {span!r}")
    for offset in (start, end):
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise ValueError(f"span offsets must be integers: {span!r}")
    if start < 0 or end < start:
        raise ValueError(f"span is not a forward range: {span!r}")
    mapping = span.get("mapping", "exact")
    if mapping not in ("exact", "degraded"):
        raise ValueError(f"span mapping must be exact or degraded: {span!r}")
    return {"start": start, "end": end, "mapping": mapping}


def touches(rng, span):
    """Strict overlap for ranges; a zero-width boundary touches on an edge.

    Two half-open ranges must share a code point: an edit that stops
    exactly where the accused text begins changed nothing inside it,
    and reporting there is a false positive.
    A deleted newline leaves no after-state text at all,
    so a zero-width boundary counts when it lies anywhere on the range, edges included.
    """
    lo = max(rng["start"], span["start"])
    hi = min(rng["end"], span["end"])
    if rng["start"] == rng["end"] or span["start"] == span["end"]:
        return lo <= hi
    return lo < hi


def line_offsets(text):
    """Code-point offset of each 1-based line's start, with an end sentinel.

    Partitions text with str.splitlines like the extractors do.
    Every terminator it recognizes (LF, CRLF, bare CR, Unicode separators)
    starts a new line in both the table and the extractors' numbering.
    """
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def locate_in_line(text, offsets, lineno, needle):
    """The absolute range of a needle that occurs exactly once in a line.

    Prose usually appears verbatim once markers are stripped.
    Return None when stripping or repetition breaks this assumption.
    This forces the caller to drop ownership rather than guess.
    """
    if not needle or lineno < 1 or lineno >= len(offsets):
        return None
    start, end = offsets[lineno - 1], offsets[lineno]
    line = text[start:end]
    first = line.find(needle)
    if first < 0 or line.find(needle, first + 1) >= 0:
        return None
    return {"start": start + first, "end": start + first + len(needle)}


def strip_quote_markers(raw):
    """The content a blockquote holds, with the markers in front of it removed.

    The markers come off before anything else looks at the line.
    Every rule that decides a line is not prose — fences, indented code, headings,
    tables, reference definitions, inline HTML — reads the content rather than the marker,
    and a rule that ran first would see the marker instead and call the line prose.

    The indentation inside the quote is kept, because the four-space rule depends on it.
    """
    while True:
        match = QUOTE_MARKER_RE.match(raw)
        if not match:
            return raw
        raw = raw[match.end():]


def prose_lines_markdown(text):
    """Yield (lineno, raw_line, prose) for checkable Markdown lines.

    Yields (lineno, None, None) for lines that break paragraph continuity.
    """
    fence = None  # the mark and length of the open fence, which only its own closes
    in_frontmatter = False
    in_pre = False
    after_refdef = False
    in_table = False
    lines = text.splitlines()
    for i, raw in enumerate(lines, 1):
        content = strip_quote_markers(raw)
        stripped = content.strip()
        if i == 1 and stripped == "---":
            in_frontmatter = True
            yield i, None, None
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            yield i, None, None
            continue
        if in_pre:
            # Code inside an HTML block carries pipes and braces of its own,
            # so it leaves before any rule that reads either as markup.
            if "</pre" in stripped.lower():
                in_pre = False
            yield i, None, None
            continue
        if in_table:
            # The block runs to the first blank line or the next block-level
            # structure, which is where a table ends for a reader too.
            if stripped and not stripped.startswith(("#", "```", "~~~")):
                yield i, None, None
                continue
            in_table = False
        if "|" in stripped:
            following = lines[i] if i < len(lines) else ""
            following = strip_quote_markers(following).strip()
            if "|" in following and TABLE_DELIMITER_RE.match(following):
                in_table = True  # this line is the header the delimiter names
                yield i, None, None
                continue
        marker = FENCE_RE.match(stripped)
        if marker:
            mark, width = marker.group(1)[0], len(marker.group(1))
            if fence is None:
                fence = (mark, width)
            elif fence[0] == mark and width >= fence[1]:
                fence = None
            yield i, None, None
            continue
        if fence is not None:
            yield i, None, None
            continue
        if content.startswith(("    ", "\t")):
            yield i, None, None
            continue
        if PRE_OPEN_RE.match(stripped):
            in_pre = "</pre" not in stripped.lower()
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
        comment = MD_STANDALONE_RE.match(stripped)
        # ADR-0010 permits only ASCII space/tab as directive WS,
        # including at the raw line's ends.
        # `stripped` reached the "<!--...-->" form through Python's Unicode-aware .strip(),
        # which folds NBSP, em space, and other wide whitespace away exactly like the ASCII forms.
        # An ASCII-only strip of the same text must land on the same string,
        # or a candidate the grammar never authorized would be yielded as a directive carrier instead of staying markup.
        if comment and content.strip(" \t\r") == stripped:
            carrier_content = comment.group(1).strip(" \t")
            parsed = parse_directive(carrier_content)
            if parsed is not None and parsed is not MALFORMED:
                # A directive-only HTML comment is the one markup line the
                # stream keeps: recognition happens downstream, after the
                # licence cut has had its say (ADR-0010).
                yield i, raw, carrier_content
                continue
        # A malformed or non-directive comment falls through to the
        # exclusion below and stays markup.
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("|")
            or "://" in stripped
            or stripped.startswith("<")
        ):
            yield i, None, None
            continue
        # A new list item starts a new paragraph.
        # One item measured against the next is two thoughts compared as though they were one,
        # and the break between them was never a wrap.
        if LIST_ITEM_RE.match(stripped):
            yield i, None, None
        prose = LIST_ITEM_RE.sub("", stripped)
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


def header_comment_text(text, lang):
    """Every comment line standing above a file's first line of code.

    A generator writes its marker under whatever licence it emits,
    so a fixed number of leading lines misses the marker exactly when a licence stands first.
    The first line of code ends the header, which is what keeps the scan
    from reading a `DO NOT EDIT` written in prose further down as one.
    """
    header = []
    in_block = False
    close = ""
    for raw in text.splitlines():
        s = raw.strip()
        if in_block:
            header.append(s)
            if close in s:
                in_block = False
            continue
        if not s:
            continue
        opened = False
        for open_d, close_d in lang.blocks:
            if s.startswith(open_d):
                header.append(s)
                in_block = close_d not in s[len(open_d):]
                close = close_d
                opened = True
                break
        if opened:
            continue
        if lang.line and s.startswith(lang.line):
            header.append(s)
            continue
        break
    return "\n".join(header)

PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$")
PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$")


def prose_stream(text, path):
    """Return the prose-line generator for path, or None if not a target."""
    if is_markdown(path):
        return prose_lines_markdown(text)
    lang = lang_for_path(path)
    if lang is None:
        return None
    # Two reaches, and the header is added to the first five lines rather than
    # replacing them: narrowing the older rule would start checking files it
    # now skips, and a change that adds findings is not one this corpus can score.
    head = "\n".join(text.splitlines()[:5])
    if GENERATED_RE.search(head) or GENERATED_RE.search(header_comment_text(text, lang)):
        return iter(())
    return prose_lines_code(text, lang)


def _paragraph_without_license(paragraph):
    """One buffered comment paragraph, silenced when any line of it carries a marker.

    The paragraph is the unit rather than the line.
    A copyright line is where the marker sits,
    and the sentences a licence is made of are on the lines after it.
    """
    if any(LICENSE_RE.search(prose) for _, _, prose in paragraph):
        return [(lineno, None, None) for lineno, _, _ in paragraph]
    return paragraph


def without_license_text(lines, text, path):
    """The prose stream with licence text removed, wherever in the file it sits.

    Two cuts, because neither one covers what the other does.
    The leading region is cut by extent, which reaches a header
    whose own first line carries nothing a marker matches.
    Every other comment paragraph is cut when some line of it carries a marker,
    which reaches the second copyright block a generated file puts below its code.
    Markdown has no leading extent and gets only the paragraph cut,
    which reaches the licence block a carbon-lang file opens inside an HTML comment.

    Both readers of the extractor cut here, and that is the point of the function.
    A sampling frame that enumerated a boundary the checker refuses to judge
    would hold a violation no predicate could ever reach.
    """
    lang = None if is_markdown(path) else lang_for_path(path)
    cut = license_header_extent(text, lang) if lang else 0
    paragraph = []
    for lineno, raw, prose in lines:
        if prose is not None and lineno > cut:
            paragraph.append((lineno, raw, prose))
            continue
        yield from _paragraph_without_license(paragraph)
        paragraph = []
        yield lineno, None, None
    yield from _paragraph_without_license(paragraph)


def _line_range(text, offsets, lineno):
    """The raw line as a half-open range, its line terminator excluded.

    splitlines strips whichever terminator ends the line — LF, CRLF,
    bare CR, or a Unicode separator — so the range never accuses one.
    """
    start, end = offsets[lineno - 1], offsets[lineno]
    split = text[start:end].splitlines()
    content = split[0] if split else ""
    return {"start": start, "end": start + len(content)}


# The repeatable line leaders a suggestion's prefix may be built from:
# whitespace, then zero or more of #, //, ;, or a blockquote >, each
# optionally followed by more whitespace.
# A list marker, a docstring's opening quotes, and a block comment's
# opening /* all fail this whitelist on purpose.
# * is deliberately absent even though it is also a legitimate
# block-comment continuation marker: the Markdown extractor also treats
# a leading * as a list bullet and strips it from prose while keeping
# it in raw, so admitting it here would duplicate that bullet and split
# one list item into two.
# Losing the suggestion on a real block-comment continuation is the
# accepted missed-suggestion cost of closing that hole.
_SUGGESTION_PREFIX_RE = re.compile(r"^[ \t]*(?:(?:#|//|;|>)[ \t]*)*$")

# The suggestion's tail may carry only trailing whitespace; nothing may
# move across the break.
_SUGGESTION_TAIL_RE = re.compile(r"^[ \t]*$")


def _fused_suggestion(prose, raw, match):
    """A two-line suggested replacement for an automatic-class fused finding, or None.

    Maximally conservative rather than a real protected-span engine: no
    suggestion unless FUSED_RE matches exactly once, the terminator sits
    with nothing between it and a single ASCII space, `prose` has no
    backtick/`<`/`>` anywhere on the line, `raw` contains `prose`
    exactly once, and the prefix/tail around `prose` in `raw` both pass
    the structural whitelist above.
    Any closing quote, bracket, paren, or emphasis mark between the
    terminator and the space withholds the suggestion instead of trying
    to reattach it.
    `raw` cannot carry an embedded `\\r` on any current entry path
    (every extractor reaches it through `str.splitlines()`), so that
    check is a belt over an already-fastened suspender, kept for a
    future entry path that might skip it.
    """
    if "\r" in raw:
        return None
    if len(list(FUSED_RE.finditer(prose))) != 1:
        return None
    if "`" in prose or "<" in prose or ">" in prose:
        return None
    if raw.count(prose) != 1:
        return None
    text = match.group(0)
    ws = re.search(r"\s+", text)
    if ws.group(0) != " ":
        return None
    terminator = text[ws.start() - 1]
    if terminator not in "!?":
        return None
    idx = raw.find(prose)
    prefix = raw[:idx]
    tail_text = raw[idx + len(prose):]
    if not _SUGGESTION_PREFIX_RE.match(prefix) or not _SUGGESTION_TAIL_RE.match(tail_text):
        return None
    cut = match.start() + ws.start()
    p1 = prose[:cut]
    p2 = prose[cut:].lstrip(" ")
    return {"lines": [prefix + p1, prefix + p2 + tail_text]}


def diagnose(text, path, spans=None):
    """Return a list of diagnostic dicts, sorted by line.

    Each dict carries the finding plus its three ranges.
    `anchor` is the raw line the finding was read from.
    `evidence` is what the finder looked at — both lines for `wrap`.
    `ownership` is the causal tokens, or None when a locate could not pin them exactly.
    `spans=None` reports everything;
    a spans list restricts reporting to diagnostics whose ownership touches a normalized span,
    and a degraded diagnostic is withheld under spans.
    """
    normalized = None if spans is None else [normalize_span(span) for span in spans]
    suppressions = {}
    lines = prose_stream(text, path)
    if lines is None:
        return []
    lines = without_license_text(lines, text, path)
    is_md = is_markdown(path)
    lang = None if is_md else lang_for_path(path)

    offsets = line_offsets(text)
    findings = []
    limit = active_long_limit(path)
    prev = None  # (lineno, prose) of previous prose line in the same paragraph
    for lineno, raw, prose in lines:
        if prose is None:
            prev = None
            continue

        # Checked against the still-unrebound raw line: the trailing-carrier
        # block below this one reassigns `raw` later in the same iteration.
        parsed = parse_directive(prose)
        if (parsed is not None and parsed is not MALFORMED
                and _standalone_carrier_is_ascii(raw, prose)):
            # A well-formed standalone directive line is a paragraph boundary,
            # not prose (ADR-0010).
            # A MALFORMED line, or one whose carrier whitespace is not
            # ASCII (ADR-0010's WS grammar), falls through and stays
            # visible prose.
            offset, kinds = parsed
            suppressions.setdefault(lineno + offset, set()).update(kinds)
            prev = None
            continue
        carrier_stripped = False
        tail = trailing_carrier(raw, is_md, lang)
        if tail:
            (offset, kinds), judged_raw, carrier = tail
            trimmed_prose = prose.rstrip(" \t")
            if trimmed_prose.endswith(carrier):
                suppressions.setdefault(lineno + offset, set()).update(kinds)
                raw = judged_raw
                prose = trimmed_prose[:-len(carrier)].rstrip(" \t")
                carrier_stripped = True
                if not prose:
                    prev = None
                    continue
            # else: the carrier is not a shared suffix of both views;
            # treat the tail as unrecognized so raw and prose stay one text.

        match = FUSED_RE.search(prose)
        if match:
            anchor = _line_range(text, offsets, lineno)
            located = locate_in_line(text, offsets, lineno, match.group(0))
            if located and located["end"] <= anchor["end"]:
                tail = re.search(r"\s", text[located["end"]:anchor["end"]])
                end = located["end"] + tail.start() if tail else anchor["end"]
                ownership, basis = {"start": located["start"], "end": end}, "token"
            else:
                ownership, basis = None, "degraded"
            finding = {
                "kind": "fused", "line": lineno,
                "message": "two sentences on one line — one sentence per line",
                "excerpt": prose,
                "anchor": anchor, "evidence": dict(anchor),
                "ownership": ownership, "ownership_basis": basis,
            }
            if not carrier_stripped:
                suggestion = _fused_suggestion(prose, raw, match)
                if suggestion is not None:
                    finding["suggestion"] = suggestion
            findings.append(finding)

        if prev is not None:
            prev_no, prev_prose = prev
            first_word = re.match(r"[a-z]+", prose)
            if (
                not line_ending(prev_prose).endswith(OK_LINE_ENDERS)
                and first_word
                and first_word.group(0) not in CONNECTORS
            ):
                upper_words = line_ending(prev_prose).rsplit(maxsplit=1)
                upper = (locate_in_line(text, offsets, prev_no, upper_words[-1])
                         if upper_words else None)
                lower = locate_in_line(text, offsets, lineno, first_word.group(0))
                anchor = _line_range(text, offsets, prev_no)
                evidence = {"start": anchor["start"],
                            "end": _line_range(text, offsets, lineno)["end"]}
                if upper and lower and upper["end"] <= lower["start"]:
                    ownership, basis = {"start": upper["start"], "end": lower["end"]}, "token"
                else:
                    ownership, basis = None, "degraded"
                findings.append({
                    "kind": "wrap", "line": prev_no,
                    "message": "ends mid-clause (column-wrapped?) — break at sentence or clause boundaries, not at a column",
                    "excerpt": prev_prose,
                    "anchor": anchor, "evidence": evidence,
                    "ownership": ownership, "ownership_basis": basis,
                })

        if limit and len(raw) > limit and BOUNDARY_HINT_RE.search(prose):
            anchor = _line_range(text, offsets, lineno)
            located = locate_in_line(text, offsets, lineno, prose)
            ownership, basis = (located, "token") if located else (None, "degraded")
            findings.append({
                "kind": "long", "line": lineno,
                "message": f"advisory: {len(raw)} chars with a possible clause boundary — scan from ~{limit} rightward for ';' ':' '—' or an independent-clause 'and/but/so' / 'which/that/where', else backward; split only at a boundary where both sides stand alone, else leave the line long",
                "excerpt": prose,
                "anchor": anchor, "evidence": dict(anchor),
                "ownership": ownership, "ownership_basis": basis,
            })

        prev = (lineno, prose)
    findings.sort(key=lambda d: d["line"])
    if normalized is not None:
        findings = [d for d in findings
                    if d["ownership"] is not None
                    and any(touches(d["ownership"], span) for span in normalized)]
    if suppressions:
        findings = [d for d in findings
                    if d["kind"] not in suppressions.get(d["line"], frozenset())]
    return findings


def check(text, path):
    """Return a list of (lineno, kind, message, excerpt) findings."""
    return [(d["line"], d["kind"], d["message"], d["excerpt"])
            for d in diagnose(text, path)]


DIAGNOSTIC_SCHEMA_VERSION = 1


def to_schema(path, diagnostics):
    """The versioned document one file's diagnostics travel in.

    Text output, SARIF, and annotations are renderers over this shape;
    the version field is what lets the next breaking change announce itself instead of being discovered by a consumer's parser.
    """
    return {"schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "path": path,
            "diagnostics": diagnostics}


def _as_tuples(findings):
    """Normalize either legacy tuples or diagnostic dicts to the tuple shape.

    `format_findings` is the one renderer both callers share,
    and this line is what lets it stay ignorant of which shape it received.
    """
    return [(f["line"], f["kind"], f["message"], f["excerpt"])
            if isinstance(f, dict) else f for f in findings]


def _kind_of(finding):
    """The kind of a finding whether it is a diagnostic dict or a legacy tuple."""
    return finding["kind"] if isinstance(finding, dict) else finding[1]


def format_findings(findings, path, snippet, skill_hint=True):
    findings = _as_tuples(findings)
    where = "the text just written to" if snippet else ""
    lines = [f"semantic-linefeeds: {len(findings)} issue(s) in {where} {path}:".replace("  ", " ")]
    for lineno, kind, msg, excerpt in findings:
        label = f"line {lineno} of your edit" if snippet else f"line {lineno}"
        if len(excerpt) > 60:
            excerpt = excerpt[:57] + "..."
        lines.append(f'  [{kind}] {label}: {msg}\n         > {excerpt}')
    limit = active_long_limit(path) or DEFAULT_LONG_LINE
    if blocking_kinds(findings):
        blocking = [
            f"Fix these in the block you just wrote: one sentence per line; "
            f"split sentences over ~{limit} chars at a real clause boundary (both sides must stand alone); "
            f"never break URLs, directives, or example code. "
            f"A finding can be a false positive (e.g. an 'and' joining a compound object is not a boundary) — "
            f"judge each one; leave the line alone if the break would sever a clause."
        ]
        if skill_hint:
            blocking.append("If unsure of the rules, load the semantic-linefeeds skill.")
        lines.append(" ".join(blocking))
    else:
        # An advisory report must not say "Fix these".
        # Where a long line carries no clause boundary,
        # the skill's own instruction is to leave it long.
        kinds = {kind for _, kind, _, _ in findings}
        closing = ["Consider these, and change nothing you are not sure about."]
        if WITHHELD_KIND in kinds:
            closing.append(
                f"A {WITHHELD_KIND} finding is an evaluation of this checker rather than an "
                f"instruction to you: decide whether the line already ends at a real clause "
                f"boundary, and leave it exactly as it is if it does."
            )
        if "long" in kinds:
            closing.append(
                f"A line over ~{limit} chars is worth splitting only at a real clause boundary "
                f"where both sides stand alone. "
                f"If there is no such boundary, leaving the line long is the right answer."
            )
        closing.append("Never break URLs, directives, or example code.")
        if skill_hint:
            closing.append("If unsure of the rules, load the semantic-linefeeds skill.")
        lines.append(" ".join(closing))
    return "\n".join(lines)


# ADR-0010: the suppression grammar.
# Longest name first, so `semlf-ignore-next` is one token,
# never `semlf-ignore` trailed by an unknown argument.
DIRECTIVE_KINDS = frozenset({"fused", "wrap", "long"})
DIRECTIVE_NAMES = ("semlf-ignore-next", "semlf-ignore")

# A recognized name with an unknown argument suppresses nothing at all;
# a sentinel keeps that state distinct from "not a directive".
MALFORMED = object()


def _standalone_carrier_is_ascii(raw, prose):
    """Whether raw's whitespace around the recognized directive text is ASCII-only.

    ADR-0010 permits only ASCII space/tab as directive WS,
    including between a comment leader and the directive and at the raw line's ends.
    The extractors reach `prose` through Python's Unicode-aware .strip(),
    which folds NBSP, em space, and other Unicode whitespace away just like the ASCII forms.
    This checks the same characters `str.strip()` removes.
    Left unguarded, that fold would let text the grammar forbids masquerade as a well-formed carrier.
    A non-whitespace character on either side (a comment leader, `<!--`/`-->`) is carrier syntax and always fine.
    """
    idx = raw.find(prose)
    if idx < 0:
        return False
    outer = raw[:idx] + raw[idx + len(prose):]
    return all(ch in " \t\r" for ch in outer if ch.isspace())


def parse_directive(content):
    """Parse content that should be exactly one directive.

    Returns (offset, kinds) for a well-formed directive,
    where offset 0 targets the carrier's own line and 1 the next raw line,
    MALFORMED for a recognized name with any unknown argument,
    and None when content is not a directive at all.
    WS is ASCII space or horizontal tab, per the contract.
    """
    tokens = [t for t in re.split(r"[ \t]+", content) if t]
    if not tokens or tokens[0] not in DIRECTIVE_NAMES:
        return None
    args = tokens[1:]
    if any(a not in DIRECTIVE_KINDS for a in args):
        return MALFORMED
    offset = 1 if tokens[0] == "semlf-ignore-next" else 0
    return offset, (frozenset(args) or DIRECTIVE_KINDS)


# A trailing HTML-comment carrier: the rightmost comment, ending the line.
# [^<>] keeps the match inside one comment, so an earlier comment stays prose.
MD_TRAILING_RE = re.compile(r"<!--([^<>]*)-->[ \t]*$")

# A line that is exactly one HTML comment; its content may be a directive.
MD_STANDALONE_RE = re.compile(r"^<!--([^<>]*)-->$")


def trailing_carrier(line, is_md, lang):
    """The parsed directive, judged prefix, and carrier suffix, or None.

    ADR-0010: the carrier is the rightmost leader-to-line-end suffix
    after the end trim, and a malformed tail is wholly inert —
    it neither suppresses nor is stripped from the judged text.
    The returned carrier is the exact suffix the caller must also
    strip from the extracted prose, so raw and prose never diverge.
    """
    trimmed = line.rstrip(" \t")
    if is_md:
        m = MD_TRAILING_RE.search(trimmed)
        if not m:
            return None
        parsed = parse_directive(m.group(1))
        if parsed is None or parsed is MALFORMED:
            return None
        return parsed, trimmed[:m.start()].rstrip(" \t"), trimmed[m.start():]
    if lang is None or not lang.line:
        return None
    idx = trimmed.rfind(lang.line)
    if idx <= 0:
        return None  # no marker, or only the comment's own leading marker
    parsed = parse_directive(trimmed[idx + len(lang.line):])
    if parsed is None or parsed is MALFORMED:
        return None
    return parsed, trimmed[:idx].rstrip(" \t"), trimmed[idx:]


# The kinds that stop an edit.
# Everything else is advice,
# and advice that blocks costs more trust than the advice is worth.
# `wrap` left this set with the release that measured it:
# a labeled corpus put its false positives at seven in 450,
# and a kind that misfires on correct prose cannot be the one that refuses an edit.
BLOCKING_KINDS = frozenset({"fused"})

# ADR-0006: the bounded disagreement rule, carried by every judgment-layer
# surface; appended after the degraded-position note and before the
# suppression instruction, which ADR-0010 pins as the report's final text.
AGENT_JUDGMENT_NOTE = (
    "Judge a finding before rewriting: if you consider it a false positive, or "
    "the same finding survives one repair attempt, stop retrying and surface "
    "the disagreement to the user instead of rewriting correct prose again."
)

# ADR-0010: hook feedback is a judgment-layer surface and carries this verbatim.
AGENT_SUPPRESSION_NOTE = (
    "An agent never adds a suppression directive on its own authority: "
    "if you judge a finding to be a false positive, leave the text as it is "
    "and surface the disagreement to the user instead."
)

# The kind under evaluation.
# It is withheld from hook feedback entirely rather than downgraded to advice,
# because advice the model has to weigh still costs it attention.
# `--file` audits keep it, since an audit is read by a person who asked for it.
WITHHELD_KIND = "wrap"

WITHHELD_OPT_IN = "SEMLF_EXPERIMENTAL_WRAP"

# Values that read as "off" rather than as an opt-in.
DISABLED_VALUES = {"", "0", "false", "no", "off"}


def opted_into_withheld_kind():
    """Whether the caller asked to see the kind this release withholds."""
    return os.environ.get(WITHHELD_OPT_IN, "").strip().lower() not in DISABLED_VALUES


def model_visible(findings):
    """The findings a hook may put in front of the model.

    Narrower than what `check` returns, and deliberately so.
    The gate this release is measured by asks what the model is told,
    not what the checker can see.
    """
    if opted_into_withheld_kind():
        return list(findings)
    return [finding for finding in findings if _kind_of(finding) != WITHHELD_KIND]


def blocking_kinds(findings):
    """True when some finding must block the edit rather than merely advise."""
    return any(_kind_of(f) in BLOCKING_KINDS for f in findings)


def _identity(stat):
    """The four fields that must agree for a snapshot to be one file."""
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _read_snapshot(path):
    """One stable snapshot of path, or None when it cannot be trusted.

    Strict decoding: a replacement character would shift offsets while
    the mapping still claimed to be exact.
    The descriptor is stat'd before and after the read (an in-place
    change moves size or mtime), and the path is stat'd after it (an
    atomic replacement moves the inode), so bytes from a file the path
    no longer names degrade instead of being labeled exact.
    """
    try:
        with open(path, encoding="utf-8") as f:
            before = os.fstat(f.fileno())
            text = f.read()
            after = os.fstat(f.fileno())
        final = os.stat(path)
    except (OSError, UnicodeDecodeError):
        return None
    if not (_identity(before) == _identity(after) == _identity(final)):
        return None
    return text


def _locate_unique(text, needle):
    """The span of needle's only occurrence, or None.

    Overlapping repeats count as ambiguous, so the second search starts
    one code point after the first hit rather than after its end.
    """
    if not needle:
        return None
    first = text.find(needle)
    if first < 0 or text.find(needle, first + 1) >= 0:
        return None
    return {"start": first, "end": first + len(needle)}


def _looks_like_the_skill(path):
    """Whether path is a readable file whose frontmatter names this skill.

    A bare existence check, or a bare substring search, would send an
    agent to load a corrupt or unrelated file at the same path -- a
    file whose *body* happens to mention the skill's name is not the
    skill.
    Requiring the exact name line to sit inside an opened and
    closed `---` block rules that out without parsing YAML.

    Reads 1025 bytes so a closing delimiter can never be confused with
    end of file: if fewer than 1025 came back, the buffer already is
    the whole file, so a trailing `\\n---` at the end of it is a true
    close.
    If exactly 1025 came back, the file continues past the
    probe, so only a closing delimiter followed by `\\n` fully inside
    the first 1024 decoded characters counts -- the 1025th byte itself
    never enters the match, since its only job is telling truncated
    from whole.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(1025)
    except OSError:
        return False
    truncated = len(head) == 1025
    if truncated:
        head = head[:1024]
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text.startswith("---\n"):
        return False
    body = text[4:]
    close_pattern = r"\n---\n" if truncated else r"\n---(?:\n|$)"
    close = re.search(close_pattern, body)
    if not close:
        return False
    frontmatter = body[:close.start()]
    return "name: semantic-linefeeds" in frontmatter.splitlines()


def _judgment_layer_present(transport):
    """Whether hook feedback may tell the model to load a judgment-layer skill.

    Claude Code always has one: the skill ships inside the plugin that runs
    this hook.
    Codex has one only when a candidate at either location Codex resolves
    standalone skills from (ADR-0006) reads back as this skill: a
    repository `.agents/skills` directory, or `$HOME/.agents/skills` when
    `$HOME` actually resolves to something (`os.path.expanduser("~")`
    returns its input unchanged when it cannot).
    """
    if transport == "claude":
        return True
    if transport == "codex":
        candidates = [os.path.join(".agents", "skills", "semantic-linefeeds", "SKILL.md")]
        home = os.path.expanduser("~")
        if home != "~":
            candidates.append(os.path.join(home, ".agents", "skills",
                                            "semantic-linefeeds", "SKILL.md"))
        return any(_looks_like_the_skill(p) for p in candidates)
    return True


def deliver(reports, transport, note=None):
    """Write hook findings on the transport their status implies, and return the status.

    Status comes from the kinds present, and transport comes from the status.
    Blocking findings go to stderr, which both hosts show to the model.
    Everything else exits 0 and travels as host-native additional context,
    because exit-0 stderr reaches no model in either host:
    Claude Code files it under its debug log,
    and Codex reads non-blocking feedback only from JSON on stdout.

    `reports` is a sequence of (path, findings, snippet) triples rather
    than one pair, since a single Codex patch can touch several files,
    each report carries its own snippet flag per ADR-0005's span-source
    table, and the non-blocking transport is one JSON object.
    Both hosts accept the same object shape,
    so the transport does not vary by agent.
    `transport` is `"claude"` or `"codex"`;
    it decides whether the closing "load the semantic-linefeeds skill"
    sentence is included (ADR-0006):
    Claude always has the skill, Codex only when a usable copy is present.
    A finding that carries a `suggestion` (the automatic `!`/`?` class ADR-0007 restricts
    delivery to) gets its own block after the report bodies, labeled with the same line-number
    phrasing the body uses.
    A single-file delivery keeps that line-number label as-is, since the report body right above it already names the one file in play;
    once a second report is present, each label also names its file, or two findings sharing a line number across files would read as the same one.
    """
    reports = [(p, model_visible(f), s) for p, f, s in reports]
    reports = [(p, f, s) for p, f, s in reports if f]
    if not reports:
        return 0
    skill_hint = _judgment_layer_present(transport)
    body = "\n".join(format_findings(f, p, s, skill_hint=skill_hint) for p, f, s in reports)
    multi = len(reports) > 1
    for path, findings, snippet in reports:
        for finding in findings:
            if not isinstance(finding, dict) or "suggestion" not in finding:
                continue
            label = f"line {finding['line']} of your edit" if snippet else f"line {finding['line']}"
            if multi:
                label = f"{label} of {path}"
            line1, line2 = finding["suggestion"]["lines"]
            body += f"\nSuggested replacement for {label}:\n    {line1}\n    {line2}"
    if note and any(s for _, _, s in reports):
        body += "\n" + note
    body += "\n" + AGENT_JUDGMENT_NOTE
    body += "\n" + AGENT_SUPPRESSION_NOTE
    if any(blocking_kinds(f) for _, f, _ in reports):
        print(body, file=sys.stderr)
        return 2
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": body,
    }}))
    return 0


def read_payload():
    """The hook payload as an object, or None when stdin was not one.

    Parsing and shape are separate failures.
    Text that parses into a list or a number reached attribute access unguarded,
    and a post-edit hook that raises has failed closed on an edit it was only meant to inspect.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def run_hook_claude():
    payload = read_payload()
    if payload is None:
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    path = tool_input.get("file_path")
    if not isinstance(path, str):
        return 0
    if not (is_markdown(path) or lang_for_path(path) is not None):
        return 0
    if skip_path(path) or excluded(path):
        return 0
    new_string = tool_input.get("new_string")
    if isinstance(new_string, str):
        if not new_string:
            # A deletion: its zero-width boundary has no locatable text
            # without a preimage, and a guess would own text the edit
            # never touched.
            # A missed finding is the accepted cost.
            return 0
        snapshot = None if tool_input.get("replace_all") else _read_snapshot(path)
        span = _locate_unique(snapshot, new_string) if snapshot is not None else None
        if span:
            return deliver([(path, diagnose(snapshot, path, spans=[span]), False)], "claude")
        return deliver([(path, diagnose(new_string, path), True)], "claude")
    content = tool_input.get("content")
    if isinstance(content, str) and content:
        # A Write hands over the whole file: content is both the context
        # and one whole-file span (ADR-0005), so degraded ownership is
        # withheld rather than guessed.
        spans = [{"start": 0, "end": len(content)}]
        return deliver([(path, diagnose(content, path, spans=spans), False)], "claude")
    return 0


def hunks_by_file(patch):
    """Map file path -> hunks, each a list of (kind, text) lines.

    kind is "add", "ctx", or "del".
    A deleted line contributes no post-state text but keeps its position,
    because its collapse point is a changed boundary ADR-0005 requires as a zero-width span.
    Context lines carry the apply_patch space prefix when present;
    one is stripped.
    A `*** Move to:` rename re-keys the entry to the destination path.
    """
    files = {}
    current = None
    hunk = None
    for line in patch.splitlines():
        m = PATCH_FILE_RE.match(line)
        if m:
            current = m.group(1).strip()
            files.setdefault(current, [])
            hunk = None
            continue
        mv = PATCH_MOVE_RE.match(line)
        if mv and current is not None:
            files[mv.group(1).strip()] = files.pop(current)
            current = mv.group(1).strip()
            hunk = None
            continue
        if line.startswith("*** "):
            current = None
            hunk = None
            continue
        if current is None:
            continue
        if line.startswith("@@"):
            hunk = None
            continue
        if hunk is None:
            hunk = []
            files[current].append(hunk)
        if line.startswith("+"):
            hunk.append(("add", line[1:]))
        elif line.startswith("-"):
            hunk.append(("del", ""))
        else:
            hunk.append(("ctx", line[1:] if line.startswith(" ") else line))
    return {p: [h for h in hunks if h] for p, hunks in files.items()
            if any(hunks)}


def _locate_hunk(text, body):
    """The unique line-bounded occurrence of a hunk body, or None.

    A hunk is whole lines,
    so its match must start at offset 0 or after a newline and end at end-of-text or before one;
    a body embedded in a longer unchanged line is not this hunk,
    and such interior hits neither match nor make the real one ambiguous.
    """
    if not body:
        return None
    found = None
    start = 0
    while True:
        idx = text.find(body, start)
        if idx < 0:
            return found
        end = idx + len(body)
        if ((idx == 0 or text[idx - 1] == "\n")
                and (end == len(text) or text[end] == "\n")):
            if found is not None:
                return None
            found = {"start": idx, "end": end}
        start = idx + 1


def run_hook_codex():
    payload = read_payload()
    if payload is None:
        return 0
    if payload.get("tool_name") != "apply_patch":
        return 0
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, str):
        patch = tool_input
    elif isinstance(tool_input, dict):
        # "command" is the current stable contract; "input"/"patch" are
        # best-effort fallbacks for older payload shapes.
        patch = (tool_input.get("command") or tool_input.get("input")
                 or tool_input.get("patch") or "")
    else:
        return 0
    if not isinstance(patch, str):
        return 0
    reports = []
    for path, hunks in sorted(hunks_by_file(patch).items()):
        if skip_path(path) or excluded(path):
            continue
        snapshot = _read_snapshot(path)
        spans = [] if snapshot is not None else None
        for hunk in hunks if spans is not None else ():
            post = [(kind, text) for kind, text in hunk if kind != "del"]
            body = "\n".join(text for _, text in post)
            located = _locate_hunk(snapshot, body)
            if located is None:
                spans = None
                break
            starts, offset = [], 0
            for _, text in post:
                starts.append(offset)
                offset += len(text) + 1  # the joining newline
            index = 0
            for kind, text in hunk:
                if kind == "del":
                    # The deletion run collapsed here: a zero-width after-state boundary,
                    # at the start of the next post-state line.
                    # When the deletion closes the hunk,
                    # the collapse point sits after the retained terminator, never before it
                    # — a boundary at the end of the line's content would touch ownership on the retained line
                    # and over-own an unchanged finding there.
                    if index < len(post):
                        at = located["start"] + starts[index]
                    elif located["end"] < len(snapshot):
                        at = located["end"] + 1  # past the retained "\n"
                    else:
                        at = located["end"]  # true end-of-text
                    spans.append({"at": at})
                    continue
                if kind == "add":
                    spans.append({"start": located["start"] + starts[index],
                                  "end": located["start"] + starts[index] + len(text)})
                index += 1
        if spans:
            reports.append((path, diagnose(snapshot, path, spans=spans), False))
        else:
            # A run is a maximal contiguous stretch of "add" lines,
            # broken by any other entry: context, deletion, or a new hunk.
            # Joining whole hunks with a bare "\n" would glue two disjoint "+" groups in one hunk into a single paragraph,
            # fabricating a wrap finding neither run has on its own.
            runs = []
            for hunk in hunks:
                run = None
                for kind, text in hunk:
                    if kind == "add":
                        if run is None:
                            run = []
                            runs.append(run)
                        run.append(text)
                    else:
                        run = None
            added = "\n\n".join("\n".join(run) for run in runs)
            findings = diagnose(added, path) if added.strip() else []
            reports.append((path, findings, True))
    return deliver(reports, "codex", note=(
        "(line numbers are approximate positions within the added "
        "lines of your patch; locate findings by the quoted excerpts)"))


def run_sources(sources, as_json=False):
    """Check (path, text) pairs and report exactly like --file mode.

    The one rendering and exit-code loop every checking mode shares:
    run_files feeds it disk reads,
    and the semlf git modes feed it snapshot content.
    Reading and read-error policy stay with the caller,
    because only the caller knows what a missing source means there.
    Exit 1 on any fused/wrap violation; long stays advisory.
    """
    violations = 0
    reports = []
    for path, text in sources:
        findings = diagnose(text, path)
        if findings:
            violations += sum(1 for d in findings if d["kind"] != "long")
            if as_json:
                reports.append(to_schema(path, findings))
            else:
                print(format_findings(findings, path, snippet=False))
    if as_json:
        print(json.dumps(reports, indent=2))
    return 1 if violations else 0


def run_files(paths, as_json=False):
    read_errors = 0
    pairs = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                pairs.append((path, f.read()))
        except OSError as e:
            print(f"semantic-linefeeds: cannot read {path}: {e}", file=sys.stderr)
            read_errors += 1
    rc = run_sources(pairs, as_json=as_json)
    return 1 if read_errors else rc


def main(prog=None):
    ap = argparse.ArgumentParser(prog=prog or "check_linefeeds", description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--hook", nargs="?", const="claude",
                      choices=["claude", "codex"], default=None,
                      help="read a PostToolUse JSON payload on stdin and check only the "
                           "text just written; fused exits 2 with the report on stderr, "
                           "advisory-only findings exit 0 as JSON on stdout; wrap is "
                           "withheld unless SEMLF_EXPERIMENTAL_WRAP is set "
                           "(default agent: claude)")
    # Zero or more, with a trailing catch-all, so that `--file --json PATH` parses.
    # With `nargs="+"`, an option word standing where a path belongs left `--file` with
    # nothing to consume, which turned a common ordering into a usage error.
    mode.add_argument("--file", nargs="*", default=None, metavar="PATH",
                      help="check whole files and report to stdout; exit 1 on any "
                           "fused/wrap violation (long findings are advisory only)")
    ap.add_argument("paths", nargs="*", metavar="PATH", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version",
                    version=f"%(prog)s {__version__}",
                    help="print the version and exit")
    ap.add_argument("--json", action="store_true",
                    help="with --file, emit findings as JSON instead of text")
    ap.add_argument("--long-limit", type=int, default=None, metavar="N",
                    help="long-line advisory threshold in chars; 0 disables "
                         "(default: $SEMLF_LONG_LINE or 120)")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(0 if e.code == 0 else 64)
    if args.long_limit is not None:
        if args.long_limit < 0:
            print(f"{ap.prog}: --long-limit must be >= 0", file=sys.stderr)
            sys.exit(64)
        global CLI_LONG_LIMIT
        CLI_LONG_LIMIT = args.long_limit
    files = None if args.file is None else args.file + args.paths
    if args.json and files is None:
        print(f"{ap.prog}: --json requires --file", file=sys.stderr)
        sys.exit(64)
    if args.hook == "claude":
        sys.exit(run_hook_claude())
    if args.hook == "codex":
        sys.exit(run_hook_codex())
    if files:
        sys.exit(run_files(files, as_json=args.json))
    ap.print_usage(sys.stderr)
    sys.exit(64)


if __name__ == "__main__":
    main()
