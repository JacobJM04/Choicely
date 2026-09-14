"""The agent activity log + backlog triage, heuristic path only."""
from app import agent, models


def _decision(text, **over):
    row = {
        "text": text, "decision_type": "health", "stakes": "low", "urgency": "low",
        "source": "dataset_prior", "prior_category_label": "skipping meals",
        "blended_regret_estimate": 0.4, "confidence": 0.0,
    }
    row.update(over)
    did = models.insert_decision(row)
    models.set_topic_id(did, did)
    return models.get_decision(did)


def test_logged_decision_creates_a_logged_event():
    d = _decision("should I skip lunch")
    agent.on_decision_logged(d)
    events = models.list_agent_events()
    assert [e["event_type"] for e in events] == ["logged"]


def test_auto_resolved_decision_creates_an_answered_event():
    d = _decision("skip breakfast", auto_resolution="You always regret skipping meals, so: eat something.")
    agent.on_decision_logged(d)
    events = models.list_agent_events()
    assert events[0]["event_type"] == "auto_resolved"
    assert "eat something" in events[0]["detail"]


def test_events_are_idempotent():
    d = _decision("should I skip lunch")
    agent.on_decision_logged(d)
    agent.on_decision_logged(d)
    agent.on_decision_logged(d)
    assert len(models.list_agent_events()) == 1


def test_outcome_recorded_closes_the_loop_and_scores_it():
    d = _decision("should I skip lunch", blended_regret_estimate=0.8)
    agent.on_decision_logged(d)
    models.update_outcome(d["id"], "regret")
    agent.on_outcome_recorded(models.get_decision(d["id"]))
    closed = [e for e in models.list_agent_events() if e["event_type"] == "loop_closed"]
    assert len(closed) == 1
    assert "hit" in closed[0]["reasoning"]


def test_backlog_triage_answers_a_one_sided_habit():
    # 10 regretted outcomes for the category -> confidence 1.0, estimate high
    for _ in range(10):
        did = models.insert_decision(
            {"text": "skipped again", "decision_type": "health", "stakes": "low", "urgency": "low",
             "prior_category_label": "skipping meals", "source": "blended"}
        )
        models.update_outcome(did, "regret")
    _decision("should I skip breakfast tomorrow", blended_regret_estimate=0.9, confidence=1.0)

    verdicts = {a["verdict"] for a in agent.assess_backlog()}
    assert "answer_now" in verdicts


def test_narrative_is_plain_language_and_empty_state_works():
    empty = {"answered": 0, "loops_closed": 0, "check_ins_raised": 0, "patterns_found": 0,
             "watching": 0, "would_answer": 0, "left_alone": 0}
    assert "hasn't had enough" in agent._narrative(empty, [])

    summary = {"answered": 1, "loops_closed": 3, "check_ins_raised": 2, "patterns_found": 1,
               "watching": 1, "would_answer": 0, "left_alone": 1}
    events = [{"event_type": "pattern_found", "title": "Mornings are your weak spot"}]
    text = agent._narrative(summary, events)
    # no stats jargon leaking into the recap
    for jargon in ("confidence", "regret estimate", "data point", "n="):
        assert jargon not in text.lower()
    assert "Mornings are your weak spot" in text


def test_backlog_collapses_repeated_topics():
    first = _decision("should I quit the club")
    for _ in range(3):
        did = models.insert_decision(
            {"text": "should I quit the club", "decision_type": "health", "stakes": "low",
             "urgency": "low", "source": "dataset_prior", "topic_id": first["id"]}
        )
    assessments = agent.assess_backlog()
    assert sum(1 for a in assessments if "quit the club" in a["text"]) == 1
