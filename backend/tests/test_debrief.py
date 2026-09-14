"""The debrief with no ANTHROPIC_API_KEY -- the heuristic path only."""
from app import debt, debrief, models


def _log(text, outcome=None, category="skipping meals", dtype="health"):
    """Mimic main.create_decision's topic grouping: a repeat of an open
    question joins the existing topic instead of starting a new one."""
    existing_topic = debt.find_matching_topic(dtype, text)
    did = models.insert_decision(
        {"text": text, "decision_type": dtype, "stakes": "low", "urgency": "low",
         "prior_category_label": category, "source": "dataset_prior",
         "topic_id": existing_topic}
    )
    topic_id = existing_topic if existing_topic is not None else did
    if existing_topic is None:
        models.set_topic_id(did, did)
    models.recount_topic(topic_id)
    if outcome:
        models.update_outcome(did, outcome)
    return did


def test_debrief_returns_the_expected_shape():
    out = debrief.debrief("I can't decide whether to skip breakfast before the gym tomorrow.")
    for key in (
        "real_question", "whats_at_stake", "grounded_read", "recommendation",
        "confidence", "regret_estimate", "related", "source",
    ):
        assert key in out
    assert out["source"] == "heuristic"
    assert 0.0 <= out["regret_estimate"] <= 1.0


def test_debrief_grounds_in_personal_history():
    for _ in range(6):
        _log("skipped breakfast again", "regret", category="skipping meals")
    out = debrief.debrief("should I skip breakfast before my workout")
    # 6 regretted outcomes -> the read should lean high-confidence and cite a number
    assert out["personal_data_points"] >= 6
    assert out["confidence"] in ("medium", "high")
    assert any(ch.isdigit() for ch in out["grounded_read"])


def test_debrief_detects_a_decision_debt_loop():
    for _ in range(4):
        _log("should I quit the book club", category="general interpersonal decisions",
             dtype="interpersonal")
    out = debrief.debrief(
        "I keep going back and forth about quitting the book club. I never finish the books "
        "and I dread going but I don't want to let everyone down."
    )
    assert out["in_decision_debt"] is True
    assert "quit" in out["real_question"].lower()


def test_debrief_related_dedupes_repeats():
    for _ in range(3):
        _log("cancel my weekend trip", category="general social decisions", dtype="social")
    out = debrief.debrief("thinking hard about whether to cancel my weekend trip, I'm so tired")
    texts = [r["text"] for r in out["related"]]
    assert len(texts) == len(set(texts))
