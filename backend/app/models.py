"""SQLite storage for logged decisions."""
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "choicely.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    stakes TEXT NOT NULL,
    urgency TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    outcome TEXT,
    outcome_recorded_at TEXT,
    source TEXT NOT NULL DEFAULT 'dataset_prior',
    prior_category_label TEXT,
    prior_regret_rate REAL,
    prior_sample_size INTEGER,
    prior_description TEXT,
    personal_regret_estimate REAL,
    profile_adjusted_regret_rate REAL,
    blended_regret_estimate REAL,
    confidence REAL,
    personal_data_points INTEGER NOT NULL DEFAULT 0,
    auto_resolution TEXT,
    breakdown_json TEXT,
    topic_id INTEGER,
    reopened_count INTEGER NOT NULL DEFAULT 0,
    -- Opt-in flag to hold synthetic rows out of a real user's stats/debt/
    -- forecast. The bundled demo seed deliberately does NOT set it (that
    -- history is treated as the demo persona's own), so it's currently
    -- inert -- kept for callers that want isolated fixtures.
    is_seed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    planning_score REAL NOT NULL,
    planning_label TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

# SQLite's datetime('now') is UTC. Everything else in this app (the Python
# datetime.now() calls in load.py / checkins.py / reflection.py, the seed
# script, the "9pm" cutoff in the time-of-day insight) works in local time, so
# every timestamp SQLite writes is stamped 'localtime' to match. Keep this
# convention consistent -- mixing the two silently shifts every window and
# "how long ago" by the machine's UTC offset.
_NOW = "datetime('now', 'localtime')"

# Added after the initial schema -- no migration framework exists yet, so new
# columns are applied idempotently at startup via ALTER TABLE instead.
_NEW_COLUMNS = {
    "user_profile": {
        "risk_tolerance_financial": "REAL",
        "risk_tolerance_social": "REAL",
        "regret_orientation": "TEXT",
        "social_energy": "TEXT",
        "social_energy_stability": "TEXT",
        "decisiveness": "REAL",
        "conflict_style": "TEXT",
        "stakes_sensitivity": "TEXT",
    },
    "decisions": {
        "personality_adjusted_regret_rate": "REAL",
        "outcome_due_at": "TEXT",
    },
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(_SCHEMA)
        for table, columns in _NEW_COLUMNS.items():
            for column, col_type in columns.items():
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                except sqlite3.OperationalError:
                    pass  # column already exists


def get_profile() -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
        return dict(row) if row else None


def save_profile(
    name: str,
    planning_score: float,
    planning_label: str,
    personality: dict | None = None,
) -> None:
    personality = personality or {}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_profile (
                id, name, planning_score, planning_label,
                risk_tolerance_financial, risk_tolerance_social, regret_orientation,
                social_energy, social_energy_stability, decisiveness, conflict_style,
                stakes_sensitivity
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                planning_score = excluded.planning_score,
                planning_label = excluded.planning_label,
                risk_tolerance_financial = excluded.risk_tolerance_financial,
                risk_tolerance_social = excluded.risk_tolerance_social,
                regret_orientation = excluded.regret_orientation,
                social_energy = excluded.social_energy,
                social_energy_stability = excluded.social_energy_stability,
                decisiveness = excluded.decisiveness,
                conflict_style = excluded.conflict_style,
                stakes_sensitivity = excluded.stakes_sensitivity,
                completed_at = datetime('now', 'localtime')
            """,
            (
                name,
                planning_score,
                planning_label,
                personality.get("risk_tolerance_financial"),
                personality.get("risk_tolerance_social"),
                personality.get("regret_orientation"),
                personality.get("social_energy"),
                personality.get("social_energy_stability"),
                personality.get("decisiveness"),
                personality.get("conflict_style"),
                personality.get("stakes_sensitivity"),
            ),
        )


def count_decisions() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()
        return row["n"]


def get_outcomes_for_category(category_label: str) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT outcome FROM decisions WHERE prior_category_label = ? AND outcome IS NOT NULL",
            (category_label,),
        ).fetchall()
        return [row["outcome"] for row in rows]


def get_category_history(category_label: str, include_seed: bool = True) -> list[dict]:
    """Every recorded outcome for a dataset category, oldest first.

    Ordered by when the outcome landed (falling back to the decision's own
    timestamp for seed rows, which never went through update_outcome). This
    is the raw material for the regret-forecast trajectory: replaying the
    blend one outcome at a time in the order they actually came in.
    """
    seed_clause = "" if include_seed else "AND is_seed = 0"
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT text, outcome, is_seed,
                   COALESCE(outcome_recorded_at, timestamp) AS recorded_at
            FROM decisions
            WHERE prior_category_label = ? AND outcome IS NOT NULL {seed_clause}
            ORDER BY recorded_at ASC, id ASC
            """,
            (category_label,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_category_rows(include_seed: bool = True) -> list[dict]:
    """One row per dataset category the user has ever logged against."""
    seed_clause = "" if include_seed else "AND is_seed = 0"
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT prior_category_label AS category_label,
                   COUNT(*) AS times_logged,
                   SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END) AS outcomes_recorded,
                   MAX(timestamp) AS last_logged
            FROM decisions
            WHERE prior_category_label IS NOT NULL {seed_clause}
            GROUP BY prior_category_label
            ORDER BY times_logged DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_latest_decision_for_category(category_label: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM decisions
            WHERE prior_category_label = ?
            ORDER BY id DESC LIMIT 1
            """,
            (category_label,),
        ).fetchone()
        return dict(row) if row else None


def get_open_decisions_by_type(decision_type: str) -> list[dict]:
    """Decisions of this type with no outcome recorded yet -- candidates for
    decision-debt matching. Resolved decisions must never match here: a
    routine choice made and decided each day (e.g. "skip breakfast") is not
    the same thing as a standing question that never gets answered."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, text, topic_id FROM decisions WHERE decision_type = ? AND outcome IS NULL",
            (decision_type,),
        ).fetchall()
        return [dict(row) for row in rows]


def insert_decision(decision: dict) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO decisions
                (text, decision_type, stakes, urgency, timestamp, outcome, source,
                 prior_category_label, prior_regret_rate, prior_sample_size, prior_description,
                 personal_regret_estimate, profile_adjusted_regret_rate, personality_adjusted_regret_rate,
                 blended_regret_estimate, confidence, personal_data_points, auto_resolution,
                 breakdown_json, topic_id, is_seed, outcome_due_at, outcome_recorded_at)
            VALUES (?, ?, ?, ?, COALESCE(?, datetime('now', 'localtime')), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision["text"],
                decision["decision_type"],
                decision["stakes"],
                decision["urgency"],
                decision.get("timestamp"),
                decision.get("outcome"),
                decision.get("source", "dataset_prior"),
                decision.get("prior_category_label"),
                decision.get("prior_regret_rate"),
                decision.get("prior_sample_size"),
                decision.get("prior_description"),
                decision.get("personal_regret_estimate"),
                decision.get("profile_adjusted_regret_rate"),
                decision.get("personality_adjusted_regret_rate"),
                decision.get("blended_regret_estimate"),
                decision.get("confidence"),
                decision.get("personal_data_points", 0),
                decision.get("auto_resolution"),
                decision.get("breakdown_json"),
                decision.get("topic_id"),
                decision.get("is_seed", 0),
                decision.get("outcome_due_at"),
                decision.get("outcome_recorded_at"),
            ),
        )
        return cursor.lastrowid


def set_topic_id(decision_id: int, topic_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE decisions SET topic_id = ? WHERE id = ?", (topic_id, decision_id))


def recount_topic(topic_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE decisions
            SET reopened_count = (SELECT COUNT(*) FROM decisions WHERE topic_id = ?)
            WHERE topic_id = ?
            """,
            (topic_id, topic_id),
        )


def get_debt_topics(include_seed: bool = False) -> list[dict]:
    """Topic groups logged 2+ times where no outcome has ever been recorded.
    Seed/demo data is excluded by default -- it exists to make the app
    demoable, not to be mistaken for a real user's own history."""
    seed_clause = "" if include_seed else "AND is_seed = 0"
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                topic_id,
                decision_type,
                COUNT(*) AS times_logged,
                MIN(timestamp) AS first_logged,
                MAX(timestamp) AS last_logged,
                (SELECT text FROM decisions d2 WHERE d2.id = decisions.topic_id) AS canonical_text
            FROM decisions
            WHERE topic_id IS NOT NULL {seed_clause}
            GROUP BY topic_id
            HAVING COUNT(*) >= 2 AND SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END) = 0
            ORDER BY times_logged DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def update_outcome(decision_id: int, outcome: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE decisions SET outcome = ?, outcome_recorded_at = datetime('now', 'localtime') WHERE id = ?",
            (outcome, decision_id),
        )


def list_decisions(include_seed: bool = False) -> list[dict]:
    with get_connection() as conn:
        if include_seed:
            rows = conn.execute("SELECT * FROM decisions ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute("SELECT * FROM decisions WHERE is_seed = 0 ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def get_decision(decision_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        return dict(row) if row else None


def get_due_check_ins() -> list[dict]:
    """Real (non-seed) decisions with no outcome yet whose check-in time has
    arrived -- the ones Choicely should proactively ask about."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM decisions
            WHERE is_seed = 0
              AND outcome IS NULL
              AND outcome_due_at IS NOT NULL
              AND outcome_due_at <= datetime('now', 'localtime')
            ORDER BY outcome_due_at ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def shift_time(hours: float) -> int:
    """Demo aid: move every decision's clock backward by `hours` so pending
    check-ins come due and the weekly window still contains recent history.
    Shifts timestamp, outcome_due_at, and outcome_recorded_at together.
    Returns the number of rows touched."""
    delta = f"-{hours} hours"
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE decisions SET
                timestamp = datetime(timestamp, ?),
                outcome_due_at = CASE WHEN outcome_due_at IS NOT NULL
                    THEN datetime(outcome_due_at, ?) END,
                outcome_recorded_at = CASE WHEN outcome_recorded_at IS NOT NULL
                    THEN datetime(outcome_recorded_at, ?) END
            """,
            (delta, delta, delta),
        )
        return cursor.rowcount
