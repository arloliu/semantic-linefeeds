import os
import re
import shutil
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
ALLOWED_SUFFIXES = {".go", ".md", ".java", ".ts", ".rs", ".py", ".sh", ".c",
                    ".kt", ".vb", ".sql", ".lua", ".rb", ".pl", ".ps1", ".r",
                    ".hs", ".ex", ".zig"}

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


def run_cli(args, stdin_text="", env=None):
    """Run the checker as a subprocess, optionally adding environment variables."""
    import os

    environment = None
    if env:
        environment = dict(os.environ)
        environment.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        input=stdin_text, capture_output=True, text=True, env=environment,
    )


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true",
                     help="rewrite extractor golden files from current output")


HAS_GIT = shutil.which("git") is not None

_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
        "-c", "commit.gpgsign=false"]


def git(*args, cwd):
    """Run git deterministically for repo-building tests."""
    subprocess.run(_GIT + list(args), cwd=str(cwd), check=True,
                   capture_output=True)


def git_out(*args, cwd):
    """Captured stdout of a deterministic git command, decoded and stripped."""
    proc = subprocess.run(_GIT + list(args), cwd=str(cwd), check=True,
                          capture_output=True)
    return proc.stdout.decode("utf-8").strip()


def isolate_git_env(monkeypatch):
    """Pin git subprocesses against host config, env injection, and selectors.

    Config files are nulled, GIT_CONFIG_COUNT injection is zeroed,
    the init template is pointed at a nonexistent directory so no host
    hook or template file reaches a test repository,
    and every repository-selector variable is cleared.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "0")
    monkeypatch.setenv("GIT_TEMPLATE_DIR",
                       os.path.join(os.sep, "semlf-no-template"))
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
                "GIT_CEILING_DIRECTORIES", "GIT_CONFIG_PARAMETERS"):
        monkeypatch.delenv(var, raising=False)
