from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path(os.environ.get("WORKOUT_DB_PATH", "data/workouts.db"))


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with get_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS regiment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS planned_day (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regiment_id INTEGER NOT NULL REFERENCES regiment(id) ON DELETE CASCADE,
                weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
                title TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                UNIQUE (regiment_id, weekday)
            );

            CREATE TABLE IF NOT EXISTS planned_exercise (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                planned_day_id INTEGER NOT NULL REFERENCES planned_day(id) ON DELETE CASCADE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS workout_session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_date TEXT NOT NULL,
                planned_day_id INTEGER REFERENCES planned_day(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exercise_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES workout_session(id) ON DELETE CASCADE,
                planned_exercise_id INTEGER REFERENCES planned_exercise(id) ON DELETE SET NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                sets_json TEXT NOT NULL DEFAULT '[]',
                comment TEXT NOT NULL DEFAULT ''
            );
            """
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def seed_if_empty(db_path: Path | None = None) -> None:
    """Load a starter full-body regiment when the DB has no regiments."""
    with get_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM regiment").fetchone()["c"]
        if count:
            return

        now = utc_now()
        cur = conn.execute(
            "INSERT INTO regiment (name, description, is_active, created_at) VALUES (?, ?, 1, ?)",
            (
                "3-Day Strength",
                "Simple push / pull / legs rotation. Workout of the day follows the weekday map.",
                now,
            ),
        )
        regiment_id = cur.lastrowid

        # Mon=0 ... Sun=6 in Python datetime.weekday()
        days = [
            (
                0,
                "Push",
                "Chest, shoulders, triceps",
                [
                    ("Bench Press", "3x5 @ challenging weight", ""),
                    ("Overhead Press", "3x8", ""),
                    ("Incline DB Press", "3x10", ""),
                    ("Tricep Pushdown", "3x12", ""),
                    ("Lateral Raise", "3x15", ""),
                ],
            ),
            (
                1,
                "Pull",
                "Back and biceps",
                [
                    ("Barbell Row", "3x5", ""),
                    ("Pull-Up / Lat Pulldown", "3x8", "Use band or machine if needed"),
                    ("Seated Cable Row", "3x10", ""),
                    ("Face Pull", "3x15", ""),
                    ("Barbell Curl", "3x10", ""),
                ],
            ),
            (
                2,
                "Legs",
                "Quads, hamstrings, calves",
                [
                    ("Back Squat", "3x5", ""),
                    ("Romanian Deadlift", "3x8", ""),
                    ("Walking Lunge", "3x10/leg", ""),
                    ("Leg Curl", "3x12", ""),
                    ("Calf Raise", "3x15", ""),
                ],
            ),
            (
                3,
                "Push (repeat)",
                "Lighter volume optional",
                [
                    ("Bench Press", "3x5", ""),
                    ("Overhead Press", "3x8", ""),
                    ("Incline DB Press", "3x10", ""),
                    ("Tricep Pushdown", "3x12", ""),
                    ("Lateral Raise", "3x15", ""),
                ],
            ),
            (
                4,
                "Pull (repeat)",
                "",
                [
                    ("Barbell Row", "3x5", ""),
                    ("Pull-Up / Lat Pulldown", "3x8", ""),
                    ("Seated Cable Row", "3x10", ""),
                    ("Face Pull", "3x15", ""),
                    ("Barbell Curl", "3x10", ""),
                ],
            ),
            (5, "Rest / Mobility", "Optional easy cardio or stretch", []),
            (6, "Rest", "Full rest day", []),
        ]

        for weekday, title, notes, exercises in days:
            cur = conn.execute(
                "INSERT INTO planned_day (regiment_id, weekday, title, notes) VALUES (?, ?, ?, ?)",
                (regiment_id, weekday, title, notes),
            )
            day_id = cur.lastrowid
            for i, (name, target, ex_notes) in enumerate(exercises):
                conn.execute(
                    """
                    INSERT INTO planned_exercise
                        (planned_day_id, sort_order, name, target, notes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (day_id, i, name, target, ex_notes),
                )


# --- regiment queries ---


def list_regiments(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM regiment ORDER BY is_active DESC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_active_regiment(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM regiment WHERE is_active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    return row_to_dict(row)


def set_active_regiment(conn: sqlite3.Connection, regiment_id: int) -> None:
    conn.execute("UPDATE regiment SET is_active = 0")
    conn.execute("UPDATE regiment SET is_active = 1 WHERE id = ?", (regiment_id,))


def get_planned_day_for_weekday(
    conn: sqlite3.Connection, regiment_id: int, weekday: int
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM planned_day
        WHERE regiment_id = ? AND weekday = ?
        """,
        (regiment_id, weekday),
    ).fetchone()
    if not row:
        return None
    day = dict(row)
    day["exercises"] = list_planned_exercises(conn, day["id"])
    return day


def list_planned_days(conn: sqlite3.Connection, regiment_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM planned_day
        WHERE regiment_id = ?
        ORDER BY weekday
        """,
        (regiment_id,),
    ).fetchall()
    days = []
    for r in rows:
        d = dict(r)
        d["exercises"] = list_planned_exercises(conn, d["id"])
        days.append(d)
    return days


def list_planned_exercises(conn: sqlite3.Connection, planned_day_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM planned_exercise
        WHERE planned_day_id = ?
        ORDER BY sort_order, id
        """,
        (planned_day_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_wod(conn: sqlite3.Connection, on_date: date | None = None) -> dict[str, Any] | None:
    on_date = on_date or date.today()
    regiment = get_active_regiment(conn)
    if not regiment:
        return None
    day = get_planned_day_for_weekday(conn, regiment["id"], on_date.weekday())
    if not day:
        return None
    return {
        "date": on_date.isoformat(),
        "weekday": on_date.weekday(),
        "regiment": regiment,
        "planned_day": day,
    }


# --- sessions ---


def create_session_from_wod(
    conn: sqlite3.Connection,
    on_date: date | None = None,
    comment: str = "",
) -> dict[str, Any]:
    wod = get_wod(conn, on_date)
    if not wod:
        raise ValueError("No active regiment / planned day for this date")

    now = utc_now()
    day = wod["planned_day"]
    cur = conn.execute(
        """
        INSERT INTO workout_session
            (workout_date, planned_day_id, title, comment, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (wod["date"], day["id"], day["title"], comment, now, now),
    )
    session_id = cur.lastrowid
    for i, ex in enumerate(day["exercises"]):
        conn.execute(
            """
            INSERT INTO exercise_log
                (session_id, planned_exercise_id, sort_order, name, sets_json, comment)
            VALUES (?, ?, ?, ?, '[]', '')
            """,
            (session_id, ex["id"], i, ex["name"]),
        )
    return get_session(conn, session_id)  # type: ignore[return-value]


def create_blank_session(
    conn: sqlite3.Connection,
    title: str,
    on_date: date | None = None,
    comment: str = "",
) -> dict[str, Any]:
    on_date = on_date or date.today()
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO workout_session
            (workout_date, planned_day_id, title, comment, created_at, updated_at)
        VALUES (?, NULL, ?, ?, ?, ?)
        """,
        (on_date.isoformat(), title, comment, now, now),
    )
    return get_session(conn, cur.lastrowid)  # type: ignore[return-value]


def list_sessions(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, workout_date, title, comment, created_at, updated_at, planned_day_id
        FROM workout_session
        ORDER BY workout_date DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_session(conn: sqlite3.Connection, session_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM workout_session WHERE id = ?", (session_id,)
    ).fetchone()
    if not row:
        return None
    session = dict(row)
    ex_rows = conn.execute(
        """
        SELECT * FROM exercise_log
        WHERE session_id = ?
        ORDER BY sort_order, id
        """,
        (session_id,),
    ).fetchall()
    exercises = []
    for er in ex_rows:
        e = dict(er)
        try:
            e["sets"] = json.loads(e.pop("sets_json") or "[]")
        except json.JSONDecodeError:
            e["sets"] = []
        exercises.append(e)
    session["exercises"] = exercises
    return session


def update_session_comment(conn: sqlite3.Connection, session_id: int, comment: str) -> None:
    conn.execute(
        "UPDATE workout_session SET comment = ?, updated_at = ? WHERE id = ?",
        (comment, utc_now(), session_id),
    )


def update_exercise_log(
    conn: sqlite3.Connection,
    exercise_id: int,
    *,
    name: str | None = None,
    sets: list[dict[str, Any]] | None = None,
    comment: str | None = None,
) -> None:
    row = conn.execute(
        "SELECT * FROM exercise_log WHERE id = ?", (exercise_id,)
    ).fetchone()
    if not row:
        raise ValueError("Exercise log not found")

    new_name = name if name is not None else row["name"]
    new_comment = comment if comment is not None else row["comment"]
    if sets is not None:
        sets_json = json.dumps(sets)
    else:
        sets_json = row["sets_json"]

    conn.execute(
        """
        UPDATE exercise_log
        SET name = ?, sets_json = ?, comment = ?
        WHERE id = ?
        """,
        (new_name, sets_json, new_comment, exercise_id),
    )
    conn.execute(
        "UPDATE workout_session SET updated_at = ? WHERE id = ?",
        (utc_now(), row["session_id"]),
    )


def add_exercise_log(
    conn: sqlite3.Connection,
    session_id: int,
    name: str,
    comment: str = "",
) -> dict[str, Any]:
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) AS m FROM exercise_log WHERE session_id = ?",
        (session_id,),
    ).fetchone()["m"]
    cur = conn.execute(
        """
        INSERT INTO exercise_log
            (session_id, planned_exercise_id, sort_order, name, sets_json, comment)
        VALUES (?, NULL, ?, ?, '[]', ?)
        """,
        (session_id, max_order + 1, name, comment),
    )
    conn.execute(
        "UPDATE workout_session SET updated_at = ? WHERE id = ?",
        (utc_now(), session_id),
    )
    row = conn.execute(
        "SELECT * FROM exercise_log WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    e = dict(row)
    e["sets"] = []
    e.pop("sets_json", None)
    return e


def delete_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute("DELETE FROM workout_session WHERE id = ?", (session_id,))
