"""The line Choicely says back once you tell it how a decision went.

Not analytics -- the thing a friend says when you tell them how it turned
out. A genuine "nice, that's your read working" when it went well; real
perspective, never a lecture, when it didn't. Claude through the shared
`llm` seam when a key is set (cached, cooldown-protected), a grounded
template otherwise. Generated once when the outcome is recorded and stored
on the decision so it survives the frontend's refetch.
"""
import re

from . import llm, models

_SYSTEM = (
    "You are the user's most level-headed friend. They just recorded how a "
    "decision they'd logged actually turned out. React the way a good friend "
    "would when you tell them how something went -- warm, specific, real. "
    "2-3 sentences, max ~55 words.\n"
    "- If it went well: be genuinely pleased for them and, where the numbers "
    "support it, point out that their instinct or their track record was "
    "right.\n"
    "- If it was just fine: keep it light; not everything has to be a win.\n"
    "- If they regret it: be kind first. Normalise it, then offer ONE piece of "
    "perspective -- often that logging it is what makes the next call of this "
    "kind sharper. Never scold, never say 'I told you so', never open with "
    "criticism.\n"
    "Use only the numbers and history you're given; never invent past events. "
    "Refer to their actual decision, not a generic version of it. "
    "Be careful which way the decision went -- if they logged 'should I skip X' "
    "and went ahead, they SKIPPED it; don't describe them as having done X. "
    "Second person ('you'). No greeting, no sign-off, don't call yourself "
    'their friend. Return JSON: {"reaction": "<your line>"}'
)

_OUTCOME_WORD = {"good": "went well", "neutral": "was just okay", "regret": "you regret it"}

# "should I skip X" is a decision about NOT doing something, so "did" (went
# ahead) means they went ahead with the skip. Spell that out for Claude so it
# doesn't invert the story.
_NEGATIVE_FRAME = re.compile(
    r"^\s*should i\s+(skip|not\b|avoid|quit|cancel|bail|drop|ditch|pass on|say no)", re.I
)


def _plain_action(text: str, action_taken: str | None) -> str | None:
    if action_taken not in ("did", "held_off"):
        return None
    negative = bool(_NEGATIVE_FRAME.search(text or ""))
    if action_taken == "did":
        return (
            "They went ahead with it -- so they did skip / opt out / not do the thing."
            if negative
            else "They went ahead and did it."
        )
    return (
        "They held off -- so they did NOT skip; they went and did the thing anyway."
        if negative
        else "They held off and didn't do it."
    )


def _context(decision: dict, category_label: str | None) -> dict:
    outcomes = models.get_outcomes_for_category(category_label) if category_label else []
    n = len(outcomes)
    regret_n = sum(1 for o in outcomes if o == "regret")
    good_n = sum(1 for o in outcomes if o == "good")
    est = decision.get("blended_regret_estimate")
    if est is None:
        est = decision.get("personality_adjusted_regret_rate")
    if est is None:
        est = decision.get("profile_adjusted_regret_rate")
    if est is None:
        est = decision.get("prior_regret_rate")
    outcome = decision.get("outcome")
    # Did Choicely's estimate point the right way?
    forecast_hit = None
    if est is not None and outcome in ("good", "regret"):
        predicted_regret = est >= 0.5
        actual_regret = outcome == "regret"
        forecast_hit = predicted_regret == actual_regret
    return {
        "text": decision["text"],
        "outcome": outcome,
        "action_taken": decision.get("action_taken"),
        "decision_type": decision.get("decision_type"),
        "stakes": decision.get("stakes"),
        "category_label": category_label,
        "regret_estimate": est,
        "data_points": n,
        "regret_count": regret_n,
        "good_count": good_n,
        "forecast_hit": forecast_hit,
    }


def _prompt(ctx: dict) -> str:
    lines = [f'Decision they logged: "{ctx["text"]}"']
    plain = _plain_action(ctx["text"], ctx["action_taken"])
    if plain:
        lines.append(f'{plain} They now say it {_OUTCOME_WORD.get(ctx["outcome"], ctx["outcome"])}.')
    else:
        lines.append(f'They now say it {_OUTCOME_WORD.get(ctx["outcome"], ctx["outcome"])}.')
    if ctx["stakes"]:
        lines.append(f'Kind: {ctx["decision_type"]}, stakes: {ctx["stakes"]}.')
    if ctx["regret_estimate"] is not None:
        lines.append(f'Choicely had put the regret odds around {round(ctx["regret_estimate"] * 100)}%.')
        if ctx["forecast_hit"] is True:
            lines.append("That estimate pointed the right way.")
        elif ctx["forecast_hit"] is False:
            lines.append("That estimate pointed the wrong way this time.")
    if ctx["data_points"] > 1:
        lines.append(
            f'Counting this one, their record for "{ctx["category_label"]}" is '
            f'{ctx["data_points"]} outcomes: {ctx["good_count"]} went well, '
            f'{ctx["regret_count"]} regretted.'
        )
    return "\n".join(lines)


def _heuristic(ctx: dict) -> str:
    n, reg, good = ctx["data_points"], ctx["regret_count"], ctx["good_count"]
    outcome = ctx["outcome"]

    if outcome == "good":
        if n >= 3 and good / n >= 0.6:
            return (
                f"Nice -- and it's not a fluke. That's {good} of your last {n} calls like this "
                f"landing well. Your read on these is good; trust it a little faster next time."
            )
        if ctx["forecast_hit"] is True and (ctx["regret_estimate"] or 0) <= 0.4:
            return (
                "Good -- that's the one Choicely expected to go your way, and it did. "
                "Worth remembering you don't need to agonise over this kind of call."
            )
        return (
            "Glad that worked out. Logging the wins matters as much as the misses -- it's how "
            "Choicely learns which of your instincts to back."
        )

    if outcome == "neutral":
        return (
            "Fine is fine. Not every decision needs to be a win, and this one's off your plate now. "
            "One more data point toward knowing how these usually go for you."
        )

    # regret
    opener = "That one stings -- sorry it didn't land."
    if n >= 3 and reg / n >= 0.6:
        return (
            f"{opener} And honestly, your history was already saying this: {reg} of {n} like it "
            f"have gone this way. Next time this comes up, that's your answer -- you don't have to "
            f"re-litigate it."
        )
    if ctx["forecast_hit"] is True and (ctx["regret_estimate"] or 0) >= 0.6:
        return (
            f"{opener} Choicely did flag this one as regret-prone -- not to say 'told you so', but "
            f"the forecast is worth a bit more weight next time it reads high."
        )
    return (
        f"{opener} It's one outcome, not a verdict on your judgement. The useful part: Choicely now "
        f"has a real data point here, so the next call of this kind will be a sharper read."
    )


def for_outcome(decision: dict, category_label: str | None) -> str:
    """The warm line Choicely says back when an outcome is recorded."""
    ctx = _context(decision, category_label)
    parsed = llm.complete_json(_SYSTEM, _prompt(ctx), max_tokens=260)
    if parsed and isinstance(parsed.get("reaction"), str) and parsed["reaction"].strip():
        return parsed["reaction"].strip()[:500]
    return _heuristic(ctx)
