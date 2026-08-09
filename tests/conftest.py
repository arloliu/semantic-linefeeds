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


def run_cli(args, stdin_text=""):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        input=stdin_text, capture_output=True, text=True,
    )


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true",
                     help="rewrite extractor golden files from current output")
