#!/bin/sh
# Run every batch of one family, skipping any whose answer already parses.
#
#     sh tests/corpus/repairs/run_round.sh <family> <batches-dir> <out-dir>
#
# Sequential on purpose.
# Three families run beside each other,
# and one family hammering a provider in parallel buys wall-clock at the cost of limits.
# Re-running is safe and resumes: an answer that already parses is left alone.
#
# `RUN_PASS` overrides the command a batch is sent through,
# so the loop is testable without reaching a provider.
set -eu

family="$1"
batches="$2"
out="$3"
run_pass="${RUN_PASS:-tests/corpus/repairs/run_pass.sh}"
mkdir -p "$out"

parses() {
  [ -s "$1" ] || return 1
  python3 -c "
import pathlib, sys
sys.path.insert(0, 'tests')
from corpus_harness import pass_answers
sys.exit(0 if pass_answers(pathlib.Path(sys.argv[1])) else 1)
" "$1"
}

for batch in "$batches"/batch-*.md; do
  index=$(basename "$batch" .md | sed 's/batch-//')
  answer="$out/$family-$index.out"
  if parses "$answer"; then
    echo "$family $index: already answered"
    continue
  fi
  echo "$family $index: running"
  if sh "$run_pass" "$family" "$batch" "$answer"; then
    echo "$family $index: done"
  else
    echo "$family $index: FAILED" >&2
  fi
done

# A loop that ended is not a round that finished.
# A batch can fail, or return something nothing can read,
# and leave the family short by a whole batch while the file count looks complete.
# That is how round-1 lost eight units without saying so.
short=""
for batch in "$batches"/batch-*.md; do
  index=$(basename "$batch" .md | sed 's/batch-//')
  parses "$out/$family-$index.out" || short="$short $index"
done
if [ -n "$short" ]; then
  echo "$family: no readable answer for batch(es):$short" >&2
  echo "$family: DID NOT FINISH — re-run to fill the gaps" >&2
  exit 1
fi
echo "$family: finished, every batch answered"
