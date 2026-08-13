"""Subcommand routing for the semlf CLI.

The layering this file preserves:
the CLI supplies invocation and paths, the portable core supplies analysis.
Delegating to core.main() keeps flag parsing, output,
and the exit-code contract identical to the bare core by construction.
Help and usage are the one exception:
they must present the semlf surface, not the core's internal name.
"""
import sys

import check_linefeeds as core

USAGE = """usage: semlf [--version] [--help] <mode>

modes:
  check PATH...          check whole files (alias for --file PATH...)
  --file PATH...         check whole files; exit 1 on any fused/wrap violation
  --hook [claude|codex]  run as a PostToolUse hook reading JSON on stdin
options forwarded to the core: --json, --long-limit N
"""


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
