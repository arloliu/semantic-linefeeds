"""The payload registry: one declarative table for every packaging and lifecycle consumer (the redesign ADR).

Each row names a logical id (also its provenance record name where one exists),
the canonical repository path, the embedded member path in both wheel and zipapp,
the owning install target, and its apply-order position.
The wheel build hook, the zipapp builder, the installer, and the identity checks all import this table;
no consumer invents a second mapping.
Members carry canonical bytes; transforms run on the installing machine,
and every transform fails loud when its match count is wrong,
so a canonical-source edit can never silently disable a rewrite.
"""

import json
import zipfile
from collections import namedtuple
from pathlib import Path

from semlf import manifest

PayloadRow = namedtuple(
    "PayloadRow",
    [
        "id",
        "source",
        "member",
        "owner",
        "order",
        "recorded",
        "identity",
        "dest",
        "render",
    ],
)

CHECKER_NAME = "check_linefeeds.py"


def _in(base, name):
    """base / name, or None when the base itself does not resolve."""
    return None if base is None else base / name


def _data_path(name):
    return _in(manifest.semlf_data_dir(), name)


# The row lambdas reference render functions defined further down;
# module-level names resolve at call time, so the forward references are safe,
# and the table stays one readable block.
ROWS = (
    PayloadRow(
        "checker",
        "scripts/check_linefeeds.py",
        "semlf/payloads/checker",
        "codex",
        0,
        True,
        True,
        lambda: _data_path(CHECKER_NAME),
        lambda data_dir: payload_bytes("checker"),
    ),
    PayloadRow(
        "readme",
        "README.md",
        "semlf/payloads/readme",
        "codex",
        1,
        True,
        True,
        lambda: _data_path("README.md"),
        lambda data_dir: payload_bytes("readme"),
    ),
    PayloadRow(
        "codex-hook-template",
        "adapters/codex/hooks.json",
        "semlf/payloads/codex-hook-template",
        "codex",
        2,
        False,
        False,
        lambda: _in(manifest.codex_home(), "hooks.json"),
        None,
    ),
    PayloadRow(
        "codex-skill",
        "skills/semantic-linefeeds/SKILL.md",
        "semlf/payloads/codex-skill",
        "codex",
        3,
        True,
        False,
        manifest.codex_skill_dest,
        lambda data_dir: render_codex_skill(data_dir).encode("utf-8"),
    ),
    PayloadRow(
        "opencode-plugin",
        "adapters/opencode/semantic-linefeeds.ts",
        "semlf/payloads/opencode-plugin",
        "opencode",
        4,
        True,
        False,
        lambda: _in(manifest.opencode_plugins_dir(), "semantic-linefeeds.ts"),
        lambda data_dir: payload_bytes("opencode-plugin"),
    ),
    PayloadRow(
        "opencode-checker",
        "scripts/check_linefeeds.py",
        "semlf/payloads/opencode-checker",
        "opencode",
        5,
        True,
        True,
        lambda: _in(manifest.opencode_plugins_dir(), CHECKER_NAME),
        lambda data_dir: payload_bytes("opencode-checker"),
    ),
    PayloadRow(
        "agentsmd-snippet",
        "adapters/agentsmd/SNIPPET.md",
        "semlf/payloads/agentsmd-snippet",
        "agentsmd",
        6,
        False,
        False,
        None,
        None,
    ),
)

BY_ID = {row.id: row for row in ROWS}


class TransformError(ValueError):
    """A registry transform's match count came out wrong.

    Raised instead of rendering silently:
    a canonical-source edit that breaks a rewrite must break the install,
    never ship an artifact with the rewrite quietly skipped.
    """


def _replace_exactly_once(text, old, new, what):
    count = text.count(old)
    if count != 1:
        raise TransformError(f"{what}: expected exactly one match, found {count}")
    return text.replace(old, new)


def _repo_root():
    """The enclosing checkout's root, or None when not running from one."""
    root = Path(__file__).resolve().parents[2]
    if (root / "scripts" / CHECKER_NAME).is_file():
        return root
    return None


def payload_bytes(row_id):
    """The canonical bytes for one row, wherever this artifact came from.

    Three sources, tried in order:
    a staged payloads directory beside this module (a wheel install),
    the enclosing zipapp archive (a pyz install),
    and the checkout's canonical file (the development tree, where nothing packaging-only is ever committed).
    """
    row = BY_ID[row_id]
    here = Path(__file__).resolve().parent
    staged = here / "payloads" / row.id
    if staged.is_file():
        return staged.read_bytes()
    archive = here.parent
    if archive.is_file() and zipfile.is_zipfile(str(archive)):
        with zipfile.ZipFile(str(archive)) as z:
            return z.read(row.member)
    root = _repo_root()
    if root is not None:
        return (root / row.source).read_bytes()
    raise FileNotFoundError(f"payload {row_id!r} is neither embedded nor in a checkout")


def stage_payloads(build_root, repo=None):
    """Place every registry payload at its member path under build_root.

    The one shared staging step:
    the wheel's build hook and the zipapp builder both call it,
    and it writes into a build tree only — never into the repository.
    With repo given, bytes come from that checkout's canonical files;
    without it, from payload_bytes, so a wheel-installed artifact can stage a zipapp-shaped tree too.
    """
    build_root = Path(build_root)
    for row in ROWS:
        if repo is not None:
            data = (Path(repo) / row.source).read_bytes()
        else:
            data = payload_bytes(row.id)
        dest = build_root / Path(*row.member.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


# The three exact literal edits the installed codex skill needs:
# the fenced command line points at the neutral checker path,
# the CLAUDE_PLUGIN_ROOT fallback sentence is removed,
# and the relative suppression-section link is rewritten to the neutral README path,
# so it resolves on air-gapped machines too.
SKILL_COMMAND_OLD = (
    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_linefeeds.py" --file <files>'
)
SKILL_FALLBACK_LINE = (
    "(If `CLAUDE_PLUGIN_ROOT` is unset, the script is at "
    "`../../scripts/check_linefeeds.py` relative to this SKILL.md.)\n\n"
)
SKILL_README_LINK_OLD = "../../README.md"


def render_codex_skill(data_dir):
    """The installed skill body, pinned to the neutral root."""
    if data_dir is None:
        raise ValueError("data_dir cannot be None: no data root resolves here")
    data_dir = Path(data_dir)
    text = payload_bytes("codex-skill").decode("utf-8")
    checker = data_dir / CHECKER_NAME
    text = _replace_exactly_once(
        text,
        SKILL_COMMAND_OLD,
        f'python3 "{checker}" --file <files>',
        "codex-skill command",
    )
    text = _replace_exactly_once(
        text, SKILL_FALLBACK_LINE, "", "codex-skill fallback line"
    )
    return _replace_exactly_once(
        text,
        SKILL_README_LINK_OLD,
        str(data_dir / "README.md"),
        "codex-skill readme link",
    )


def render_codex_hook_entry(data_dir):
    """The one PostToolUse entry the installer merges."""
    if data_dir is None:
        raise ValueError("data_dir cannot be None: no data root resolves here")
    data_dir = Path(data_dir)
    text = payload_bytes("codex-hook-template").decode("utf-8")
    checker = data_dir / CHECKER_NAME
    text = _replace_exactly_once(
        text, "__CHECKER__", str(checker), "codex hook template"
    )
    return json.loads(text)["hooks"]["PostToolUse"][0]
