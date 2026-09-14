"""The friendly note under a freshly logged decision.

Not a statistic read back at you -- the thing a level-headed friend who has
been watching your decisions would actually say: name the real tradeoff,
weigh in with whatever your history says, and land on one concrete next
step. Claude when a key is set (through the shared `llm` seam, so it's
cached and has a cooldown), a grounded template otherwise. Generated once at
log time and stored on the decision so it survives the frontend's refetch.
"""
from . import llm, models

_SYSTEM = (
    "You are the user's most level-headed friend, reacting to a decision they "
    "just logged in a decision-tracking app. Talk to them the way a friend who "
    "actually knows their patterns would -- not a coach, not a therapist.\n"
    "Write 3-4 sentences, max ~90 words:\n"
    "1. Name the real tradeoff underneath the decision in one line.\n"
    "2. Weigh in using the number and history you're given -- what their own "
    "record or the general pattern actually says here.\n"
    "3. End on ONE concrete next step (sleep on it / just go / text them back / "
    "pick one and close it / set a decide-by date).\n"
    "Warm but honest. Second person ('you'). Use only the numbers and history "
    "you're given -- never invent past events. No greeting, no sign-off, don't "
    'call yourself their friend. Return JSON: {"advice": "<your note>"}'
)

_OPTIONS_SYSTEM = (
    "You are the user's most level-headed friend. They just asked a "
    "decision-tracking app to compare a few options for one decision. Each "
    "option has its own regret estimate (lower = they're less likely to regret "
    "it). Write 3-4 sentences, max ~90 words:\n"
    "1. Say what the choice is really between, in plain terms.\n"
    "2. Note which option the numbers favour and whether it's a clear win or "
    "close.\n"
    "3. Point at the one real question that should settle it for them.\n"
    "Warm, direct, second person. Use only what you're given. No greeting, no "
    'sign-off. Return JSON: {"advice": "<your note>"}'
)


def _context(decision: dict, category_label: str | None) -> dict:
    outcomes = models.get_outcomes_for_category(category_label) if category_label else []
    est = decision.get("blended_regret_estimate")
    if est is None:
        est = decision.get("personality_adjusted_regret_rate")
    if est is None:
        est = decision.get("profile_adjusted_regret_rate")
    if est is None:
        est = decision.get("prior_regret_rate") or 0.5
    return {
        "text": decision["text"],
        "decision_type": decision["decision_type"],
        "stakes": decision["stakes"],
        "category_label": category_label,
        "regret_estimate": est,
        "data_points": len(outcomes),
        "regret_count": sum(1 for o in outcomes if o == "regret"),
        # reopened_count is the number of times this topic has been logged;
        # >1 with no outcome recorded means it's decision debt.
        "times_logged": decision.get("reopened_count") or 0,
        "in_debt": (decision.get("reopened_count") or 0) > 1 and not decision.get("outcome"),
        "cold_start": decision.get("source") == "cold_start",
    }


def _prompt(ctx: dict) -> str:
    lines = [
        f'Decision they logged: "{ctx["text"]}"',
        f'Kind: {ctx["decision_type"]}, stakes: {ctx["stakes"]}.',
    ]
    est = round(ctx["regret_estimate"] * 100)
    if ctx["cold_start"]:
        lines.append("This is the very first decision they've ever logged here.")
    elif ctx["data_points"] > 0:
        lines.append(
            f'Their own record for "{ctx["category_label"]}": {ctx["data_points"]} recorded '
            f'outcome(s), regretted {ctx["regret_count"]}. Choicely puts their regret odds '
            f'on this one around {est}%.'
        )
    else:
        lines.append(
            f'No personal history for this kind of call yet. The going regret rate for it '
            f'is about {est}%.'
        )
    if ctx["in_debt"]:
        lines.append(
            f'They have logged this same question {ctx["times_logged"]} times without ever '
            f'deciding -- it is stuck.'
        )
    return "\n".join(lines)


def _heuristic(ctx: dict) -> str:
    est = round(ctx["regret_estimate"] * 100)
    if ctx["in_debt"]:
        return (
            f"The real question here isn't which way to go -- it's that you keep carrying it "
            f"unresolved. You've logged this {ctx['times_logged']} times without recording a "
            f"decision, and the not-deciding is costing you more than either answer would. "
            f"Set yourself a decide-by date this week, pick the one you can live with, and let it go."
        )
    if ctx["cold_start"]:
        return (
            "This is the first decision you've logged, so there's no read on your history yet -- "
            "everything from here builds on how these actually turn out for you. Go with your gut "
            "on this one. Then come back and tell Choicely how it landed, so the next call like it "
            "has something to stand on."
        )
    if ctx["data_points"] >= 3 and est >= 60:
        return (
            f"Underneath this is the usual pull between the easy thing now and how you tend to feel "
            f"about it after. Your own record isn't kind here: you've regretted it "
            f"{ctx['regret_count']} of {ctx['data_points']} times, and Choicely reads this one at "
            f"about {est}%. Lean toward not doing it -- and if you do, notice whether the regret "
            f"shows up the way it usually does."
        )
    if ctx["data_points"] >= 3 and est <= 35:
        return (
            f"This looks like a bigger deal in your head than your history says it is. Across "
            f"{ctx['data_points']} times, you've been glad you did it (or fine with it) far more "
            f"often than not -- only around {est}% regret. Trust that pattern, go ahead, and log "
            f"how it lands so the read stays honest."
        )
    if est >= 60:
        return (
            f"The tension here is between what's convenient today and what you'll wish you'd done "
            f"tomorrow. This kind of call tips into regret more often than not (~{est}%), and you "
            f"don't have much of your own history on it yet. If you can give it a night before you "
            f"commit, do -- then check back in with yourself in the morning."
        )
    if est <= 35:
        return (
            f"You're weighing a small cost now against a payoff you're probably underrating. The "
            f"odds are on your side here -- about {est}% regret for this kind of call. If you're "
            f"leaning toward it, that's likely the honest read; go with it and record how it "
            f"actually went."
        )
    return (
        f"This one genuinely goes both ways -- Choicely puts it near a coin toss (~{est}%), and "
        f"there isn't enough of your history yet to break the tie. That means there's no wrong "
        f"answer to agonise over. Pick the one you can defend to yourself, and make sure you log "
        f"the outcome so the next one like it is a clearer call."
    )


def for_decision(decision: dict, category_label: str | None) -> str:
    """The friendly note for a just-logged yes/no decision."""
    ctx = _context(decision, category_label)
    parsed = llm.complete_json(_SYSTEM, _prompt(ctx), max_tokens=400)
    if parsed and isinstance(parsed.get("advice"), str) and parsed["advice"].strip():
        return parsed["advice"].strip()[:700]
    return _heuristic(ctx)


def _options_prompt(header: str, items: list[dict], lean_idx: int, clear: bool) -> str:
    lines = [f'The decision: "{header}"' if header else "They're choosing between a few options."]
    lines.append("Options, with Choicely's regret estimate for each:")
    for i, o in enumerate(items):
        tag = " (lowest regret)" if i == lean_idx else ""
        lines.append(f'  - "{o["text"]}" -- {round(o.get("regret_estimate", 0) * 100)}%{tag}')
    spread = max(o.get("regret_estimate", 0) for o in items) - min(
        o.get("regret_estimate", 0) for o in items
    )
    lines.append(
        f'The lowest-regret option is {"a clear pick" if clear else "only just ahead"} '
        f'(spread {round(spread * 100)} points).'
    )
    return "\n".join(lines)


def _options_heuristic(header: str, items: list[dict], lean_idx: int, clear: bool) -> str:
    best = items[lean_idx]
    best_pct = round(best.get("regret_estimate", 0) * 100)
    if clear:
        body = (
            f'Of these, "{best["text"]}" comes out clearly lowest at {best_pct}% regret, so if '
            f"you've got no strong pull the other way, that's the one to take."
        )
    else:
        others = [o for i, o in enumerate(items) if i != lean_idx]
        runner = min(others, key=lambda o: o.get("regret_estimate", 1))
        body = (
            f"\"{best['text']}\" edges it at {best_pct}%, but it's close with "
            f"\"{runner['text']}\" -- close enough that the number shouldn't be what decides it."
        )
    return (
        f"What you're really choosing between is how much you protect your own time and energy "
        f"versus not missing out. {body} The question that should settle it: which version will "
        f"you be glad you picked a week from now, not just tonight?"
    )


def for_options(header: str, analysis: dict) -> str:
    """The friendly note for a just-logged compare-options decision."""
    items = analysis.get("items", [])
    if not items:
        return ""
    lean_idx = analysis.get("lean_idx", 0)
    clear = bool(analysis.get("clear"))
    parsed = llm.complete_json(
        _OPTIONS_SYSTEM, _options_prompt(header, items, lean_idx, clear), max_tokens=400
    )
    if parsed and isinstance(parsed.get("advice"), str) and parsed["advice"].strip():
        return parsed["advice"].strip()[:700]
    return _options_heuristic(header, items, lean_idx, clear)
