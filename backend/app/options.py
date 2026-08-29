"""
Multi-option decisions: comparing A vs B vs C instead of a single yes/no.

Each option is run through the same cold-start pipeline a standalone
decision would be -- classified for its own type, matched to a population
prior, adjusted for the user's planning style and personality, then
blended with whatever personal history exists for that category. The
result is a per-option regret estimate, and the lowest one is Choicely's
lean.

Once the user records which option they went with, the decision adopts
that option (models.adopt_chosen_option) and from then on behaves like any
other resolved decision -- it shows up in the forecast for the chosen
option's category, feeds calibration, and so on.
"""
from . import classifier, dataset, personality, profile, regret

_LEVEL = {"low": 0, "medium": 1, "high": 2}
_LEVEL_NAME = {0: "low", 1: "medium", 2: "high"}

# How much lower the best option's estimate must be than the runner-up
# before Choicely will call it a clear lean rather than "roughly even".
_CLEAR_MARGIN = 0.08


def analyze_option(text: str, profile_row: dict | None) -> dict:
    classification = classifier.classify_decision(text, profile_row)
    dtype = classification["decision_type"]
    prior = dataset.get_prior(dtype, text)

    profile_adjusted = profile.adjust_prior(prior["regret_rate"], prior["planning_alignment"])
    personality_adjusted = personality.adjust_prior(
        profile_adjusted if profile_adjusted is not None else prior["regret_rate"],
        prior["planning_alignment"],
        dtype,
        classification["stakes"],
        profile_row,
    )
    effective = personality_adjusted if personality_adjusted is not None else (
        profile_adjusted if profile_adjusted is not None else prior["regret_rate"]
    )
    prediction = regret.predict(prior["category_label"], effective)

    if prediction["personal_data_points"] == 0:
        if personality_adjusted is not None:
            source = "personality_prior"
        elif profile_adjusted is not None:
            source = "profile_prior"
        else:
            source = "dataset_prior"
    elif prediction["confidence"] >= 1.0:
        source = "personal"
    else:
        source = "blended"

    return {
        "text": text,
        "decision_type": dtype,
        "stakes": classification["stakes"],
        "urgency": classification["urgency"],
        "category_label": prior["category_label"],
        "prior_regret_rate": prior["regret_rate"],
        "prior_sample_size": prior["sample_size"],
        "prior_description": prior["description"],
        "profile_adjusted_regret_rate": profile_adjusted,
        "personality_adjusted_regret_rate": personality_adjusted,
        "regret_estimate": prediction["blended_regret_estimate"],
        "confidence": prediction["confidence"],
        "data_points": prediction["personal_data_points"],
        "source": source,
    }


def analyze(option_texts: list[str], profile_row: dict | None) -> dict:
    items = [analyze_option(t, profile_row) for t in option_texts]
    order = sorted(range(len(items)), key=lambda i: items[i]["regret_estimate"])
    lean_idx = order[0]
    margin = (
        items[order[1]]["regret_estimate"] - items[order[0]]["regret_estimate"]
        if len(order) > 1
        else 1.0
    )
    for i, item in enumerate(items):
        item["is_lean"] = i == lean_idx
    return {"items": items, "lean_idx": lean_idx, "clear": margin >= _CLEAR_MARGIN}


def overall_classification(header_text: str, option_texts: list[str], profile_row, items: list[dict]) -> dict:
    """decision_type / stakes / urgency for the comparison as a whole.

    Type and urgency come from the framing text (that's where "today" or
    "should I quit" lives); stakes is the highest across the framing and any
    single option, so 'stay vs quit the job' reads as high-stakes even if
    'stay' alone wouldn't.
    """
    framing = header_text or " / ".join(option_texts)
    hc = classifier.classify_decision(framing, profile_row)
    stakes_level = max(
        [_LEVEL.get(hc["stakes"], 1)] + [_LEVEL.get(o["stakes"], 1) for o in items]
    )
    return {
        "decision_type": hc["decision_type"],
        "stakes": _LEVEL_NAME[stakes_level],
        "urgency": hc["urgency"],
    }
