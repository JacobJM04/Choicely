import json
import math
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import (
    advice,
    agent,
    calibration,
    checkins,
    classifier,
    community,
    dataset,
    debrief,
    debt,
    gametheory,
    insights,
    load,
    models,
    options,
    personality,
    profile,
    push,
    reaction,
    reflection,
    regret,
    safety,
    triggers,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    models.init_db()
    yield


app = FastAPI(title="Choicely API", lifespan=lifespan)

# CORS origins: any localhost port for dev (Vite hops 5173 -> 5174 -> ... when a
# port is taken), plus anything in CHOICELY_ORIGINS (comma-separated) for a
# deployed frontend.
import os as _os

_extra_origins = [o.strip() for o in _os.environ.get("CHOICELY_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_extra_origins,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# Input bounds -- generous for real use, tight enough that a single request
# can't spike memory / CPU / LLM token spend.
_MAX_TEXT = 2000
_MAX_OPTION = 300


class DecisionIn(BaseModel):
    text: str = Field(default="", max_length=_MAX_TEXT)
    # 2-4 alternatives turns this into a "compare these options" decision.
    options: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("options")
    @classmethod
    def _cap_option_length(cls, v: list[str]) -> list[str]:
        return [o[:_MAX_OPTION] for o in v]


class OutcomeIn(BaseModel):
    outcome: str = Field(max_length=16)
    # Required only when the decision was a compare-options one: which
    # option (0-based) the user actually went with.
    chosen_option: int | None = Field(default=None, ge=0, le=7)
    # For a yes/no decision: what the user actually did, captured just before
    # they say how it went. "did" | "held_off". Optional -- older clients and
    # compare-options decisions don't send it.
    action_taken: str | None = Field(default=None, max_length=16)
    # When true, the (category, outcome) pair is added to the shared pool
    # (see community.py). Anonymous -- no text, no id.
    contribute: bool = False


class ProfileIn(BaseModel):
    name: str = Field(max_length=80)
    answers: list[float] = Field(max_length=20)
    personality_answers: dict[str, float | str] = Field(default_factory=dict, max_length=40)


VALID_OUTCOMES = {"good", "neutral", "regret"}
VALID_ACTIONS = {"did", "held_off"}


def _serialize(row: dict) -> dict:
    row = dict(row)
    breakdown_json = row.pop("breakdown_json", None)
    row["breakdown"] = json.loads(breakdown_json) if breakdown_json else None
    options_json = row.pop("options_json", None)
    row["options"] = json.loads(options_json) if options_json else None
    safety_json = row.pop("safety_json", None)
    row["safety"] = json.loads(safety_json) if safety_json else None
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
def create_decision(payload: DecisionIn, background_tasks: BackgroundTasks):
    option_texts = [o.strip() for o in payload.options if o.strip()]
    if len(option_texts) >= 2:
        return _create_option_decision(payload.text.strip(), option_texts[:4], background_tasks)

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Decision text cannot be empty.")

    flag = safety.screen(text)
    if flag and flag["tier"] == "crisis":
        return _create_flagged_decision(text, flag)

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
            "safety_json": json.dumps(flag) if flag else None,
            "reference_regret_rate": prior.get("reference_regret_rate"),
            "community_n": prior.get("community_n") or 0,
        }
    )

    final_topic_id = existing_topic_id if existing_topic_id is not None else decision_id
    if existing_topic_id is None:
        models.set_topic_id(decision_id, decision_id)
    models.recount_topic(final_topic_id)

    created = models.get_decision(decision_id)

    # The friendly line under the card -- skip it when Choicely already
    # answered outright (the auto-resolution is the advice). Generated in the
    # background: it's a Claude call, and logging a decision shouldn't make
    # someone wait on a nice-to-have note. The client picks it up on its next
    # refetch; `advice` is just null until then.
    if not auto_resolution_text:
        background_tasks.add_task(_write_advice, decision_id, created, prior["category_label"])

    agent.on_decision_logged(created)
    return _serialize(created)


def _write_advice(decision_id: int, decision: dict, category_label: str | None) -> None:
    note = advice.for_decision(decision, category_label)
    models.set_advice(decision_id, note)


def _create_flagged_decision(text: str, flag: dict) -> dict:
    """A crisis-tier decision: logged so the person doesn't lose what they
    wrote, but with no prediction, no category, and no check-in nagging."""
    decision_id = models.insert_decision(
        {
            "text": text,
            "decision_type": "routine",
            "stakes": "high",
            "urgency": "low",
            "source": "flagged_crisis",
            "safety_json": json.dumps(flag),
        }
    )
    models.set_topic_id(decision_id, decision_id)
    return _serialize(models.get_decision(decision_id))


def _create_option_decision(header: str, option_texts: list[str], background_tasks: BackgroundTasks) -> dict:
    flag = safety.screen(header, *option_texts)
    if flag and flag["tier"] == "crisis":
        return _create_flagged_decision(
            header or "Choosing between: " + ", ".join(option_texts), flag
        )

    profile_row = models.get_profile()
    analysis = options.analyze(option_texts, profile_row)
    overall = options.overall_classification(header, option_texts, profile_row, analysis["items"])

    text = header or "Choosing between: " + ", ".join(option_texts)
    best = min(o["regret_estimate"] for o in analysis["items"])

    decision_id = models.insert_decision(
        {
            "text": text,
            "decision_type": overall["decision_type"],
            "stakes": overall["stakes"],
            "urgency": overall["urgency"],
            "outcome_due_at": checkins.outcome_due_at(
                overall["decision_type"], overall["stakes"], overall["urgency"]
            ),
            "source": "options",
            # category is unset until an option is chosen (see
            # models.adopt_chosen_option); the estimate shown meanwhile is the
            # best any option can do.
            "blended_regret_estimate": best,
            "options_json": json.dumps(analysis),
            "safety_json": json.dumps(flag) if flag else None,
        }
    )
    models.set_topic_id(decision_id, decision_id)
    created = models.get_decision(decision_id)

    background_tasks.add_task(_write_options_advice, decision_id, text, analysis)

    agent.on_decision_logged(created)
    return _serialize(created)


def _write_options_advice(decision_id: int, header: str, analysis: dict) -> None:
    note = advice.for_options(header, analysis)
    if note:
        models.set_advice(decision_id, note)


@app.get("/decisions")
def get_decisions(include_seed: bool = False):
    return [_serialize(row) for row in models.list_decisions(include_seed)]


@app.post("/decisions/{decision_id}/outcome")
def record_outcome(decision_id: int, payload: OutcomeIn, background_tasks: BackgroundTasks):
    if payload.outcome not in VALID_OUTCOMES:
        raise HTTPException(status_code=400, detail=f"outcome must be one of {sorted(VALID_OUTCOMES)}")
    if payload.action_taken is not None and payload.action_taken not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action_taken must be one of {sorted(VALID_ACTIONS)}")

    existing = models.get_decision(decision_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Decision not found.")
    if existing["outcome"] is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Outcome already recorded as '{existing['outcome']}'. It's a one-time tap, not editable.",
        )

    if existing["options_json"]:
        items = json.loads(existing["options_json"])["items"]
        idx = payload.chosen_option
        if idx is None or not (0 <= idx < len(items)):
            raise HTTPException(
                status_code=400,
                detail="This was a compare-options decision -- pass chosen_option (0-based) for the one you went with.",
            )
        models.adopt_chosen_option(decision_id, idx, items[idx])

    # Race-safe: only one concurrent tap actually records the outcome.
    if not models.update_outcome(decision_id, payload.outcome, payload.action_taken):
        current = models.get_decision(decision_id)
        raise HTTPException(
            status_code=409,
            detail=f"Outcome already recorded as '{current['outcome']}'. It's a one-time tap, not editable.",
        )

    updated = models.get_decision(decision_id)
    if payload.contribute and updated["prior_category_label"] and updated["source"] != "flagged_crisis":
        community.contribute(updated["prior_category_label"], payload.outcome)

    # The warm line Choicely says back -- a nod when it went well, perspective
    # when it didn't. Generated in the background for the same reason as the
    # logging-time advice: it's a Claude call, and recording an outcome
    # shouldn't hang on it. `outcome_reaction` is null until the next refetch.
    background_tasks.add_task(_write_reaction, decision_id, updated, updated["prior_category_label"])

    agent.on_outcome_recorded(updated)
    return _serialize(updated)


def _write_reaction(decision_id: int, decision: dict, category_label: str | None) -> None:
    reaction_line = reaction.for_outcome(decision, category_label)
    models.set_outcome_reaction(decision_id, reaction_line)


@app.get("/reflection")
def get_reflection():
    """A short plain-language read on recent decisions -- Claude when a key is set, heuristics otherwise."""
    return reflection.weekly_reflection()


class DebriefIn(BaseModel):
    text: str = Field(max_length=_MAX_TEXT)


@app.post("/debrief")
def post_debrief(payload: DebriefIn):
    """Read a messy paragraph about a decision someone's stuck on and hand back
    a grounded read: the real question, what's at stake, their options, and a
    recommendation built on their own recorded history. Does not log anything."""
    text = payload.text.strip()
    if len(text) < 8:
        raise HTTPException(status_code=400, detail="Give me a sentence or two about the decision.")
    flag = safety.screen(text)
    if flag and flag["tier"] == "crisis":
        return {"source": "flagged_crisis", "safety": flag}
    return debrief.debrief(text)


@app.get("/agent/activity")
def get_agent_activity():
    """The agent's log: what Choicely auto-resolved, checked in on, and spotted,
    plus a live triage of the open backlog (answer now / keep watching / leave it)."""
    return agent.activity()


@app.get("/check-ins")
def get_check_ins():
    """Decisions whose check-in time has come -- Choicely circling back so you don't have to."""
    due = models.get_due_check_ins()
    prompts = checkins.pending(due)
    # Let Claude phrase the question when it's available; falls back to the
    # template inside agent.checkin_question.
    for row, prompt in zip(due, prompts):
        prompt["prompt"] = agent.checkin_question(row)
    return prompts


class AdvanceIn(BaseModel):
    # bounded: this rewrites every timestamp in the DB, and an out-of-range
    # or non-finite value makes SQLite write NULLs and brick the data.
    hours: float = Field(default=24, gt=0, le=24 * 60)


# The demo clock is disabled on a real deploy unless CHOICELY_DEMO is set --
# otherwise anyone could shuffle the timeline. Local dev leaves it on.
_DEMO_ENABLED = _os.environ.get("CHOICELY_DEMO", "1") not in ("0", "false", "False", "")


@app.post("/demo/advance")
def advance_time(payload: AdvanceIn):
    """Demo aid only: rewind every decision's clock so pending check-ins come due."""
    if not _DEMO_ENABLED:
        raise HTTPException(status_code=404, detail="Not found.")
    if not math.isfinite(payload.hours):
        raise HTTPException(status_code=400, detail="hours must be a finite number")
    touched = models.shift_time(payload.hours)
    pushed = push.notify_due()
    synced = agent.sync()
    return {"shifted_hours": payload.hours, "rows_touched": touched, "push": pushed, "agent": synced}


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


@app.get("/triggers")
def get_triggers(include_seed: bool = True):
    """Conditions under which the user regrets decisions more (or less) than usual."""
    return triggers.regret_triggers(include_seed)


@app.get("/community/stats")
def get_community_stats():
    """Size of the shared-outcome pool and how much of it is real contributions."""
    return community.stats()


@app.get("/dashboard")
def get_dashboard(include_seed: bool = False):
    topics = models.get_debt_topics(include_seed)
    return [
        {
            **topic,
            "callout": (
                f"You've logged \"{topic['canonical_text']}\" {topic['times_logged']} times "
                f"and never recorded what you decided."
            ),
        }
        for topic in topics
    ]


# --- static frontend (single-container deploy) ----------------------------
# When frontend/dist exists (built by the Dockerfile), serve it from the same
# origin as the API so there's one thing to deploy. In local dev this block is
# a no-op and Vite serves the frontend on its own port.
_DIST = _os.path.realpath(_os.path.join(_os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if _os.path.isdir(_DIST):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _INDEX = _os.path.join(_DIST, "index.html")
    app.mount("/assets", StaticFiles(directory=_os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # Serve a real file only if it resolves to something *inside* _DIST --
        # otherwise "../../etc/passwd" style paths would escape the build dir.
        if full_path:
            candidate = _os.path.realpath(_os.path.join(_DIST, full_path))
            if (
                candidate == _DIST or candidate.startswith(_DIST + _os.sep)
            ) and _os.path.isfile(candidate):
                return FileResponse(candidate)
        return FileResponse(_INDEX)
