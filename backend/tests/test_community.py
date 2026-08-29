from app import community, models


def test_starter_pool_seeded_on_init():
    stats = community.stats()
    assert stats["total"] > 0
    assert stats["contributed"] == 0


def test_ensure_seeded_is_idempotent():
    before = community.stats()["total"]
    community.ensure_seeded()
    assert community.stats()["total"] == before


def test_below_min_n_leaves_rate_untouched():
    # a category with no starter data
    adj = community.effective_prior("general routine decisions", 0.35)
    assert adj["regret_rate"] == 0.35
    assert adj["community_rate"] is None


def test_blend_moves_toward_community_but_stays_bounded():
    # starter pool has skipping exercise well below the 0.58 reference
    adj = community.effective_prior("skipping exercise", 0.58)
    assert adj["community_rate"] is not None
    assert adj["community_rate"] < adj["regret_rate"] < 0.58  # partway, not all the way


def test_contribute_then_influences_the_blend():
    ref = 0.40
    base = community.effective_prior("canceling social plans", ref)["regret_rate"]
    for _ in range(40):
        community.contribute("canceling social plans", "regret")
    after = community.effective_prior("canceling social plans", ref)["regret_rate"]
    assert after > base  # a flood of regrets pushes the number up


def test_contribute_ignores_bad_input():
    n0 = models.community_totals()["total"]
    community.contribute("", "regret")
    community.contribute("skipping meals", "not-an-outcome")
    assert models.community_totals()["total"] == n0
