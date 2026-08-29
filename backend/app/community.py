"""
Community priors: the population number, made a little less hypothetical.

The reference dataset (data/reference_dataset.json) is a documented
synthetic prior. This layer lets it be corrected by real outcomes that
users have chosen to share -- category label and outcome only, nothing
that identifies anyone. When enough have accumulated for a category, the
population rate Choicely quotes shifts partway from the textbook number
toward what people actually reported.

Blend: effective = reference * (1 - k) + community * k, where
    k = MAX_WEIGHT * n / (n + HALF_N)
so the community view can move the number but never fully overrides the
reference -- k tops out at MAX_WEIGHT no matter how big the pool gets.
"""
from . import models, regret

# Community outcomes cap out at this share of the blended rate.
MAX_WEIGHT = 0.55
# n at which the community view carries ~a third weight (MAX_WEIGHT * n/(n+HALF_N)).
HALF_N = 35
# Below this many shared outcomes for a category, don't shift the number at all.
MIN_N = 12


def _rate(outcomes: list[str]) -> float:
    return sum(regret.OUTCOME_SCORES.get(o, 0.5) for o in outcomes) / len(outcomes)


def effective_prior(category_label: str, reference_rate: float) -> dict:
    """Return the population-prior view for a category, community-adjusted.

    Always returns reference_rate under 'reference_rate'. 'regret_rate' is
    the value callers should actually use -- equal to the reference until
    there are at least MIN_N shared outcomes for the category.
    """
    pool = models.community_outcome_counts().get(category_label, [])
    n = len(pool)
    if n < MIN_N:
        return {
            "regret_rate": reference_rate,
            "reference_rate": reference_rate,
            "community_rate": None,
            "community_n": n,
        }
    community_rate = _rate(pool)
    k = MAX_WEIGHT * n / (n + HALF_N)
    blended = reference_rate * (1 - k) + community_rate * k
    return {
        "regret_rate": blended,
        "reference_rate": reference_rate,
        "community_rate": community_rate,
        "community_n": n,
    }


def contribute(category_label: str, outcome: str) -> None:
    if category_label and outcome in regret.OUTCOME_SCORES:
        models.add_community_outcome(category_label, outcome, is_seed=0)


def stats() -> dict:
    totals = models.community_totals()
    pool = models.community_outcome_counts()
    return {
        "total": totals["total"],
        "contributed": totals["contributed"],
        "categories": len(pool),
    }
