"""Subcommand routing for the semlf CLI.

The layering this file exists to prove:
the CLI supplies *content and paths*, the portable core supplies *analysis*.
Nothing here re-implements a heuristic.
"""

import argparse
import subprocess
import sys

import check_linefeeds as core

from . import __version__


def _git(args):
    """Run a git command, returning stdout, or None when git fails."""
    try:
        p = subprocess.run(["git"] + args, capture_output=True, text=True)
    except (OSError, ValueError):
        return None
    return p.stdout if p.returncode == 0 else None


def staged_paths():
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    if out is None:
        return None
    return [p for p in out.splitlines() if p.strip()]


def index_blob(path):
    """Return the staged content of path — the index blob, never the worktree.

    Roadmap section 8.3: an unstaged edit must not supply context for a staged check.
    """
    return _git(["show", ":" + path])


def cmd_check(args):
    if args.staged:
        paths = staged_paths()
        if paths is None:
            print("semlf: not a git repository", file=sys.stderr)
            return 64
        violations = 0
        for path in paths:
            if not (core.is_markdown(path) or core.lang_for_path(path)):
                continue
            text = index_blob(path)
            if text is None:
                continue
            findings = core.check(text, path)
            if findings:
                violations += sum(1 for f in findings if f[1] != "long")
                print(core.format_findings(findings, path, snippet=False))
        return 1 if violations else 0
    if not args.paths:
        print("semlf check: give paths or --staged", file=sys.stderr)
        return 64
    return core.run_files(args.paths, as_json=args.json)


def cmd_hook(args):
    if args.agent == "codex":
        return core.run_hook_codex()
    return core.run_hook_claude()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="semlf")
    ap.add_argument("--version", action="version",
                    version="semlf " + __version__ +
                            " (core: " + core.__name__ + ")")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("check", help="check files, or the git index")
    c.add_argument("paths", nargs="*", metavar="PATH")
    c.add_argument("--staged", action="store_true",
                   help="check the staged content of changed files")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    h = sub.add_parser("hook", help="run a PostToolUse hook")
    h.add_argument("agent", nargs="?", default="claude",
                   choices=["claude", "codex"])
    h.set_defaults(fn=cmd_hook)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_usage(sys.stderr)
        return 64
    return args.fn(args)
