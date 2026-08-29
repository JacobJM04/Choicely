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

# Starter pool so the shared-outcome layer isn't empty on a fresh install.
# (category_label, count, mean_regret_rate) -- a plausible drift off the
# reference dataset. Seeded once by models.init_db() when the table is empty.
STARTER_POOL = [
    ("skipping meals", 46, 0.80),
    ("skipping exercise", 54, 0.45),
    ("going out despite low energy", 40, 0.29),
    ("sleep vs. social/obligation tradeoff", 44, 0.72),
    ("impulse purchases", 50, 0.74),
    ("avoiding a difficult conversation", 42, 0.68),
    ("canceling social plans", 36, 0.54),
]

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


def ensure_seeded() -> None:
    """Populate the shared pool from STARTER_POOL if it's empty. Deterministic
    split so each category's pooled mean lands on its target rate."""
    if models.community_totals()["total"] > 0:
        return
    rows: list[tuple[str, str, int]] = []
    for category, count, rate in STARTER_POOL:
        n_neutral = round(count * 0.14)
        n_regret = max(0, min(count - n_neutral, round(count * rate - n_neutral * 0.5)))
        n_good = count - n_regret - n_neutral
        for outcome, k in (("regret", n_regret), ("neutral", n_neutral), ("good", n_good)):
            rows.extend((category, outcome, 1) for _ in range(k))
    models.add_community_outcomes_bulk(rows)


def stats() -> dict:
    totals = models.community_totals()
    pool = models.community_outcome_counts()
    return {
        "total": totals["total"],
        "contributed": totals["contributed"],
        "categories": len(pool),
    }
