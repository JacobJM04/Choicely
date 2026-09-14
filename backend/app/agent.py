"""
Choicely as an agent.

The pieces were always here -- auto-resolve answers a decision once it's seen
enough, check-ins circle back on the ones it couldn't, the trigger analysis
notices patterns. This module makes that one visible loop: an activity log of
what Choicely did on its own, plus a Claude-driven triage of the open backlog
that decides, per decision, whether there's enough evidence to answer it now,
whether to keep watching, or whether to leave it alone.

Nothing here is on a timer -- a real deploy would run `sync()` from a
scheduler; in the app it's called whenever the demo clock advances or the
activity view loads. Every Claude call degrades to a plain-rules answer.

Event types in the log:
  logged         -- a decision came in and got an estimate
  auto_resolved  -- Choicely answered it directly, no check-in needed
  checkin_raised -- a decision's outcome is due; Choicely is asking about it
  loop_closed    -- an outcome landed; prediction scored against it
  pattern_found  -- the trigger analysis surfaced a condition that moves regret
"""
import json
from datetime import datetime

from . import checkins, llm, models, triggers

_TS_FMT = "%Y-%m-%d %H:%M:%S"
_OUTCOME_WORD = {"good": "went well", "neutral": "was fine", "regret": "was regretted"}
_PREDICTED_SOURCES = {"blended", "personal", "profile_prior", "personality_prior", "dataset_prior"}


# --- writing events ------------------------------------------------------


def on_decision_logged(decision: dict) -> None:
    d_id = decision["id"]
    ts = decision.get("timestamp")
    if decision.get("auto_resolution"):
        if not models.agent_event_exists("auto_resolved", d_id):
            models.record_agent_event(
                "auto_resolved",
                title="Answered it outright",
                detail=decision["auto_resolution"],
                decision_id=d_id,
                created_at=ts,
                reasoning=(
                    f"Looking back at the {decision.get('personal_data_points', 0)} times you've "
                    f'logged something like "{decision.get("prior_category_label")}", the pattern '
                    f"was one-sided enough that Choicely just told you instead of making you decide."
                ),
            )
        return

    if (decision.get("reopened_count") or 0) > 1:
        # The same still-open question logged more than once -- that's a
        # decision-debt signal, not a fresh log. One event per standing
        # question, not per repeat.
        topic_id = decision.get("topic_id")
        already = (
            models.agent_event_exists_for_topic("reopened", topic_id)
            if topic_id is not None
            else models.agent_event_exists("reopened", d_id)
        )
        if not already:
            models.record_agent_event(
                "reopened",
                title="Noticed a repeat",
                detail=f'"{_short(decision["text"])}" logged again with no decision recorded — '
                       f'{decision["reopened_count"]} times now, still open.',
                decision_id=d_id,
                created_at=ts,
                reasoning=(
                    "This reads as the same question you've already logged and never answered, "
                    "so Choicely is grouping them instead of treating this as something new."
                ),
            )
        return

    if decision.get("source") in _PREDICTED_SOURCES and decision.get("blended_regret_estimate") is not None:
        if not models.agent_event_exists("logged", d_id):
            est = round(decision["blended_regret_estimate"] * 100)
            models.record_agent_event(
                "logged",
                title="Logged and estimated",
                detail=f'"{_short(decision["text"])}" — {est}% regret estimate, watching for the outcome.',
                decision_id=d_id,
                created_at=ts,
            )


def on_outcome_recorded(decision: dict) -> None:
    d_id = decision["id"]
    if models.agent_event_exists("loop_closed", d_id):
        return
    outcome = decision.get("outcome")
    predicted = decision.get("blended_regret_estimate")
    detail = f'"{_short(decision["text"])}" — {_OUTCOME_WORD.get(outcome, outcome)}.'
    reasoning = None
    if predicted is not None and outcome in _OUTCOME_WORD:
        actual = {"good": 0.0, "neutral": 0.5, "regret": 1.0}[outcome]
        miss = abs(predicted - actual)
        pct = round(predicted * 100)
        if miss <= 0.34:
            reasoning = (
                f"Choicely had guessed about a {pct}% chance you'd regret this — a hit, "
                f"close to how it actually turned out."
            )
        else:
            reasoning = (
                f"Choicely had guessed about a {pct}% chance you'd regret this — this time it "
                f"missed; what actually happened was pretty different from that guess."
            )
    models.record_agent_event(
        "loop_closed", title="Closed the loop", detail=detail, decision_id=d_id, reasoning=reasoning,
        created_at=decision.get("outcome_recorded_at") or decision.get("timestamp"),
    )


# --- syncing (idempotent; safe to call often) --------------------------


def _sync_checkins() -> int:
    made = 0
    for decision in models.get_due_check_ins():
        if models.agent_event_exists("checkin_raised", decision["id"]):
            continue
        question = checkin_question(decision)
        models.record_agent_event(
            "checkin_raised",
            title="Raised a check-in",
            detail=question,
            decision_id=decision["id"],
            created_at=decision.get("outcome_due_at"),
            reasoning=(
                f"You logged this {checkins._relative(decision['timestamp']).lower()} and never said "
                f"how it went — enough time has passed that it's almost certainly played out by now, "
                f"so Choicely is asking instead of leaving it hanging."
            ),
        )
        made += 1
    return made


def _sync_patterns() -> int:
    made = 0
    report = triggers.regret_triggers(include_seed=True)
    for trig in report.get("triggers", []):
        title = trig["headline"]
        if any(e["event_type"] == "pattern_found" and e["title"] == title
               for e in models.list_agent_events(limit=100)):
            continue
        models.record_agent_event(
            "pattern_found",
            title=title,
            detail=trig["detail"],
            reasoning=(
                f"Choicely compared {trig['n_trigger']} decisions made this way against "
                f"{trig['n_contrast']} made the other way — regret showed up about "
                f"{trig['ratio']}× as often in the first group. That gap is big enough to "
                f"call a real pattern, not just chance."
            ),
        )
        made += 1
    return made


def sync() -> dict:
    return {"checkins": _sync_checkins(), "patterns": _sync_patterns()}


# --- Claude-written check-in questions ---------------------------------

_CHECKIN_SYSTEM = """You are Choicely, circling back on a decision someone logged a while ago \
to find out how it turned out. Write ONE short, warm question (max 20 words) that names the \
specific decision and asks how it landed. No preamble, no multiple questions. \
Respond with ONLY JSON: {"question": "..."}"""


def checkin_question(decision: dict) -> str:
    fallback = checkins.check_in_prompt(decision)["prompt"]
    if not llm.available():
        return fallback
    logged = checkins._relative(decision["timestamp"])
    parsed = llm.complete_json(
        _CHECKIN_SYSTEM,
        f'Decision (logged {logged}): "{decision["text"]}"\nType: {decision["decision_type"]}, '
        f'stakes: {decision["stakes"]}.',
        max_tokens=120,
    )
    if parsed and parsed.get("question"):
        return str(parsed["question"])[:200]
    return fallback


# --- Claude backlog triage (the showcase) -----------------------------

_TRIAGE_SYSTEM = """You are Choicely's decision agent. You manage someone's backlog of open \
decisions -- the ones they logged but never recorded an outcome for. For each one, decide what \
the agent should do:

  "answer_now"    -- their own history is one-sided enough that Choicely should just give them
                     the answer instead of waiting
  "keep_watching" -- reasonable to wait; the outcome isn't knowable yet or there isn't enough
                     history to call it
  "stay_quiet"    -- low stakes and low regret either way; not worth a nudge, let it go

Be conservative with "answer_now" -- only when the numbers really support it. Be willing to use
"stay_quiet"; part of lifting mental load is NOT nagging.

Write "why" the way you'd explain it out loud to a friend who has never looked at a spreadsheet --
plain everyday words, no jargon like "confidence", "variance", or "data points". A number is great
when it helps ("regretted it 8 of the last 10 times"); skip it if it would just sound technical.

Respond with ONLY JSON:
{"assessments": [{"id": <number>, "verdict": "answer_now|keep_watching|stay_quiet", "why": "one short, plain-spoken sentence"}]}"""


def _backlog_context(open_rows: list[dict]) -> str:
    lines = []
    for r in open_rows:
        cat = r.get("prior_category_label") or r["decision_type"]
        hist = models.get_category_history(cat, include_seed=True) if r.get("prior_category_label") else []
        outs = [h["outcome"] for h in hist if h["outcome"]]
        n = len(outs)
        reg = sum(1 for o in outs if o == "regret")
        hist_str = f"{n} past outcomes, {reg} regretted" if n else "no history in this category"
        lines.append(
            f'- id {r["id"]}: "{r["text"]}" | {r["decision_type"]}/{r["stakes"]} | '
            f'logged {r.get("reopened_count", 0) or 1}x, still open | estimate '
            f'{round((r.get("blended_regret_estimate") or 0) * 100)}% | {hist_str}'
        )
    return "\n".join(lines)


_VERDICTS = {"answer_now", "keep_watching", "stay_quiet"}


def _heuristic_triage(open_rows: list[dict]) -> list[dict]:
    out = []
    for r in open_rows:
        est = r.get("blended_regret_estimate") or 0
        conf = r.get("confidence") or 0
        reopened = r.get("reopened_count", 0) or 0
        if conf >= 1.0 and (est >= 0.65 or est <= 0.2):
            verdict, why = (
                "answer_now",
                f"Your own history is strong enough here — about {round(est * 100)}% of the time "
                f"a decision like this ends in regret — that Choicely is confident enough to just "
                f"tell you instead of waiting for you to decide.",
            )
        elif r["stakes"] == "low" and 0.3 < est < 0.6 and reopened <= 1:
            verdict, why = (
                "stay_quiet",
                "This is low-stakes and roughly a coin flip either way — not worth a nudge from Choicely.",
            )
        else:
            why = "It's not clear yet which way this will go, so Choicely is keeping an eye on it rather than guessing."
            if reopened >= 2:
                why = (
                    f"You've logged this {reopened} times without ever deciding — the back-and-forth "
                    f"itself is the real cost here, more than either answer would be."
                )
            verdict = "keep_watching"
        out.append({"id": r["id"], "verdict": verdict, "why": why, "text": r["text"]})
    return out


def _collapse_by_topic(rows: list[dict]) -> list[dict]:
    """One entry per standing question. rows come newest-first, so the first
    time we see a topic is its most recent form."""
    seen, out = set(), []
    for r in rows:
        key = r.get("topic_id") or r["id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def assess_backlog(limit: int = 12) -> list[dict]:
    open_rows = _collapse_by_topic(models.get_open_decisions(include_seed=True))[:limit]
    if not open_rows:
        return []

    by_id = {r["id"]: r for r in open_rows}
    result = None
    if llm.available():
        parsed = llm.complete_json(
            _TRIAGE_SYSTEM,
            "Open decisions:\n" + _backlog_context(open_rows),
            max_tokens=700,
        )
        if parsed and isinstance(parsed.get("assessments"), list):
            result = []
            for a in parsed["assessments"]:
                rid = a.get("id")
                if rid in by_id and a.get("verdict") in _VERDICTS:
                    result.append(
                        {"id": rid, "verdict": a["verdict"], "why": str(a.get("why", ""))[:240],
                         "text": by_id[rid]["text"]}
                    )
            # any the model skipped, fill from the heuristic
            covered = {a["id"] for a in result}
            for r in open_rows:
                if r["id"] not in covered:
                    result += [h for h in _heuristic_triage([r])]

    if result is None:
        result = _heuristic_triage(open_rows)

    result.sort(key=lambda a: {"answer_now": 0, "keep_watching": 1, "stay_quiet": 2}.get(a["verdict"], 3))
    return result


# --- activity feed ----------------------------------------------------


def _short(text: str, n: int = 60) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _relative(ts: str | None) -> str:
    try:
        parsed = datetime.strptime((ts or "")[:19], _TS_FMT)
    except ValueError:
        return ""
    mins = (datetime.now() - parsed).total_seconds() / 60
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{round(mins)}m ago"
    hours = mins / 60
    if hours < 24:
        return f"{round(hours)}h ago"
    days = round(hours / 24)
    return "yesterday" if days == 1 else f"{days}d ago"


# Events worth always showing; the rest (logged / loop_closed) are routine
# churn and only the most recent few earn a slot.
_SIGNAL_EVENTS = {"auto_resolved", "checkin_raised", "pattern_found", "reopened"}
_ROUTINE_SHOWN = 6


def _narrative(summary: dict, events: list[dict]) -> str:
    """A short, plain-English recap of what the agent has actually been doing --
    written for someone who has never seen a regret estimate or a confidence
    score. Built entirely from numbers already computed elsewhere (the summary
    counts, one example pattern title), so it can't invent anything and needs
    no Claude call to be accurate."""
    answered = summary["answered"]
    closed = summary["loops_closed"]
    checked_in = summary["check_ins_raised"]
    patterns = summary["patterns_found"]
    watching, left_alone, would_answer = (
        summary["watching"],
        summary["left_alone"],
        summary["would_answer"],
    )

    if not any((answered, closed, checked_in, patterns, watching, left_alone, would_answer)):
        return (
            "Choicely hasn't had enough of your decisions yet to do anything on its own. Log a few, "
            "record how they go, and this page will fill in with what it notices and handles for you."
        )

    def s(n: int) -> str:
        return "" if n == 1 else "s"

    parts = []
    if answered:
        parts.append(
            f"It has felt sure enough, {answered} time{s(answered)}, to just answer a decision for "
            f"you outright — your own past choices on that kind of question were one-sided enough "
            f"that there was nothing left to weigh, so it told you instead of making you think it "
            f"through."
        )
    if closed:
        parts.append(
            f"You've told it how things turned out {closed} time{s(closed)}, and each time it "
            f"checked that against the guess it made beforehand — that's how it gets better at "
            f"reading you."
        )
    if checked_in:
        parts.append(
            f"It reached out on its own {checked_in} time{s(checked_in)} to ask how something you'd "
            f"logged actually went, instead of waiting for you to remember to update it."
        )
    if patterns:
        example = next((e["title"] for e in events if e["event_type"] == "pattern_found"), None)
        tail = f' For example: {example.rstrip(".")}.' if example else ""
        parts.append(
            f"Along the way it spotted {patterns} pattern{s(patterns)} in when your decisions tend "
            f"to go well or badly — things like the time of day or how rushed you were.{tail}"
        )
    backlog_total = watching + left_alone + would_answer
    if backlog_total:
        bits = []
        if would_answer:
            bits.append(f"answer {would_answer} of them for you outright")
        if watching:
            bits.append(f"keep watching {watching} while it waits for more information")
        if left_alone:
            bits.append(f"leave {left_alone} alone as too low-stakes to bother you about")
        parts.append(
            f"Right now there {'is' if backlog_total == 1 else 'are'} {backlog_total} question"
            f"{s(backlog_total)} you haven't closed out, and Choicely is ready to "
            + "; ".join(bits) + "."
        )

    return " ".join(parts)


def activity() -> dict:
    sync()
    raw = models.list_agent_events(limit=120)
    signal = [e for e in raw if e["event_type"] in _SIGNAL_EVENTS]
    routine = [e for e in raw if e["event_type"] not in _SIGNAL_EVENTS][:_ROUTINE_SHOWN]
    events = sorted(signal + routine, key=lambda e: (e["created_at"], e["id"]), reverse=True)[:20]
    for e in events:
        e["relative"] = _relative(e["created_at"])
    counts = models.agent_event_type_counts()
    assessments = assess_backlog()
    summary = {
        "answered": counts.get("auto_resolved", 0),
        "loops_closed": counts.get("loop_closed", 0),
        "check_ins_raised": counts.get("checkin_raised", 0),
        "patterns_found": counts.get("pattern_found", 0),
        "watching": sum(1 for a in assessments if a["verdict"] == "keep_watching"),
        "would_answer": sum(1 for a in assessments if a["verdict"] == "answer_now"),
        "left_alone": sum(1 for a in assessments if a["verdict"] == "stay_quiet"),
    }

    return {
        "events": events,
        "summary": summary,
        # A plain-English recap for someone who has never seen a regret estimate --
        # what the agent has actually done, spelled out in full sentences.
        "narrative": _narrative(summary, events),
        "backlog": assessments,
        "llm": llm.available(),
    }


# --- seed support ----------------------------------------------------


def backfill_events() -> None:
    """Rebuild the activity log from whatever history is already in the DB --
    used by the demo seed so the agent feed isn't empty on a fresh demo."""
    models.clear_agent_events()
    rows = sorted(models.list_decisions(include_seed=True), key=lambda r: r["id"])
    for r in rows:
        on_decision_logged(r)
        if r.get("outcome"):
            on_outcome_recorded(r)
    sync()
