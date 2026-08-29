import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import (
    calibration,
    checkins,
    classifier,
    dataset,
    debt,
    gametheory,
    insights,
    load,
    models,
    personality,
    profile,
    push,
    reflection,
    regret,
)

app = FastAPI(title="Choicely API")

app.add_middleware(
    CORSMiddleware,
    # Vite falls back to 5174, 5175, ... whenever 5173 is already taken (this
    # bit us mid-development), so match any localhost dev port rather than
    # hardcoding one.
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    models.init_db()


class DecisionIn(BaseModel):
    text: str


class OutcomeIn(BaseModel):
    outcome: str


class ProfileIn(BaseModel):
    name: str
    answers: list[float]
    personality_answers: dict[str, float | str] = {}


VALID_OUTCOMES = {"good", "neutral", "regret"}


def _serialize(row: dict) -> dict:
    row = dict(row)
    breakdown_json = row.pop("breakdown_json", None)
    row["breakdown"] = json.loads(breakdown_json) if breakdown_json else None
    return row


@app.get("/survey-questions")
def get_survey_questions():
    return profile.SURVEY_QUESTIONS


@app.get("/personality-questions")
def get_personality_questions():
    return personality.PERSONALITY_QUESTIONS


@app.get("/profile")
def get_profile():
    saved = models.get_profile()
    if saved is None:
        raise HTTPException(status_code=404, detail="No profile saved yet.")
    return saved


@app.post("/profile")
def create_profile(payload: ProfileIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    try:
        planning_score, planning_label = profile.score_survey(payload.answers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        personality_profile = personality.score_personality(payload.personality_answers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    models.save_profile(name, planning_score, planning_label, personality_profile)
    return models.get_profile()


@app.post("/decisions")
def create_decision(payload: DecisionIn):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Decision text cannot be empty.")

    is_first_ever = models.count_decisions() == 0
    profile_row = models.get_profile()

    classification = classifier.classify_decision(text, profile_row)
    decision_type = classification["decision_type"]
    prior = dataset.get_prior(decision_type, text)

    profile_adjusted_rate = profile.adjust_prior(prior["regret_rate"], prior["planning_alignment"])
    personality_adjusted_rate = personality.adjust_prior(
        profile_adjusted_rate if profile_adjusted_rate is not None else prior["regret_rate"],
        prior["planning_alignment"],
        decision_type,
        classification["stakes"],
        profile_row,
    )
    effective_prior_rate = personality_adjusted_rate if personality_adjusted_rate is not None else (
        profile_adjusted_rate if profile_adjusted_rate is not None else prior["regret_rate"]
    )

    prediction = regret.predict(prior["category_label"], effective_prior_rate)

    if is_first_ever:
        source = "cold_start"
    elif prediction["personal_data_points"] == 0:
        if personality_adjusted_rate is not None:
            source = "personality_prior"
        elif profile_adjusted_rate is not None:
            source = "profile_prior"
        else:
            source = "dataset_prior"
    elif prediction["confidence"] >= 1.0:
        source = "personal"
    else:
        source = "blended"

    auto_resolution_text = regret.auto_resolution(
        prior["category_label"],
        prediction["blended_regret_estimate"],
        prediction["confidence"],
        prior["high_regret_advice"],
        prior["low_regret_advice"],
    )

    breakdown_json = None
    if decision_type == "interpersonal":
        breakdown_json = json.dumps(gametheory.analyze(text, profile_row))

    existing_topic_id = debt.find_matching_topic(decision_type, text)

    # A check-in is Choicely circling back on something it couldn't answer.
    # If it auto-resolved the decision, there's nothing to nag about.
    due_at = None if auto_resolution_text else checkins.outcome_due_at(
        decision_type, classification["stakes"], classification["urgency"]
    )

    decision_id = models.insert_decision(
        {
            "text": text,
            "decision_type": decision_type,
            "stakes": classification["stakes"],
            "urgency": classification["urgency"],
            "outcome_due_at": due_at,
            "source": source,
            "prior_category_label": prior["category_label"],
            "prior_regret_rate": prior["regret_rate"],
            "prior_sample_size": prior["sample_size"],
            "prior_description": prior["description"],
            "profile_adjusted_regret_rate": profile_adjusted_rate,
            "personality_adjusted_regret_rate": personality_adjusted_rate,
            "personal_regret_estimate": prediction["personal_regret_estimate"],
            "blended_regret_estimate": prediction["blended_regret_estimate"],
            "confidence": prediction["confidence"],
            "personal_data_points": prediction["personal_data_points"],
            "auto_resolution": auto_resolution_text,
            "breakdown_json": breakdown_json,
            "topic_id": existing_topic_id,
        }
    )

    final_topic_id = existing_topic_id if existing_topic_id is not None else decision_id
    if existing_topic_id is None:
        models.set_topic_id(decision_id, decision_id)
    models.recount_topic(final_topic_id)

    return _serialize(models.get_decision(decision_id))


@app.get("/decisions")
def get_decisions(include_seed: bool = False):
    return [_serialize(row) for row in models.list_decisions(include_seed)]


@app.post("/decisions/{decision_id}/outcome")
def record_outcome(decision_id: int, payload: OutcomeIn):
    if payload.outcome not in VALID_OUTCOMES:
        raise HTTPException(status_code=400, detail=f"outcome must be one of {sorted(VALID_OUTCOMES)}")

    existing = models.get_decision(decision_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Decision not found.")
    if existing["outcome"] is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Outcome already recorded as '{existing['outcome']}'. It's a one-time tap, not editable.",
        )

    models.update_outcome(decision_id, payload.outcome)
    return _serialize(models.get_decision(decision_id))


@app.get("/reflection")
def get_reflection():
    """A short plain-language read on recent decisions -- Claude when a key is set, heuristics otherwise."""
    return reflection.weekly_reflection()


@app.get("/check-ins")
def get_check_ins():
    """Decisions whose check-in time has come -- Choicely circling back so you don't have to."""
    return checkins.pending(models.get_due_check_ins())


class AdvanceIn(BaseModel):
    hours: float = 24


@app.post("/demo/advance")
def advance_time(payload: AdvanceIn):
    """Demo aid only: rewind every decision's clock so pending check-ins come due."""
    touched = models.shift_time(payload.hours)
    pushed = push.notify_due()
    return {"shifted_hours": payload.hours, "rows_touched": touched, "push": pushed}


class PushSubscriptionIn(BaseModel):
    subscription: dict


class PushUnsubscribeIn(BaseModel):
    endpoint: str


@app.get("/push/config")
def push_config():
    """VAPID public key + whether push is available server-side."""
    return push.config()


@app.post("/push/subscribe")
def push_subscribe(payload: PushSubscriptionIn):
    try:
        push.add_subscription(payload.subscription)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.post("/push/unsubscribe")
def push_unsubscribe(payload: PushUnsubscribeIn):
    push.remove_subscription(payload.endpoint)
    return {"ok": True}


@app.post("/push/test")
def push_test():
    return push.send_test()


@app.get("/load")
def get_load(include_seed: bool = False):
    """Mental-load accounting for the last week -- what Choicely carried vs. what's still on you."""
    return load.weekly_load(include_seed)


@app.get("/insights")
def get_insights(include_seed: bool = True):
    """Regret-forecast data per category -- the trajectory behind the chart."""
    return insights.all_forecasts(include_seed)


@app.get("/insights/{category_label}")
def get_category_insight(category_label: str, include_seed: bool = True):
    forecast = insights.category_forecast(category_label, include_seed)
    if forecast is None:
        raise HTTPException(status_code=404, detail="No history for that category yet.")
    return forecast


@app.get("/track-record")
def get_track_record(include_seed: bool = True):
    """How close Choicely's past regret predictions came to the recorded outcomes."""
    return calibration.track_record(include_seed)


@app.get("/dashboard")
def get_dashboard(include_seed: bool = False):
    topics = models.get_debt_topics(include_seed)
    return [
        {
            **topic,
            "callout": f"You've reopened \"{topic['canonical_text']}\" {topic['times_logged']} times without deciding.",
        }
        for topic in topics
    ]
