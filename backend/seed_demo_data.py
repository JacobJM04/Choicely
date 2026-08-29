"""
Seed a demo persona -- "Maya" -- and roughly two weeks of her decision
history, so every layer of the app has something to show live without
waiting on real elapsed time. Run once before demoing (delete
data/choicely.db first for a clean slate):

    python seed_demo_data.py

The history is inserted as normal decisions (not flagged demo/seed) -- it
IS Maya's history for the purposes of the demo -- so it flows into the
mental-load dashboard, the regret forecast, and the debt dashboard the
same way a real user's would.

Seeds:
  1. 5 past "skip the workout" decisions -- confidence reaches 50%, so a
     live "should I skip leg day" shows a blended estimate pulling away
     from the 58% dataset prior.
  2. 10 past "skip breakfast" decisions (mostly regret) -- confidence
     saturates at 100%, so a live "should I skip breakfast" triggers
     auto-resolve: "You always regret skipping meals, so: eat something."
  3. 4 repeated, still-undecided "should I quit this club" entries -- shows
     up on the decision-debt dashboard as a reopened-without-deciding
     pattern.
  4. 2 recent decisions with no outcome yet and a check-in nearly due --
     advance the demo clock once (bottom-right control) and Choicely
     proactively asks how they went.
"""
import json
from datetime import datetime, timedelta

from app import checkins, dataset, debt, models, options, personality, profile as profile_mod, regret

# (text, outcome, days_ago, hour) -- hour spreads the history across the day so
# the regret-trigger analysis has a real time-of-day signal to find. Maya's
# pattern: breakfast-skips happen in the morning rush and she regrets almost
# all of them; her evening social calls almost always land well; her daytime
# workout calls are mixed.
WORKOUT_SEEDS = [
    ("should I skip the gym today, feeling exhausted", "good", 6, 13),
    ("skip leg day, still sore from yesterday", "good", 5, 12),
    ("should I skip my run this morning", "neutral", 4, 15),
    ("thinking about skipping the gym tonight", "good", 2, 16),
    ("skip workout, too busy with work", "regret", 1, 14),
]

BREAKFAST_SEEDS = [
    ("should I skip breakfast, out the door late", "regret", 22, 7),
    ("skip breakfast again, not hungry", "regret", 19, 8),
    ("thinking about skipping breakfast today", "neutral", 16, 7),
    ("should I just skip breakfast and eat lunch early", "regret", 13, 8),
    ("skip breakfast, don't feel like cooking", "regret", 10, 7),
    ("no time for breakfast today, skip it", "regret", 6, 8),
    ("should I skip breakfast before work", "regret", 4, 7),
    ("skip breakfast, not feeling well", "neutral", 3, 8),
    ("thinking about skipping breakfast again", "regret", 2, 7),
    ("should I skip breakfast one more time", "regret", 1, 8),
]

# Social: forcing herself out when low on energy. She's a planner who fears
# missing out, so both the population prior AND her tuned prior read this as
# fairly regret-prone -- but her actual outcomes say she's almost always glad
# she went. A third forecast card, and the clearest "your history overrides
# the prior, in the good direction" story.
SOCIAL_SEEDS = [
    ("should I go out tonight even though I'm exhausted", "good", 20, 19),
    ("drag myself to the party this weekend or bail", "good", 15, 20),
    ("worth going on the weekend trip when I'm this tired", "good", 9, 18),
    ("make it to the hang out tonight, feeling drained", "neutral", 5, 20),
    ("should I go out for drinks after work, wiped", "good", 2, 19),
]

DEBT_SEEDS = [
    ("should I quit this club", None, 21, 14),
    ("should I quit this club", None, 15, 14),
    ("should I quit this club", None, 9, 14),
    ("should I quit this club", None, 3, 14),
]

# Real (not seed-flagged) decisions logged recently with no outcome yet and a
# check-in already just about due -- so a single "advance a day" in the demo
# brings them up as proactive check-ins Choicely asks about.
PENDING_SEEDS = [
    # (text, decision_type, stakes, urgency, hours_ago)
    ("should I go to the party tonight or stay in and rest", "social", "low", "low", 26),
    ("should I finally reply to my sister's message", "interpersonal", "medium", "low", 30),
]


def _adjusted_rates(prior: dict, decision_type: str, stakes: str):
    """(profile_adjusted, personality_adjusted, effective_rate) -- the same
    prior-adjustment pipeline main.create_decision runs, so seeded rows carry
    the tuned-prior numbers the forecast chart reads."""
    profile_row = models.get_profile()
    profile_adjusted = profile_mod.adjust_prior(prior["regret_rate"], prior["planning_alignment"])
    personality_adjusted = personality.adjust_prior(
        profile_adjusted if profile_adjusted is not None else prior["regret_rate"],
        prior["planning_alignment"],
        decision_type,
        stakes,
        profile_row,
    )
    effective = personality_adjusted or profile_adjusted or prior["regret_rate"]
    return profile_adjusted, personality_adjusted, effective


# One live "compare these options" decision, unresolved -- shows the per-option
# regret estimates side by side. Maya's instinct is to skip (she's inaction-
# averse, so skipping reads as regret-prone), but her own outcomes say she's
# almost always glad she pushed herself out, so Choicely leans the other way.
OPTION_SEED = (
    "the weekend trip -- everyone's going and I'm wiped",
    ["go for the whole weekend", "go just for Saturday", "skip it, I need the rest"],
    2,   # days ago
    19,  # hour
)


def _insert_option_seed(header: str, option_texts: list[str], days_ago: int, hour: int) -> None:
    profile_row = models.get_profile()
    analysis = options.analyze(option_texts, profile_row)
    overall = options.overall_classification(header, option_texts, profile_row, analysis["items"])
    logged = (datetime.now() - timedelta(days=days_ago)).replace(hour=hour, minute=15, second=0, microsecond=0)
    due = logged + timedelta(hours=checkins.due_delay_hours(
        overall["decision_type"], overall["stakes"], overall["urgency"]
    ))
    best = min(o["regret_estimate"] for o in analysis["items"])
    decision_id = models.insert_decision(
        {
            "text": header,
            "decision_type": overall["decision_type"],
            "stakes": overall["stakes"],
            "urgency": overall["urgency"],
            "timestamp": logged.strftime("%Y-%m-%d %H:%M:%S"),
            "outcome_due_at": due.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "options",
            "blended_regret_estimate": best,
            "options_json": json.dumps(analysis),
            "is_seed": 0,
        }
    )
    models.set_topic_id(decision_id, decision_id)


def _insert_pending(text: str, decision_type: str, stakes: str, urgency: str, hours_ago: int) -> None:
    from app import gametheory

    prior = dataset.get_prior(decision_type, text)
    profile_adjusted, personality_adjusted, effective_rate = _adjusted_rates(prior, decision_type, stakes)
    prediction = regret.predict(prior["category_label"], effective_rate)
    logged = datetime.now() - timedelta(hours=hours_ago)
    due = logged + timedelta(hours=checkins.due_delay_hours(decision_type, stakes, urgency))
    breakdown_json = None
    if decision_type == "interpersonal":
        import json as _json
        breakdown_json = _json.dumps(gametheory.analyze(text, models.get_profile()))
    decision_id = models.insert_decision(
        {
            "text": text,
            "decision_type": decision_type,
            "stakes": stakes,
            "urgency": urgency,
            "timestamp": logged.strftime("%Y-%m-%d %H:%M:%S"),
            "outcome_due_at": due.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "dataset_prior",
            "prior_category_label": prior["category_label"],
            "prior_regret_rate": prior["regret_rate"],
            "prior_sample_size": prior["sample_size"],
            "prior_description": prior["description"],
            "profile_adjusted_regret_rate": profile_adjusted,
            "personality_adjusted_regret_rate": personality_adjusted,
            "blended_regret_estimate": prediction["blended_regret_estimate"],
            "confidence": prediction["confidence"],
            "personal_data_points": prediction["personal_data_points"],
            "breakdown_json": breakdown_json,
            "is_seed": 0,
        }
    )
    models.set_topic_id(decision_id, decision_id)


def _source_for(prediction: dict, profile_adjusted, personality_adjusted) -> str:
    """Mirror main.create_decision's source labelling for a seeded row."""
    if prediction["personal_data_points"] == 0:
        if personality_adjusted is not None:
            return "personality_prior"
        if profile_adjusted is not None:
            return "profile_prior"
        return "dataset_prior"
    if prediction["confidence"] >= 1.0:
        return "personal"
    return "blended"


def _insert_seeded(
    text: str,
    decision_type: str,
    stakes: str,
    urgency: str,
    outcome: str | None,
    days_ago: int,
    hour: int = 12,
) -> None:
    prior = dataset.get_prior(decision_type, text)
    profile_adjusted, personality_adjusted, effective_rate = _adjusted_rates(prior, decision_type, stakes)

    prediction = regret.predict(prior["category_label"], effective_rate)
    auto_resolution_text = regret.auto_resolution(
        prior["category_label"],
        prediction["blended_regret_estimate"],
        prediction["confidence"],
        prior["high_regret_advice"],
        prior["low_regret_advice"],
    )
    logged_at = (datetime.now() - timedelta(days=days_ago)).replace(
        hour=hour, minute=15, second=0, microsecond=0
    )
    timestamp = logged_at.strftime("%Y-%m-%d %H:%M:%S")
    # Outcomes were "recorded" a few hours after the decision -- keeps the
    # weekly mental-load window and time-to-close stats realistic.
    recorded_at = (
        (logged_at + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S") if outcome else None
    )
    existing_topic_id = debt.find_matching_topic(decision_type, text)

    decision_id = models.insert_decision(
        {
            "text": text,
            "decision_type": decision_type,
            "stakes": stakes,
            "urgency": urgency,
            "timestamp": timestamp,
            "outcome": outcome,
            "outcome_recorded_at": recorded_at,
            "source": _source_for(prediction, profile_adjusted, personality_adjusted),
            "prior_category_label": prior["category_label"],
            "prior_regret_rate": prior["regret_rate"],
            "prior_sample_size": prior["sample_size"],
            "prior_description": prior["description"],
            "profile_adjusted_regret_rate": profile_adjusted,
            "personality_adjusted_regret_rate": personality_adjusted,
            "personal_regret_estimate": prediction["personal_regret_estimate"],
            "blended_regret_estimate": prediction["blended_regret_estimate"],
            "confidence": prediction["confidence"],
            "personal_data_points": prediction["personal_data_points"],
            "auto_resolution": auto_resolution_text,
            "topic_id": existing_topic_id,
            "is_seed": 0,
        }
    )

    final_topic_id = existing_topic_id if existing_topic_id is not None else decision_id
    if existing_topic_id is None:
        models.set_topic_id(decision_id, decision_id)
    models.recount_topic(final_topic_id)


# Maya: a planner who over-deliberates, hates missing out (regrets chances not
# taken), avoids conflict. Both onboarding signals push the same way -- a
# planner AND someone who fears inaction both read "skipping" as regret-prone --
# so the population -> profile-tuned -> personality-tuned staircase is clearly
# visible on the forecast, and her actual history then either confirms it
# (breakfast, up to 90%) or overrides it (workouts, down to ~44%).
# decisiveness 1.0 also lights up the "you tend to deliberate" debt panel.
DEMO_PROFILE = {
    "name": "Maya",
    "planning_answers": [1, 1, 1, 0.5, 1],  # planning_score 0.9 -> "planner"
    "personality_answers": {
        "risk_financial": 0.5,
        "risk_social": 1,
        "regret_orientation_1": "inaction-averse",
        "regret_orientation_2": "inaction-averse",
        "social_energy_leaning": "extrovert",
        "social_energy_stability": "fluctuating",
        "decisiveness_1": 1,
        "decisiveness_2": 1,
        "conflict_style": "avoidant",
        "stakes_sensitivity": "high",
    },
}


def _seed_profile() -> None:
    from app import personality, profile as profile_mod

    planning_score, planning_label = profile_mod.score_survey(DEMO_PROFILE["planning_answers"])
    personality_profile = personality.score_personality(DEMO_PROFILE["personality_answers"])
    models.save_profile(DEMO_PROFILE["name"], planning_score, planning_label, personality_profile)


def seed() -> None:
    models.init_db()

    if models.get_profile() is None:
        _seed_profile()

    for text, outcome, days_ago, hour in WORKOUT_SEEDS:
        _insert_seeded(text, "health", "low", "low", outcome, days_ago, hour)

    for text, outcome, days_ago, hour in BREAKFAST_SEEDS:
        _insert_seeded(text, "health", "low", "low", outcome, days_ago, hour)

    for text, outcome, days_ago, hour in SOCIAL_SEEDS:
        _insert_seeded(text, "social", "low", "low", outcome, days_ago, hour)

    for text, outcome, days_ago, hour in DEBT_SEEDS:
        _insert_seeded(text, "routine", "high", "low", outcome, days_ago, hour)

    for text, dtype, stakes, urgency, hours_ago in PENDING_SEEDS:
        _insert_pending(text, dtype, stakes, urgency, hours_ago)

    _insert_option_seed(*OPTION_SEED)

    total = len(WORKOUT_SEEDS) + len(BREAKFAST_SEEDS) + len(SOCIAL_SEEDS) + len(DEBT_SEEDS)
    print(f"Seeded profile '{DEMO_PROFILE['name']}' + {total} decisions "
          f"({len(WORKOUT_SEEDS)} workout, {len(BREAKFAST_SEEDS)} breakfast, "
          f"{len(SOCIAL_SEEDS)} social, {len(DEBT_SEEDS)} debt) plus {len(PENDING_SEEDS)} "
          f"pending + 1 compare-options (advance the demo clock once to see check-ins).")


def reset() -> None:
    """Clear all data and reseed -- a clean slate for a demo run. Works even
    with the backend running (clears tables rather than deleting the file)."""
    models.init_db()
    with models.get_connection() as conn:
        conn.execute("DELETE FROM decisions")
        conn.execute("DELETE FROM user_profile")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'decisions'")
    seed()


if __name__ == "__main__":
    import sys

    if "--reset" in sys.argv:
        reset()
    else:
        seed()
