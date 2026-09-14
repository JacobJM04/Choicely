"""
Decision classification: text -> {decision_type, stakes, urgency}.

Swappable seam: if ANTHROPIC_API_KEY is set, classify_decision() calls the
Claude API with a structured prompt. Otherwise it falls back to a
keyword-based heuristic so the app runs end-to-end without a key.
"""
import json
import os
import re

from .textmatch import whole_word_match

DECISION_TYPES = ["routine", "social", "financial", "health", "interpersonal"]
STAKES_LEVELS = ["low", "medium", "high"]
URGENCY_LEVELS = ["low", "medium", "high"]

_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

_CLASSIFY_PROMPT = """Classify this decision that someone is facing. Respond with ONLY a JSON object, no other text.

Decision: "{text}"

Return JSON with exactly these fields:
- "decision_type": one of {types}
- "stakes": one of {stakes}
- "urgency": one of {urgency}
""".format(types=DECISION_TYPES, stakes=STAKES_LEVELS, urgency=URGENCY_LEVELS, text="{text}")

_TYPE_KEYWORDS = {
    "health": ["sleep", "gym", "workout", "exercise", "leg day", "eat", "meal",
               "breakfast", "lunch", "dinner", "diet", "run", "training", "rest",
               "tired", "sick", "doctor", "medicine", "nap"],
    "financial": ["buy", "bought", "purchase", "impulse", "spend", "money", "save",
                  "saving", "invest", "budget", "afford", "price", "cost", "shopping",
                  "sell", "rent", "loan", "debt", "refund", "return it"],
    "interpersonal": ["text", "reply", "message", "call", "confront", "argument",
                       "breakup", "friend", "partner", "boyfriend", "girlfriend",
                       "family", "conflict", "tell them", "conversation", "relationship",
                       "apologize", "forgive", "roommate", "coworker", "boss", "propose"],
    "social": ["party", "trip", "weekend", "hang out", "go out", "outing", "plans",
               "event", "invite", "invited", "birthday", "wedding", "concert"],
}

_HIGH_STAKES_KEYWORDS = ["quit", "breakup", "break up", "fire", "move", "propose",
                          "resign", "divorce", "job offer", "lease"]
_LOW_STAKES_KEYWORDS = ["leg day", "skip", "snack", "what to wear", "what to eat", "netflix"]

_URGENT_KEYWORDS = ["today", "tonight", "now", "asap", "in an hour", "this morning"]


def _heuristic_classify(text: str, profile: dict | None = None) -> dict:
    lowered = text.lower()

    decision_type = "routine"
    best_hits = 0
    for dtype, keywords in _TYPE_KEYWORDS.items():
        hits = sum(1 for kw in keywords if whole_word_match(kw, lowered))
        if hits > best_hits:
            best_hits = hits
            decision_type = dtype

    if any(whole_word_match(kw, lowered) for kw in _HIGH_STAKES_KEYWORDS):
        stakes = "high"
    elif any(whole_word_match(kw, lowered) for kw in _LOW_STAKES_KEYWORDS):
        stakes = "low"
    else:
        stakes = "medium"

    # A user who reports being highly sensitive to stated stakes reads
    # ambiguous ("medium") decisions as higher-stakes than most people would.
    if stakes == "medium" and profile and profile.get("stakes_sensitivity") == "high":
        stakes = "high"

    urgency = "high" if any(whole_word_match(kw, lowered) for kw in _URGENT_KEYWORDS) else "low"

    return {"decision_type": decision_type, "stakes": stakes, "urgency": urgency}


def _profile_context(profile: dict) -> str:
    bits = []
    if profile.get("stakes_sensitivity"):
        bits.append(f"stakes sensitivity: {profile['stakes_sensitivity']}")
    if profile.get("decisiveness") is not None:
        bits.append(f"decisiveness: {'deliberates a lot' if profile['decisiveness'] >= 0.6 else 'decides quickly'}")
    if profile.get("social_energy"):
        bits.append(f"social energy: {profile['social_energy']}")
    if not bits:
        return ""
    return "\nAbout this person: " + ", ".join(bits) + ".\n"


def _claude_classify(text: str, profile: dict | None = None) -> dict:
    import anthropic

    # Bounded so a slow network / Claude outage can't stall the whole
    # "log a decision" request -- the SDK default timeout is minutes long,
    # and this call is on the critical path of every decision logged.
    client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY, max_retries=1, timeout=12.0)
    prompt = _CLASSIFY_PROMPT.format(text=text)
    if profile:
        prompt += _profile_context(profile)
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = next((b.text for b in message.content if getattr(b, "type", None) == "text"), "")
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(match.group(0) if match else raw)

    if parsed.get("decision_type") not in DECISION_TYPES:
        parsed["decision_type"] = "routine"
    if parsed.get("stakes") not in STAKES_LEVELS:
        parsed["stakes"] = "medium"
    if parsed.get("urgency") not in URGENCY_LEVELS:
        parsed["urgency"] = "low"
    return parsed


def classify_decision(text: str, profile: dict | None = None) -> dict:
    if _ANTHROPIC_API_KEY:
        try:
            return _claude_classify(text, profile)
        except Exception:
            pass
    return _heuristic_classify(text, profile)
