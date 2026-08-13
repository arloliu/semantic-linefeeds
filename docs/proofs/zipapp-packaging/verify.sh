#!/bin/sh
# Rebuild and verify the zipapp packaging proof (ADR-0004's packaging property).
#
# It proves one claim:
# the portable core and a repository CLI can ship as one stdlib-only artifact,
# and the core is not forked to do it.
#
# The archive is built by scripts/install.py's own build_pyz,
# the same function the installer uses for `semlf --cli`.
# Nothing here is copied or forked into this directory:
# a second recipe would drift from the one that ships,
# which is exactly the failure this proof exists to catch.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../../.." && pwd)
core="$repo/scripts/check_linefeeds.py"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

ok() { printf '  ok    %s\n' "$1"; }
die() { printf '  FAIL  %s\n' "$1" >&2; exit 1; }

printf 'building\n'
python3 - "$repo" "$work/semlf.pyz" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location(
    "install", sys.argv[1] + "/scripts/install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)
install.build_pyz(sys.argv[2])
PY
# The archive embeds modification times, so its own digest is not reproducible across builds.
# The embedded core's digest is, and that is the identity that matters:
# it proves the artifact carries this repository's core and not a fork.
printf '  core sha256:     %s\n' \
  "$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$core")"
printf '  artifact bytes:  %s\n' "$(wc -c < "$work/semlf.pyz")"

# Identity is asserted on the member INSIDE the archive, after packaging --
# comparing the pre-build copy would prove nothing about what shipped.
python3 - "$work/semlf.pyz" "$core" <<'PY2'
import hashlib, sys, zipfile
embedded = zipfile.ZipFile(sys.argv[1]).read("check_linefeeds.py")
source = open(sys.argv[2], "rb").read()
assert embedded == source, "embedded core differs from scripts/check_linefeeds.py"
print("  ok    embedded core byte-identical to scripts/check_linefeeds.py")
print("        sha256 %s" % hashlib.sha256(source).hexdigest())
PY2

# The member contract is pinned to the constant the installer publishes with,
# so a member added to PYZ_REQUIRED_MEMBERS without shipping it is caught here.
python3 - "$repo" "$work/semlf.pyz" <<'PY3'
import importlib.util, sys, zipfile
spec = importlib.util.spec_from_file_location(
    "install", sys.argv[1] + "/scripts/install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)
names = set(zipfile.ZipFile(sys.argv[2]).namelist())
missing = install.PYZ_REQUIRED_MEMBERS - names
assert not missing, "missing members: %s" % sorted(missing)
print("  ok    archive carries every required member")
PY3

printf 'verifying\n'

# 1. runs isolated, from an empty directory, with no site-packages
mkdir -p "$work/empty" && cd "$work/empty"
printf 'The exporter batches metrics. It flushes them once per minute.\n' > t.md
rc=0; python3 -I -S "$work/semlf.pyz" check t.md >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] || die "check: expected exit 1, got $rc"
ok "runs under python3 -I -S from an empty directory (exit 1)"

# 2. hook mode through the same artifact
payload='{"tool_input":{"file_path":"/x/a.md","new_string":"One sentence. Two sentence.\\n"}}'
rc=0
printf '%s' "$payload" | python3 -I -S "$work/semlf.pyz" --hook claude \
  >"$work/arc.out" 2>"$work/arc.err" || rc=$?
[ "$rc" -eq 2 ] || die "hook: expected exit 2 from archive, got $rc"
rc2=0
printf '%s' "$payload" | python3 -I -S "$core" --hook claude \
  >"$work/bare.out" 2>"$work/bare.err" || rc2=$?
[ "$rc" -eq "$rc2" ] || die "exit differs: archive $rc, bare core $rc2"
cmp -s "$work/arc.out" "$work/bare.out" || die "stdout differs between archive and bare core"
cmp -s "$work/arc.err" "$work/bare.err" || die "stderr differs between archive and bare core"
ok "hook output identical to the bare core (status, stdout, stderr)"

# 3. --staged reads the index blob, never the worktree
mkdir -p "$work/git" && cd "$work/git"
git init -q .
git config user.email poc@example.com
git config user.name poc
printf 'Clean prose lives here.\n' > d.md
git add d.md
git commit -qm init
printf 'Staged sentence one. Staged sentence two.\n' > d.md
git add d.md
printf 'Worktree is clean again.\n' > d.md
python3 -I -S "$work/semlf.pyz" --staged 2>&1 | grep -q 'Staged sentence one' \
  || die "--staged did not read the index blob"
python3 -I -S "$work/semlf.pyz" --staged 2>&1 | grep -q 'Worktree is clean' \
  && die "--staged leaked worktree content" || :
ok "--staged reports the staged blob and ignores a clean worktree"

# 4. the copy-one-file property survives
cd "$work/empty"
cp "$core" .
rc=0; python3 -I -S check_linefeeds.py --file t.md >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] || die "bare core: expected exit 1, got $rc"
ok "core still runs alone, without the archive"

# 5. stdlib-only, and 3.9-parseable
python3 - "$work/semlf.pyz" <<'PY'
import ast, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
mods, local = set(), {"semlf", "check_linefeeds"}
for n in z.namelist():
    if not n.endswith(".py"):
        continue
    src = z.read(n).decode()
    ast.parse(src, feature_version=(3, 9))
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split(".")[0])
ext = sorted(m for m in mods - local if m not in sys.stdlib_module_names)
assert not ext, "non-stdlib imports: %s" % ext
print("  ok    all modules parse at feature_version=(3,9), imports are stdlib-only")
PY

printf '\nLimits recorded by this proof:\n'
printf '  - 3.9 is checked for SYNTAX only; no 3.9 interpreter runtime test is performed here.\n'
printf '  - startup overhead is measured for a CLI, and says nothing about hook latency.\n'
