"""Subcommand routing for the semlf CLI.

The layering this file preserves:
the CLI supplies invocation, selection, and paths;
the portable core supplies analysis, rendering, and exit codes.
File checking delegates to core.main(), which keeps its flag parsing
and exit-code contract identical to the bare core by construction.
The git modes parse their own three flags —
they are CLI surface, not core surface —
and hand every selected snapshot to core.run_sources,
so rendering and exit codes still come from the one shared loop.
Help and usage are the one exception:
they must present the semlf surface, not the core's internal name.
"""

import argparse
import json
import sys

import check_linefeeds as core

from semlf import providers

USAGE = """usage: semlf [--version] [--help] <mode>

modes:
  check PATH...          check whole files (alias for --file PATH...)
  --file PATH...         check whole files; exit 1 on any fused/wrap violation
  --staged               check staged content (the index, not the worktree)
  --diff                 check unstaged changes against the index
  --changed              check all changes against HEAD
  --base REF             check files changed since merge-base(REF, HEAD),
                         reporting only diagnostics the changed lines own
  --all                  check every tracked file under the configured excludes
  --hook [claude|codex]  run as a PostToolUse hook reading JSON on stdin
  reflow [REF]           verify the worktree differs from REF (default HEAD)
                         only in where its prose breaks; exit 1 on any other change
  render sarif|github [DOCS.json|-]
                         render a --json documents list (file or stdin) as SARIF
                         or GitHub annotations; never analyzes, never gates
  doctor                 replay a synthetic payload end to end and report evidence
  install [TARGET...]    detect agents, list every path the plan writes, ask y/N;
                         naming a target (codex, opencode, agentsmd PATH) applies it immediately
  status [agentsmd PATH] report every discoverable or recorded artifact's state
  uninstall TARGET...    preflight-then-apply removal of a target's artifacts
options forwarded to the core: --json, --long-limit N (git modes accept both)
options: install takes --yes, --dry-run, --force; uninstall takes --dry-run, --force
"""

GIT_MODE_FLAGS = ("--staged", "--diff", "--changed", "--base", "--all")


def _git_mode(argv):
    """One git snapshot, checked through the core's shared runner."""
    ap = argparse.ArgumentParser(prog="semlf", add_help=False, allow_abbrev=False)
    mode = ap.add_mutually_exclusive_group(required=True)
    for flag in ("--staged", "--diff", "--changed", "--all"):
        mode.add_argument(flag, action="store_true")
    mode.add_argument("--base", metavar="REF")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--long-limit", type=int, default=None, metavar="N")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 64
    if args.long_limit is not None and args.long_limit < 0:
        print("semlf: --long-limit must be >= 0", file=sys.stderr)
        return 64
    if args.base:

        def provider(root, ref=args.base):
            return providers.base_sources(root, ref)
    else:
        provider = (
            providers.staged_sources
            if args.staged
            else providers.diff_sources
            if args.diff
            else providers.all_sources
            if args.all
            else providers.changed_sources
        )
    saved_limit = core.CLI_LONG_LIMIT
    if args.long_limit is not None:
        core.CLI_LONG_LIMIT = args.long_limit
    try:
        sources = provider(providers.repo_root())
        return core.run_sources(sources, as_json=args.json)
    except providers.SourceError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        core.CLI_LONG_LIMIT = saved_limit


def _render(argv):
    """Render a documents list somebody already analyzed.

    Exit 0 however many findings the documents hold —
    what a finding means for a build is the gate's decision —
    and nonzero only for arguments (64) or unusable input (1).
    """
    from semlf import render

    if len(argv) not in (1, 2) or argv[0] not in ("sarif", "github"):
        print("usage: semlf render sarif|github [DOCUMENTS.json|-]", file=sys.stderr)
        return 64
    source = argv[1] if len(argv) == 2 else "-"
    try:
        raw = (
            sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()
        )
    except OSError as exc:
        print(f"semlf render: cannot read {source}: {exc}", file=sys.stderr)
        return 1
    try:
        documents = json.loads(raw)
        if not isinstance(documents, list) or not all(
            isinstance(one, dict) and "diagnostics" in one for one in documents
        ):
            raise ValueError("not a documents list")
        if argv[0] == "sarif":
            print(json.dumps(render.sarif(documents), indent=2))
        else:
            for line in render.github_annotations(documents):
                print(line)
    except (ValueError, KeyError, TypeError) as exc:
        print(
            f"semlf render: {source} is not what --json emits: {exc}", file=sys.stderr
        )
        return 1
    return 0


def _reflow(argv):
    """Verify a change is a pure prose reflow, file by file.

    The verdict a reviewer needs is not "how big is the diff"
    but "did any word, code line, or paragraph actually change".
    The core answers that per file pair; this supplies the pairs and the exit code.
    """
    if len(argv) > 1 or argv[:1] and argv[0].startswith("-"):
        print("usage: semlf reflow [REF]", file=sys.stderr)
        return 64
    ref = argv[0] if argv else "HEAD"
    try:
        pairs = providers.reflow_pairs(providers.repo_root(), ref)
    except providers.SourceError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not pairs:
        print(f"nothing differs from {ref}")
        return 0
    clean = True
    moved = 0
    for rel, display, old_text, new_text in pairs:
        if old_text is None or new_text is None:
            what = "added" if old_text is None else "deleted or unreadable"
            print(f"CHANGED  {display}: {what}")
            clean = False
            continue
        got = core.prose_reflow(old_text, new_text, rel)
        if got["reflow"]:
            print(f"reflow   {display}: {got['moved']} break(s) moved")
            moved += got["moved"]
        else:
            print(f"CHANGED  {display}: {got['reason']}")
            clean = False
    if clean:
        print(f"pure reflow against {ref}: {moved} break(s) moved, no words changed")
        return 0
    print(f"not a pure reflow against {ref}", file=sys.stderr)
    return 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--version"]:
        print(f"semlf {core.__version__}")
        return 0
    if argv[:1] in (["--help"], ["-h"]) or argv[:2] in (
        ["check", "--help"],
        ["check", "-h"],
    ):
        print(USAGE, end="")
        return 0
    if argv == ["check"]:
        print("semlf check: give at least one PATH", file=sys.stderr)
        print(USAGE, end="", file=sys.stderr)
        return 64
    if argv and argv[0] == "check":
        argv = ["--file"] + argv[1:]
    if argv[:1] == ["render"]:
        return _render(argv[1:])
    if argv[:1] == ["reflow"]:
        return _reflow(argv[1:])
    if argv[:1] == ["doctor"]:
        from semlf import doctor

        return doctor.run(argv[1:])
    if argv[:1] and argv[0] in ("install", "status", "uninstall"):
        if argv[1:2] and argv[1] in ("--help", "-h"):
            print(USAGE, end="")
            return 0
        from semlf import lifecycle

        return lifecycle.run(argv[0], argv[1:])
    head = argv[: argv.index("--")] if "--" in argv else argv
    if any(flag in head for flag in GIT_MODE_FLAGS):
        return _git_mode(argv)
    saved_argv = sys.argv
    saved_limit = core.CLI_LONG_LIMIT
    sys.argv = ["semlf"] + argv
    try:
        core.main(prog="semlf")
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    finally:
        sys.argv = saved_argv
        core.CLI_LONG_LIMIT = saved_limit
