# Repairing procedure

This file is procedure, not rule.

The normative source for what a line should become is
[`skills/semantic-linefeeds/SKILL.md`](../../../skills/semantic-linefeeds/SKILL.md),
pinned by digest in [`manifest.json`](../manifest.json).
Judge every candidate against that file.
If this one seems to contradict it, that file wins and this one is wrong.

## What a repairer sees

One unit is a window.
It holds a line the checker reported,
the line beneath it when the two share a paragraph,
and the finding delivered the way the hook delivers one.
Beside it is a numbered list of candidate repairs,
each shown as the lines it would write.

You will not see the checker's own suggested repair.
You will not see another pass's answers.
That is the point.
A repair taken from the tool's suggestion measures agreement with the tool.
It does not judge the prose.
And three passes that read each other stop being three passes.

Units arrive in an order randomized for you, in bounded batches.
Order is randomized so that fatigue and drift do not line up across passes.

## What to return, for every unit

Three things, every time.

1. **Accept or reject every candidate on the list.**
   Every one of them,
   including the one you would make yourself,
   and including the candidate that leaves the window exactly as it is.
   Accept a candidate when the lines it writes are correct prose under the rule.
   Reject it when they are not.
2. **Name the one candidate you would make.**
   It must be one you accepted.
3. **Say so if the repair you would make is not on the list.**
   Do not pick the nearest one.
   A repair the list does not offer means the list was built wrongly,
   and saying so is more useful than an answer fitted to a list.

## What acceptance means

A candidate is acceptable when the prose it produces is correct.
Not when it is the one you would have chosen.

More than one candidate is often acceptable.
A long line can break at more than one real clause boundary,
and both results read correctly.
Accepting several is the normal answer rather than a hedge.

Leaving the window alone is a candidate like any other.
Some findings are best answered by changing nothing,
and that answer is on the list so that it can be given.

## What never to do

**Never rewrite the words.**
A repair moves where a line breaks.
It does not reword, shorten, correct, or improve the prose.
A candidate that changed a word would have been dropped before you saw it.

**Never add a suppression directive.**
Not to the window, not to the file, and not as a candidate you would make.

**Never look for the tool's answer.**
Do not run the checker on the window.
Do not go looking for the file it came from to see what the tool said about it.

**Never decide by how many candidates you have already accepted.**
There is no target number.
One acceptable candidate is ordinary, and so are five.

## What happens to your answers

Three passes answer the same unit independently.
How three sets of verdicts become one is deliberately not described here,
for the reason [`LABELING.md`](../LABELING.md) gives for the same omission:
a pass that knows which answer survives a disagreement is answering a different question.
