"""
Game-theoretic breakdown for interpersonal decisions: a short structured
readout, not deep game theory -- what the user wants, what the other party
likely wants, and the best response to a good or bad reaction.

Swappable seam: uses the Claude API when ANTHROPIC_API_KEY is set; falls
back to a generic templated breakdown otherwise so the app still runs.
"""
import json
import os
import re

_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

_FIELDS = ["your_want", "their_likely_want", "if_they_react_well", "if_they_react_poorly"]

_PROMPT = """Someone is facing this interpersonal decision: "{text}"

Give a short, structured breakdown as ONLY a JSON object, no other text, with exactly these fields:
- "your_want": one short sentence on what they likely want out of this
- "their_likely_want": one short sentence on what the other person likely wants
- "if_they_react_well": one short sentence on the best next move if the other person reacts well
- "if_they_react_poorly": one short sentence on the best next move if the other person reacts poorly

Keep each sentence plain, concrete, and under 20 words.
"""


_CONFLICT_STYLE_FALLBACKS = {
    "avoidant": {
        "your_want": "For this to get resolved without a big confrontation.",
        "their_likely_want": "To not feel ambushed or put on the spot about it.",
        "if_they_react_well": "Great -- send a short, low-pressure follow-up text confirming what you agreed on.",
        "if_they_react_poorly": "Don't push further in the moment. Text them a calm one-liner later: \"Just wanted to close the loop on this -- no rush.\"",
    },
    "direct": {
        "your_want": "A clear, fast resolution -- you'd rather just say it than dance around it.",
        "their_likely_want": "To know exactly where you stand, even if it's blunt.",
        "if_they_react_well": "Confirm the outcome in one sentence and move on -- no need to over-explain.",
        "if_they_react_poorly": "Hold your position calmly, restate it once, and give them space to come around.",
    },
    "accommodating": {
        "your_want": "For everyone to end up okay, even if that means you give a little.",
        "their_likely_want": "To feel like their side was actually taken into account.",
        "if_they_react_well": "Great -- check in afterward to make sure the compromise still feels fair to you too.",
        "if_they_react_poorly": "Resist the urge to immediately back down -- pause, and revisit once things cool off.",
    },
    "competitive": {
        "your_want": "To make sure your side of this actually gets heard and acted on.",
        "their_likely_want": "To not feel steamrolled, even if they're in the wrong.",
        "if_they_react_well": "Lock in the outcome you wanted, but leave them a clear way to save face.",
        "if_they_react_poorly": "Stay firm on the substance, but ease off the tone -- a win that costs the relationship isn't a win.",
    },
}

_DEFAULT_FALLBACK = {
    "your_want": "A resolution that feels fair to you without damaging the relationship.",
    "their_likely_want": "To feel heard and not blindsided by how this comes up.",
    "if_they_react_well": "Follow up warmly and lock in the next concrete step together.",
    "if_they_react_poorly": "Stay calm, acknowledge their reaction, and revisit it later rather than pushing further now.",
}


def _fallback_breakdown(text: str, conflict_style: str | None = None) -> dict:
    return _CONFLICT_STYLE_FALLBACKS.get(conflict_style, _DEFAULT_FALLBACK)


def _profile_context(profile: dict) -> str:
    bits = []
    if profile.get("conflict_style"):
        bits.append(f"their conflict style: {profile['conflict_style']}")
    if profile.get("social_energy"):
        bits.append(f"social energy: {profile['social_energy']}")
    if profile.get("regret_orientation"):
        bits.append(f"regret orientation: {profile['regret_orientation']}")
    if not bits:
        return ""
    return (
        "\nAbout this person: " + ", ".join(bits) + ". Tailor the tone and, especially "
        "for if_they_react_well/if_they_react_poorly, the concreteness of the suggested "
        "move to this -- e.g. an avoidant person needs a specific, low-friction script "
        "rather than generic advice like \"be direct.\"\n"
    )


def _claude_breakdown(text: str, profile: dict | None = None) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
    prompt = _PROMPT.format(text=text)
    if profile:
        prompt += _profile_context(profile)
    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(match.group(0) if match else raw)
    if not all(k in parsed for k in _FIELDS):
        raise ValueError("incomplete breakdown from Claude")
    return {k: parsed[k] for k in _FIELDS}


def analyze(text: str, profile: dict | None = None) -> dict:
    if _ANTHROPIC_API_KEY:
        try:
            return _claude_breakdown(text, profile)
        except Exception:
            pass
    conflict_style = profile.get("conflict_style") if profile else None
    return _fallback_breakdown(text, conflict_style)
