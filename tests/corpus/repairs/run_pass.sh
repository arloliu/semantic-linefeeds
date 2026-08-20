#!/bin/sh
# Run one repair batch through one model family and save its answer.
#
#     sh tests/corpus/repairs/run_pass.sh <family> <batch.md> <out.out>
#
# Each family reads the batch from a file rather than from an argument:
# a batch is about 56KB and an argv limit is not a thing to discover mid-round.
# Nothing here passes the checkout, the sample, or another pass's answers.
set -eu

family="$1"
batch="$2"
out="$3"

case "$family" in
  claude)
    claude -p --model sonnet --allowedTools "" < "$batch" > "$out"
    ;;
  codex)
    codex exec --sandbox read-only -m gpt-5.6-terra -c model_reasoning_effort=medium \
      --output-last-message "$out" "$(cat "$batch")" < /dev/null > /dev/null
    ;;
  agy)
    agy --model "gemini-3.7-flash-high" -p "$(cat "$batch")" > "$out"
    ;;
  *)
    echo "unknown family: $family" >&2
    exit 2
    ;;
esac
