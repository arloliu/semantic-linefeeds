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
COVARIATES = ("prose_width", "raw_end_column", "indentation_depth", "language",
              "markdown_nesting", "trailing_inline_markup", "list_item_adjacency",
              "paragraph_line_count", "eligible_anchor_count")

SECTIONS = ("schema_version", "rubric", "reporting", "covariate_definitions",
            "eligible_anchor", "frames", "protocol_notes", "sources", "units")

SOURCE_FIELDS = ("id", "side", "composition", "url", "commit", "license",
                 "selection_command")

# Both sides carry the same three compositions.
# A predicate calibrated only against one author's habits fails the holdout uninterpretably.
COMPOSITIONS = ("self-authored", "third-party-code", "third-party-markdown")

# Unit text is vendored into this repository, so the licence decides what may be stored at all.
PERMISSIVE = ("Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MIT")

# What a third-party source is admitted on.
# Selecting sources by finding density would repeat, at repository granularity,
# the error ADR-0003 forbids at candidate granularity.
QUALIFICATION = ("wrapping_column", "qualification")

# The dimensions a rate may be broken down by.
# Fixed here rather than in the manifest:
# a stratum the manifest can drop is a floor the manifest can drop.
REPORTED_STRATA = ("language", "markdown_nesting", "list_item_adjacency",
                   "trailing_inline_markup", "indentation_depth", "raw_end_column")

# Settled before any rate existed, and checked so that no rate can loosen them afterwards.
REPORTING = {
    "interval": "wilson-95",
    "min_true_violations": 10,
    "max_interval_half_width": 0.15,
    "max_ambiguous_fraction": 0.25,
}


class ScoringRefused(Exception):
    """The holdout may not be opened, and the message says which rule refused."""


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
        "sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)
    return (hmac.new(root, b"keystream", hashlib.sha256).digest(),
            hmac.new(root, b"tag", hashlib.sha256).digest())


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
    runs, current = [], []
    for lineno, raw, prose in stream:
        if prose is None or lineno <= _license_cut(text, path):
            if len(current) > 1:
                runs.append(current)
            current = []
            continue
        current.append(ProseLine(lineno, raw, prose))
    if len(current) > 1:
        runs.append(current)
    return runs


def _license_cut(text, path):
    """The last line of a leading licence region, which the checker also refuses to judge.

    A licence header is a never-break class.
    A unit drawn from one is a violation the detector is structurally unable to report,
    so it would sit in the denominator forever without any predicate ever reaching it.
    """
    import check_linefeeds

    if check_linefeeds.is_markdown(path):
        return 0
    lang = check_linefeeds.lang_for_path(path)
    return check_linefeeds.license_header_extent(text, lang) if lang else 0


def boundaries(text, path):
    """Every adjacent line boundary inside a paragraph, attributed to the upper line.

    Both kinds are labeled here.
    `wrap` is a property of the boundary and `fused` a property of the upper line,
    and one reading of the pair yields both labels.
    """
    return [Boundary(path, run[i], run[i + 1], run)
            for run in paragraphs(text, path)
            for i in range(len(run) - 1)]


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
    return {kind for lineno, kind, _, _ in check_linefeeds.check(text, "replay" + suffix)
            if lineno == upper}


def covariates(unit):
    """The nine dimensions recorded for every labeled unit.

    Quotas run on the structurally rare ones only.
    The rest arrive spread on their own,
    and all nine are recorded so a reader can recompute any cross without trusting this split.
    """
    import check_linefeeds

    raw = unit.upper.raw.rstrip()
    shown = raw.expandtabs(TAB_WIDTH)
    return {
        "prose_width": max(len(line.raw.rstrip().expandtabs(TAB_WIDTH))
                           for line in unit.paragraph),
        "raw_end_column": len(raw),
        "indentation_depth": len(shown) - len(shown.lstrip()),
        "language": _language(unit.path),
        "markdown_nesting": _nesting(unit),
        "trailing_inline_markup": unit.upper.prose.rstrip().endswith(tuple(TRAILING_MARKUP)),
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
    return sum(1 for i, char in enumerate(prose)
               if char == " "
               and len(prose[:i].strip()) >= ANCHOR_MIN_SIDE
               and len(prose[i + 1:].strip()) >= ANCHOR_MIN_SIDE)


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
        raise ValueError(f"source {source['id']} selects files by an unrecognized command")
    return subprocess.run(["git", "-C", str(root), "ls-files"] + words[2:],
                          capture_output=True, text=True, check=True).stdout.split()


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
            window = unit.paragraph[start:first + CONTEXT + 2]
            out.append({
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
            })
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
    chosen = {record["id"]: record
              for record in _rng(seed, "base").sample(pool, min(base, len(pool)))}
    for dimension, (bands, per_level) in sorted(quotas.items()):
        members = collections.defaultdict(list)
        for record in pool:
            members[level_of(record, dimension, bands)].append(record)
        for level, at_level in sorted(members.items()):
            short = per_level - sum(1 for r in at_level if r["id"] in chosen)
            if short <= 0:
                continue
            rest = [r for r in at_level if r["id"] not in chosen]
            for record in _rng(seed, dimension, level).sample(rest, min(short, len(rest))):
                chosen[record["id"]] = record
    return sorted(chosen.values(), key=lambda record: record["id"])


def band_levels(bands):
    """Every level a set of band edges names, whether or not the population reaches it."""
    edges = list(bands)
    return tuple([f"..{edges[0]}"]
                 + [f"{low + 1}..{high}" for low, high in zip(edges, edges[1:])]
                 + [f"{edges[-1] + 1}.."])


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
        wanted = (band_levels(bands) if bands
                  else sorted({level_of(record, dimension, None) for record in population}))
        present = {level_of(record, dimension, bands) for record in population}
        if len(present) < 2:
            held = sorted(present)[0] if present else "nothing"
            problems.append("%s: the population holds %s%s, so the quota separates nothing"
                            % (dimension, "only " if present else "", held))
            continue
        counts = collections.Counter(level_of(record, dimension, bands) for record in drawn)
        problems += ["%s at %s: %d of %d" % (dimension, level, counts[level], per_level)
                     for level in wanted if counts[level] < per_level]
    return problems


def labeling_batches(sample, labeler, size):
    """One labeler's units, in an order of their own, in bounded batches.

    Order is randomized per labeler so that fatigue and drift do not line up across passes,
    and batches are bounded because a labeler judging a hundred units at a sitting drifts inside it.
    """
    order = sorted(sample, key=lambda record: record["id"])
    _rng(labeler).shuffle(order)
    return [order[i:i + size] for i in range(0, len(order), size)]


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
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
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
        counts = levels.setdefault(level, {"true": 0, "detected": 0, "ambiguous": 0, "labeled": 0})
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
                "fewer than %d true violations" % REPORTING["min_true_violations"])
        if interval and (interval[1] - interval[0]) / 2 > REPORTING["max_interval_half_width"]:
            withheld.append("interval wider than %d points"
                            % round(REPORTING["max_interval_half_width"] * 100))
        if counts["ambiguous"] > REPORTING["max_ambiguous_fraction"] * counts["labeled"]:
            withheld.append("more than a quarter of the labels are ambiguous")
        report[level] = dict(
            counts,
            interval=interval,
            withheld=tuple(withheld),
            rate=None if withheld or not interval else counts["detected"] / counts["true"],
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
            where = kind if not dimension else "%s at %s %s" % (kind, dimension, level)
            counts = report.get(level)
            if counts is None:
                problems.append("%s: a floor of %.2f, and nothing labeled there" % (where, floor))
            elif counts["rate"] is None:
                problems.append("%s: a floor of %.2f, and no rate to hold it — %s"
                                % (where, floor, "; ".join(counts["withheld"])))
            elif counts["rate"] < floor:
                problems.append("%s: %d of %d is %.3f, below the floor of %.2f"
                                % (where, counts["detected"], counts["true"], counts["rate"], floor))
    return problems


def manifest_problems(document):
    """Everything wrong with a manifest, named by unit rather than counted.

    A gate that reports a number tells a reader to go looking;
    a gate that reports `c-0417: expected status missing` tells them where.
    """
    problems = [f"the manifest has no {name} section"
                for name in SECTIONS if name not in document]
    problems += _reporting_problems(document.get("reporting", {}))
    defined = document.get("covariate_definitions", {})
    problems += [f"dimension {name} is recorded on units but never defined"
                 for name in COVARIATES if not defined.get(name)]
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
    return [f"reporting rule {name} is {reporting.get(name)!r}, "
            f"and the frozen value is {value!r}"
            for name, value in REPORTING.items() if reporting.get(name) != value]


def _source_problems(source):
    name = source.get("id", "<unnamed source>")
    problems = [f"source {name} records no {field}"
                for field in SOURCE_FIELDS if not source.get(field)]
    if source.get("side") not in ("calibration", "holdout"):
        problems.append(f"source {name} is on side {source.get('side')!r}, "
                        "and calibration and holdout stay separate")
    if source.get("composition") not in COMPOSITIONS:
        problems.append(f"source {name} has composition {source.get('composition')!r}")
    elif source["composition"].startswith("third-party"):
        if source.get("license") not in PERMISSIVE:
            problems.append(f"source {name} vendors text under {source.get('license')!r}, "
                            f"and only {', '.join(sorted(PERMISSIVE))} may be stored here")
        problems += [f"source {name} records no {field}, "
                     "and a third-party source qualifies on that measurement alone"
                     for field in QUALIFICATION if not source.get(field)]
    return problems


def _unit_problems(record, declared_sources, declared_frames):
    unit = record.get("id", "<unnamed unit>")
    problems = []
    if record.get("source") not in declared_sources:
        problems.append(f"{unit}: source {record.get('source')!r} is not declared in the manifest")
    if record.get("frame") not in declared_frames:
        problems.append(f"{unit}: frame {record.get('frame')!r} is not declared in the manifest")
    for name in COVARIATES:
        if name not in record.get("covariates", {}):
            problems.append(f"{unit}: covariate {name} is missing")

    settled = resolution(sorted(record.get("passes", {}).values()))
    label = record.get("label")
    if settled == "adjudicated":
        if not record.get("adjudication"):
            problems.append(f"{unit}: a refuted unit needs a recorded adjudication reason")
        if label not in LABELS:
            problems.append(f"{unit}: label {label!r} is not one of {LABELS}")
    else:
        if label != settled:
            problems.append(
                f"{unit}: label {label!r} contradicts what the passes settle on ({settled!r})")
        if record.get("adjudication"):
            problems.append(f"{unit}: adjudication recorded for a unit nobody refuted")

    if record.get("question") not in KINDS:
        problems.append(f"{unit}: question {record.get('question')!r} is not one of {KINDS}")

    if label == "true":
        if record.get("expected") not in ("detected", "accepted_miss"):
            problems.append(
                f"{unit}: a true violation must carry a frozen expected status")
    elif record.get("expected") is not None:
        problems.append(
            f"{unit}: only a true violation carries an expected status, "
            "and rates exclude this unit")
    return problems


class Holdout:
    """One sealed bundle, plus the append-only ledger that decides whether it opens."""

    def __init__(self, bundle, ledger, predicate, manifest):
        self.bundle = bundle
        self.ledger = ledger
        self.predicate = predicate
        self.manifest = manifest

    def seal(self, text, passphrase):
        """Write the ciphertext bundle.

        The plaintext never reaches the working tree.
        """
        salt = os.urandom(16)
        mask_key, tag_key = _keys(passphrase, salt, KDF_ITERATIONS)
        ciphertext = _mask(text.encode("utf-8"), mask_key)
        self.bundle.write_text(json.dumps({
            "kdf": "pbkdf2-hmac-sha256",
            "iterations": KDF_ITERATIONS,
            "salt": base64.b64encode(salt).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "tag": base64.b64encode(
                hmac.new(tag_key, ciphertext, hashlib.sha256).digest()).decode("ascii"),
        }, indent=2) + "\n", encoding="utf-8")

    def freeze(self, reporting_rules):
        """Commit to a predicate, a calibration manifest, and a bundle, before seeing any of it."""
        self._append({
            "record": "freeze",
            "predicate_digest": self._predicate_digest(),
            "manifest_digest": self._manifest_digest(),
            "ciphertext_digest": self._ciphertext_digest(),
            "reporting_rules": reporting_rules,
        })

    def open(self, passphrase):
        """Return the sealed text, or refuse and say which rule refused."""
        self._require_freeze()
        self._require_unspent()
        return self._decrypt(passphrase)

    def record_evaluation(self, result):
        """Spend this bundle, against the freeze record it answers."""
        frozen = self._require_freeze()
        self._require_unspent()
        self._append({
            "record": "evaluation",
            "predicate_digest": frozen["predicate_digest"],
            "manifest_digest": frozen["manifest_digest"],
            "ciphertext_digest": frozen["ciphertext_digest"],
            "reporting_rules": frozen["reporting_rules"],
            "result": result,
        })

    def _require_freeze(self):
        """The matching freeze record, or a refusal that names what moved.

        A refusal an operator cannot act on gets worked around,
        so a stale predicate and a missing record must not read the same.
        """
        ciphertext = self._ciphertext_digest()
        frozen = [record for record in self._records()
                  if record.get("record") == "freeze"
                  and record["ciphertext_digest"] == ciphertext]
        if not frozen:
            raise ScoringRefused("no freeze record names this bundle")
        predicate, manifest = self._predicate_digest(), self._manifest_digest()
        for record in frozen:
            if (record["predicate_digest"] == predicate
                    and record["manifest_digest"] == manifest):
                return record
        if not any(record["predicate_digest"] == predicate for record in frozen):
            raise ScoringRefused(
                "the predicate changed since the freeze; a tuned predicate needs a new holdout")
        raise ScoringRefused("the calibration manifest changed since the freeze")

    def _require_unspent(self):
        ciphertext = self._ciphertext_digest()
        for record in self._records():
            if (record.get("record") == "evaluation"
                    and record["ciphertext_digest"] == ciphertext):
                raise ScoringRefused(
                    "this bundle has already been evaluated; scoring again needs a new holdout")

    def _decrypt(self, passphrase):
        bundle = json.loads(self.bundle.read_text(encoding="utf-8"))
        ciphertext = base64.b64decode(bundle["ciphertext"])
        mask_key, tag_key = _keys(
            passphrase, base64.b64decode(bundle["salt"]), bundle["iterations"])
        tag = hmac.new(tag_key, ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, base64.b64decode(bundle["tag"])):
            raise ScoringRefused("the passphrase does not open this bundle")
        return _mask(ciphertext, mask_key).decode("utf-8")

    def _records(self):
        if not self.ledger.exists():
            return []
        return [json.loads(line)
                for line in self.ledger.read_text(encoding="utf-8").splitlines() if line.strip()]

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
