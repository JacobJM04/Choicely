"""
Track record: Choicely scoring its own past predictions.

Every decision the user has closed the loop on carries two numbers we can
now compare:

  - what Choicely predicted at log time (`blended_regret_estimate`, the same
    figure the card showed), and
  - how it actually landed (`outcome`, scored 0.0 / 0.5 / 1.0 like everywhere
    else in the app).

The honest, and most useful, story here is not "Choicely is always right" --
early on it is working off a population average and the user may be
atypical. It is that the predictions *get sharper as Choicely learns you*:
the prior-only tier is the loosest, the personal tier is the tightest. That
trend is the whole argument for recording outcomes at all, so it is what
this module is built to surface.

Because outcomes are 0 / 0.5 / 1 the per-decision error of a *probabilistic*
forecast is always chunky (a well-calibrated 70% still lands 0.3 or 0.7 off a
single binary result), so the honest read is the group-level one:

  - reliability   predictions bucketed by confidence vs. the actual regret
                  rate in each bucket -- "when it says 80%, does it happen?"
  - skill         Brier score vs. a population-prior-only baseline; how much
                  personalising to the user's history actually bought
  - by_tier       error at each stage of the blend (prior -> blended ->
                  personal), which should fall as Choicely learns the user
mae / population_mae are kept in the payload as a secondary "typical miss"
but deliberately not the headline.
"""
from . import models, regret

# Below this many closed loops there isn't enough signal to score anything
# honestly -- the UI shows a "still learning" state instead of a number.
MIN_SCORED = 5

_TIER_BY_SOURCE = {
    "cold_start": "prior",
    "dataset_prior": "prior",
    "profile_prior": "prior",
    "personality_prior": "prior",
    "blended": "blended",
    "personal": "personal",
}

_TIER_LABEL = {
    "prior": "Population / tuned prior only",
    "blended": "Blended with your history",
    "personal": "Your history alone",
}

_TIER_ORDER = ["prior", "blended", "personal"]

_BUCKETS = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0001)]


def _scored_rows(include_seed: bool) -> list[dict]:
    """Every resolved decision paired with (predicted, actual)."""
    rows = models.list_decisions(include_seed=True)
    out = []
    for r in rows:
        if not include_seed and r["is_seed"]:
            continue
        if r["outcome"] is None:
            continue
        predicted = r["blended_regret_estimate"]
        if predicted is None:
            predicted = r["prior_regret_rate"]
        if predicted is None:
            continue
        out.append(
            {
                "text": r["text"],
                "source": r["source"],
                "tier": _TIER_BY_SOURCE.get(r["source"], "prior"),
                "predicted": float(predicted),
                "population_prior": (
                    float(r["prior_regret_rate"])
                    if r["prior_regret_rate"] is not None
                    else float(predicted)
                ),
                "actual": regret.OUTCOME_SCORES.get(r["outcome"], 0.5),
                "outcome": r["outcome"],
                "recorded_at": r["outcome_recorded_at"] or r["timestamp"],
                "auto_resolved": bool(r["auto_resolution"]),
            }
        )
    out.sort(key=lambda x: x["recorded_at"])
    return out


def _mae(rows: list[dict], key: str = "predicted") -> float:
    return sum(abs(r[key] - r["actual"]) for r in rows) / len(rows)


def _brier(rows: list[dict]) -> float:
    return sum((r["predicted"] - r["actual"]) ** 2 for r in rows) / len(rows)


def _tier_summary(rows: list[dict]) -> list[dict]:
    summary = []
    for tier in _TIER_ORDER:
        group = [r for r in rows if r["tier"] == tier]
        if not group:
            continue
        summary.append(
            {
                "tier": tier,
                "label": _TIER_LABEL[tier],
                "n": len(group),
                "mae": _mae(group),
                "avg_predicted": sum(r["predicted"] for r in group) / len(group),
                "avg_actual": sum(r["actual"] for r in group) / len(group),
            }
        )
    return summary


def _reliability(rows: list[dict]) -> list[dict]:
    buckets = []
    for lo, hi in _BUCKETS:
        group = [r for r in rows if lo <= r["predicted"] < hi]
        if not group:
            continue
        buckets.append(
            {
                "lo": lo,
                "hi": min(hi, 1.0),
                "n": len(group),
                "predicted": sum(r["predicted"] for r in group) / len(group),
                "actual": sum(r["actual"] for r in group) / len(group),
            }
        )
    return buckets


def _top_bucket_line(reliability: list[dict]) -> str | None:
    """The strongest honest sentence: at the high-confidence end, where
    Choicely actually acts (auto-resolve), does the prediction hold up?"""
    top = [b for b in reliability if b["lo"] >= 0.75 and b["n"] >= 3]
    if not top:
        return None
    b = top[0]
    return (
        f"When Choicely put your regret odds at {round(b['lo'] * 100)}% or higher, "
        f"you went on to regret it {round(b['actual'] * 100)}% of the time."
    )


def _headline(scored: int, skill: float, reliability: list[dict]) -> str:
    """Accountability framing: lead with where the record is strong -- the
    high-confidence end, which is the only place Choicely answers outright."""
    line = _top_bucket_line(reliability)
    if line:
        return f"{line} That's the range where it's confident enough to just answer."
    if skill >= 0.08:
        return (
            f"Across {scored} closed loops, personalising to your history made "
            f"Choicely's predictions {round(skill * 100)}% sharper than population "
            f"averages alone."
        )
    return (
        f"Choicely has scored {scored} of its own predictions. So far it tracks "
        f"about even with population averages -- more of your history sharpens it."
    )


def _verdict(skill: float, reliability: list[dict]) -> str:
    """How much weight the UI should put on the number. 'honest' = show the
    reliability curve and the caveats, don't claim high accuracy."""
    if _top_bucket_line(reliability):
        return "confident_end_holds"
    if skill >= 0.08:
        return "sharpening"
    return "learning"


def track_record(include_seed: bool = True) -> dict:
    rows = _scored_rows(include_seed)
    scored = len(rows)

    if scored < MIN_SCORED:
        return {
            "scored_count": scored,
            "min_scored": MIN_SCORED,
            "verdict": "early",
            "headline": (
                f"Choicely has scored {scored} of its own predictions so far. "
                f"After {MIN_SCORED} closed loops it starts reporting how accurate it's been."
            ),
        }

    mae = _mae(rows)
    population_mae = _mae(rows, key="population_prior")
    brier = _brier(rows)
    # Baseline: what if we had never personalised and shown the raw population
    # prior every time? Skill is the fractional reduction in Brier score over
    # that -- i.e. what learning the user's history actually bought.
    population_brier = sum((r["population_prior"] - r["actual"]) ** 2 for r in rows) / scored
    skill = 1 - brier / population_brier if population_brier > 0 else 0.0
    base_rate = sum(r["actual"] for r in rows) / scored
    tiers = _tier_summary(rows)
    reliability = _reliability(rows)

    # The accountability crux: when Choicely stuck its neck out (predicted a
    # lopsided >=75% or <=25%), how often did the outcome bear it out?
    confident = [r for r in rows if r["predicted"] >= 0.75 or r["predicted"] <= 0.25]
    confident_hits = sum(
        1
        for r in confident
        if (r["predicted"] >= 0.75 and r["actual"] >= 0.5)
        or (r["predicted"] <= 0.25 and r["actual"] < 0.5)
    )
    auto = [r for r in rows if r["auto_resolved"]]
    auto_hits = sum(1 for r in auto if r["actual"] >= 0.5)

    return {
        "scored_count": scored,
        "min_scored": MIN_SCORED,
        "mae": mae,
        "population_mae": population_mae,
        "brier": brier,
        "population_brier": population_brier,
        "skill": skill,
        "avg_predicted": sum(r["predicted"] for r in rows) / scored,
        "avg_actual": base_rate,
        "confident_calls": {"n": len(confident), "hits": confident_hits},
        "auto_resolve_calls": {"n": len(auto), "hits": auto_hits},
        "by_tier": tiers,
        "reliability": reliability,
        "recent": [
            {
                "text": r["text"],
                "predicted": r["predicted"],
                "actual": r["actual"],
                "outcome": r["outcome"],
                "error": abs(r["predicted"] - r["actual"]),
                "auto_resolved": r["auto_resolved"],
                "recorded_at": r["recorded_at"],
            }
            for r in rows[-8:][::-1]
        ],
        "headline": _headline(scored, skill, reliability),
        "verdict": _verdict(skill, reliability),
    }
