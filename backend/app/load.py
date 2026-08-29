"""
Mental-load accounting: the wellness-facing counterpart to the regret model.

Choicely's pitch is that it carries decisions you're tired of holding. This
module turns the decision log into that story -- how much got taken off your
plate this week versus how much is still sitting on it.

Definitions (all windowed to the last WINDOW_DAYS unless noted):
  - logged:     decisions captured in the window
  - lifted:     decisions Choicely answered outright (auto_resolution set) --
                zero deliberation required of you
  - guided:     decisions that came with a confident estimate (confidence >=
                0.5) but not a full auto-resolve -- you still chose, but not
                from a blank slate
  - closed:     decisions you recorded an outcome for in the window -- loops
                you actually shut
  - carried:    open decision-debt topics (reopened 2+ times, never decided) --
                load still on you, counted all-time because that's how debt
                works
  - open_loops: logged-but-unresolved decisions that aren't (yet) debt
  - avg_hours_to_close: mean time from logging to recording an outcome
"""
from datetime import datetime, timedelta

from . import models

WINDOW_DAYS = 7
_TS_FMT = "%Y-%m-%d %H:%M:%S"

CONFIDENT_ESTIMATE_THRESHOLD = 0.5


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts[:19], _TS_FMT)
    except ValueError:
        return None


def weekly_load(include_seed: bool = False) -> dict:
    rows = models.list_decisions(include_seed=include_seed)
    now = datetime.now()
    cutoff = now - timedelta(days=WINDOW_DAYS)

    def in_window(ts: str | None) -> bool:
        parsed = _parse(ts)
        return parsed is not None and parsed >= cutoff

    windowed = [r for r in rows if in_window(r["timestamp"])]

    logged = len(windowed)
    lifted = sum(1 for r in windowed if r["auto_resolution"])
    guided = sum(
        1
        for r in windowed
        if not r["auto_resolution"]
        and (r["confidence"] or 0) >= CONFIDENT_ESTIMATE_THRESHOLD
    )
    closed = sum(1 for r in rows if in_window(r["outcome_recorded_at"]))

    close_durations = []
    regret_hits = 0
    outcomes_in_window = 0
    for r in rows:
        if in_window(r["outcome_recorded_at"]):
            outcomes_in_window += 1
            if r["outcome"] == "regret":
                regret_hits += 1
            started, ended = _parse(r["timestamp"]), _parse(r["outcome_recorded_at"])
            if started and ended and ended >= started:
                close_durations.append((ended - started).total_seconds() / 3600)

    avg_hours_to_close = (
        round(sum(close_durations) / len(close_durations), 1) if close_durations else None
    )
    recent_regret_rate = (
        round(regret_hits / outcomes_in_window, 2) if outcomes_in_window else None
    )

    debt_topics = models.get_debt_topics(include_seed=include_seed)
    carried = len(debt_topics)

    resolved_ids = {r["topic_id"] for r in rows if r["outcome"] is not None and r["topic_id"]}
    debt_topic_ids = {t["topic_id"] for t in debt_topics}
    open_loops = sum(
        1
        for r in rows
        if r["outcome"] is None
        and r["topic_id"] not in debt_topic_ids
        and not _is_stale_duplicate(r, rows)
    )

    offloaded = lifted + guided

    all_time = {
        "logged": len(rows),
        "closed": sum(1 for r in rows if r["outcome"] is not None),
        "lifted": sum(1 for r in rows if r["auto_resolution"]),
    }

    return {
        "window_days": WINDOW_DAYS,
        "logged": logged,
        "lifted": lifted,
        "guided": guided,
        "offloaded": offloaded,
        "closed": closed,
        "carried": carried,
        "open_loops": open_loops,
        "avg_hours_to_close": avg_hours_to_close,
        "recent_regret_rate": recent_regret_rate,
        "headline": _headline(offloaded, carried, closed, open_loops),
        "all_time": all_time,
    }


def _is_stale_duplicate(row: dict, rows: list[dict]) -> bool:
    """A later logging of the same topic supersedes earlier open ones -- only
    the most recent open entry per topic counts as a live loop."""
    if not row["topic_id"]:
        return False
    same_topic = [r for r in rows if r["topic_id"] == row["topic_id"] and r["outcome"] is None]
    if len(same_topic) <= 1:
        return False
    newest = max(same_topic, key=lambda r: r["id"])
    return row["id"] != newest["id"]


def _headline(offloaded: int, carried: int, closed: int, open_loops: int = 0) -> str:
    open_total = carried + open_loops
    if offloaded == 0 and closed == 0:
        if open_total == 0:
            return "Nothing weighing on you that Choicely can see."
        return (
            f"{open_total} decision{'s' if open_total != 1 else ''} "
            f"{'are' if open_total != 1 else 'is'} open and waiting on you."
        )
    parts = []
    if offloaded:
        parts.append(f"took {offloaded} decision{'s' if offloaded != 1 else ''} off your plate")
    if closed:
        parts.append(f"helped you close {closed} loop{'s' if closed != 1 else ''}")
    lead = "This week, Choicely " + " and ".join(parts) + "."
    if open_total:
        lead += (
            f" {open_total} question{'s' if open_total != 1 else ''} "
            f"{'are' if open_total != 1 else 'is'} still open."
        )
    return lead
