"""
Cold-start dataset lookup: given a classified decision, find the closest
matching entry in the reference (population prior) dataset.
"""
import json
from pathlib import Path

from .textmatch import whole_word_match

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "reference_dataset.json"

with open(_DATA_PATH, "r", encoding="utf-8") as f:
    _DATASET = json.load(f)

_ENTRIES = _DATASET["entries"]


def get_prior(decision_type: str, text: str) -> dict:
    """Return the best-matching population-prior entry for this decision.

    Matching: prefer an entry of the same decision_type whose tags appear
    in the text; fall back to that type's tag-less "general" entry.

    Ranked by (hit count, total matched-tag length) so that on a tie -- e.g.
    "should I skip breakfast before the gym" hits both "gym" (exercise) and
    "breakfast" (meals) once each -- the more specific/distinctive matched
    word wins instead of silently falling back to whichever category
    happens to be listed first in the dataset.
    """
    lowered = text.lower()
    candidates = [e for e in _ENTRIES if e["decision_type"] == decision_type]

    best_entry = None
    best_score = (0, 0)
    general_entry = None
    for entry in candidates:
        tags = entry.get("tags", [])
        if not tags:
            general_entry = entry
            continue
        matched = [tag for tag in tags if whole_word_match(tag, lowered)]
        score = (len(matched), sum(len(t) for t in matched))
        if score > best_score:
            best_score = score
            best_entry = entry

    chosen = best_entry if best_entry else general_entry
    if chosen is None:
        return {
            "category_label": "general decisions",
            "regret_rate": 0.4,
            "sample_size": 0,
            "description": "No population data available for this decision type yet.",
            "high_regret_advice": None,
            "low_regret_advice": None,
            "planning_alignment": None,
        }

    return {
        "category_label": chosen["category_label"],
        "regret_rate": chosen["regret_rate"],
        "sample_size": chosen["sample_size"],
        "description": chosen["description"],
        "high_regret_advice": chosen.get("high_regret_advice"),
        "low_regret_advice": chosen.get("low_regret_advice"),
        "planning_alignment": chosen.get("planning_alignment"),
    }
