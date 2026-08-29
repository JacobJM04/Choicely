"""
Regret triggers: the conditions under which this person regrets decisions
more (or less) than they usually do.

Where the regret forecast asks "what kind of decision is this?", this asks
"what was going on when you made it?" -- time of day, time pressure, how
much was already on your plate that day, whether you'd been going back and
forth. It splits every closed decision along each axis and surfaces the
splits where the regret rate actually moves.

Same outcome scoring as the rest of the app (good 0.0 / neutral 0.5 /
regret 1.0). A split only counts as a trigger when both sides have enough
decisions behind them AND the gap is large enough to act on -- otherwise
it's noise, and Choicely says so rather than inventing a pattern.
"""
from collections import defaultdict
from datetime import datetime

_TS_FMT = "%Y-%m-%d %H:%M:%S"
_SCORE = {"regret": 1.0, "neutral": 0.5, "good": 0.0}

# A split needs at least this many decisions on each side, and the regret
# rates need to differ by at least this much with at least this ratio.
_MIN_SIDE = 4
_MIN_GAP = 0.18
_MIN_RATIO = 1.4

# (noun for headlines, phrase for mid-sentence, hour test)
_PARTS = [
    ("Mornings", "first thing in the morning", lambda h: 5 <= h < 9),
    ("Daytime", "during the day", lambda h: 9 <= h < 17),
    ("Evenings", "in the evening", lambda h: 17 <= h < 22),
    ("Late nights", "late at night", lambda h: h >= 22 or h < 5),
]

# What Choicely examined, for the "we checked, here's what we found" line.
CHECKED = [
    "time of day",
    "time pressure",
    "how much was already on your plate",
    "going back and forth",
    "stakes",
]


def _parse(ts):
    try:
        return datetime.strptime((ts or "")[:19], _TS_FMT)
    except ValueError:
        return None


def _resolved(rows):
    return [r for r in rows if r["outcome"] in _SCORE]


def _rate(rows):
    return sum(_SCORE[r["outcome"]] for r in rows) / len(rows) if rows else 0.0


def _pct(v):
    return round(v * 100)


def _trigger(dimension, headline_word, trigger_rows, contrast_rows, label, contrast_label, sentence_fn):
    if len(trigger_rows) < _MIN_SIDE or len(contrast_rows) < _MIN_SIDE:
        return None
    tr, cr = _rate(trigger_rows), _rate(contrast_rows)
    gap = tr - cr
    ratio = (tr / cr) if cr > 0 else (999.0 if tr > 0 else 1.0)
    worse = gap >= _MIN_GAP and ratio >= _MIN_RATIO
    inv_ratio = (cr / tr) if tr > 0 else (999.0 if cr > 0 else 1.0)
    better = gap <= -_MIN_GAP and inv_ratio >= _MIN_RATIO
    if not (worse or better):
        return None
    strength = abs(gap) * min(len(trigger_rows), len(contrast_rows)) ** 0.5
    shown_ratio = round(ratio if worse else inv_ratio, 1)
    return {
        "dimension": dimension,
        "direction": "worse" if worse else "better",
        "label": label,
        "contrast_label": contrast_label,
        "trigger_rate": tr,
        "contrast_rate": cr,
        "ratio": shown_ratio,
        "n_trigger": len(trigger_rows),
        "n_contrast": len(contrast_rows),
        "headline": _headline(dimension, worse, headline_word),
        "detail": sentence_fn(tr, cr, shown_ratio),
        "_strength": strength,
    }


def _headline(dimension, worse, headline_word):
    if dimension == "time_of_day":
        return f"{headline_word} are your weak spot" if worse else f"{headline_word} are your strong window"
    table = {
        "time_pressure": ("Deciding under pressure costs you", "Room to think pays off"),
        "load": ("Your busiest days cost you", "Lighter days, better calls"),
        "back_and_forth": ("Going back and forth doesn't help", "Quick calls serve you better"),
        "stakes": ("The high-stakes ones slip", "Routine calls, routine outcomes"),
    }
    pair = table.get(dimension, ("A pattern Choicely noticed", "A pattern Choicely noticed"))
    return pair[0] if worse else pair[1]


def _time_of_day(rows):
    buckets = defaultdict(list)
    phrases = {}
    for r in rows:
        ts = _parse(r["timestamp"])
        if not ts:
            continue
        for noun, phrase, test in _PARTS:
            if test(ts.hour):
                buckets[noun].append(r)
                phrases[noun] = phrase
                break
    eligible = {k: v for k, v in buckets.items() if len(v) >= _MIN_SIDE}
    if len(eligible) < 2:
        return []
    found = []
    for noun, part_rows in eligible.items():
        rest = [r for k, v in eligible.items() if k != noun for r in v]
        phrase = phrases[noun]

        def _s(tr, cr, ratio, _phrase=phrase):
            if tr >= cr:
                return (
                    f"Decisions you made {_phrase} ended in regret {_pct(tr)}% of the time, "
                    f"against {_pct(cr)}% the rest of the day -- about {ratio}x."
                )
            return (
                f"Your decisions {_phrase} land well {100 - _pct(tr)}% of the time, "
                f"versus {100 - _pct(cr)}% otherwise. Protect that window."
            )

        t = _trigger("time_of_day", noun, part_rows, rest, phrase, "the rest of the day", _s)
        if t:
            found.append(t)
    # Time of day can produce several splits at once; keep only the sharpest
    # "worse" window and the sharpest "better" one, so the panel isn't three
    # variations on the same theme.
    worse = max((t for t in found if t["direction"] == "worse"), key=lambda t: t["_strength"], default=None)
    better = max((t for t in found if t["direction"] == "better"), key=lambda t: t["_strength"], default=None)
    return [t for t in (worse, better) if t]


def _two_way(rows, dimension, predicate, label, contrast_label, sentence_fn):
    trig = [r for r in rows if predicate(r)]
    rest = [r for r in rows if not predicate(r)]
    t = _trigger(dimension, None, trig, rest, label, contrast_label, sentence_fn)
    return [t] if t else []


def _load(rows):
    by_day = defaultdict(int)
    for r in rows:
        ts = _parse(r["timestamp"])
        if ts:
            by_day[ts.date()] += 1
    if not by_day:
        return []
    heavy_days = {d for d, n in by_day.items() if n >= 4}
    light_days = {d for d, n in by_day.items() if n <= 2}

    def on_heavy(r):
        ts = _parse(r["timestamp"])
        return ts is not None and ts.date() in heavy_days

    def _s(tr, cr, ratio):
        return (
            f"On days you logged 4+ decisions, your regret rate was {_pct(tr)}% -- "
            f"about {ratio}x the {_pct(cr)}% on lighter days. Decision fatigue, showing up in your own data."
        )

    trig = [r for r in rows if on_heavy(r)]
    rest = []
    for r in rows:
        ts = _parse(r["timestamp"])
        if ts and ts.date() in light_days:
            rest.append(r)
    t = _trigger("load", None, trig, rest, "your busiest days", "lighter days", _s)
    return [t] if t else []


def regret_triggers(include_seed: bool = True) -> dict:
    from . import models

    rows = _resolved(models.list_decisions(include_seed=include_seed))
    analyzed = len(rows)
    baseline = _rate(rows)

    if analyzed < 8:
        return {
            "analyzed": analyzed,
            "min_analyzed": 8,
            "baseline_rate": baseline,
            "checked": CHECKED,
            "triggers": [],
            "verdict": "early",
        }

    candidates = []
    candidates += _time_of_day(rows)
    candidates += _two_way(
        rows,
        "time_pressure",
        lambda r: r["urgency"] == "high",
        "made under time pressure",
        "made with room to think",
        lambda tr, cr, ratio: (
            f"When you decided in a hurry, you regretted it {_pct(tr)}% of the time, "
            f"versus {_pct(cr)}% when you had room to think."
        ),
    )
    candidates += _load(rows)
    candidates += _two_way(
        rows,
        "back_and_forth",
        lambda r: (r["reopened_count"] or 0) >= 2,
        "you kept reopening",
        "you settled in one go",
        lambda tr, cr, ratio: (
            f"The decisions you reopened again and again ended in regret {_pct(tr)}% of the time -- "
            f"more than the ones you settled in one go ({_pct(cr)}%). Sitting with these isn't helping."
        ),
    )
    candidates += _two_way(
        rows,
        "stakes",
        lambda r: r["stakes"] == "high",
        "high-stakes",
        "routine",
        lambda tr, cr, ratio: (
            f"Your high-stakes decisions turn regretful {_pct(tr)}% of the time, "
            f"against {_pct(cr)}% for the routine ones."
        ),
    )

    candidates.sort(key=lambda c: c["_strength"], reverse=True)
    top = candidates[:3]
    for c in top:
        c.pop("_strength", None)

    return {
        "analyzed": analyzed,
        "min_analyzed": 8,
        "baseline_rate": baseline,
        "checked": CHECKED,
        "triggers": top,
        "verdict": "found" if top else "nothing_stood_out",
    }
