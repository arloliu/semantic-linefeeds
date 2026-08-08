#!/usr/bin/env bash
# Fixture tests for check_linefeeds.py.
# The bad fixtures come from the worked examples in the semantic-linefeeds rule document;
# the good fixtures are their conformant counterparts plus every never-flag case.
set -u
cd "$(dirname "$0")"
CHECK="python3 ../scripts/check_linefeeds.py"
fail=0

expect() { # expect <desc> <want> <got>
  if [ "$2" = "$3" ]; then
    echo "ok   $1"
  else
    echo "FAIL $1: want '$2', got '$3'"
    fail=1
  fi
}

count() { # count <kind> <file>
  $CHECK --file "$2" | grep -c "\[$1\]"
}

# --file mode: bad fixtures must be flagged with the right kinds.
expect "bad_wrapped.go fused"  3 "$(count fused fixtures/bad_wrapped.go)"
expect "bad_wrapped.go wrap"   2 "$(count wrap  fixtures/bad_wrapped.go)"
expect "bad_wrapped.md fused"  1 "$(count fused fixtures/bad_wrapped.md)"
expect "bad_wrapped.md wrap"   2 "$(count wrap  fixtures/bad_wrapped.md)"

# --file mode: good fixtures must be completely silent.
expect "good_sembr.go silent"  0 "$($CHECK --file fixtures/good_sembr.go | grep -c '\[')"
expect "good_sembr.go exit"    0 "$($CHECK --file fixtures/good_sembr.go >/dev/null; echo $?)"
expect "good_sembr.md silent"  0 "$($CHECK --file fixtures/good_sembr.md | grep -c '\[')"
expect "good_sembr.md exit"    0 "$($CHECK --file fixtures/good_sembr.md >/dev/null; echo $?)"
expect "bad_wrapped.go exit"   1 "$($CHECK --file fixtures/bad_wrapped.go >/dev/null; echo $?)"

# A long line whose only "boundary" is a compound-predicate 'and' is printed
# as an advisory but must not fail the run (120 is a guide, not a gate).
expect "advisory_long.md printed" 1 "$(count long fixtures/advisory_long.md)"
expect "advisory_long.md exit 0"  0 "$($CHECK --file fixtures/advisory_long.md >/dev/null; echo $?)"

# --hook mode: violating Edit payload -> exit 2 with stderr feedback.
hook_exit() { printf '%s' "$1" | $CHECK --hook 2>/dev/null; echo $?; }
BAD_EDIT='{"tool_name":"Edit","tool_input":{"file_path":"/x/doc.go","new_string":"// Package cache provides caches. A cache\n// holds a bounded number of entries here\n// and evicts old ones."}}'
GOOD_EDIT='{"tool_name":"Edit","tool_input":{"file_path":"/x/doc.go","new_string":"// Package cache provides fixed-capacity, in-memory key/value caches.\n// A cache holds a bounded number of entries."}}'
OTHER_FILE='{"tool_name":"Write","tool_input":{"file_path":"/x/main.py","content":"wrapped prose. More prose\nthat would be flagged in md."}}'
expect "hook bad edit exit 2"    2 "$(hook_exit "$BAD_EDIT")"
expect "hook good edit exit 0"   0 "$(hook_exit "$GOOD_EDIT")"
expect "hook non-target file"    0 "$(hook_exit "$OTHER_FILE")"
expect "hook malformed json"     0 "$(printf 'not json' | $CHECK --hook 2>/dev/null; echo $?)"
expect "hook stderr has skill pointer" 1 "$(printf '%s' "$BAD_EDIT" | $CHECK --hook 2>&1 >/dev/null | grep -c 'semantic-linefeeds skill')"

# Escaped \n in JSON must become real newlines for the wrap check to see line pairs.
expect "hook bad edit finds wrap" 1 "$(printf '%s' "$BAD_EDIT" | $CHECK --hook 2>&1 >/dev/null | grep -c '\[wrap\]')"

if [ "$fail" = 0 ]; then echo "ALL PASS"; else echo "FAILURES"; exit 1; fi
