"""
Grounded decision debrief.

The composer's one-line box is fine for "should I skip leg day". It is not
fine for the decision you've been carrying around for two weeks. The debrief
is for that one: you dump a messy paragraph (or a voice note transcript) and
Choicely reads it back to you the way a friend who's been paying attention
would --

  - the real question under the question you asked
  - what's actually at stake
  - the thing you keep circling and not saying
  - your options, each with a note
  - a grounded read that quotes your own recorded history
  - a recommendation and how sure it is

The "grounded" part is the point: the read is built on top of retrieval over
your own decision log -- the population prior for this kind of call, every
outcome you've recorded in the same category, and whether this exact question
is already sitting in your decision debt. Claude does the synthesis; the
numbers and the cited history are computed here and pinned so they can't
drift. No Claude key -> a plainer read assembled from the same retrieved
context.

The debrief is read-only. It does not log a decision -- the client offers a
"log this" button that posts to /decisions the normal way.
"""
import re
from datetime import datetime

from . import classifier, dataset, debt, llm, models, profile as profile_mod, personality, regret

_TS_FMT = "%Y-%m-%d %H:%M:%S"
_OUTCOME_WORD = {"good": "went well", "neutral": "was fine", "regret": "regretted it"}


def _parse(ts: str | None) -> datetime | None:
    try:
        return datetime.strptime((ts or "")[:19], _TS_FMT)
    except ValueError:
        return None


def _ago(ts: str | None) -> str:
    parsed = _parse(ts)
    if parsed is None:
        return "a while back"
    days = (datetime.now() - parsed).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def _first_sentence(text: str, cap: int = 160) -> str:
    """Best-effort 'the question' from a paragraph, for the no-Claude path."""
    text = " ".join((text or "").split())
    # Prefer the first sentence that reads like a question.
    for chunk in re.split(r"(?<=[.?!])\s+", text):
        if "?" in chunk or re.match(r"(?i)^(should|do|is|can|would|whether|am|will)\b", chunk):
            return (chunk if len(chunk) <= cap else chunk[: cap - 1] + "…").strip()
    first = re.split(r"(?<=[.?!])\s+", text)[0]
    return (first if len(first) <= cap else first[: cap - 1] + "…").strip()


def _related_decisions(text: str, category_label: str, limit: int = 6) -> list[dict]:
    """Decisions from the user's log that bear on this one: same matched
    category, or enough shared words to be the same underlying question.

    Uses a raw shared-word count rather than Jaccard similarity -- the debrief
    input is a paragraph, so its word set dwarfs a one-line logged decision
    and Jaccard would always score near zero."""
    new_words = debt._normalize(text)
    rows = models.list_decisions(include_seed=True)
    scored = []
    for row in rows:
        same_category = bool(category_label) and row.get("prior_category_label") == category_label
        shared = len(new_words & debt._normalize(row["text"] or ""))
        if same_category or shared >= 3:
            scored.append((shared + (3 if same_category else 0), row))
    scored.sort(key=lambda x: (x[0], x[1]["id"]), reverse=True)

    out = []
    seen_text = set()
    for _, row in scored:
        norm = (row["text"] or "").strip().lower()
        if norm in seen_text:
            continue
        seen_text.add(norm)
        if len(out) >= limit:
            break
        out.append(
            {
                "text": row["text"],
                "outcome": row["outcome"],
                "outcome_word": _OUTCOME_WORD.get(row["outcome"]),
                "when": _ago(row["timestamp"]),
                "predicted_regret": row.get("blended_regret_estimate"),
            }
        )
    return out


def retrieve(text: str) -> dict:
    """Everything Choicely knows that's relevant to this decision, before any
    Claude call. Also the fallback's raw material."""
    profile_row = models.get_profile()
    classification = classifier.classify_decision(text, profile_row)
    decision_type = classification["decision_type"]
    prior = dataset.get_prior(decision_type, text)

    profile_adj = profile_mod.adjust_prior(prior["regret_rate"], prior["planning_alignment"])
    personality_adj = personality.adjust_prior(
        profile_adj if profile_adj is not None else prior["regret_rate"],
        prior["planning_alignment"],
        decision_type,
        classification["stakes"],
        profile_row,
    )
    effective_rate = personality_adj if personality_adj is not None else (
        profile_adj if profile_adj is not None else prior["regret_rate"]
    )
    prediction = regret.predict(prior["category_label"], effective_rate)

    history = models.get_category_history(prior["category_label"], include_seed=True)
    outcomes = [h["outcome"] for h in history if h["outcome"]]
    regret_count = sum(1 for o in outcomes if o == "regret")

    related = _related_decisions(text, prior["category_label"])

    # Is this one of the questions they keep logging without settling? Match
    # debt topics by word overlap with the input or with anything we pulled as
    # related -- find_matching_topic alone misses because the debrief input is
    # a paragraph, not a one-liner.
    debt_match = None
    debt_topics = models.get_debt_topics(include_seed=True)
    input_words = debt._normalize(text)
    related_texts = {r["text"] for r in related}
    for topic in debt_topics:
        canonical = topic.get("canonical_text") or ""
        if canonical in related_texts or len(input_words & debt._normalize(canonical)) >= 2:
            debt_match = topic
            break

    return {
        "classification": classification,
        "decision_type": decision_type,
        "category_label": prior["category_label"],
        "prior_regret_rate": prior["regret_rate"],
        "prior_description": prior["description"],
        "effective_prior_rate": effective_rate,
        "regret_estimate": prediction["blended_regret_estimate"],
        "confidence": prediction["confidence"],
        "personal_data_points": prediction["personal_data_points"],
        "personal_outcomes": outcomes,
        "personal_regret_count": regret_count,
        "profile": profile_row,
        "debt_match": debt_match,
        "related": related,
    }


# --- Claude path ----------------------------------------------------------

_SYSTEM = """You are Choicely, a decision companion. Someone has been carrying a decision \
around and just dumped it on you unstructured. Read it back to them the way a perceptive \
friend who has been watching their decisions for weeks would -- specific, warm, and honest, \
never a nag and never generic advice.

You are given retrieved context from their own decision log: the population regret rate for \
this kind of call, their own recorded outcomes in the same category, and whether this exact \
question is already unresolved in their history. Ground every claim in that context. Do not \
invent history that isn't there. If the context is thin, say the read is provisional.

Respond with ONLY a JSON object:
{
  "real_question": "the actual decision under what they asked, one sentence",
  "whats_at_stake": "what actually turns on this, one or two sentences",
  "avoiding": "the thing they keep circling and not naming -- or null if nothing stands out",
  "options": [{"label": "3-6 words", "note": "one plain sentence, reference their history if relevant"}],
  "grounded_read": "2-3 sentences. Must cite a concrete number or a specific past decision from the context.",
  "recommendation": "one clear next step -- not necessarily an answer, could be 'gather X first'",
  "confidence": "low | medium | high"
}"""


def _history_block(ctx: dict) -> str:
    lines = []
    n = ctx["personal_data_points"]
    if n:
        regretted = ctx["personal_regret_count"]
        lines.append(
            f"Their own record for \"{ctx['category_label']}\": {n} recorded outcomes, "
            f"regretted {regretted} ({round(regretted / n * 100)}%)."
        )
    else:
        lines.append(f"No personal outcomes recorded yet for \"{ctx['category_label']}\".")
    lines.append(
        f"Population regret rate for this kind of decision: {round(ctx['prior_regret_rate'] * 100)}%."
    )
    lines.append(
        f"Choicely's current blended estimate for them: {round(ctx['regret_estimate'] * 100)}% "
        f"(confidence {round(ctx['confidence'] * 100)}%)."
    )
    if ctx["debt_match"]:
        d = ctx["debt_match"]
        lines.append(
            f"This question is ALREADY in their decision debt: \"{d['canonical_text']}\" logged "
            f"{d['times_logged']} times with no decision recorded."
        )
    if ctx["related"]:
        lines.append("Related decisions from their log:")
        for r in ctx["related"][:6]:
            tail = f" -> {r['outcome_word']}" if r["outcome_word"] else " -> still open"
            lines.append(f"  - \"{r['text']}\" ({r['when']}){tail}")
    prof = ctx["profile"] or {}
    if prof.get("planning_label"):
        bits = [prof["planning_label"] + " decider"]
        for k in ("regret_orientation", "conflict_style"):
            if prof.get(k):
                bits.append(prof[k])
        lines.append("About them: " + ", ".join(bits) + ".")
    return "\n".join(lines)


def _claude_debrief(text: str, ctx: dict) -> dict | None:
    user = f'What they wrote:\n"""\n{text}\n"""\n\nRetrieved context:\n{_history_block(ctx)}'
    parsed = llm.complete_json(_SYSTEM, user, max_tokens=900)
    if not parsed or "real_question" not in parsed:
        return None

    options = []
    for opt in parsed.get("options", [])[:4]:
        if isinstance(opt, dict) and opt.get("label"):
            options.append({"label": str(opt["label"])[:80], "note": str(opt.get("note", ""))[:240]})
    return {
        "real_question": str(parsed["real_question"])[:240],
        "whats_at_stake": str(parsed.get("whats_at_stake", ""))[:400],
        "avoiding": (str(parsed["avoiding"])[:240] if parsed.get("avoiding") else None),
        "options": options,
        "grounded_read": str(parsed.get("grounded_read", ""))[:600],
        "recommendation": str(parsed.get("recommendation", ""))[:300],
        "confidence": parsed.get("confidence") if parsed.get("confidence") in ("low", "medium", "high") else "low",
        "source": "claude",
    }


# --- fallback path -------------------------------------------------------


def _heuristic_debrief(text: str, ctx: dict) -> dict:
    n = ctx["personal_data_points"]
    rate = ctx["regret_estimate"]
    pct = round(rate * 100)

    if ctx["debt_match"]:
        d = ctx["debt_match"]
        real_q = f"Whether to finally settle \"{d['canonical_text']}\" instead of logging it again."
        avoiding = (
            f"You've brought this up {d['times_logged']} times without deciding. "
            f"The indecision is costing you more than either answer would."
        )
        stake = (
            "The cost here isn't the decision itself — it's the "
            f"{d['times_logged']} rounds you've already spent carrying it unresolved."
        )
        grounded = (
            f"You've logged \"{d['canonical_text']}\" {d['times_logged']} times and recorded an "
            f"outcome zero times. That pattern says the hard part isn't which way to go — it's "
            f"committing to either. Pick the one you can live with and close it."
        )
        return {
            "real_question": real_q,
            "whats_at_stake": stake,
            "avoiding": avoiding,
            "options": [
                {"label": "Commit to leaving", "note": "Accept the small loss and free up the attention."},
                {"label": "Commit to staying", "note": "Decide it's worth it and stop turning the question over."},
            ],
            "grounded_read": grounded,
            "recommendation": "Set a decide-by date this week. Either answer beats carrying it another round.",
            "confidence": "medium",
            "source": "heuristic",
        }

    real_q = _first_sentence(text)
    avoiding = None

    if n >= 3:
        regretted = ctx["personal_regret_count"]
        grounded = (
            f"You've recorded {n} outcomes for decisions like this and regretted {regretted} "
            f"of them ({round(regretted / n * 100)}%). "
        )
        grounded += (
            "That's not really an open question anymore." if rate >= 0.65 or rate <= 0.2
            else "It genuinely goes both ways for you."
        )
        confidence = "high" if n >= 8 else "medium"
    else:
        grounded = (
            f"You don't have much history here yet, so this leans on the population rate: "
            f"about {round(ctx['prior_regret_rate'] * 100)}% of people regret this kind of call."
        )
        confidence = "low"

    if rate >= 0.65:
        rec = "The pattern is clear enough to just act on it. Don't re-litigate this one."
    elif rate <= 0.25:
        rec = "History says this is low-regret for you. Go ahead and stop deliberating."
    else:
        rec = "Log it and record how it lands -- a few more outcomes will settle which way this leans."

    stake = ctx["prior_description"] or "Small on its own, but it's the kind of call you make often."

    return {
        "real_question": real_q,
        "whats_at_stake": stake,
        "avoiding": avoiding,
        "options": [],
        "grounded_read": grounded,
        "recommendation": rec,
        "confidence": confidence,
        "source": "heuristic",
    }


def debrief(text: str) -> dict:
    text = (text or "").strip()
    ctx = retrieve(text)

    read = None
    if llm.available():
        read = _claude_debrief(text, ctx)
    if read is None:
        read = _heuristic_debrief(text, ctx)

    read["generated_at"] = datetime.now().strftime(_TS_FMT)
    read["category_label"] = ctx["category_label"]
    read["decision_type"] = ctx["decision_type"]
    read["stakes"] = ctx["classification"]["stakes"]
    read["regret_estimate"] = ctx["regret_estimate"]
    read["confidence_pct"] = round(ctx["confidence"] * 100)
    read["personal_data_points"] = ctx["personal_data_points"]
    read["population_regret_rate"] = ctx["prior_regret_rate"]
    read["in_decision_debt"] = ctx["debt_match"] is not None
    read["related"] = [
        {"text": r["text"], "outcome": r["outcome"], "outcome_word": r["outcome_word"], "when": r["when"]}
        for r in ctx["related"]
        if r["text"] and r["text"].strip().lower() != text.strip().lower()
    ][:5]
    return read
