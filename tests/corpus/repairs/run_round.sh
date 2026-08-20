#!/bin/sh
# Run every batch of one family, skipping any whose answer already parses.
#
#     sh tests/corpus/repairs/run_round.sh <family> <batches-dir> <out-dir>
#
# Sequential on purpose.
# Three families run beside each other,
# and one family hammering a provider in parallel buys wall-clock at the cost of limits.
# Re-running is safe and resumes: an answer that already parses is left alone.
set -eu

family="$1"
batches="$2"
out="$3"
mkdir -p "$out"

for batch in "$batches"/batch-*.md; do
  index=$(basename "$batch" .md | sed 's/batch-//')
  answer="$out/$family-$index.out"
  if [ -s "$answer" ] && python3 -c "
import pathlib, sys
sys.path.insert(0, 'tests')
from corpus_harness import pass_answers
sys.exit(0 if pass_answers(pathlib.Path('$answer')) else 1)
"; then
    echo "$family $index: already answered"
    continue
  fi
  echo "$family $index: running"
  if sh tests/corpus/repairs/run_pass.sh "$family" "$batch" "$answer"; then
    echo "$family $index: done"
  else
    echo "$family $index: FAILED" >&2
  fi
done
echo "$family: finished"
