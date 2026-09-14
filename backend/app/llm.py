"""
One shared Claude seam for the whole app.

Every feature that wants Claude's judgment (the decision debrief, the agent's
check-in phrasing and backlog triage, the weekly reflection) goes through
here instead of constructing its own client. Benefits:

- **One switch.** `available()` is the single check for "is Claude wired up".
- **Bounded demo cost.** Responses are cached in SQLite keyed by a hash of
  the exact prompt, so replaying the same seeded demo doesn't re-bill.
- **Never fatal.** Any failure (no key, network, malformed JSON, refusal)
  returns None and the caller falls back to its heuristic path.

Model: `claude-sonnet-5` -- the app standardised on it before this module
(fast, 1M context, cheap enough to leave on for a live demo). Override with
CHOICELY_LLM_MODEL if you want Opus for a judged run.
"""
import hashlib
import json
import os
import re
import time

from . import models

MODEL = os.environ.get("CHOICELY_LLM_MODEL", "claude-sonnet-5")

_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# Let a deploy force the heuristic path even with a key present (e.g. to keep
# a public demo's spend at exactly zero).
_DISABLED = os.environ.get("CHOICELY_LLM_DISABLED", "") in ("1", "true", "True")

_client = None
_MISSES_UNTIL = 0.0  # after a hard failure, skip Claude for a cooldown window


def available() -> bool:
    return bool(_API_KEY) and not _DISABLED


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=_API_KEY, max_retries=1, timeout=30.0)
    return _client


def _hash(system: str, user: str) -> str:
    h = hashlib.sha256()
    h.update(MODEL.encode())
    h.update(b"\x00")
    h.update(system.encode())
    h.update(b"\x00")
    h.update(user.encode())
    return h.hexdigest()


def _extract_json(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def complete_json(system: str, user: str, *, max_tokens: int = 900, use_cache: bool = True) -> dict | None:
    """Ask Claude for a JSON object. Returns the parsed dict, or None on any
    failure so the caller can fall back. Identical prompts are served from a
    SQLite cache."""
    global _MISSES_UNTIL
    if not available():
        return None

    key = _hash(system, user)
    if use_cache:
        cached = models.llm_cache_get(key)
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    if time.time() < _MISSES_UNTIL:
        return None

    try:
        message = _get_client().messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        if message.stop_reason == "refusal":
            return None
        raw = next((b.text for b in message.content if b.type == "text"), "")
    except Exception:
        # Back off for a minute so a broken key / outage doesn't add latency
        # to every request in the demo.
        _MISSES_UNTIL = time.time() + 60
        return None

    parsed = _extract_json(raw)
    if parsed is None:
        return None
    if use_cache:
        models.llm_cache_put(key, json.dumps(parsed), MODEL)
    return parsed
