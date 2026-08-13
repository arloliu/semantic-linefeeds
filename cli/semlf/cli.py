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
  --hook [claude|codex]  run as a PostToolUse hook reading JSON on stdin
options forwarded to the core: --json, --long-limit N (git modes accept both)
"""

GIT_MODE_FLAGS = ("--staged", "--diff", "--changed")


def _git_mode(argv):
    """One git snapshot, checked through the core's shared runner."""
    ap = argparse.ArgumentParser(prog="semlf", add_help=False,
                                 allow_abbrev=False)
    mode = ap.add_mutually_exclusive_group()
    for flag in GIT_MODE_FLAGS:
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--long-limit", type=int, default=None, metavar="N")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 64
    if args.long_limit is not None and args.long_limit < 0:
        print("semlf: --long-limit must be >= 0", file=sys.stderr)
        return 64
    provider = (providers.staged_sources if args.staged
                else providers.diff_sources if args.diff
                else providers.changed_sources)
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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--version"]:
        print(f"semlf {core.__version__}")
        return 0
    if argv[:1] in (["--help"], ["-h"]) or argv[:2] in (["check", "--help"], ["check", "-h"]):
        print(USAGE, end="")
        return 0
    if argv == ["check"]:
        print("semlf check: give at least one PATH", file=sys.stderr)
        print(USAGE, end="", file=sys.stderr)
        return 64
    if argv and argv[0] == "check":
        argv = ["--file"] + argv[1:]
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
