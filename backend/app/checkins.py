"""
Proactive check-ins: Choicely's promise that it will circle back so you
don't have to remember to reflect.

When a decision is logged, we estimate when it will have played out and
stamp `outcome_due_at`. Once that time passes with no outcome recorded, the
decision surfaces as a check-in ("you were weighing X -- how did it land?").
Answering it feeds the same outcome pipeline as the manual buttons.

The delay is deliberately short for urgent/routine things and longer for
high-stakes ones -- you know within hours whether skipping breakfast was a
mistake; whether quitting the club was takes days.
"""
import json
from datetime import datetime, timedelta

_TS_FMT = "%Y-%m-%d %H:%M:%S"


def due_delay_hours(decision_type: str, stakes: str, urgency: str) -> float:
    if urgency == "high":
        return 4
    if stakes == "high":
        return 72
    if decision_type in ("routine", "health"):
        return 20
    if decision_type == "social":
        return 30
    return 48


def outcome_due_at(decision_type: str, stakes: str, urgency: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    due = now + timedelta(hours=due_delay_hours(decision_type, stakes, urgency))
    return due.strftime(_TS_FMT)


def _relative(logged_at: str | None) -> str:
    parsed = None
    if logged_at:
        try:
            parsed = datetime.strptime(logged_at[:19], _TS_FMT)
        except ValueError:
            parsed = None
    if parsed is None:
        return "A little while ago"
    hours = (datetime.now() - parsed).total_seconds() / 3600
    if hours < 1:
        return "Earlier"
    if hours < 24:
        return f"{round(hours)}h ago"
    days = round(hours / 24)
    return "Yesterday" if days == 1 else f"{days} days ago"


def check_in_prompt(decision: dict) -> dict:
    option_texts = None
    if decision.get("options_json"):
        try:
            option_texts = [o["text"] for o in json.loads(decision["options_json"])["items"]]
        except (ValueError, KeyError, TypeError):
            option_texts = None

    if option_texts:
        joined = ", ".join(option_texts[:-1]) + f" or {option_texts[-1]}"
        prompt = f'You were choosing between {joined}. Which did you go with -- and how did it land?'
    else:
        prompt = f'You were weighing: "{decision["text"]}". How did it land?'

    return {
        "id": decision["id"],
        "text": decision["text"],
        "decision_type": decision["decision_type"],
        "stakes": decision["stakes"],
        "logged_relative": _relative(decision["timestamp"]),
        "prompt": prompt,
        "options": option_texts,
        "had_prediction": decision.get("source") in ("blended", "personal", "profile_prior", "personality_prior"),
        "predicted_regret": decision.get("blended_regret_estimate"),
    }


def pending(due_rows: list[dict]) -> list[dict]:
    return [check_in_prompt(r) for r in due_rows]
