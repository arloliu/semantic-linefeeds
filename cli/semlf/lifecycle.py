"""Shared lifecycle operations behind both doors (the redesign ADR).

`semlf install` and `scripts/install.py` are thin parsers over the operations here,
so the two doors produce byte-identical artifacts everywhere.
The engine is request-wide preflight then ordered apply:
every artifact of the whole request is classified read-only first,
any refusal aborts the run before the first write,
apply follows the registry's order,
provenance is recorded immediately after each artifact's publication,
and the published-but-not-recorded half-state is reported by name.
Rollback is deliberately not offered; a rerun converges.
Concurrent lifecycle commands stay out of scope (ADR-0014's boundary).
"""
import os
import re
import shutil
import stat
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

from semlf import classify, manifest, registry

Planned = namedtuple("Planned",
                     ["label", "name", "dest", "verdict", "do", "done"])
Planned.__new__.__defaults__ = (None,)
# label is the DISCLOSURE line (plans, prompts, dry runs);
# done, when set, is the COMPLETION line apply_plan prints instead —
# a leg whose pinned outputs differ between "would install" and
# "installed" carries both, and a leg with one voice sets only label.

_VERSION_RE = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


def artifact_version():
    """The version of this artifact's own embedded checker payload.

    Read textually so nothing is imported;
    on the checkout door this is the canonical core file,
    so both doors agree by construction.
    """
    text = registry.payload_bytes("checker").decode("utf-8")
    match = _VERSION_RE.search(text)
    return match.group(1) if match else "unknown"


def payload_destinations():
    """Each recorded single-file artifact's destination, or None entries.

    Derived from the registry rows — never a hand-maintained mapping.
    """
    return {row.id: row.dest() for row in registry.ROWS if row.recorded}


def rendered_bytes(name):
    """The exact bytes name's transform produces on this machine.

    Callers refuse a None destination before rendering,
    and every row whose rendering needs the data root has a destination
    that resolves exactly when the data root does,
    so the ValueError the codex-skill renderer raises on a None data root marks a caller bug, not a user-facing path.
    """
    return registry.BY_ID[name].render(manifest.semlf_data_dir())


# --- publication primitives -------------------------------------------------
# publish_exclusive and exclusive_backup move here verbatim from scripts/install.py (_publish_new, _exclusive_backup), docstrings included;
# install.py imports them back so the cli verb keeps its exact behavior.


def publish_bytes(dest, data):
    """Atomic complete-file publication: same-directory temp, os.replace."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)
    except BaseException:
        os.unlink(tmp)
        raise


def publish_exclusive(staged, dest):
    """Exclusively publish staged at dest; False when dest already appeared.

    os.link fails with FileExistsError when dest exists,
    so a file that appeared after classification is never replaced unclassified.
    The staged file is always consumed.
    """
    try:
        os.link(staged, dest)
    except FileExistsError:
        return False
    finally:
        os.unlink(staged)
    return True


def exclusive_backup(src, bak, data):
    """Write data — the already-guarded classification snapshot — to bak.

    data, never a fresh read of src, is the point:
    the caller took src's bytes through the no-follow snapshot primitive once, to classify it,
    and the backup must preserve exactly what was classified, not whatever src holds by the time this runs.
    O_EXCL is the other half: the backup slot is claimed atomically,
    so a concurrent double --force cannot overwrite the only copy of a hand-patched artifact,
    and a pre-existing symlink at bak is refused, never followed.
    copystat still reads src's own metadata (permissions, timestamps) — that is a stat call, not a content read,
    and src is already proven a regular file by the caller before this runs.
    The cleanup covers every step including copystat:
    a failure at any point releases the slot,
    so a retry never finds it occupied by a half-made backup.
    """
    fd = os.open(str(bak), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        shutil.copystat(src, bak)
    except BaseException:
        os.unlink(bak)
        raise


def _describe(name, dest, verdict):
    if verdict.action == "write":
        return f"{name}: install {dest}"
    if verdict.action == "adopt":
        return f"{name}: up to date ({dest})"
    if verdict.action == "backup-replace":
        return f"{name}: back up and replace {dest} ({verdict.state})"
    return f"{name}: replace {dest} ({verdict.state})"


def plan_file(name, force, snapshot, destinations, planned, refusals):
    """Classify one registry single-file artifact into the plan."""
    dest = destinations[name]
    if dest is None:
        refusals.append(f"refusing to install {name}: cannot determine "
                        "a home directory to install it under.")
        return
    try:
        rendered = rendered_bytes(name)
    except registry.TransformError as exc:
        refusals.append(f"refusing to install {name}: cannot render "
                        f"this artifact's payload ({exc}).")
        return
    verdict = classify.classify_artifact(snapshot.get(name), dest,
                                         rendered, artifact_version(),
                                         force)
    if verdict.action == "refuse":
        refusals.append(verdict.detail)
        return
    record_trouble = manifest.record_preflight(name)
    if record_trouble is not None:
        refusals.append(f"refusing to install {name}: {record_trouble}")
        return

    def _do(name=name, dest=dest, rendered=rendered, verdict=verdict):
        return apply_file(name, dest, rendered, verdict)

    planned.append(Planned(_describe(name, dest, verdict), name, dest,
                           verdict, _do))


def apply_file(name, dest, rendered, verdict):
    """Publish one classified artifact and record it.

    Returns None on success, or the published-but-not-recorded half-state note when the record write failed after publication —
    the destination is correct, and a rerun adopts the missing record.
    """
    if verdict.action == "adopt":
        try:
            manifest.record(name, dest, artifact_version(),
                            manifest.sha256_bytes(rendered))
        except OSError as exc:
            return (f"{name}: {dest} is already correct, but its "
                    f"provenance could not be recorded: {exc}; "
                    "a re-run records it")
        return None
    if verdict.action == "backup-replace":
        bak = dest.with_name(dest.name + ".bak")
        exclusive_backup(dest, bak, verdict.snapshot)
        try:
            publish_bytes(dest, rendered)
        except BaseException:
            # This attempt's backup must not poison the slot:
            # the destination is unchanged (publication failed before its os.replace),
            # so removing the backup keeps the rerun convergent instead of refusing on an occupied slot.
            os.unlink(bak)
            raise
    elif verdict.action == "write":
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, staged_name = tempfile.mkstemp(dir=str(dest.parent),
                                           prefix=dest.name)
        with os.fdopen(fd, "wb") as fh:
            fh.write(rendered)
        if not publish_exclusive(Path(staged_name), dest):
            raise OSError(f"{dest} appeared after classification; "
                          "re-run so it can be classified")
    else:
        publish_bytes(dest, rendered)
    try:
        manifest.record(name, dest, artifact_version(),
                        manifest.sha256_bytes(rendered))
    except OSError as exc:
        return (f"{name}: published {dest} but could not record its "
                f"provenance: {exc}; a re-run records it")
    return None


def apply_plan(planned):
    """Ordered apply with per-artifact reporting; 0 clean, 1 otherwise."""
    had_error = False
    completed = []
    for i, item in enumerate(planned):
        if item.do is None:
            print(item.label)
            continue
        try:
            note = item.do()
        except OSError as exc:
            remaining = [p.label for p in planned[i + 1:]
                         if p.do is not None]
            print(f"error while applying {item.label}: {exc}",
                  file=sys.stderr)
            print("applied: "
                  + (", ".join(completed) if completed else "(nothing)"),
                  file=sys.stderr)
            print("not applied: " + ", ".join([item.label] + remaining),
                  file=sys.stderr)
            print("a re-run converges: completed artifacts no-op, "
                  "incomplete ones are attempted again.", file=sys.stderr)
            return 1
        if note:
            print(note, file=sys.stderr)
            had_error = True
        else:
            print(item.done or item.label)
        completed.append(item.label)
    return 1 if had_error else 0


def describe_plan(planned, refusals, prefix=""):
    """The read-only report every disclosure path shares.

    The dry run passes prefix="[dry-run] "
    so scripts keep a stable marker to grep for;
    the consent prompt and the refusal report print the same lines bare.
    A refusing request reports every artifact's verdict, not only the refusals —
    the admissible legs are part of the disclosure.
    """
    for item in planned:
        print(prefix + item.label)
    for refusal in refusals:
        print(f"{prefix}would refuse: {refusal}")


# --- shared-file artifacts ---------------------------------------------------
# The codex hook and the agentsmd snippet each own a shared file this kit does not control end to end:
# structural admission over hooks.json's PostToolUse entries,
# and sentinel-block admission over a user-named Markdown file.
# Both keep their own preflight-then-apply plan, folded into the same
# `planned`/`refusals` lists every other artifact uses.


SENTINEL_OPEN = "<!-- semantic-linefeeds -->"
SENTINEL_CLOSE = "<!-- /semantic-linefeeds -->"

TRUST_NOTE = ("note: Codex hashes unmanaged hooks; on your next "
              "interactive codex run it will ask you to trust this "
              "hook — accept it once.")


def bak_sibling_ok(path):
    """Whether path's .bak sibling is absent or a plain regular file."""
    bak = path.with_name(path.name + ".bak")
    try:
        return (not os.path.lexists(bak)
                or stat.S_ISREG(os.lstat(bak).st_mode))
    except OSError:
        return False


def publish_shared(path, text):
    """atomic_write for a shared merged file (hooks.json, AGENTS.md).

    Ported from install.py's atomic_write with semantics unchanged:
    an existing regular file is first copied to <name>.bak — last-run-wins,
    because the next run re-merges the shared file, so the backup is never the only copy of anything —
    and a non-regular object in the slot raises OSError instead of being written through.
    Publication is the same-directory temp file and os.replace.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_name(path.name + ".bak")
        try:
            bak_mode = os.lstat(bak).st_mode
        except FileNotFoundError:
            bak_mode = None
        if bak_mode is not None and not stat.S_ISREG(bak_mode):
            raise OSError(f"backup slot {bak} exists and is not a "
                          "regular file; move it aside and re-run")
        shutil.copy2(path, bak)
    publish_bytes(path, text.encode("utf-8"))


def plan_codex_hook(planned, refusals):
    """Plan the PostToolUse merge into $CODEX_HOME/hooks.json.

    Structural admission, no provenance record:
    ownership is parse_managed_codex_hook over the shared file, never per-file bytes,
    and foreign entries are preserved exactly.
    """
    import json
    home = manifest.codex_home()
    data_dir = manifest.semlf_data_dir()
    if home is None or data_dir is None:
        refusals.append("refusing to install the codex hook: cannot "
                        "determine a home directory to install it under.")
        return
    try:
        entry = registry.render_codex_hook_entry(data_dir)
    except registry.TransformError as exc:
        refusals.append(f"refusing to install the codex hook: cannot "
                        f"render this artifact's payload ({exc}).")
        return
    command = entry["hooks"][0]["command"]
    path = home / "hooks.json"
    if not os.path.lexists(path):
        data = {"hooks": {"PostToolUse": [entry]}}
        label = f"codex hook: create {path}"
    else:
        data = manifest.read_state_json(path)
        if data is None or not isinstance(data, dict):
            refusals.append(f"refusing to touch {path}: cannot read or "
                            "parse it; merge the entry from the codex "
                            "adapter template by hand.")
            return
        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            refusals.append(f"refusing to touch {path}: cannot parse "
                            "it; repair it by hand.")
            return
        post = hooks.setdefault("PostToolUse", [])
        if not isinstance(post, list):
            refusals.append(f"refusing to touch {path}: cannot parse "
                            "it; repair it by hand.")
            return
        # Guard every nested level before iterating:
        # a parseable but hostile shape ({"hooks": 7}, a non-dict block) must plan around the garbage,
        # never raise TypeError mid-preflight.
        ours = [h for block in post if isinstance(block, dict)
                and isinstance(block.get("hooks"), list)
                for h in block["hooks"]
                if isinstance(h, dict)
                and manifest.parse_managed_codex_hook(
                    block.get("matcher"), h) is not None]
        if ours and all(h["command"] == command for h in ours):
            # The no-op is decided BEFORE backup-slot admission:
            # an up-to-date hook writes nothing, so a hostile unused
            # .bak must not turn clean idempotence into a refusal.
            planned.append(Planned(
                f"codex hook: up to date ({path})",
                "codex-hook", path, None, None))
            return
        if not bak_sibling_ok(path):
            bak = path.with_name(path.name + ".bak")
            refusals.append(f"refusing to touch {path}: its backup slot "
                            f"{bak} exists and is not a regular file; "
                            "move it aside and re-run.")
            return
        if ours:
            for h in ours:
                h["command"] = command
            label = f"codex hook: update the checker path in {path}"
        else:
            post.append(entry)
            label = f"codex hook: append the PostToolUse entry to {path}"
    text = json.dumps(data, indent=2) + "\n"

    def _do(path=path, text=text):
        publish_shared(path, text)
        print(TRUST_NOTE)
        return None

    planned.append(Planned(label, "codex-hook", path, None, _do))


def agents_block():
    body = registry.payload_bytes("agentsmd-snippet").decode("utf-8")
    return f"{SENTINEL_OPEN}\n{body.rstrip()}\n{SENTINEL_CLOSE}\n"


def _semlf_note():
    if shutil.which("semlf") is None:
        print("note: semlf is not on PATH; the snippet's check "
              "command needs it. install it with `uv tool install "
              "semlf` (or `pipx install semlf`).")


def plan_agentsmd(target, planned, refusals):
    """Plan the sentinel-block splice into the user-named file.

    Sentinel admission in a user-owned file:
    force never overrides a refusal here,
    and every malformed-sentinel shape is a repair-by-hand refusal, exactly as before.
    """
    target = Path(target)
    block = agents_block()
    if os.path.lexists(target):
        data = manifest.read_regular_bytes(target, manifest.CLASSIFY_LIMIT)
        if data is None:
            refusals.append(f"refusing to touch {target}: it exists but "
                            "is not a readable regular file.")
            return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            refusals.append(f"refusing to touch {target}: cannot decode "
                            "it as UTF-8; repair it by hand.")
            return
        has_open = SENTINEL_OPEN in text
        has_close = SENTINEL_CLOSE in text
        if has_open != has_close:
            refusals.append(f"refusing to touch {target}: found one "
                            "sentinel marker without its pair; repair "
                            "the block by hand.")
            return
        if has_open and (text.count(SENTINEL_OPEN) != 1
                         or text.count(SENTINEL_CLOSE) != 1
                         or text.index(SENTINEL_OPEN) > text.index(SENTINEL_CLOSE)):
            refusals.append(f"refusing to touch {target}: sentinel "
                            "markers are out of order or repeated; "
                            "repair the block by hand.")
            return
        if has_open:
            pre = text.split(SENTINEL_OPEN)[0]
            post_raw = text.split(SENTINEL_CLOSE, 1)[1]
            post = post_raw.lstrip("\n")
            if post:
                post = "\n" + post
            new = pre + block + post
        else:
            new = text.rstrip("\n") + "\n\n" + block
        if new == text:
            # The up-to-date leg has no `do` closure to defer through,
            # so it ends by printing the same advisory note the write leg's closure prints,
            # exactly as install_agentsmd did inline before this planner existed.
            _semlf_note()
            planned.append(Planned(
                f"agentsmd: already up to date ({target})",
                "agentsmd", target, None, None))
            return
    else:
        new = block

    def _do(target=target, new=new):
        publish_shared(target, new)
        _semlf_note()
        return None

    planned.append(Planned(f"agentsmd: wrote the snippet block to {target}",
                           "agentsmd", target, None, _do))


# --- the `semlf install` command surface --------------------------------


def detect_agents():
    """[(agent, evidence)] for every agent this machine shows signs of.

    Detection is a presence probe, never an execution:
    a binary on PATH or the agent's own directory existing is evidence enough to offer an install,
    and printing the evidence keeps the decision inspectable.
    """
    found = []
    if shutil.which("codex"):
        found.append(("codex", "`codex` on PATH"))
    else:
        home = manifest.codex_home()
        if home is not None and home.is_dir():
            found.append(("codex", f"{home} exists"))
    if shutil.which("opencode"):
        found.append(("opencode", "`opencode` on PATH"))
    else:
        d = manifest.opencode_plugins_dir()
        if d is not None and d.parent.is_dir():
            found.append(("opencode", f"{d.parent} exists"))
    return found


def _parse_targets(argv, verb, allowed_flags):
    """(ordered targets, agentsmd_path, flags) or None after a usage error."""
    targets = []
    agentsmd_path = None
    flags = {"yes": False, "dry_run": False, "force": False}
    by_flag = {"--yes": "yes", "--dry-run": "dry_run", "--force": "force"}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in by_flag and by_flag[arg] in allowed_flags:
            flags[by_flag[arg]] = True
        elif arg in ("codex", "opencode"):
            if arg not in targets:
                targets.append(arg)
        elif arg == "agentsmd":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                print(f"semlf {verb}: agentsmd requires an explicit "
                      "path; refusing to default one.", file=sys.stderr)
                return None
            i += 1
            agentsmd_path = Path(argv[i])
        else:
            print(f"semlf {verb}: unknown target or flag {arg!r}",
                  file=sys.stderr)
            return None
        i += 1
    return targets, agentsmd_path, flags


def plan_install(targets, agentsmd_path, force):
    """The whole request's plan, walked in the registry's own order.

    The apply order comes from the rows' order field —
    the neutral checker and readme first, then each integration's own files —
    never from a hand-maintained call sequence here.
    """
    planned, refusals = [], []
    snapshot = manifest.load()
    destinations = payload_destinations()
    for row in registry.ROWS:
        if row.recorded and row.owner in targets:
            plan_file(row.id, force, snapshot, destinations,
                      planned, refusals)
        elif row.id == "codex-hook-template" and "codex" in targets:
            plan_codex_hook(planned, refusals)
        elif (row.id == "agentsmd-snippet"
                and agentsmd_path is not None):
            plan_agentsmd(agentsmd_path, planned, refusals)
    return planned, refusals


def claude_code_trailer():
    """The marketplace pair, visually set off as the last block."""
    home = os.path.expanduser("~")
    has_dir = home != "~" and (Path(home) / ".claude").exists()
    if not (shutil.which("claude") or has_dir):
        return
    print("")
    print("Claude Code is managed by its own plugin marketplace — "
          "semlf never touches it:")
    print("  claude plugin marketplace add "
          "https://github.com/arloliu/semantic-linefeeds")
    print("  claude plugin install semantic-linefeeds@semantic-linefeeds")


def shim_warning():
    """Warn when `semlf` on PATH is not the artifact that ran this."""
    resolved = shutil.which("semlf")
    if resolved is None:
        return
    try:
        if os.path.realpath(resolved) != os.path.realpath(sys.argv[0]):
            print(f"warning: `semlf` on PATH resolves to {resolved}, "
                  "not this artifact; a pre-redesign zipapp or a second "
                  "channel may be shadowing it. remove it with the "
                  "checkout door (install.py --uninstall --cli) or the "
                  "other package manager.")
    except OSError:
        pass


def _finish(rc):
    """Every valid install/status outcome ends with the trailer.

    The design pins the marketplace block as the LAST block of the output,
    so success, dry run, refusal, and a declined prompt all route through here;
    only usage errors (64) skip it.
    """
    claude_code_trailer()
    return rc


def install_command(argv):
    parsed = _parse_targets(argv, "install",
                            ("yes", "dry_run", "force"))
    if parsed is None:
        return 64
    targets, agentsmd_path, flags = parsed
    named = bool(targets or agentsmd_path is not None)
    if not named:
        detected = detect_agents()
        for agent, evidence in detected:
            print(f"{agent}: detected ({evidence})")
        if not detected:
            print("semlf install: no supported agents detected; "
                  "nothing to do.")
            return _finish(0)
        targets = [agent for agent, _ in detected]
    planned, refusals = plan_install(targets, agentsmd_path,
                                     flags["force"])
    if flags["dry_run"]:
        describe_plan(planned, refusals, prefix="[dry-run] ")
        return _finish(0)
    if refusals:
        # A refusing request reports every artifact's verdict,
        # not only the refusals (the design's disclosure rule).
        describe_plan(planned, [])
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return _finish(1)
    if not named and not flags["yes"]:
        describe_plan(planned, refusals)
        if not sys.stdin.isatty():
            print("semlf install: not a terminal; re-run with --yes "
                  "to apply this plan.", file=sys.stderr)
            return _finish(1)
        try:
            answer = input("apply this plan? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            print("")
            return _finish(1)
        if answer.strip().lower() not in ("y", "yes"):
            return _finish(1)
    rc = apply_plan(planned)
    shim_warning()
    return _finish(rc)


def installed_consumers():
    """Integrations whose own artifacts are present on this machine.

    codex counts as installed when EITHER its hook entry or its installed skill file is present:
    the skill references the neutral checker and README too,
    so removing only the hook must not downgrade required payloads to leftovers.
    """
    found = set()
    home = manifest.codex_home()
    if home is not None:
        data = manifest.read_state_json(home / "hooks.json")
        if manifest.owned_codex_hooks(data):
            found.add("codex")
    skill = manifest.codex_skill_dest()
    if skill is not None and os.path.lexists(str(skill)):
        found.add("codex")
    d = manifest.opencode_plugins_dir()
    if d is not None and os.path.lexists(str(d / "semantic-linefeeds.ts")):
        found.add("opencode")
    return found


def payload_identity(name):
    """(state, human line) for one published payload.

    Guarded bytes decide the state, never the version string alone:
    two builds can differ under one version,
    and on a downgrade the published copy is ahead, not behind.
    The version is the human-facing label in the line.
    """
    dest = payload_destinations()[name]
    if dest is None:
        return "missing", f"{name}: missing, no destination resolves here"
    state = classify.object_state(dest)
    if state == "absent":
        return "missing", f"{name}: missing, not published ({dest})"
    if state != "regular":
        return "unreadable", f"{name}: {dest} is a {state}"
    current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
    if current is None:
        return "unreadable", f"{name}: {dest} is unreadable"
    if current == rendered_bytes(name):
        return "ok", f"{name}: current ({dest})"
    entry = manifest.load().get(name)
    prov = manifest.classify_entry(entry, dest)
    running = artifact_version()
    if prov != "managed":
        return "edited", (f"{name}: edited or unrecorded ({dest}); "
                          "rerun `semlf install` with --force to replace it")
    recorded = entry["version"]
    rv, cv = (classify.parse_version(recorded),
              classify.parse_version(running))
    if rv is None or cv is None:
        return "unorderable", (f"{name}: managed, but the recorded "
                               f"version ({recorded}) cannot be ordered "
                               f"against this artifact's ({running})")
    if rv < cv:
        return "lagging", (f"{name}: published v{recorded} lags this "
                           f"artifact (v{running}); run `semlf install` "
                           "to refresh it")
    if rv > cv:
        return "ahead", (f"{name}: published v{recorded} is ahead of "
                         f"this artifact (v{running})")
    return "same-version-different-bytes", (
        f"{name}: published v{recorded} matches this artifact's "
        "version but not its bytes; run `semlf install` to refresh it")


def snippet_state(target):
    if not os.path.lexists(target):
        return "absent"
    data = manifest.read_regular_bytes(target, manifest.CLASSIFY_LIMIT)
    if data is None:
        return "unreadable"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "unreadable"
    has_open = SENTINEL_OPEN in text
    has_close = SENTINEL_CLOSE in text
    if not has_open and not has_close:
        return "absent"
    # The same pairing, count, and order predicate the install plan enforces:
    # a repeated or reversed pair is malformed, not present.
    if (has_open != has_close
            or text.count(SENTINEL_OPEN) != 1
            or text.count(SENTINEL_CLOSE) != 1
            or text.index(SENTINEL_OPEN) > text.index(SENTINEL_CLOSE)):
        return "malformed"
    return "present"


def status_command(argv):
    if argv[:1] == ["agentsmd"]:
        if len(argv) != 2:
            print("semlf status: agentsmd requires an explicit path.",
                  file=sys.stderr)
            return 64
        target = Path(argv[1])
        print(f"agentsmd: block {snippet_state(target)} in {target}")
        return 0
    if argv:
        print(f"semlf status: unknown argument {argv[0]!r}",
              file=sys.stderr)
        return 64
    consumers = installed_consumers()
    snapshot = manifest.load()
    destinations = payload_destinations()
    leftover_paths = []
    # Every identity payload — both checker copies and the readme — reports through payload_identity;
    # the classifier vocabulary never appears on a payload line.
    for row in registry.ROWS:
        if not row.identity:
            continue
        state, line = payload_identity(row.id)
        if (state == "missing" and row.owner not in consumers
                and snapshot.get(row.id) is None):
            # Only a payload with neither a consumer nor a valid provenance record is irrelevant here:
            # status reports every discoverable OR RECORDED artifact,
            # so a recorded payload whose file vanished is named as missing.
            continue
        print(f"payload {line}")
        if state != "missing" and row.owner not in consumers:
            # The leftover pointer derives from the row's own destination —
            # an opencode-checker leftover lives in the opencode plugins directory, never under the data root.
            leftover_paths.append(destinations[row.id])
    home = manifest.codex_home()
    data_dir = manifest.semlf_data_dir()
    if home is None or data_dir is None:
        # CODEX_HOME may resolve while no data root does;
        # rendering the wanted command needs both,
        # so guard both (a bare render_codex_hook_entry(None) would raise instead of report).
        print("codex hook: no home to check")
    else:
        hooks_path = home / "hooks.json"
        data = manifest.read_state_json(hooks_path)
        owned = manifest.owned_codex_hooks(data)
        if not os.path.lexists(str(hooks_path)):
            print(f"codex hook: not installed ({hooks_path})")
        elif data is None:
            print(f"codex hook: unreadable ({hooks_path})")
        elif not owned:
            print(f"codex hook: not installed ({hooks_path})")
        else:
            try:
                entry = registry.render_codex_hook_entry(data_dir)
            except registry.TransformError as exc:
                print(f"codex hook: cannot render the managed entry ({exc})")
            else:
                import shlex as _shlex
                wanted = _shlex.split(entry["hooks"][0]["command"])
                if all(argv_ == wanted for argv_ in owned):
                    print(f"codex hook: installed ({hooks_path})")
                else:
                    print("codex hook: installed (stale checker path; "
                          "re-run `semlf install codex`)")
    # The skill and the plugin are integration artifacts, not identity payloads:
    # they report the classifier state verbatim (the one manifest snapshot and destinations above serve this loop too).
    for name, label in (("codex-skill", "codex skill"),
                        ("opencode-plugin", "opencode plugin")):
        dest = destinations[name]
        if dest is None:
            print(f"{label}: no home to check")
            continue
        state = classify.object_state(dest)
        if state == "absent":
            print(f"{label}: not installed ({dest})")
            continue
        try:
            rendered = rendered_bytes(name)
        except registry.TransformError as exc:
            print(f"{label}: cannot render this artifact's payload ({exc})")
            continue
        verdict = classify.classify_artifact(
            snapshot.get(name), dest, rendered,
            artifact_version(), False)
        print(f"{label}: {verdict.state} ({dest})")
    if leftover_paths:
        listed = ", ".join(str(p) for p in leftover_paths)
        print(f"payloads: no remaining consumer; remove {listed} "
              "by hand if unwanted.")
    shim_warning()
    return _finish(0)


def _prune_empty_parent(dest):
    parent = dest.parent
    try:
        if not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def _forget_note(dest, name):
    """Unlink already succeeded.

    Forget provenance without letting its own failure masquerade as dest never having been removed.
    Returns None on a clean forget.
    On a raised OSError it returns an accurate stderr line instead —
    the caller still counts dest as removed either way.
    """
    try:
        manifest.forget(name)
    except OSError as exc:
        return (f"removed {dest}, but could not clear its provenance "
               f"record: {exc}")
    return None


def plan_remove_file(label, dest, name, force, planned, refusals,
                     prune_parent=False):
    """Plan removal of one installer-owned file, or a refusal.

    Shared by the codex skill and both opencode files.
    """
    if dest is None:
        refusals.append(f"refusing to uninstall the {label}: cannot "
                        "determine a home directory to uninstall it from.")
        return
    dest = Path(dest)
    try:
        st = os.lstat(dest)
    except FileNotFoundError:
        planned.append(Planned(f"{label}: not installed ({dest})",
                               name, dest, None, None))
        return
    except OSError as exc:
        refusals.append(f"refusing to uninstall the {label}: cannot "
                        f"inspect {dest}: {exc}.")
        return
    if stat.S_ISDIR(st.st_mode):
        refusals.append(f"refusing to remove {dest}: it is a directory; "
                        "removing a tree is not this verb's one-file unlink.")
        return
    admit = False
    reason = None
    if not stat.S_ISREG(st.st_mode):
        reason = (f"refusing to remove {dest}: it is not a regular file "
                  "(symlink or special file).")
    else:
        current = manifest.read_regular_bytes(dest, manifest.CLASSIFY_LIMIT)
        if current is None:
            reason = (f"refusing to remove {dest}: it exists but is not a "
                      "readable regular file.")
        else:
            try:
                rendered = rendered_bytes(name)
            except registry.TransformError as exc:
                refusals.append(f"refusing to remove {name}: cannot "
                                f"render this artifact's payload ({exc}).")
                return
            if (current == rendered
                    or manifest.classify(name, dest) == "managed"):
                admit = True
            else:
                reason = (f"refusing to remove {dest}: its content differs "
                          "from what this kit installed (hand-patched or "
                          "older version).")
    if not (admit or force):
        refusals.append(reason + " re-run with --force to remove it anyway.")
        return

    def _do(dest=dest, name=name, prune_parent=prune_parent):
        os.unlink(dest)
        note = _forget_note(dest, name)
        if prune_parent:
            _prune_empty_parent(dest)
        return note

    planned.append(Planned(str(dest), name, dest, None, _do,
                           done=f"removed {dest}"))


def plan_remove_codex_hook(planned, refusals):
    import json
    home = manifest.codex_home()
    if home is None:
        refusals.append("refusing to uninstall the codex hook: cannot "
                        "determine a home directory to uninstall it from.")
        return
    path = home / "hooks.json"
    try:
        os.lstat(path)
    except FileNotFoundError:
        planned.append(Planned(f"codex: not installed ({path})",
                               "codex-hook", path, None, None))
        return
    except OSError as exc:
        refusals.append(f"refusing to uninstall the codex hook: cannot "
                        f"inspect {path}: {exc}.")
        return
    data = manifest.read_state_json(path)
    # Same parity as plan_codex_hook's own guard: a shape too strange to locate PostToolUse in — a non-dict top level, a "hooks" value that isn't a dict, or a "PostToolUse" value that isn't a list — is a refusal, not silently nothing-to-do.
    # A "hooks" or "PostToolUse" key that is simply *absent* from an otherwise-sane dict is not strange; it is empty, and empty is a legitimate no-op.
    hooks = data.get("hooks", {}) if isinstance(data, dict) else None
    post = hooks.get("PostToolUse", []) if isinstance(hooks, dict) else None
    if (not isinstance(data, dict) or not isinstance(hooks, dict)
            or not isinstance(post, list)):
        refusals.append(f"refusing to touch {path}: cannot read or parse "
                        "it; repair or remove it by hand.")
        return
    if not bak_sibling_ok(path):
        bak = path.with_name(path.name + ".bak")
        refusals.append(f"refusing to touch {path}: its backup slot {bak} "
                        "exists and is not a regular file; move it aside "
                        "and re-run.")
        return
    changed = False
    new_post = []
    for block in post:
        if isinstance(block, dict) and isinstance(block.get("hooks"), list):
            original = block["hooks"]
            kept = [h for h in original
                    if not (isinstance(h, dict)
                            and manifest.parse_managed_codex_hook(
                                block.get("matcher"), h) is not None)]
            if len(kept) == len(original):
                # Nothing of ours was in this block: preserve it exactly, including a foreign block that was already empty before we ever looked at it.
                new_post.append(block)
                continue
            changed = True
            if kept:
                block = dict(block)
                block["hooks"] = kept
                new_post.append(block)
            # else: our own filtering emptied this block; drop it.
        else:
            new_post.append(block)
    hooks["PostToolUse"] = new_post
    if not changed:
        planned.append(Planned(
            f"codex: no managed hook entry found in {path}",
            "codex-hook", path, None, None))
        return
    text = json.dumps(data, indent=2) + "\n"

    def _do(path=path, text=text):
        publish_shared(path, text)
        return None

    planned.append(Planned(f"the managed hook entry from {path}",
                           "codex-hook", path, None, _do,
                           done=f"removed the managed hook entry from {path}"))


def plan_remove_agentsmd(target, planned, refusals):
    """Plan splicing the sentinel block out of target, or a refusal.

    target is user-owned, so --force never overrides a refusal here —
    unlike the installer-owned single-file artifacts above.
    """
    target = Path(target)
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        planned.append(Planned(f"agentsmd: not installed ({target})",
                               "agentsmd", target, None, None))
        return
    except OSError as exc:
        refusals.append(f"refusing to uninstall agentsmd: cannot inspect "
                        f"{target}: {exc}.")
        return
    if not stat.S_ISREG(st.st_mode):
        refusals.append(f"refusing to touch {target}: it is not a regular "
                        "file; repair it by hand.")
        return
    if not bak_sibling_ok(target):
        bak = target.with_name(target.name + ".bak")
        refusals.append(f"refusing to touch {target}: its backup slot {bak} "
                        "exists and is not a regular file; move it aside "
                        "and re-run.")
        return
    data = manifest.read_regular_bytes(target, manifest.CLASSIFY_LIMIT)
    if data is None:
        refusals.append(f"refusing to touch {target}: cannot read it; "
                        "repair or remove it by hand.")
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        refusals.append(f"refusing to touch {target}: cannot decode it as "
                        "UTF-8; repair it by hand.")
        return
    has_open = SENTINEL_OPEN in text
    has_close = SENTINEL_CLOSE in text
    if has_open != has_close:
        refusals.append(f"refusing to touch {target}: found one sentinel "
                        "marker without its pair; repair the block by hand.")
        return
    if has_open and (text.count(SENTINEL_OPEN) != 1
                      or text.count(SENTINEL_CLOSE) != 1
                      or text.index(SENTINEL_OPEN) > text.index(SENTINEL_CLOSE)):
        refusals.append(f"refusing to touch {target}: sentinel markers are "
                        "out of order or repeated; repair the block by hand.")
        return
    if not has_open:
        planned.append(Planned(f"agentsmd: no block found in {target}",
                               "agentsmd", target, None, None))
        return

    def _do(target=target, text=text):
        pre = text.split(SENTINEL_OPEN)[0]
        post = text.split(SENTINEL_CLOSE, 1)[1].lstrip("\n")
        new = pre.rstrip("\n")
        if new and post:
            new = new + "\n\n" + post
        elif post:
            new = post
        elif new:
            new = new + "\n"
        publish_shared(target, new)
        return None

    planned.append(Planned(f"the semantic-linefeeds block from {target}",
                           "agentsmd", target, None, _do,
                           done=f"removed the semantic-linefeeds block from {target}"))


def uninstall_command(argv):
    parsed = _parse_targets(argv, "uninstall", ("dry_run", "force"))
    if parsed is None:
        return 64
    targets, agentsmd_path, flags = parsed
    if not targets and agentsmd_path is None:
        print("semlf uninstall: name a target (codex, opencode, "
              "agentsmd PATH).", file=sys.stderr)
        return 64
    planned, refusals = [], []
    if "codex" in targets:
        plan_remove_codex_hook(planned, refusals)
        plan_remove_file("codex skill",
                         payload_destinations()["codex-skill"],
                         "codex-skill", flags["force"], planned,
                         refusals, prune_parent=True)
    if "opencode" in targets:
        destinations = payload_destinations()
        plan_remove_file("opencode plugin",
                         destinations["opencode-plugin"],
                         "opencode-plugin", flags["force"], planned,
                         refusals)
        plan_remove_file("opencode checker",
                         destinations["opencode-checker"],
                         "opencode-checker", flags["force"], planned,
                         refusals)
    if agentsmd_path is not None:
        plan_remove_agentsmd(agentsmd_path, planned, refusals)
    if flags["dry_run"]:
        # Dry-run dominates everything: it reports the would-be refusals instead of taking them, and exits 0 (the design's fixed precedence covers the whole command surface).
        for item in planned:
            print(item.label if item.do is None
                  else f"[dry-run] would remove {item.label}")
        for refusal in refusals:
            print(f"[dry-run] would refuse: {refusal}")
        return 0
    if refusals:
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1
    rc = apply_plan(planned)
    if "codex" in targets and rc == 0:
        print(f"note: the published payloads under "
              f"{manifest.semlf_data_dir()} are shared and retained; "
              "`semlf status` reports leftovers.")
    return rc


def run(command, argv):
    if command == "install":
        return install_command(argv)
    if command == "status":
        return status_command(argv)
    if command == "uninstall":
        return uninstall_command(argv)
    return 64
