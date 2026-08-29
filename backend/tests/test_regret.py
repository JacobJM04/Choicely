from app import models, regret


def _record(category, outcomes):
    for o in outcomes:
        did = models.insert_decision(
            {"text": "x", "decision_type": "health", "stakes": "low", "urgency": "low",
             "prior_category_label": category}
        )
        models.update_outcome(did, o)


def test_no_personal_history_returns_prior():
    conf, blended = regret.blend(prior_rate=0.6, personal_estimate=None, data_points=0)
    assert conf == 0.0
    assert blended == 0.6


def test_confidence_scales_to_saturation():
    assert regret.blend(0.6, 0.2, 5)[0] == 0.5
    assert regret.blend(0.6, 0.2, 10)[0] == 1.0
    assert regret.blend(0.6, 0.2, 25)[0] == 1.0


def test_blend_moves_toward_personal():
    _, at2 = regret.blend(0.6, 0.0, 2)
    _, at8 = regret.blend(0.6, 0.0, 8)
    assert at8 < at2 < 0.6  # more personal data -> closer to the 0.0 personal rate


def test_personal_estimate_from_recorded_outcomes():
    _record("skipping meals", ["regret", "regret", "good", "neutral"])
    est, n = regret.personal_estimate_for_category("skipping meals")
    assert n == 4
    assert est == (1.0 + 1.0 + 0.0 + 0.5) / 4


def test_auto_resolution_needs_full_confidence_and_lopsided_signal():
    assert regret.auto_resolution("skipping meals", 0.9, 1.0, "eat something", None) is not None
    # not confident enough
    assert regret.auto_resolution("skipping meals", 0.9, 0.9, "eat something", None) is None
    # confident but not lopsided
    assert regret.auto_resolution("skipping meals", 0.5, 1.0, "eat something", "skip it") is None
