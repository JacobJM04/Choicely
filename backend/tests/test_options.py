from app import models, options


def test_analyze_scores_each_option_and_marks_the_lowest(profile):
    a = options.analyze(["go for the whole weekend", "skip it and rest", "go but leave early"], profile)
    assert len(a["items"]) == 3
    assert all(0.0 <= o["regret_estimate"] <= 1.0 for o in a["items"])
    lowest = min(range(3), key=lambda i: a["items"][i]["regret_estimate"])
    assert a["lean_idx"] == lowest
    assert a["items"][lowest]["is_lean"] is True


def test_clear_flag_reflects_the_margin(profile):
    a = options.analyze(["reply to her tonight", "wait until the weekend", "call her instead"], profile)
    ordered = sorted(o["regret_estimate"] for o in a["items"])
    assert a["clear"] == (ordered[1] - ordered[0] >= options._CLEAR_MARGIN)


def test_overall_stakes_is_the_max_across_options(profile):
    items = options.analyze(["stay in the job", "quit and travel"], profile)["items"]
    overall = options.overall_classification("", ["stay in the job", "quit and travel"], profile, items)
    assert overall["stakes"] in ("low", "medium", "high")


def test_adopt_chosen_option_makes_it_a_normal_decision(profile):
    a = options.analyze(["go to the gym", "take a rest day"], profile)
    did = models.insert_decision(
        {"text": "gym or rest", "decision_type": "health", "stakes": "low", "urgency": "low",
         "source": "options"}
    )
    models.adopt_chosen_option(did, 1, a["items"][1])
    models.update_outcome(did, "good")
    row = models.get_decision(did)
    assert row["chosen_option_idx"] == 1
    assert row["prior_category_label"] == a["items"][1]["category_label"]
    assert row["outcome"] == "good"
