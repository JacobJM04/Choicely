"""
Crisis guardrails.

Some things a person types into a decision box are not decisions a regret
model has any business scoring -- self-harm, abuse, a medical emergency,
or a money move that could sink them. For those, Choicely steps back:
it still keeps the note (losing what someone just wrote would be worse),
but instead of a probability it shows a short, calm pointer to real help.

Two tiers:
  - "crisis"    -> no estimate at all. self-harm / abuse / medical emergency.
  - "sensitive" -> the estimate still shows, with a banner above it saying
                   this is bigger than an average and naming who to talk to.

Heuristic phrase matching here; the Claude classifier path (classifier.py)
also returns a safety verdict when a key is set. Conservative on the
crisis tier -- a false positive shows someone a kind message with a
hotline number, which is a survivable mistake; a false negative is not.
"""
import re

_FINDAHELPLINE = {"label": "findahelpline.com", "url": "https://findahelpline.com",
                  "detail": "free, confidential lines by country"}

_RESOURCES = {
    "self_harm": [
        {"label": "988 Suicide & Crisis Lifeline", "detail": "call or text 988 (US, 24/7)"},
        _FINDAHELPLINE,
    ],
    "abuse": [
        {"label": "National Domestic Violence Hotline", "detail": "1-800-799-7233 (US, 24/7)"},
        _FINDAHELPLINE,
    ],
    "medical": [
        {"label": "Your local emergency number", "detail": "911 in the US -- don't wait on an app"},
    ],
    "financial": [
        {"label": "nfcc.org", "url": "https://www.nfcc.org", "detail": "free non-profit credit counseling (US)"},
    ],
}

_MESSAGES = {
    "self_harm": (
        "This sounds heavier than something Choicely should weigh in on. If you're "
        "thinking about hurting yourself, please reach out to someone now -- you deserve "
        "support with this, not a probability. Your note stays here if you want to come back to it."
    ),
    "abuse": (
        "If you're not safe, that comes before any decision Choicely could model. Talking to "
        "someone who handles this every day will help more than an estimate would. Your note stays here."
    ),
    "medical": (
        "If this might be a medical emergency, call your local emergency number now -- don't "
        "wait on an app. Choicely has left this one alone; your note stays here."
    ),
    "financial": (
        "This is a high-consequence money decision, and the kind where a regret average isn't "
        "enough to go on. Worth talking through with a free credit counselor or someone you trust "
        "before you commit. The estimate below is a starting point, not an answer."
    ),
}

# --- crisis tier ----------------------------------------------------------

_SELF_HARM = re.compile(
    r"\b(kill(ing)?\s+myself|end(ing)?\s+my\s+life|take\s+my\s+own\s+life|end\s+it\s+all|"
    r"want\s+to\s+die|wish\s+i\s+(was|were)\s+dead|better\s+off\s+dead|no\s+reason\s+to\s+live|"
    r"don'?t\s+want\s+to\s+(be\s+here|live)|can'?t\s+go\s+on|suicid|self[-\s]?harm|"
    r"harm(ing)?\s+myself|hurt(ing)?\s+myself|cut(ting)?\s+myself|overdos)",
    re.I,
)
_ABUSE = re.compile(
    r"\b(hits?\s+me|hit\s+me|beats?\s+me|beat\s+me\s+up|abus(es|ed|ing|ive)|"
    r"domestic\s+(violence|abuse)|afraid\s+(for|of)\s+my\s+(life|safety)|not\s+safe\s+at\s+home|"
    r"threaten(s|ed|ing)?\s+to\s+hurt|hurts?\s+me\s+when)",
    re.I,
)
_MEDICAL = re.compile(
    r"\b(chest\s+pain|can'?t\s+breathe|cannot\s+breathe|trouble\s+breathing|not\s+breathing|"
    r"call\s+an?\s+ambulance|took\s+too\s+many\s+pills|overdosed|unconscious|"
    r"won'?t\s+stop\s+bleeding|bleeding\s+won'?t\s+stop)",
    re.I,
)

# --- sensitive tier -----------------------------------------------------

_FINANCIAL = re.compile(
    r"\b(payday\s+loan|payday\s+lend|title\s+loan|loan\s+shark|"
    r"max(ing)?\s+out\s+my\s+credit\s+card|gambl\w*\s+(my|the)\s+(savings|rent|paycheck)|"
    r"bet\s+my\s+savings|cash\s+out\s+my\s+(401k|retirement|pension)|"
    r"borrow\s+against\s+my\s+(401k|house|home)|pawn\s+my)",
    re.I,
)

_CRISIS = [
    ("self_harm", _SELF_HARM),
    ("abuse", _ABUSE),
    ("medical", _MEDICAL),
]
_SENSITIVE = [
    ("financial", _FINANCIAL),
]


def _flag(tier: str, category: str) -> dict:
    return {
        "tier": tier,
        "category": category,
        "message": _MESSAGES[category],
        "resources": _RESOURCES.get(category, []),
    }


def screen(*texts: str) -> dict | None:
    """Return a safety flag for the highest-severity match across all the
    given strings (decision text plus any option texts), or None."""
    blob = "  ".join(t for t in texts if t)
    if not blob.strip():
        return None
    for category, pattern in _CRISIS:
        if pattern.search(blob):
            return _flag("crisis", category)
    for category, pattern in _SENSITIVE:
        if pattern.search(blob):
            return _flag("sensitive", category)
    return None
