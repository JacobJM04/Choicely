"""
Regret-forecast insights: the data behind the chart.

For every dataset category the user has logged against, replay the
prior-to-personal blend one outcome at a time, in the order the outcomes
actually came in. That produces a trajectory the frontend can draw:

  - a flat population-prior line (what the dataset says for everyone)
  - a flat style-tuned prior line (that number nudged by onboarding answers)
  - one dot per recorded outcome (good = 0, neutral = 0.5, regret = 1.0)
  - the blended-estimate curve bending away from the prior toward the
    personal rate as confidence climbs from 0 to 1 over the first
    CONFIDENCE_SATURATION_POINTS outcomes
  - a 95% interval around that curve, from two variance sources: an a-priori
    "your rate might not be the population's" term that decays as the blend
    stops leaning on the prior, plus the ordinary sampling variance of your
    own outcomes. It genuinely tightens as the estimate earns its keep.

The blended curve is the exact arithmetic in regret.py, unrolled step by
step so it can be seen instead of returned as one number on a card.
"""
import math

from . import dataset, models, regret

# A priori (before any personal outcomes), assume someone's personal regret
# rate for a category sits within roughly +-17pp of the population rate.
# Variance of that belief; it's the width of the band at zero personal data.
PRIOR_MISMATCH_VAR = 0.03
_Z = 1.96

_ENTRY_BY_CATEGORY = {e["category_label"]: e for e in dataset._ENTRIES}


def _verdict(blended: float, confidence: float, category_label: str, data_points: int) -> str:
    """One plain sentence. The numbers and the how-confident caveat live in the
    UI around it, so this stays qualitative."""
    if data_points == 0:
        return "Not enough of your own outcomes yet, so this is just the general pattern."
    if blended >= 0.7:
        return "You almost always end up regretting this."
    if blended >= 0.55:
        return "You regret this more often than not."
    if blended > 0.45:
        return "For you, this one is roughly a coin flip."
    if blended <= 0.25:
        return "You almost never regret this."
    return "You usually don't regret this."


def _interval(blended: float, confidence: float, n: int) -> tuple[float, float]:
    """95% interval around the blended estimate. Two independent variance
    sources: the decaying prior-mismatch term (weight (1-confidence)^2) and
    the sampling variance of the personal rate (weight confidence^2)."""
    prior_term = (1 - confidence) ** 2 * PRIOR_MISMATCH_VAR
    sampling_term = (confidence ** 2) * (blended * (1 - blended) / n) if n > 0 else 0.0
    half = _Z * math.sqrt(prior_term + sampling_term)
    return max(0.0, blended - half), min(1.0, blended + half)


def _trajectory(base_rate: float, outcome_scores: list[float]) -> list[dict]:
    low, high = _interval(base_rate, 0.0, 0)
    points = [{
        "n": 0, "blended": base_rate, "personal": None, "confidence": 0.0,
        "ci_low": low, "ci_high": high,
    }]
    running_sum = 0.0
    for i, score in enumerate(outcome_scores, start=1):
        running_sum += score
        personal = running_sum / i
        confidence = min(1.0, i / regret.CONFIDENCE_SATURATION_POINTS)
        blended = (1 - confidence) * base_rate + confidence * personal
        low, high = _interval(blended, confidence, i)
        points.append({
            "n": i, "blended": blended, "personal": personal, "confidence": confidence,
            "ci_low": low, "ci_high": high,
        })
    return points


def category_forecast(category_label: str, include_seed: bool = True) -> dict | None:
    latest = models.get_latest_decision_for_category(category_label)
    if latest is None:
        return None

    # The forecast's "everyone" line is the reference-dataset rate, held
    # steady regardless of the community-adjusted number a freshly-logged
    # decision in this category may have stored (see community.py). Falls
    # back to the stored rate for categories not in the reference set.
    _ref_entry = _ENTRY_BY_CATEGORY.get(category_label, {})
    population_prior = _ref_entry.get("regret_rate", latest["prior_regret_rate"])
    profile_prior = latest["profile_adjusted_regret_rate"]
    personality_prior = latest["personality_adjusted_regret_rate"]
    # The starting point the blend actually works from -- the last adjustment
    # step that ran (matches the pipeline in main.create_decision).
    tuned_prior = (
        personality_prior
        if personality_prior is not None
        else profile_prior
    )
    base_rate = tuned_prior if tuned_prior is not None else population_prior

    history = models.get_category_history(category_label, include_seed=include_seed)
    outcome_scores = [regret.OUTCOME_SCORES.get(h["outcome"], 0.5) for h in history]
    trajectory = _trajectory(base_rate, outcome_scores)

    outcomes = [
        {
            "n": i + 1,
            "outcome": h["outcome"],
            "score": regret.OUTCOME_SCORES.get(h["outcome"], 0.5),
            "recorded_at": h["recorded_at"],
            "text": h["text"],
            "is_seed": bool(h["is_seed"]),
        }
        for i, h in enumerate(history)
    ]

    current = trajectory[-1]
    entry = _ENTRY_BY_CATEGORY.get(category_label, {})

    return {
        "category_label": category_label,
        "decision_type": latest["decision_type"],
        "population_prior": population_prior,
        "profile_prior": profile_prior,
        "personality_prior": personality_prior,
        "tuned_prior": tuned_prior,
        "base_rate": base_rate,
        "sample_size": latest["prior_sample_size"],
        "description": entry.get("description"),
        "data_points": len(history),
        "confidence": current["confidence"],
        "blended_now": current["blended"],
        "personal_now": current["personal"],
        "saturation_points": regret.CONFIDENCE_SATURATION_POINTS,
        "outcomes": outcomes,
        "trajectory": trajectory,
        "verdict": _verdict(current["blended"], current["confidence"], category_label, len(history)),
    }


def all_forecasts(include_seed: bool = True) -> list[dict]:
    rows = models.get_category_rows(include_seed=include_seed)
    forecasts = []
    for row in rows:
        forecast = category_forecast(row["category_label"], include_seed=include_seed)
        if forecast is not None:
            forecasts.append(forecast)
    # Most-personalized first: the categories where the chart has the most to show.
    forecasts.sort(key=lambda f: (f["data_points"], f["confidence"]), reverse=True)
    # A category with no recorded outcomes is just a flat prior line -- keep it
    # only if it's all the user has, otherwise it's noise.
    with_data = [f for f in forecasts if f["data_points"] > 0]
    return with_data if with_data else forecasts
