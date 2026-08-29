"""
Onboarding survey: a one-time, five-question check on where someone falls
between spontaneous and planner. Used to nudge the population-prior regret
rate toward what's statistically more likely for *this kind of person*
before any real personal outcome data exists -- a second cold-start layer
sitting between "population average" and "your own history":

    dataset prior -> profile-adjusted prior -> blended -> personal

Deliberately does NOT feed auto-resolve: a 5-question survey is too coarse
a signal to justify answering a decision outright. It only nudges the
starting point that real outcome data then blends away from.
"""
from . import models

# Each answer contributes 0 (spontaneous), 0.5 (balanced), or 1 (planner).
# planning_score is the mean of all answers given.
SURVEY_QUESTIONS = [
    {
        "id": "plans_change",
        "question": "When plans change last minute, you feel...",
        "options": [
            {"label": "Kind of into it -- keeps things interesting", "value": 0},
            {"label": "It's fine, I adapt", "value": 0.5},
            {"label": "Thrown off -- I like knowing what's happening", "value": 1},
        ],
    },
    {
        "id": "big_purchase",
        "question": "Before a big purchase, you usually...",
        "options": [
            {"label": "Just buy it if I want it", "value": 0},
            {"label": "Think it over for a bit", "value": 0.5},
            {"label": "Research and compare for days first", "value": 1},
        ],
    },
    {
        "id": "ideal_saturday",
        "question": "Your ideal Saturday is...",
        "options": [
            {"label": "Whatever comes up", "value": 0},
            {"label": "A mix of plans and open time", "value": 0.5},
            {"label": "Scheduled out in advance", "value": 1},
        ],
    },
    {
        "id": "to_do_list",
        "question": "Your to-do list is...",
        "options": [
            {"label": "Mostly in my head", "value": 0},
            {"label": "A loose list I sometimes check", "value": 0.5},
            {"label": "Written down and worked through in order", "value": 1},
        ],
    },
    {
        "id": "commitments",
        "question": "When you commit to something, you...",
        "options": [
            {"label": "Often change your mind later", "value": 0},
            {"label": "Usually follow through", "value": 0.5},
            {"label": "Almost always follow through, no matter what", "value": 1},
        ],
    },
]

_VALID_ANSWER_VALUES = {0, 0.5, 1}

# How far an archetype can shift the population prior at the extremes, in
# percentage points of regret rate. Kept modest -- this is a coarse survey
# signal, not real outcome data, so it should nudge, not dominate.
MAX_SHIFT = 0.15


def score_survey(answers: list[float]) -> tuple[float, str]:
    """answers: one value per question, in SURVEY_QUESTIONS order.
    Returns (planning_score in [0,1], label)."""
    if len(answers) != len(SURVEY_QUESTIONS):
        raise ValueError(f"expected {len(SURVEY_QUESTIONS)} answers, got {len(answers)}")
    for value in answers:
        if value not in _VALID_ANSWER_VALUES:
            raise ValueError(f"invalid answer value: {value}")

    planning_score = sum(answers) / len(answers)
    if planning_score < 0.4:
        label = "spontaneous"
    elif planning_score > 0.6:
        label = "planner"
    else:
        label = "balanced"
    return planning_score, label


def adjust_prior(prior_regret_rate: float, planning_alignment: int | None) -> float | None:
    """Nudge the population prior toward this user's planning style.

    Returns None if there's no saved profile, or this category is too
    general to safely nudge (planning_alignment is None) -- callers should
    fall back to the unadjusted prior in that case.
    """
    if planning_alignment is None:
        return None
    profile = models.get_profile()
    if profile is None:
        return None

    deviation_from_average = profile["planning_score"] - 0.5  # population assumed centered at 0.5
    shift = deviation_from_average * planning_alignment * MAX_SHIFT
    return min(0.95, max(0.05, prior_regret_rate + shift))
