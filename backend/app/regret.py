"""
Regret-prediction: heuristic-weighted blend of the dataset prior and the
user's own logged outcomes for a decision's matched category.

Blending is keyed by the dataset's category_label (e.g. "skipping exercise",
"skipping meals") rather than the broader decision_type, so distinct habits
within the same type (skipping workouts vs. skipping breakfast) build
separate personal signals instead of diluting each other.

Swappable seam: this is intentionally a simple weighted average, not a
trained model. It can be swapped for a real classifier later as long as it
keeps the same (prior, personal history) -> (estimate, confidence) shape.
"""
from . import models

OUTCOME_SCORES = {"good": 0.0, "neutral": 0.5, "regret": 1.0}

# Confidence reaches 1.0 once this many personal outcomes exist for the category.
CONFIDENCE_SATURATION_POINTS = 10

# Auto-resolve only fires once confidence is fully personal and the signal
# is one-sided enough that giving a direct answer is more useful than asking.
AUTO_RESOLVE_CONFIDENCE_THRESHOLD = 1.0
AUTO_RESOLVE_HIGH_REGRET = 0.65
AUTO_RESOLVE_LOW_REGRET = 0.20


def personal_estimate_for_category(category_label: str) -> tuple[float | None, int]:
    """Return (personal_regret_estimate, data_points) for a dataset category.

    personal_regret_estimate is None if no outcomes have been recorded yet.
    """
    outcomes = models.get_outcomes_for_category(category_label)
    data_points = len(outcomes)
    if data_points == 0:
        return None, 0
    scores = [OUTCOME_SCORES.get(o, 0.5) for o in outcomes]
    return sum(scores) / len(scores), data_points


def blend(prior_rate: float, personal_estimate: float | None, data_points: int) -> tuple[float, float]:
    """Return (confidence, blended_estimate).

    confidence = min(1, data_points / CONFIDENCE_SATURATION_POINTS)
    blended = (1 - confidence) * prior + confidence * personal
    """
    confidence = min(1.0, data_points / CONFIDENCE_SATURATION_POINTS)
    if personal_estimate is None:
        return 0.0, prior_rate
    blended_estimate = (1 - confidence) * prior_rate + confidence * personal_estimate
    return confidence, blended_estimate


def predict(category_label: str, prior_rate: float) -> dict:
    """Full prediction bundle for a newly-logged decision matching this category."""
    personal_estimate, data_points = personal_estimate_for_category(category_label)
    confidence, blended_estimate = blend(prior_rate, personal_estimate, data_points)
    return {
        "personal_regret_estimate": personal_estimate,
        "personal_data_points": data_points,
        "confidence": confidence,
        "blended_regret_estimate": blended_estimate,
    }


def auto_resolution(
    category_label: str,
    blended_regret_estimate: float,
    confidence: float,
    high_regret_advice: str | None,
    low_regret_advice: str | None,
) -> str | None:
    """Plain-language direct answer, once enough personal data exists to be confident.

    Returns None if there isn't enough personal history yet, the signal isn't
    one-sided enough, or this category is too broad to safely auto-resolve
    (no advice text configured for it).
    """
    if confidence < AUTO_RESOLVE_CONFIDENCE_THRESHOLD:
        return None
    if blended_regret_estimate >= AUTO_RESOLVE_HIGH_REGRET and high_regret_advice:
        return f"You always regret {category_label}, so: {high_regret_advice}."
    if blended_regret_estimate <= AUTO_RESOLVE_LOW_REGRET and low_regret_advice:
        return f"You rarely regret {category_label}, so: {low_regret_advice}."
    return None
