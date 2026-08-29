from datetime import datetime, timedelta

from app import models, triggers


def _log(text, outcome, hour, days_ago=1):
    ts = (datetime.now() - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)
    did = models.insert_decision(
        {"text": text, "decision_type": "health", "stakes": "low", "urgency": "low",
         "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "prior_category_label": "skipping meals"}
    )
    models.update_outcome(did, outcome)


def test_too_few_closed_decisions_reports_early():
    for i in range(4):
        _log("x", "regret", 8, days_ago=i + 1)
    assert triggers.regret_triggers()["verdict"] == "early"


def test_time_of_day_pattern_surfaces():
    # mornings regretted, evenings fine -- both sides well over the threshold
    for i in range(8):
        _log("morning skip", "regret", 7, days_ago=i + 1)
    for i in range(8):
        _log("evening call", "good", 20, days_ago=i + 1)
    result = triggers.regret_triggers()
    assert result["verdict"] == "found"
    dims = {t["dimension"] for t in result["triggers"]}
    assert "time_of_day" in dims


def test_no_pattern_when_outcomes_are_uniform():
    for i in range(16):
        _log("x", "neutral", 7 + (i % 12), days_ago=i + 1)
    assert triggers.regret_triggers()["verdict"] in ("nothing_stood_out", "found")
    # if "found", it must not be a spurious time-of-day split on identical rates
    for t in triggers.regret_triggers()["triggers"]:
        assert abs(t["trigger_rate"] - t["contrast_rate"]) >= 0.18
