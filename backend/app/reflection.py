"""
Weekly reflection: a short, plain-language read on someone's recent
decisions -- the kind of thing a thoughtful friend would notice after
watching you for a couple of weeks.

Swappable seam: when ANTHROPIC_API_KEY is set, Claude reads a compact
serialization of the decision history and writes the insights. Without a
key, a set of heuristic generators computes candidate insights directly
from the data, scores them by how much signal they carry, and returns the
strongest few. Both paths return the same shape.

Design intent: specific (name the number), non-judgmental, and at least one
insight should be affirming when the data supports it -- this is a wellness
feature, not a nag.
"""
import json
import os
import re
from collections import defaultdict
from datetime import datetime

from . import dataset, models

_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
_TS_FMT = "%Y-%m-%d %H:%M:%S"

_REGRET = 1.0
_NEUTRAL = 0.5
_GOOD = 0.0
_SCORE = {"regret": _REGRET, "neutral": _NEUTRAL, "good": _GOOD}

_SPONTANEOUS_WORDS = ("skip", "skipping", "skipped", "cancel", "bail", "flake", "avoid", "quit")

# Dataset category labels are analytic ("going out despite low energy"); this
# turns them into something that reads naturally mid-sentence.
_PHRASE_OVERRIDES = {
    "sleep vs. social/obligation tradeoff": "trading sleep for something else",
    "going out despite low energy": "pushing yourself to go out when you're tired",
    "choosing to save/invest over spending": "saving instead of spending",
    "general health/routine decisions": "everyday health calls",
    "general social decisions": "everyday social calls",
    "general financial decisions": "everyday money calls",
    "general interpersonal decisions": "everyday people decisions",
    "general routine decisions": "everyday routine calls",
}


def _phrase(category_label: str) -> str:
    return _PHRASE_OVERRIDES.get(category_label, category_label)


def _parse(ts):
    try:
        return datetime.strptime((ts or "")[:19], _TS_FMT)
    except ValueError:
        return None


def _resolved(rows):
    return [r for r in rows if r["outcome"] in _SCORE]


# --- heuristic insight generators -------------------------------------------
# Each returns (insight_dict, score) or None. Higher score = more signal.


def _habit_insight(rows):
    by_cat = defaultdict(list)
    for r in _resolved(rows):
        if r["prior_category_label"]:
            by_cat[r["prior_category_label"]].append(r["outcome"])
    best = None
    for cat, outcomes in by_cat.items():
        n = len(outcomes)
        if n < 4:
            continue
        regret_rate = sum(_SCORE[o] for o in outcomes) / n
        if regret_rate >= 0.6:
            advice = _advice_for(cat, high=True)
            phrase = _phrase(cat)
            strength = regret_rate * n
            detail = (
                f"You've logged {phrase} {n} times, and regretted it "
                f"{round(regret_rate * 100)}% of the time."
            )
            if advice:
                detail += f" That's not really an open question anymore -- {advice}."
            candidate = ({
                "headline": f"You keep asking yourself about {phrase}",
                "detail": detail,
                "kind": "habit",
            }, strength)
            if best is None or candidate[1] > best[1]:
                best = candidate
    return best


def _affirming_insight(rows):
    by_cat = defaultdict(list)
    for r in _resolved(rows):
        if r["prior_category_label"]:
            by_cat[r["prior_category_label"]].append(r["outcome"])
    best = None
    for cat, outcomes in by_cat.items():
        n = len(outcomes)
        if n < 4:
            continue
        regret_rate = sum(_SCORE[o] for o in outcomes) / n
        if regret_rate <= 0.3:
            phrase = _phrase(cat)
            strength = (1 - regret_rate) * n
            candidate = ({
                "headline": f"You can trust your gut on {phrase}",
                "detail": (
                    f"{n} times now, and you were glad you did (or fine with it) "
                    f"{round((1 - regret_rate) * 100)}% of the time. This one doesn't need "
                    f"the deliberation you give it."
                ),
                "kind": "affirming",
            }, strength)
            if best is None or candidate[1] > best[1]:
                best = candidate
    return best


def _debt_insight(rows):
    topics = models.get_debt_topics(include_seed=True)
    if not topics:
        return None
    top = max(topics, key=lambda t: t["times_logged"])
    n = top["times_logged"]
    first = _parse(top["first_logged"])
    span = ""
    if first:
        days = max(1, (datetime.now() - first).days)
        span = f" over the last {days} days" if days > 1 else ""
    return ({
        "headline": "One question keeps coming back unanswered",
        "detail": (
            f"\"{top['canonical_text']}\" has come up {n} times{span} without a call. "
            f"Not deciding is also a decision -- and it might be the more expensive one."
        ),
        "kind": "debt",
    }, 4 + n)


def _stakes_latency_insight(rows):
    buckets = {"high": [], "low": []}
    for r in _resolved(rows):
        start, end = _parse(r["timestamp"]), _parse(r["outcome_recorded_at"])
        if not start or not end or end < start:
            continue
        hours = (end - start).total_seconds() / 3600
        if r["stakes"] in buckets:
            buckets[r["stakes"]].append(hours)
    if len(buckets["high"]) < 2 or len(buckets["low"]) < 2:
        return None
    high_avg = sum(buckets["high"]) / len(buckets["high"])
    low_avg = sum(buckets["low"]) / len(buckets["low"])
    if low_avg <= 0 or high_avg / low_avg < 2:
        return None
    ratio = round(high_avg / low_avg)
    return ({
        "headline": "The big decisions are the ones you leave hanging",
        "detail": (
            f"Your high-stakes decisions sit about {ratio}x longer before you close them "
            f"than your routine ones. The weight makes them harder to touch, not easier."
        ),
        "kind": "latency",
    }, 3 + ratio)


def _action_bias_insight(rows):
    skip_scores, other_scores = [], []
    for r in _resolved(rows):
        text = (r["text"] or "").lower()
        is_skip = any(re.search(rf"\b{w}\b", text) for w in _SPONTANEOUS_WORDS)
        (skip_scores if is_skip else other_scores).append(_SCORE[r["outcome"]])
    if len(skip_scores) < 3 or len(other_scores) < 3:
        return None
    skip_rate = sum(skip_scores) / len(skip_scores)
    other_rate = sum(other_scores) / len(other_scores)
    if abs(skip_rate - other_rate) < 0.15:
        return None
    if skip_rate > other_rate:
        headline = "Skipping things is where the regret lives"
        detail = (
            f"When you skip, cancel, or bail, you regret it {round(skip_rate * 100)}% of the time. "
            f"When you follow through, it's {round(other_rate * 100)}%."
        )
    else:
        headline = "Following through costs you more than skipping does"
        detail = (
            f"You regret the things you push through ({round(other_rate * 100)}%) more than "
            f"the ones you let go ({round(skip_rate * 100)}%). Worth noticing."
        )
    return ({"headline": headline, "detail": detail, "kind": "action_bias"}, 2 + abs(skip_rate - other_rate) * 10)


def _time_of_day_insight(rows):
    late, day = [], []
    for r in _resolved(rows):
        ts = _parse(r["timestamp"])
        if not ts:
            continue
        (late if (ts.hour >= 21 or ts.hour < 5) else day).append(_SCORE[r["outcome"]])
    if len(late) < 3 or len(day) < 3:
        return None
    late_rate = sum(late) / len(late)
    day_rate = sum(day) / len(day)
    if late_rate - day_rate < 0.15:
        return None
    return ({
        "headline": "Late-night decisions don't age well",
        "detail": (
            f"Decisions you logged after 9pm ended in regret {round(late_rate * 100)}% of the time, "
            f"versus {round(day_rate * 100)}% during the day. Maybe sleep on the late ones."
        ),
        "kind": "time_of_day",
    }, 2 + (late_rate - day_rate) * 10)


def _volume_insight(rows):
    stamps = [_parse(r["timestamp"]) for r in rows]
    stamps = [s for s in stamps if s]
    if len(stamps) < 5:
        return None
    span_days = max(1, (max(stamps) - min(stamps)).days)
    per_day = len(rows) / span_days
    if per_day < 1.5:
        return None
    return ({
        "headline": "You're carrying a lot right now",
        "detail": (
            f"{len(rows)} decisions in {span_days} days -- about {per_day:.0f} a day. "
            f"Offloading the small ones is the point, but that pace is worth noticing."
        ),
        "kind": "volume",
    }, 1 + per_day)


_GENERATORS = [
    _habit_insight,
    _affirming_insight,
    _debt_insight,
    _stakes_latency_insight,
    _action_bias_insight,
    _time_of_day_insight,
    _volume_insight,
]


def _advice_for(category_label, high):
    for entry in dataset._ENTRIES:
        if entry["category_label"] == category_label:
            return entry.get("high_regret_advice" if high else "low_regret_advice")
    return None


def _heuristic_reflection(rows):
    scored = []
    for gen in _GENERATORS:
        result = gen(rows)
        if result:
            scored.append(result)
    scored.sort(key=lambda x: x[1], reverse=True)

    insights = [item[0] for item in scored[:3]]
    # Guarantee an affirming note lands in the top 3 if one exists at all.
    if not any(i["kind"] == "affirming" for i in insights):
        aff = _affirming_insight(rows)
        if aff:
            insights = insights[:2] + [aff[0]]

    return {
        "source": "heuristic",
        "intro": _intro(len(_resolved(rows))),
        "insights": insights,
    }


def _intro(resolved_count):
    if resolved_count == 0:
        return "Not enough closed decisions yet for a real read. Record a few outcomes and check back."
    return "A few things Choicely noticed in your recent decisions:"


# --- Claude path -----------------------------------------------------------

_PROMPT = """You are looking at someone's logged decisions from the last couple of weeks.
Write exactly 3 short insights a perceptive friend would offer -- specific, grounded in
the numbers below, non-judgmental. At least one should be affirming if the data supports
it. This is a wellness feature, not a nag.

Person: {profile}

Decisions (text | type | stakes | logged | outcome):
{history}

Respond with ONLY a JSON object:
{{"insights": [{{"headline": "<=8 words", "detail": "one or two plain sentences with a number in them"}}]}}
"""


def _serialize_history(rows):
    lines = []
    for r in rows:
        lines.append(
            f"- {r['text']} | {r['decision_type']} | {r['stakes']} | "
            f"{(r['timestamp'] or '')[:16]} | {r['outcome'] or 'no outcome yet'}"
        )
    return "\n".join(lines)


def _profile_blurb(profile):
    if not profile:
        return "unknown"
    bits = [profile.get("planning_label", "")]
    for k in ("regret_orientation", "conflict_style", "social_energy"):
        if profile.get(k):
            bits.append(profile[k])
    return ", ".join(b for b in bits if b)


def _claude_reflection(rows, profile):
    import anthropic

    client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
    prompt = _PROMPT.format(
        profile=_profile_blurb(profile),
        # a reflection is about recent decisions -- bound the prompt so a
        # long history doesn't balloon token cost.
        history=_serialize_history(rows[-60:]),
    )
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(match.group(0) if match else raw)
    insights = [
        {"headline": i["headline"], "detail": i["detail"], "kind": "claude"}
        for i in parsed["insights"][:3]
    ]
    if not insights:
        raise ValueError("no insights from Claude")
    return {
        "source": "claude",
        "intro": _intro(len(_resolved(rows))),
        "insights": insights,
    }


def weekly_reflection():
    rows = models.list_decisions(include_seed=True)
    profile = models.get_profile()
    generated_at = datetime.now().strftime(_TS_FMT)

    if len(_resolved(rows)) == 0:
        return {"source": "empty", "generated_at": generated_at, "intro": _intro(0), "insights": []}

    if _ANTHROPIC_API_KEY:
        try:
            result = _claude_reflection(rows, profile)
            result["generated_at"] = generated_at
            return result
        except Exception:
            pass

    result = _heuristic_reflection(rows)
    result["generated_at"] = generated_at
    return result
