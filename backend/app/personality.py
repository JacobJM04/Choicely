"""
Personality onboarding: a one-time, ten-question extension of the existing
planning-style survey (see profile.py, left untouched) that measures six
additional dimensions -- risk tolerance (financial/social), regret
orientation, social energy, decisiveness, conflict style, and stakes
sensitivity.

Like profile.py's planning-style nudge, this only ever nudges the *prior*
component of a regret prediction, never the personal-history component --
structurally, that means it can never single-handedly trigger auto-resolve
(auto-resolve requires confidence == 1.0, at which point the prior's weight
in the blend is zero). It runs *before* profile.adjust_prior in the pipeline
and produces a smaller, secondary shift (+-10pp vs. planning's +-15pp) since
it's a coarser, more indirect signal.

conflict_style and social_energy are qualitative-only: they're passed as
Claude prompt context (classifier.py, gametheory.py) and select fallback
template variants, but don't feed this numeric formula.
"""
from . import models

PERSONALITY_QUESTIONS = [
    {
        "id": "risk_financial",
        "dimension": "risk_tolerance_financial",
        "question": "When it comes to money, you tend to...",
        "options": [
            {"label": "Play it safe -- I hate the idea of losing money", "value": 0},
            {"label": "Take calculated risks sometimes", "value": 0.5},
            {"label": "Go for it -- I'd rather risk it than miss out", "value": 1},
        ],
    },
    {
        "id": "risk_social",
        "dimension": "risk_tolerance_social",
        "question": "Meeting new people or trying a new social scene, you're more likely to...",
        "options": [
            {"label": "Stick with what's familiar", "value": 0},
            {"label": "Dip a toe in", "value": 0.5},
            {"label": "Jump right in", "value": 1},
        ],
    },
    {
        "id": "regret_orientation_1",
        "dimension": "regret_orientation",
        "question": "Looking back on your life so far, you regret more...",
        "options": [
            {"label": "Things I did that didn't work out", "value": "action-averse"},
            {"label": "About equally, honestly", "value": "balanced"},
            {"label": "Chances I didn't take", "value": "inaction-averse"},
        ],
    },
    {
        "id": "regret_orientation_2",
        "dimension": "regret_orientation",
        "question": "A friend is on the fence about a leap they could take. Your gut reaction is usually...",
        "options": [
            {"label": "\"Are you sure? Think it through.\"", "value": "action-averse"},
            {"label": "It depends on the situation", "value": "balanced"},
            {"label": "\"Just do it, you'll regret not trying.\"", "value": "inaction-averse"},
        ],
    },
    {
        "id": "social_energy_leaning",
        "dimension": "social_energy",
        "question": "After a full day of being around people, you feel...",
        "options": [
            {"label": "Drained -- I need quiet time to recover", "value": "introvert"},
            {"label": "A bit of both, depends on the day", "value": "balanced"},
            {"label": "Energized -- I could keep going", "value": "extrovert"},
        ],
    },
    {
        "id": "social_energy_stability",
        "dimension": "social_energy_stability",
        "question": "Your appetite for socializing week to week is...",
        "options": [
            {"label": "Pretty consistent -- I know roughly what I want", "value": "stable"},
            {"label": "All over the place depending on the week", "value": "fluctuating"},
        ],
    },
    {
        "id": "decisiveness_1",
        "dimension": "decisiveness",
        "question": "When a decision comes up, you usually...",
        "options": [
            {"label": "Decide fast and move on", "value": 0},
            {"label": "Weigh it for a bit, then decide", "value": 0.5},
            {"label": "Keep turning it over, sometimes for way too long", "value": 1},
        ],
    },
    {
        "id": "decisiveness_2",
        "dimension": "decisiveness",
        "question": "Picking something off a menu with 30+ options, you...",
        "options": [
            {"label": "Already know before the menu's open", "value": 0},
            {"label": "Narrow it down pretty quickly", "value": 0.5},
            {"label": "Are still deciding when the waiter comes back", "value": 1},
        ],
    },
    {
        "id": "conflict_style",
        "dimension": "conflict_style",
        "question": "When there's tension with someone close to you, you tend to...",
        "options": [
            {"label": "Avoid bringing it up if I can", "value": "avoidant"},
            {"label": "Say what I need to say, plainly", "value": "direct"},
            {"label": "Focus on keeping them comfortable, even if it costs me", "value": "accommodating"},
            {"label": "Push to make sure my side is heard", "value": "competitive"},
        ],
    },
    {
        "id": "stakes_sensitivity",
        "dimension": "stakes_sensitivity",
        "question": "When a decision is described as \"high stakes,\" how much does that change how you approach it?",
        "options": [
            {"label": "Not much -- I handle it the same as anything else", "value": "low"},
            {"label": "Somewhat -- I slow down a little", "value": "medium"},
            {"label": "A lot -- I go into a completely different mode", "value": "high"},
        ],
    },
]

_QUESTIONS_BY_ID = {q["id"]: q for q in PERSONALITY_QUESTIONS}

_NUMERIC_DIMENSIONS = {"risk_tolerance_financial", "risk_tolerance_social", "decisiveness"}
_CATEGORICAL_DIMENSIONS = {
    "regret_orientation", "social_energy", "social_energy_stability",
    "conflict_style", "stakes_sensitivity",
}


def score_personality(answers: dict) -> dict:
    """answers: {question_id: value}, one entry per PERSONALITY_QUESTIONS id.
    Returns the structured personality profile (dimension -> value)."""
    missing = [q["id"] for q in PERSONALITY_QUESTIONS if q["id"] not in answers]
    if missing:
        raise ValueError(f"missing answers for: {missing}")

    by_dimension: dict[str, list] = {}
    for q in PERSONALITY_QUESTIONS:
        value = answers[q["id"]]
        valid_values = {opt["value"] for opt in q["options"]}
        if value not in valid_values:
            raise ValueError(f"invalid answer for {q['id']}: {value}")
        by_dimension.setdefault(q["dimension"], []).append(value)

    result = {}
    for dimension, values in by_dimension.items():
        if dimension in _NUMERIC_DIMENSIONS:
            result[dimension] = sum(values) / len(values)
        else:
            # Majority vote for two-question categorical dimensions
            # (regret_orientation); direct pass-through for single-question ones.
            result[dimension] = max(set(values), key=values.count)
    return result


MAX_PERSONALITY_SHIFT = 0.10


def adjust_prior(
    prior_regret_rate: float,
    planning_alignment: int | None,
    decision_type: str,
    decision_stakes: str,
    profile: dict | None,
) -> float | None:
    """Nudge the prior regret rate using risk tolerance + regret orientation,
    scaled by stakes sensitivity. Returns None if there's no saved
    personality profile yet, or this category is too general to safely nudge
    (planning_alignment is None) -- same guard as profile.adjust_prior."""
    if planning_alignment is None or profile is None:
        return None
    if profile.get("risk_tolerance_financial") is None:
        return None  # personality survey not completed for this profile

    if decision_type == "financial":
        risk_tolerance = profile["risk_tolerance_financial"]
    elif decision_type in ("social", "interpersonal"):
        risk_tolerance = profile["risk_tolerance_social"]
    else:
        risk_tolerance = 0.5  # no-op

    risk_component = -(risk_tolerance - 0.5) * planning_alignment

    orientation = profile.get("regret_orientation")
    orientation_dir = {"inaction-averse": 1, "action-averse": -1}.get(orientation, 0)
    orientation_component = orientation_dir * planning_alignment

    combined = (risk_component + orientation_component) / 2

    sensitivity = profile.get("stakes_sensitivity")
    if decision_stakes == "high" and sensitivity == "high":
        stakes_multiplier = 1.5
    elif decision_stakes == "high" and sensitivity == "low":
        stakes_multiplier = 0.5
    else:
        stakes_multiplier = 1.0

    shift = combined * MAX_PERSONALITY_SHIFT * stakes_multiplier
    return min(0.95, max(0.05, prior_regret_rate + shift))
