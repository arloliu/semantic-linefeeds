"""SARIF and GitHub annotations as pure functions of the documents list.

The input is exactly what `--json` emits — a list of `to_schema` documents —
so one analysis pass serves every reader and no renderer ever re-analyzes.
A renderer also never exits on finding content:
what a finding means for a build is the gate's decision, not the renderer's,
which is what keeps the core's exit contract untouched by construction.
"""

import check_linefeeds as core

_LEVELS = {"fused": "error", "wrap": "warning", "long": "note"}

_RULES = {
    "fused": "two independent sentences on one line",
    "wrap": "a line that ends mid-clause with the sentence continuing on the next",
    "long": "a line over the length threshold, advisory in every reader",
}

# Every boundary the core's str.splitlines(keepends=True) recognizes
# (`line_offsets`),
# CRLF listed before its prefixes
# so a greedy consumer cannot split one boundary into two.
_NEWLINES = [
    "\r\n",
    "\n",
    "\r",
    "\x0b",
    "\x0c",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    " ",
    " ",
]

_COMMANDS = {"fused": "error", "wrap": "warning", "long": "notice"}


def sarif(documents):
    """One SARIF 2.1.0 document over the whole documents list.

    The diagnostic's `anchor` is an absolute code-point span over the file,
    so it is never copied into a column:
    the region is the diagnostic's own line, whole,
    column 1 through the anchor's length plus one.
    """
    results = []
    for document in documents:
        for diagnostic in document["diagnostics"]:
            anchor = diagnostic.get("anchor") or {}
            length = max(anchor.get("end", 0) - anchor.get("start", 0), 0)
            results.append(
                {
                    "ruleId": diagnostic["kind"],
                    "level": _LEVELS[diagnostic["kind"]],
                    "message": {"text": diagnostic["message"]},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": document["path"]},
                                "region": {
                                    "startLine": diagnostic["line"],
                                    "endLine": diagnostic["line"],
                                    "startColumn": 1,
                                    "endColumn": length + 1,
                                },
                            }
                        }
                    ],
                }
            )
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "semlf",
                        "version": core.__version__,
                        "informationUri": "https://github.com/arloliu/semantic-linefeeds",
                        "rules": [
                            {
                                "id": kind,
                                "shortDescription": {"text": _RULES[kind]},
                            }
                            for kind in ("fused", "wrap", "long")
                        ],
                    }
                },
                "columnKind": "unicodeCodePoints",
                "newlineSequences": _NEWLINES,
                "results": results,
            }
        ],
    }


def _escape_message(text):
    """Workflow-command message data: %, CR, LF, in that order."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text):
    """Property values additionally escape : and , (actions/toolkit escapeProperty)."""
    return _escape_message(text).replace(":", "%3A").replace(",", "%2C")


def github_annotations(documents):
    """One workflow command per diagnostic, locations pinned to the schema.

    `file` is the document's path,
    `line` and `endLine` are the diagnostic's one-based line,
    `title` names the kind,
    and the message is the diagnostic's own.
    """
    for document in documents:
        for diagnostic in document["diagnostics"]:
            command = _COMMANDS[diagnostic["kind"]]
            properties = ",".join(
                (
                    f"file={_escape_property(document['path'])}",
                    f"line={diagnostic['line']}",
                    f"endLine={diagnostic['line']}",
                    f"title={_escape_property('semlf: ' + diagnostic['kind'])}",
                )
            )
            yield f"::{command} {properties}::{_escape_message(diagnostic['message'])}"
