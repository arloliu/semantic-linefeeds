"""The sealed holdout and the ledger that governs opening it.

The holdout exists to test a predicate against prose nobody tuned against.
Plaintext in the working tree defeats that on its own,
because the agent doing the tuning reads the working tree.
So the holdout is committed as ciphertext,
and the passphrase lives only in the maintainer's head.

This is not protection against cryptanalysis and does not claim to be.
It is protection against reading, which is the threat that exists here.

A bundle opens only when the ledger already names this predicate, this calibration manifest, and this ciphertext.
Tuning the predicate changes its digest,
the freeze record stops matching,
and scoring is refused until a new bundle is committed in the open.
"""

import base64
import collections
import hashlib
import hmac
import json
import math
import os
import pathlib
import random
import re
import shlex
import subprocess

# Deliberately modest.
# The passphrase is never written down,
# and the threat is an agent reading the repository rather than an offline attack.
KDF_ITERATIONS = 200_000


LABELS = ("true", "false", "ambiguous")

# The two questions asked of every sampled boundary.
# One boundary is judged twice, and the two answers live in two records.
KINDS = ("wrap", "fused")

# The nine dimensions ADR-0003 stratifies `wrap` on.
# Only the structurally rare ones drive a quota,
# but all nine are recorded for every unit so any cross can be recomputed later.
COVARIATES = (
    "prose_width",
    "raw_end_column",
    "indentation_depth",
    "language",
    "markdown_nesting",
    "trailing_inline_markup",
    "list_item_adjacency",
    "paragraph_line_count",
    "eligible_anchor_count",
)

SECTIONS = (
    "schema_version",
    "rubric",
    "reporting",
    "repair_admission",
    "covariate_definitions",
    "eligible_anchor",
    "frames",
    "protocol_notes",
    "sources",
    "units",
)

SOURCE_FIELDS = (
    "id",
    "side",
    "composition",
    "url",
    "commit",
    "license",
    "selection_command",
)

# Both sides carry the same three compositions.
# A predicate calibrated only against one author's habits fails the holdout uninterpretably.
COMPOSITIONS = ("self-authored", "third-party-code", "third-party-markdown")

# Unit text is vendored into this repository, so the licence decides what may be stored at all.
# The LLVM exception waives Apache conditions for object-code embedding and adds none,
# so prose vendored under the combined identifier is governed by the plain Apache-2.0 terms.
PERMISSIVE = (
    "Apache-2.0",
    "Apache-2.0 WITH LLVM-exception",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "MIT",
)

# What a third-party source is admitted on.
# Selecting sources by finding density would repeat, at repository granularity,
# the error ADR-0003 forbids at candidate granularity.
QUALIFICATION = ("wrapping_column", "qualification")

# The dimensions a rate may be broken down by.
# Fixed here rather than in the manifest:
# a stratum the manifest can drop is a floor the manifest can drop.
REPORTED_STRATA = (
    "language",
    "markdown_nesting",
    "list_item_adjacency",
    "trailing_inline_markup",
    "indentation_depth",
    "raw_end_column",
)

# Settled before any rate existed, and checked so that no rate can loosen them afterwards.
REPORTING = {
    "interval": "wilson-95",
    "min_true_violations": 10,
    "max_interval_half_width": 0.15,
    "max_ambiguous_fraction": 0.25,
}

# Settled before a single repair was elicited, for the same reason REPORTING was.
# A floor stated after its labels are read is not a gate.
# Every clause is written into the manifest too, and the two copies are compared,
# so one of them moving is a failure rather than an edit.
REPAIR_ADMISSION = {
    "interval": "wilson-95",
    "floor": 0.8,
    "denominator": (
        "a unit is scored when it carries a frozen acceptable set and is not ambiguous; "
        "ambiguous units leave the rate and are kept as cases, "
        "as the label corpus already treats them"
    ),
    "activation": (
        "a class admits a repair only where every other class is absent, "
        "so it is scored on the exact class sets it activates "
        "rather than on every unit carrying it"
    ),
    "statistic": (
        "per activated exact set, the fraction of that stratum's scored units "
        "whose machine repair is in the acceptable set"
    ),
    "test": (
        "every activated stratum clears the floor on its own lower bound, "
        "independently of the others"
    ),
    "pooling": (
        "a population-weighted combination across the activated strata is reported "
        "as description, and it decides nothing; "
        "one interval over a weighted mean would need a stratified variance estimator "
        "this corpus does not define, and several units can share one window "
        "and so one repair outcome, which a binomial interval would count as "
        "independent trials"
    ),
    "unreportable_stratum": (
        "an activated stratum the frozen rules cannot rate refuses the class, "
        "and is never dropped so that the remaining strata carry the claim"
    ),
    "reportable": {
        "min_scored": 26,
        "max_interval_half_width": 0.15,
        "max_ambiguous_fraction": 0.25,
        "min_scored_note": (
            "a preregistered policy minimum rather than a derivation; "
            "what the frozen rules make reportable depends on the realized count, "
            "the half-width and the ambiguous fraction, "
            "none of them known before labeling, "
            "so nothing can prove a smaller stratum intrinsically unreportable; "
            "26 is the size at which a rate of 0.80 first fits inside the frozen "
            "half-width, and it is taken as a floor on that ground alone"
        ),
    },
    "same_algorithm": (
        "the repair transformation under test is applied to the shipped class as well, "
        "and both numbers are reported from that one algorithm; "
        "a round that scores two classes through two algorithms is refused"
    ),
    "zero_tolerance": {
        "prose_not_preserved": "a machine repair that does not preserve the prose",
        "carrier_changed": "a machine repair that changes a carrier",
        "fired_where_only_the_original_is_acceptable": (
            "a machine repair that fires on a unit whose acceptable set holds only "
            "the original; automatically repairing a line that should have been left "
            "alone is the worst outcome this tool can produce"
        ),
    },
    "baseline": (
        "the shipped class is measured and reported beside every candidate as context; "
        "it is 34 boundaries with 32 of them in one source, and it is never the bar"
    ),
    "admissible_from": (
        "no class is admissible on the calibration side; "
        "every number above is scored on a holdout round "
        "drawn after the widened predicate is frozen"
    ),
}


class ScoringRefused(Exception):
    """A step of the holdout protocol was refused, and the message says which rule refused.

    Opening a bundle is the step this guards most often.
    Drawing a sample and sealing one are guarded too,
    because a predicate frozen after the prose was drawn is not a prediction.
    """


def defect(unit):
    """Why a drawn unit carries no label, or None when it carries one.

    A sampling defect is a unit the frame should never have offered,
    such as a licence header, which the detector is structurally unable to report.
    A labeling defect is a unit the frame was right to offer
    and a pass would not answer, which is a fact about the labeler rather than the prose.

    Both leave the sample rather than being decided by whoever is left.
    A unit judged by two of three blind passes reads as unanimity wherever those two agree,
    and that is a different instrument reported under the same name.
    """
    return unit.get("sampling_defect") or unit.get("labeling_defect")


def resolution(passes):
    """The label three blind passes settle on, or "adjudicated" when they cannot.

    Refutation outranks counting, but only where it stands against agreement.
    A "false" against colleagues who agree with each other reaches a maintainer instead of losing a vote.
    A "false" inside a three-way split does not, because the unit is already unclear on its face.

    That order was measured rather than assumed.
    Sending three-way splits to the maintainer left the ambiguous label unreachable,
    and a level's ambiguous fraction cannot gate a rate when nothing ever carries the label.
    """
    unknown = sorted(set(passes) - set(LABELS))
    if unknown:
        raise ValueError("unknown label from a labeling pass: " + ", ".join(unknown))
    answers = set(passes)
    if len(answers) == 1:
        return passes[0]
    if len(answers) == len(LABELS):
        return "ambiguous"
    if "false" in answers:
        return "adjudicated"
    return "ambiguous"


def _digest(data):
    """Prefixed, so the algorithm travels with every digest a record pins."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_digest(path):
    """A digest of exactly the bytes on disk, whitespace and all."""
    return _digest(path.read_bytes())


def _keys(passphrase, salt, iterations):
    """Two independent keys from one passphrase: one to mask, one to authenticate."""
    root = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32
    )
    return (
        hmac.new(root, b"keystream", hashlib.sha256).digest(),
        hmac.new(root, b"tag", hashlib.sha256).digest(),
    )


def _keystream(key, length):
    """HMAC-SHA256 in counter mode, stdlib only."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def _mask(data, key):
    return bytes(a ^ b for a, b in zip(data, _keystream(key, len(data))))


ProseLine = collections.namedtuple("ProseLine", "lineno raw prose")
Boundary = collections.namedtuple("Boundary", "path upper lower paragraph")

# A break is counted as available when it leaves this much text standing on each side.
# The number is geometric on purpose.
# Counting anchors by punctuation or by clause openers would restate half of the detector's condition.
# Selecting on that is sampling from findings by another name.
ANCHOR_MIN_SIDE = 15

TAB_WIDTH = 8

LIST_MARKER_RE = re.compile(r"^([-*+]|\d+[.)])\s")
TRAILING_MARKUP = "*_~`)]}\"'"


def paragraphs(text, path):
    """Runs of adjacent prose lines, as the checker's own extractor groups them.

    Enumerating from the extractor aligns a unit with the text the detector actually sees.
    It also bounds every reported rate to the prose the extractor yields,
    which the manifest states as a cost rather than hides as an assumption.
    """
    import check_linefeeds

    stream = check_linefeeds.prose_stream(text, path)
    if stream is None:
        return []
    # Licence text is a never-break class.
    # A unit drawn from one is a violation the detector is structurally unable to report,
    # so it would sit in the denominator forever without any predicate ever reaching it.
    # The cut comes from the checker rather than from a copy of it here,
    # because a copy is a second rule that drifts.
    stream = check_linefeeds.without_license_text(stream, text, path)
    runs, current = [], []
    for lineno, raw, prose in stream:
        parsed = check_linefeeds.parse_directive(prose) if prose is not None else None
        # The bare-prose and code-comment standalone forms are never gated at extraction time.
        # diagnose applies this same ASCII-adjacency rule before honoring one.
        # The sampler must apply it too,
        # or a Unicode-WS candidate would be dropped here
        # while diagnose still judges it as ordinary prose.
        is_directive = (
            parsed is not None
            and parsed is not check_linefeeds.MALFORMED
            and check_linefeeds._standalone_carrier_is_ascii(raw, prose)
        )
        if prose is None or is_directive:
            # A well-formed standalone directive is a paragraph boundary to the checker,
            # so the frame must not sample it as prose.
            if len(current) > 1:
                runs.append(current)
            current = []
            continue
        current.append(ProseLine(lineno, raw, prose))
    if len(current) > 1:
        runs.append(current)
    return runs


def boundaries(text, path):
    """Every adjacent line boundary inside a paragraph, attributed to the upper line.

    Both kinds are labeled here.
    `wrap` is a property of the boundary and `fused` a property of the upper line,
    and one reading of the pair yields both labels.
    """
    return [
        Boundary(path, run[i], run[i + 1], run)
        for run in paragraphs(text, path)
        for i in range(len(run) - 1)
    ]


# A window of comment lines with nothing in front of it reads as a leading licence region.
# The checker cuts that region, so a replay without a guard would report nothing at all.
# One line of non-comment text ends the region and costs nothing else.
REPLAY_PREFIX = "replay"


def replay_kinds(unit):
    """What the checker reports at a stored unit's upper line, replayed from the manifest alone.

    This is what makes the frozen status a test rather than a claim.
    A reviewer reruns it without the source checkouts,
    and a unit that slips from detected to missed fails on identity instead of moving a total.
    """
    import check_linefeeds

    suffix = pathlib.PurePosixPath(unit["path"]).suffix
    window = list(unit["raw_window"])
    offset = 0
    if not check_linefeeds.is_markdown(unit["path"]):
        window = [REPLAY_PREFIX] + window
        offset = 1
    text = "\n".join(window) + "\n"
    upper = unit["upper_index"] + offset + 1
    return {
        kind
        for lineno, kind, _, _ in check_linefeeds.check(text, "replay" + suffix)
        if lineno == upper
    }


def covariates(unit):
    """The nine dimensions recorded for every labeled unit.

    Quotas run on the structurally rare ones only.
    The rest arrive spread on their own,
    and all nine are recorded so a reader can recompute any cross without trusting this split.
    """

    raw = unit.upper.raw.rstrip()
    shown = raw.expandtabs(TAB_WIDTH)
    return {
        "prose_width": max(
            len(line.raw.rstrip().expandtabs(TAB_WIDTH)) for line in unit.paragraph
        ),
        "raw_end_column": len(raw),
        "indentation_depth": len(shown) - len(shown.lstrip()),
        "language": _language(unit.path),
        "markdown_nesting": _nesting(unit),
        "trailing_inline_markup": unit.upper.prose.rstrip().endswith(
            tuple(TRAILING_MARKUP)
        ),
        "list_item_adjacency": bool(LIST_MARKER_RE.match(unit.lower.raw.lstrip())),
        "paragraph_line_count": len(unit.paragraph),
        "eligible_anchor_count": _eligible_anchors(unit.upper.prose),
    }


def _language(path):
    """The name of the language the extractor chose, not the specification it chose.

    The lookup hands back the whole specification, compiled patterns included,
    and a stratum label has to be a value a manifest can carry.
    """
    import check_linefeeds

    if check_linefeeds.is_markdown(path):
        return "markdown"
    lang = check_linefeeds.lang_for_path(path)
    return lang.name if lang else None


def _nesting(unit):
    """How many Markdown markers stand between the line's start and its prose.

    The extractor strips at most one blockquote marker and one list marker,
    so anything deeper never enters the stream at all.
    """
    import check_linefeeds

    if not check_linefeeds.is_markdown(unit.path):
        return 0
    rest, depth = unit.upper.raw.lstrip(), 0
    while rest.startswith(">"):
        depth += 1
        rest = rest[1:].lstrip()
    if LIST_MARKER_RE.match(rest):
        depth += 1
    return depth


def _eligible_anchors(prose):
    """How many places this line could have been broken, counted by geometry alone.

    A position qualifies when text of a usable length stands on both sides of it.
    No punctuation and no word list enters the count,
    because either one would restate the condition the corpus is measuring.
    """
    return sum(
        1
        for i, char in enumerate(prose)
        if char == " "
        and len(prose[:i].strip()) >= ANCHOR_MIN_SIDE
        and len(prose[i + 1 :].strip()) >= ANCHOR_MIN_SIDE
    )


def band_of(value, bands):
    """The level a value falls in, named from edges fixed before any draw.

    Naming a level after its edges is what stops a band from being redrawn around a known rate.
    """
    edges = list(bands)
    if value <= edges[0]:
        return f"..{edges[0]}"
    for low, high in zip(edges, edges[1:]):
        if value <= high:
            return f"{low + 1}..{high}"
    return f"{edges[-1] + 1}.."


def _rng(*parts):
    """A generator seeded from text, so a reviewer redraws rather than trusts."""
    material = hashlib.sha256(":".join(parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(material[:8], "big"))


def draw(population, key, bands, per_level, seed):
    """A quota sample anyone holding the seed can redraw.

    Quotas run only on the dimensions that are structurally rare.
    A level thinner than its quota gives up everything it has,
    which is why the report prints `x/n` there instead of a percentage.
    """
    levels = collections.defaultdict(list)
    for record in population:
        levels[band_of(record[key], bands)].append(record)
    drawn = []
    for level in sorted(levels):
        pool = sorted(levels[level], key=lambda record: record["id"])
        drawn += _rng(seed, level).sample(pool, min(per_level, len(pool)))
    return drawn


# How much of the paragraph travels with a unit.
# Enough to judge the boundary, never a whole file.
CONTEXT = 2


def files_of(source, root):
    """Exactly the files the manifest's own selection command names, and no others.

    The command is the auditable artifact,
    so a second filter applied here would be a selection rule nobody recorded.
    """
    words = shlex.split(source["selection_command"])
    if words[:2] != ["git", "ls-files"]:
        raise ValueError(
            f"source {source['id']} selects files by an unrecognized command"
        )
    return subprocess.run(
        ["git", "-C", str(root), "ls-files"] + words[2:],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()


def records_for(source, root):
    """Every boundary the extractor yields from one source, with its covariates."""
    out = []
    for name in files_of(source, root):
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for unit in boundaries(text, name):
            first = unit.paragraph.index(unit.upper)
            start = max(0, first - CONTEXT)
            window = unit.paragraph[start : first + CONTEXT + 2]
            out.append(
                {
                    # The raw lines travel with the unit, so the checker can be rerun over it offline.
                    # That is what makes a frozen status a test rather than a claim.
                    "raw_window": [line.raw for line in window],
                    "upper_index": first - start,
                    "id": f"{source['id']}:{name}:{unit.upper.lineno}",
                    "source": source["id"],
                    "frame": "main",
                    "path": name,
                    "lines": [unit.upper.lineno, unit.lower.lineno],
                    "upper": unit.upper.prose,
                    "lower": unit.lower.prose,
                    "context": [line.prose for line in window],
                    "covariates": covariates(unit),
                }
            )
    return out


def level_of(record, dimension, bands):
    """The level a unit sits at on one dimension, named so it cannot be renamed later."""
    value = record["covariates"][dimension]
    return band_of(value, bands) if bands else str(value)


def draw_corpus(population, base, quotas, seed):
    """A random base, topped up until every named level reaches its quota.

    Quotas run only on the structurally rare dimensions.
    The rest arrive spread on their own, and the base is what spreads them,
    so a top-up adds to the base and never replaces any of it.

    A level thinner than its quota gives up everything it has.
    Nothing here invents units to reach a number.
    """
    pool = sorted(population, key=lambda record: record["id"])
    chosen = {
        record["id"]: record
        for record in _rng(seed, "base").sample(pool, min(base, len(pool)))
    }
    for dimension, (bands, per_level) in sorted(quotas.items()):
        members = collections.defaultdict(list)
        for record in pool:
            members[level_of(record, dimension, bands)].append(record)
        for level, at_level in sorted(members.items()):
            short = per_level - sum(1 for r in at_level if r["id"] in chosen)
            if short <= 0:
                continue
            rest = [r for r in at_level if r["id"] not in chosen]
            for record in _rng(seed, dimension, level).sample(
                rest, min(short, len(rest))
            ):
                chosen[record["id"]] = record
    return sorted(chosen.values(), key=lambda record: record["id"])


def band_levels(bands):
    """Every level a set of band edges names, whether or not the population reaches it."""
    edges = list(bands)
    return tuple(
        [f"..{edges[0]}"]
        + [f"{low + 1}..{high}" for low, high in zip(edges, edges[1:])]
        + [f"{edges[-1] + 1}.."]
    )


def quota_shortfalls(population, drawn, quotas):
    """Every quota the population could not satisfy, named rather than counted.

    Two things count.
    A level thinner than its quota is the obvious one.
    A dimension the population holds at a single level is the one worth building this for:
    the quota reports success because nothing is left to be short of,
    and a level that vanished from the sampling frame reads as a level nobody asked about.
    """
    problems = []
    for dimension, (bands, per_level) in sorted(quotas.items()):
        wanted = (
            band_levels(bands)
            if bands
            else sorted({level_of(record, dimension, None) for record in population})
        )
        present = {level_of(record, dimension, bands) for record in population}
        if len(present) < 2:
            held = sorted(present)[0] if present else "nothing"
            problems.append(
                "{}: the population holds {}{}, so the quota separates nothing".format(
                    dimension, "only " if present else "", held
                )
            )
            continue
        counts = collections.Counter(
            level_of(record, dimension, bands) for record in drawn
        )
        problems += [
            f"{dimension} at {level}: {counts[level]} of {per_level}"
            for level in wanted
            if counts[level] < per_level
        ]
    return problems


def labeling_batches(sample, labeler, size):
    """One labeler's units, in an order of their own, in bounded batches.

    Order is randomized per labeler so that fatigue and drift do not line up across passes,
    and batches are bounded because a labeler judging a hundred units at a sitting drifts inside it.
    """
    order = sorted(sample, key=lambda record: record["id"])
    _rng(labeler).shuffle(order)
    return [order[i : i + size] for i in range(0, len(order), size)]


def wilson(successes, total):
    """The 95% interval for a proportion, or None when there is nothing to estimate.

    Wilson rather than the textbook normal interval,
    because the rates this corpus reports sit near 1 on small denominators,
    where the normal interval runs past 1 and stops meaning anything.
    """
    if total <= 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = (
        z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    )
    return max(0.0, centre - spread), min(1.0, centre + spread)


def recall(units, kind, dimension=None, bands=None):
    """Detection rate per level, with the reason attached wherever a rate is withheld.

    The reasons are the manifest's reporting rules, which were fixed before any rate existed.
    A withheld level still reports its counts:
    "3 of 4" is honest about how little it knows, where "75%" is not.
    """
    levels = {}
    for record in units:
        if record["question"] != kind:
            continue
        level = level_of(record, dimension, bands) if dimension else "all"
        counts = levels.setdefault(
            level, {"true": 0, "detected": 0, "ambiguous": 0, "labeled": 0}
        )
        counts["labeled"] += 1
        if record["label"] == "ambiguous":
            counts["ambiguous"] += 1
        elif record["label"] == "true":
            counts["true"] += 1
            counts["detected"] += record.get("expected") == "detected"

    report = {}
    for level, counts in levels.items():
        interval = wilson(counts["detected"], counts["true"])
        withheld = []
        if counts["true"] < REPORTING["min_true_violations"]:
            withheld.append(
                f"fewer than {REPORTING['min_true_violations']} true violations"
            )
        if (
            interval
            and (interval[1] - interval[0]) / 2 > REPORTING["max_interval_half_width"]
        ):
            withheld.append(
                f"interval wider than {round(REPORTING['max_interval_half_width'] * 100)} points"
            )
        if (
            counts["ambiguous"]
            > REPORTING["max_ambiguous_fraction"] * counts["labeled"]
        ):
            withheld.append("more than a quarter of the labels are ambiguous")
        report[level] = dict(
            counts,
            interval=interval,
            withheld=tuple(withheld),
            rate=None
            if withheld or not interval
            else counts["detected"] / counts["true"],
        )
    return report


def floor_problems(units, floors, dimension=None, bands=None):
    """Every floor the corpus fails to clear, named with the rate that failed it.

    Without a dimension, `floors` maps a kind to one floor for the corpus entire.
    With one, it maps a kind to a floor per level,
    because a stratum can fall a long way while the total barely moves.

    A floor on a kind or level the corpus cannot rate is a failure too.
    Otherwise a corpus satisfies every floor by shrinking
    until nothing has the denominator to contradict one.
    """
    problems = []
    for kind, stated in sorted(floors.items()):
        report = recall(units, kind, dimension, bands)
        wanted = stated if dimension else {"all": stated}
        for level, floor in sorted(wanted.items(), key=lambda pair: str(pair[0])):
            where = kind if not dimension else f"{kind} at {dimension} {level}"
            counts = report.get(level)
            if counts is None:
                problems.append(
                    f"{where}: a floor of {floor:.2f}, and nothing labeled there"
                )
            elif counts["rate"] is None:
                problems.append(
                    "{}: a floor of {:.2f}, and no rate to hold it — {}".format(
                        where, floor, "; ".join(counts["withheld"])
                    )
                )
            elif counts["rate"] < floor:
                problems.append(
                    f"{where}: {counts['detected']} of {counts['true']} is {counts['rate']:.3f}, below the floor of {floor:.2f}"
                )
    return problems


def contract_digest(contract):
    """A digest of a contract's content, canonicalized, rather than of the file holding it.

    The manifest's file digest moves whenever any of its several hundred units moves,
    so a round bound to that digest is bound to everything the corpus later grows.
    This one moves when the contract moves and at no other time,
    which is the property a freeze needs from it.
    """
    return _digest(json.dumps(contract, sort_keys=True).encode("utf-8"))


def repair_admission_digest():
    """The digest of the admission contract as this harness holds it.

    Comparing the manifest against the in-code constant catches one copy moving.
    It catches nothing when both move together once a round is underway,
    and only a freeze binding this digest does.
    """
    return contract_digest(REPAIR_ADMISSION)


def repair_admission_problems(candidate):
    """Every reason a candidate class is refused admission, or nothing when it clears.

    The clauses are `REPAIR_ADMISSION`, which was frozen before any repair existed.
    Refusal is the default here in a way it is not in `recall`:
    a condition that was not measured refuses,
    and a stratum that cannot be rated refuses,
    because a class admitted on a number nobody has is admitted on nothing.
    """
    name = candidate.get("class", "<unnamed class>")
    problems = []

    algorithm = candidate.get("algorithm")
    baseline = candidate.get("baseline_algorithm")
    if not algorithm or not baseline:
        problems.append(
            f"{name}: names no algorithm on one side or the other, "
            "and the shipped class is scored through the same one"
        )
    elif algorithm != baseline:
        problems.append(
            f"{name}: scored through {algorithm!r} while the shipped class was scored "
            f"through {baseline!r}, and one round scores both through one algorithm"
        )

    measured = candidate.get("zero_tolerance") or {}
    for condition in sorted(REPAIR_ADMISSION["zero_tolerance"]):
        count = measured.get(condition)
        if count is None:
            problems.append(
                f"{name}: {condition} was not measured, "
                "and an unmeasured condition is not a satisfied one"
            )
        elif count:
            problems.append(
                f"{name}: {count} unit(s) hit {condition}, "
                "which refuses the class however well it scores"
            )

    strata = candidate.get("strata") or {}
    if not strata:
        problems.append(
            f"{name}: activates no stratum, so nothing about it has been scored"
        )
    for stratum in sorted(strata):
        problems += _stratum_problems(name, stratum, strata[stratum])
    return problems


def _stratum_problems(name, stratum, counts):
    """One activated stratum against the floor, or against the reasons it cannot be rated.

    Each stratum is judged alone.
    A large stratum clearing the floor does not carry a small one that fails it,
    which pooling them into a single rate would let it do.
    """
    where = f"{name} on {stratum}"
    rules = REPAIR_ADMISSION["reportable"]
    scored = counts.get("scored", 0)
    acceptable = counts.get("acceptable", 0)
    ambiguous = counts.get("ambiguous", 0)
    labeled = counts.get("labeled", scored + ambiguous)
    if acceptable > scored:
        return [
            f"{where}: {acceptable} acceptable repairs on {scored} scored units, "
            "which is not a proportion"
        ]

    interval = wilson(acceptable, scored)
    withheld = []
    if scored < rules["min_scored"]:
        withheld.append(f"fewer than {rules['min_scored']} scored units")
    if interval and (interval[1] - interval[0]) / 2 > rules["max_interval_half_width"]:
        withheld.append(
            f"interval wider than {round(rules['max_interval_half_width'] * 100)} points"
        )
    if ambiguous > rules["max_ambiguous_fraction"] * labeled:
        withheld.append("more than a quarter of the labels are ambiguous")
    if withheld:
        return [
            f"{where}: {acceptable} of {scored} and no rate, "
            f"because {'; '.join(withheld)}; "
            "an activated stratum the round cannot rate refuses the class"
        ]

    if interval[0] < REPAIR_ADMISSION["floor"]:
        return [
            f"{where}: {acceptable} of {scored} is {acceptable / scored:.3f}, "
            f"and its lower bound of {interval[0]:.3f} is below the floor of "
            f"{REPAIR_ADMISSION['floor']:.2f}"
        ]
    return []


# --- what a repair is, as an object two repairs can be compared as ---------

RepairWindow = collections.namedtuple(
    "RepairWindow", "records form prose bounds breaks above below"
)


def collapsed(prose):
    """One text with every internal whitespace run reduced to a single space.

    Every offset in this module is measured in this coordinate system.
    A repair that only changes a gap from two spaces to one has moved no break,
    and a coordinate system that said otherwise would report it as one.
    """
    return " ".join(prose.split())


def repair_window(records, index):
    """The one or two judged lines a repair replaces.

    The shipped suggestion replaces the anchor alone,
    and the population says that is the wrong window for most of it:
    most units in the stratum a period widening activates carry a `wrap` too,
    and the shipped rule is that the rejoin comes before the split.
    So the window is the anchor and the line beneath it.

    A finding on the last judged line of a paragraph has no line beneath it.
    `diagnose` requires no successor, and dropping those findings would be silent,
    so the one-line form is explicit and the lower line must share the anchor's paragraph.

    Takes the whole walk and a position rather than one record,
    because finding the neighbour by line number would rescan the walk once per unit,
    and a source is enumerated a few thousand units at a time.
    """
    above = records[index]
    below = records[index + 1] if index + 1 < len(records) else None
    if below is not None and below["paragraph"] != above["paragraph"]:
        below = None
    members = (above,) if below is None else (above, below)
    bounds, at = [], 0
    for record in members:
        length = len(collapsed(record["prose"]))
        bounds.append((at, at + length))
        at += length + 1
    return RepairWindow(
        records=members,
        form="one-line" if below is None else "two-line",
        prose=" ".join(record["prose"] for record in members),
        bounds=tuple(bounds),
        breaks=_breaks_of(members),
        above=tuple(record["prose"] for record in records[:index]),
        below=tuple(record["prose"] for record in records[index + len(members) :]),
    )


def written(replacement):
    """The lines of a replacement that carry text, which are the ones a walk can return."""
    return [line for line in replacement if line.strip()]


def _breaks_of(records):
    """Where a run of judged lines breaks, as offsets into their joined prose."""
    offsets, at = [], 0
    for record in records[:-1]:
        at += len(collapsed(record["prose"]))
        offsets.append(at)
        at += 1
    return tuple(offsets)


def splice(window, replacement, text):
    """The file with the window's raw lines replaced by the ones a repair wrote.

    The terminator is the window's own, which is what keeps a CRLF file a CRLF file.
    A window at the end of a file with no final newline has none to reuse,
    and a multi-line repair there needs one, so it gets the ordinary newline.
    """
    first, last = window.records[0], window.records[-1]
    terminator = first["terminator"] or "\n"
    return (
        text[: first["raw_span"]["start"]]
        + terminator.join(replacement)
        + text[last["raw_span"]["end"] :]
    )


def normalize_repair(window, replacement, text, path):
    """Reduce a rewrite to the four facts that make two rewrites comparable.

    The replacement is spliced into the file and re-read through `judged_lines`.
    A list marker, an indent, a docstring, and a comment leader are all decided there.
    The detector decides them, rather than a second opinion about what a leader is.
    `_SUGGESTION_PREFIX_RE` could not do this job:
    it validates an already-separated prefix rather than finding one,
    and it rejects list markers on purpose,
    which is a stratum this corpus exists to score.

    `preserving`     the prose is the same text, differing only in where it breaks.
    `breaks`         where it now breaks, as offsets into the window's joined prose.
    `carrier_valid`  every produced line carries the leader and tail the rule allows.
    `intact`         re-reading yields judged prose lines in one paragraph,
                     and nothing outside the window changed what it is.

    `breaks` is None unless `preserving` and `intact` both hold,
    because an offset into prose that no longer matches is not an offset into anything.
    The original window is a point in this space,
    so leaving the line alone is an answer the corpus can represent rather than a hole.
    """
    import check_linefeeds

    spliced = splice(window, replacement, text)
    walked = check_linefeeds.judged_lines(spliced, path)
    if walked is None:
        return {
            "preserving": False,
            "breaks": None,
            "carrier_valid": False,
            "intact": False,
        }
    produced_all, _suppressions = walked
    produced = _produced_window(window, produced_all)
    # One judged line per non-blank line the repair wrote.
    # A line that stopped being prose — code without its comment marker, a table row,
    # a standalone directive — leaves the walk without leaving a gap in it,
    # and counting is what notices.
    # A blank line is not counted here because it is not lost:
    # it splits the paragraph, which `_produced_window` refuses on its own terms.
    intact = produced is not None and len(produced) == len(written(replacement))
    preserving = bool(intact) and collapsed(
        " ".join(record["prose"] for record in produced)
    ) == collapsed(window.prose)
    return {
        "preserving": preserving,
        "breaks": _breaks_of(produced) if (intact and preserving) else None,
        "carrier_valid": bool(intact) and carrier_valid(window, replacement, produced),
        "intact": intact,
    }


def _produced_window(window, records):
    """The judged lines the replacement produced, or None when the file stopped matching.

    Two halves, and the second is the one that catches a fence.
    A replacement that opens a code fence leaves its own lines looking like prose
    and takes every line below it out of the walk,
    so a check that looked only at the window would pass.
    """
    above, below = len(window.above), len(window.below)
    if len(records) < above + below + 1:
        return None
    proses = [record["prose"] for record in records]
    if tuple(proses[:above]) != window.above:
        return None
    if below and tuple(proses[len(proses) - below :]) != window.below:
        return None
    produced = records[above : len(records) - below]
    if len({record["paragraph"] for record in produced}) != 1:
        return None
    return produced


def carrier_valid(window, replacement, produced):
    """Whether every leader and tail stayed where the rule puts it.

    A line produced by splitting one original line carries that line's leader,
    byte for byte.
    A line that absorbed another drops the absorbed line's leader and keeps no trace of it.
    A tail stays on the line it belonged to and never moves across a break,
    so an original line whose tail would land mid-line must have had no tail to move.
    And a repair does not write its own line terminators.

    A repair that preserves the prose and breaks this rule is a defect, not a variant,
    and the admission contract refuses a class on one occurrence of it.
    """
    if any("\n" in line or "\r" in line for line in replacement):
        return False
    if len(produced) != len(written(replacement)):
        # The rule describes lines the detector judges as lines.
        # A line the repair wrote that is not one of those is not valid under it.
        return False
    if any(record["leader"] is None for record in produced):
        return False

    owners, at = [], 0
    for record in produced:
        length = len(collapsed(record["prose"]))
        owners.append(
            [
                index
                for index, (start, end) in enumerate(window.bounds)
                if start < at + length and at < end
            ]
        )
        at += length + 1
    if not all(owners):
        return False

    for record, owned in zip(produced, owners):
        source = window.records[owned[0]]
        if source["leader"] is None or record["leader"] != source["leader"]:
            return False
        for absorbed in owned[1:]:
            leader = window.records[absorbed]["leader"]
            # Searched past the produced line's own leader.
            # A rejoin inside a blockquote keeps one `>` legitimately,
            # and looking at the whole raw line would read that one as the absorbed one.
            body = record["raw"][len(record["leader"]) :]
            if leader and leader.strip() and leader.strip() in body:
                return False

    # Which produced line each original line's prose ends on, when one does.
    ends = {}
    for index, source in enumerate(window.records):
        carrying = [i for i, owned in enumerate(owners) if index in owned]
        if not carrying:
            return False
        last = carrying[-1]
        if owners[last][-1] == index:
            ends[last] = index
        elif (source["tail"] and source["tail"].strip()) or source["carrier"]:
            # It would have to sit in the middle of a rejoined line, so it cannot move.
            return False

    for position, record in enumerate(produced):
        source = window.records[ends[position]] if position in ends else None
        if _carrier_text(record) != (_carrier_text(source) if source else None):
            # A carrier deleted by a repair silences nothing and unsilences a line,
            # and a carrier a repair invented is a suppression nobody authorized.
            return False
        if source is not None:
            if record["tail"] != source["tail"]:
                return False
        elif record["tail"] and record["tail"].strip():
            return False
    return True


def _carrier_text(record):
    """The exact bytes of a line's suppression carrier, or None where it has none."""
    return record["carrier"]["text"] if record["carrier"] else None


def compose(window, lines):
    """An anchor-only algorithm's output, as a replacement for the whole window.

    `_fused_suggestion` returns two lines replacing the anchor
    and says nothing about the line below, so scoring it here keeps that line as it is.
    From `original_raw` rather than `raw`:
    the judged view has had any suppression carrier taken off it,
    and splicing that view back would delete the carrier from the file.
    """
    if window.form == "one-line":
        return list(lines)
    return list(lines) + [window.records[1]["original_raw"]]


def manifest_problems(document):
    """Everything wrong with a manifest, named by unit rather than counted.

    A gate that reports a number tells a reader to go looking;
    a gate that reports `c-0417: expected status missing` tells them where.
    """
    problems = [
        f"the manifest has no {name} section"
        for name in SECTIONS
        if name not in document
    ]
    problems += _reporting_problems(document.get("reporting", {}))
    problems += _repair_admission_problems(document.get("repair_admission", {}))
    defined = document.get("covariate_definitions", {})
    problems += [
        f"dimension {name} is recorded on units but never defined"
        for name in COVARIATES
        if not defined.get(name)
    ]
    for source in document.get("sources", []):
        problems += _source_problems(source)
    declared = {source["id"] for source in document.get("sources", [])}
    frames = set(document.get("frames", {}))
    for record in document.get("units", []):
        problems += _unit_problems(record, declared, frames)
    return problems


def _reporting_problems(reporting):
    """The bar below which no rate is printed, checked rather than merely recorded.

    Recording the rules in the manifest is what lets a reviewer reproduce a rate.
    Checking them here is what stops a level from being made reportable after its rate is known.
    """
    return [
        f"reporting rule {name} is {reporting.get(name)!r}, "
        f"and the frozen value is {value!r}"
        for name, value in REPORTING.items()
        if reporting.get(name) != value
    ]


def _repair_admission_problems(section):
    """The manifest's copy of the admission contract against the frozen one.

    Clause by clause rather than as one comparison,
    because a reader who is told the contract moved still has to find out where.
    The frozen side is round-tripped through JSON first:
    the manifest can only hold what JSON holds,
    and a tuple in code would differ from the list it was written as.
    """
    frozen = json.loads(json.dumps(REPAIR_ADMISSION))
    problems = [
        f"repair admission clause {name} is missing from the manifest"
        if name not in section
        else f"repair admission clause {name} does not match the frozen contract"
        for name, value in sorted(frozen.items())
        if section.get(name) != value
    ]
    problems += [
        f"repair admission clause {name} is in the manifest "
        "and not in the frozen contract"
        for name in sorted(section)
        if name not in frozen
    ]
    return problems


def _source_problems(source):
    name = source.get("id", "<unnamed source>")
    problems = [
        f"source {name} records no {field}"
        for field in SOURCE_FIELDS
        if not source.get(field)
    ]
    if source.get("side") not in ("calibration", "holdout"):
        problems.append(
            f"source {name} is on side {source.get('side')!r}, "
            "and calibration and holdout stay separate"
        )
    elif source["side"] == "holdout" and not isinstance(source.get("round"), int):
        # A holdout source is spent once the round that drew it has been opened and read.
        # Without a round on the source, a later draw enumerates the spent ones too
        # and scores a predicate against prose its repairs were fitted to.
        problems.append(
            f"source {name} is a holdout source and declares no round, "
            "so a later draw cannot tell it from a spent one"
        )
    if source.get("composition") not in COMPOSITIONS:
        problems.append(f"source {name} has composition {source.get('composition')!r}")
    elif source["composition"].startswith("third-party"):
        if source.get("license") not in PERMISSIVE:
            problems.append(
                f"source {name} vendors text under {source.get('license')!r}, "
                f"and only {', '.join(sorted(PERMISSIVE))} may be stored here"
            )
        problems += [
            f"source {name} records no {field}, "
            "and a third-party source qualifies on that measurement alone"
            for field in QUALIFICATION
            if not source.get(field)
        ]
    return problems


def _unit_problems(record, declared_sources, declared_frames):
    unit = record.get("id", "<unnamed unit>")
    problems = []
    if record.get("source") not in declared_sources:
        problems.append(
            f"{unit}: source {record.get('source')!r} is not declared in the manifest"
        )
    if record.get("frame") not in declared_frames:
        problems.append(
            f"{unit}: frame {record.get('frame')!r} is not declared in the manifest"
        )
    for name in COVARIATES:
        if name not in record.get("covariates", {}):
            problems.append(f"{unit}: covariate {name} is missing")

    settled = resolution(sorted(record.get("passes", {}).values()))
    label = record.get("label")
    if settled == "adjudicated":
        if not record.get("adjudication"):
            problems.append(
                f"{unit}: a refuted unit needs a recorded adjudication reason"
            )
        if label not in LABELS:
            problems.append(f"{unit}: label {label!r} is not one of {LABELS}")
    else:
        if label != settled:
            problems.append(
                f"{unit}: label {label!r} contradicts what the passes settle on ({settled!r})"
            )
        if record.get("adjudication"):
            problems.append(f"{unit}: adjudication recorded for a unit nobody refuted")

    if record.get("question") not in KINDS:
        problems.append(
            f"{unit}: question {record.get('question')!r} is not one of {KINDS}"
        )

    if label == "true":
        if record.get("expected") not in ("detected", "accepted_miss"):
            problems.append(
                f"{unit}: a true violation must carry a frozen expected status"
            )
    elif record.get("expected") is not None:
        problems.append(
            f"{unit}: only a true violation carries an expected status, "
            "and rates exclude this unit"
        )
    return problems


def _freeze_id(record):
    """The canonical id of a pre-draw freeze: the digest of the record without its id.

    Deriving the id from the content is what lets a reader check it.
    An id chosen freely would be a label a hand-written record could copy.
    """
    return _digest(
        json.dumps(
            {name: value for name, value in record.items() if name != "id"},
            sort_keys=True,
        ).encode("utf-8")
    )


class Holdout:
    """One sealed bundle, plus the append-only ledger that decides whether it opens."""

    def __init__(self, bundle, ledger, predicate, manifest, round=None):
        self.bundle = bundle
        self.ledger = ledger
        self.predicate = predicate
        self.manifest = manifest
        # The round a draw or a seal is acting for.
        # `open` and `record_evaluation` never need it:
        # they answer to the bundle's own freeze, which binds a ciphertext.
        self.round = round

    def freeze_predicate(self, intent):
        """Commit to a predicate, for one round, before its prose has been drawn.

        The freeze that binds a bundle can only be written once the bundle exists,
        which is after the sample was drawn, labeled, and sealed.
        By then the predicate has had every opportunity to be fitted to the prose,
        and a record written at that point proves only that nobody edited it during the sealing.

        This record is the one that carries the claim.
        It names a predicate and nothing else that has been read yet,
        and the draw refuses to run without it.

        It carries a round and an id because naming a predicate is not enough.
        Without the round, a freeze written for one round authorizes any other.
        Without the id, nothing ties the sample to the record it was drawn under,
        so a predicate could be frozen, drawn against, tuned once the prose had been read,
        frozen again, and sealed against the second freeze with nothing objecting.
        """
        if self.round is None:
            raise ScoringRefused(
                "a pre-draw freeze names the round it is for; this one names no round"
            )
        # A round whose bundle exists has been drawn, and usually labeled and sealed.
        # Appending a pre-draw record for it would write a commitment dated after the prose,
        # which is the one thing this record exists to make impossible.
        if self.bundle.exists():
            raise ScoringRefused(
                f"round {self.round} already holds a bundle; "
                "a pre-draw freeze written now would postdate the prose it claims to predict"
            )
        record = {
            "record": "predicate_freeze",
            "round": self.round,
            "predicate_digest": self._predicate_digest(),
            "manifest_digest": self._manifest_digest(),
            "intent": intent,
        }
        # One pre-draw freeze per round.
        # A second one is how a predicate read the prose and then committed to itself.
        for earlier in self._predicate_freezes():
            if earlier.get("round") == self.round:
                raise ScoringRefused(
                    f"round {self.round} was already frozen, for: {earlier['intent']}; "
                    "a round that needs a second predicate needs a new round"
                )
        record["id"] = _freeze_id(record)
        self._append(record)
        return record

    def _predicate_freezes(self):
        """Every modern pre-draw record, refusing the whole ledger if any invariant is broken.

        The writer keeps one record per round and hashes each record into its own id.
        A reader that only filters on those fields trusts them,
        and the ledger is a text file: a record can be appended by hand.
        Two hand-written shapes defeat a trusting reader.
        A second record for a round lets a predicate be committed to after its prose was read.
        A second record reusing the first one's id does the same without the sample being touched,
        because the sample names an id and two records would answer to it.

        So the invariants are checked here rather than assumed:
        an id is the digest of its own record, ids are unique, and a round has one record.
        A violation refuses the operation instead of selecting whichever record fits,
        because selecting is exactly what an appended record is written to exploit.

        Records with no round predate the rule and are not returned.
        `require_predicate_freeze` reports them separately;
        they are never honoured, so their shape is not policed here.
        """
        modern, by_round, by_id = [], {}, {}
        for record in self._records():
            if record.get("record") != "predicate_freeze" or "round" not in record:
                continue
            claimed = record.get("id")
            if claimed != _freeze_id(record):
                raise ScoringRefused(
                    f"a pre-draw record for round {record['round']} carries an id "
                    "that is not the digest of its own content; the ledger was edited by hand"
                )
            if claimed in by_id:
                raise ScoringRefused(
                    f"two pre-draw records share the id {claimed}; "
                    "a sample naming that id would answer to either of them"
                )
            if record["round"] in by_round:
                raise ScoringRefused(
                    f"round {record['round']} carries two pre-draw records; "
                    "a round is frozen once, and the second record is the one "
                    "written after the prose was read"
                )
            by_id[claimed] = record
            by_round[record["round"]] = record
            modern.append(record)
        return modern

    def require_predicate_freeze(self, drawn_under=None):
        """The record this round was frozen under, or a refusal naming what is missing.

        The manifest digest is recorded on the freeze and not compared here.
        A sample is drawn before its floors are stated,
        so the manifest is expected to move between this record and the bundle's own freeze;
        the predicate is the thing that may not.

        `drawn_under` is the record id the sample recorded at draw time.
        Passing it is what turns "some freeze names this predicate" into
        "the freeze this prose was drawn under names this predicate".
        A sealed round passes it; a draw has nothing to pass yet.

        A record with no round is from rounds 1 to 3, which were written before this rule.
        Accepted records are never edited, so those stand as they are,
        and this path refuses them rather than guessing which round they meant.
        Opening and scoring those bundles is unaffected:
        both answer to the bundle's own freeze, which binds a ciphertext.
        """
        digest = self._predicate_digest()
        for_round = [
            record
            for record in self._predicate_freezes()
            if record["round"] == self.round
        ]
        if not for_round:
            legacy = [
                record
                for record in self._records()
                if record.get("record") == "predicate_freeze" and "round" not in record
            ]
            if legacy:
                raise ScoringRefused(
                    f"no freeze record names round {self.round}; "
                    f"{len(legacy)} record(s) predate the round rule and authorize nothing, "
                    "because a freeze that names no round would authorize every round"
                )
            raise ScoringRefused(
                f"no freeze record names round {self.round}; "
                "freeze it before drawing the prose it will be scored against"
            )
        if drawn_under is not None:
            for_round = [
                record for record in for_round if record.get("id") == drawn_under
            ]
            if not for_round:
                raise ScoringRefused(
                    "the sample was drawn under a freeze this ledger does not hold; "
                    "nothing may be sealed against a freeze the prose never saw"
                )
        for record in for_round:
            if record["predicate_digest"] == digest:
                return record
        raise ScoringRefused(
            "the predicate changed since the freeze this round was drawn under; "
            "a tuned predicate needs a new round"
        )

    def seal(self, text, passphrase, drawn_under=None):
        """Write the ciphertext bundle.

        The plaintext never reaches the working tree.

        Sealing is refused for an unfrozen predicate,
        and for a predicate that is not the one the prose was drawn under.
        The first round got the ordering right by care,
        and care is not a mechanism.
        """
        self.require_predicate_freeze(drawn_under)
        salt = os.urandom(16)
        mask_key, tag_key = _keys(passphrase, salt, KDF_ITERATIONS)
        ciphertext = _mask(text.encode("utf-8"), mask_key)
        self.bundle.write_text(
            json.dumps(
                {
                    "kdf": "pbkdf2-hmac-sha256",
                    "iterations": KDF_ITERATIONS,
                    "salt": base64.b64encode(salt).decode("ascii"),
                    "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
                    "tag": base64.b64encode(
                        hmac.new(tag_key, ciphertext, hashlib.sha256).digest()
                    ).decode("ascii"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def freeze(self, reporting_rules):
        """Commit to a predicate, a calibration manifest, and a bundle, before seeing any of it."""
        self._append(
            {
                "record": "freeze",
                "predicate_digest": self._predicate_digest(),
                "manifest_digest": self._manifest_digest(),
                "ciphertext_digest": self._ciphertext_digest(),
                "reporting_rules": reporting_rules,
            }
        )

    def open(self, passphrase):
        """Return the sealed text, or refuse and say which rule refused."""
        self._require_freeze()
        self._require_unspent()
        return self._decrypt(passphrase)

    def record_evaluation(self, result):
        """Spend this bundle, against the freeze record it answers."""
        frozen = self._require_freeze()
        self._require_unspent()
        self._append(
            {
                "record": "evaluation",
                "predicate_digest": frozen["predicate_digest"],
                "manifest_digest": frozen["manifest_digest"],
                "ciphertext_digest": frozen["ciphertext_digest"],
                "reporting_rules": frozen["reporting_rules"],
                "result": result,
            }
        )

    def _require_freeze(self):
        """The matching freeze record, or a refusal that names what moved.

        A refusal an operator cannot act on gets worked around,
        so a stale predicate and a missing record must not read the same.
        """
        ciphertext = self._ciphertext_digest()
        frozen = [
            record
            for record in self._records()
            if record.get("record") == "freeze"
            and record["ciphertext_digest"] == ciphertext
        ]
        if not frozen:
            raise ScoringRefused("no freeze record names this bundle")
        predicate, manifest = self._predicate_digest(), self._manifest_digest()
        for record in frozen:
            if (
                record["predicate_digest"] == predicate
                and record["manifest_digest"] == manifest
            ):
                return record
        if not any(record["predicate_digest"] == predicate for record in frozen):
            raise ScoringRefused(
                "the predicate changed since the freeze; a tuned predicate needs a new holdout"
            )
        raise ScoringRefused("the calibration manifest changed since the freeze")

    def _require_unspent(self):
        ciphertext = self._ciphertext_digest()
        for record in self._records():
            if (
                record.get("record") == "evaluation"
                and record["ciphertext_digest"] == ciphertext
            ):
                raise ScoringRefused(
                    "this bundle has already been evaluated; scoring again needs a new holdout"
                )

    def _decrypt(self, passphrase):
        bundle = json.loads(self.bundle.read_text(encoding="utf-8"))
        ciphertext = base64.b64decode(bundle["ciphertext"])
        mask_key, tag_key = _keys(
            passphrase, base64.b64decode(bundle["salt"]), bundle["iterations"]
        )
        tag = hmac.new(tag_key, ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, base64.b64decode(bundle["tag"])):
            raise ScoringRefused("the passphrase does not open this bundle")
        return _mask(ciphertext, mask_key).decode("utf-8")

    def _records(self):
        if not self.ledger.exists():
            return []
        return [
            json.loads(line)
            for line in self.ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _append(self, record):
        with self.ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _predicate_digest(self):
        return file_digest(self.predicate)

    def _manifest_digest(self):
        return file_digest(self.manifest)

    def _ciphertext_digest(self):
        bundle = json.loads(self.bundle.read_text(encoding="utf-8"))
        return _digest(base64.b64decode(bundle["ciphertext"]))
