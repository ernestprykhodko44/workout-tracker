from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from workout_tracker import db

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

app = FastAPI(title="Workout Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    db.seed_if_empty()


def parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Use a valid date (YYYY-MM-DD)") from exc


def parse_sets_from_form(raw: str) -> list[dict[str, Any]]:
    """
    Accept lines like:
      60x5
      60 kg x 5
      135 lb x 5 @ RPE8
    or JSON array.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("sets must be a JSON array")
        return data

    sets: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^\s*(?P<weight>[\d.]+)\s*(?P<unit>kg|lb)?\s*[xX×]\s*(?P<reps>\d+)\s*(?P<note>.*)?$"
    )
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            entry: dict[str, Any] = {
                "weight": float(m.group("weight")),
                "reps": int(m.group("reps")),
            }
            if m.group("unit"):
                entry["unit"] = m.group("unit")
            note = (m.group("note") or "").strip(" -–—")
            if note:
                entry["note"] = note
            sets.append(entry)
        else:
            sets.append({"raw": line})
    return sets


def format_sets(sets: list[dict[str, Any]]) -> str:
    lines = []
    for s in sets:
        if "raw" in s and "weight" not in s:
            lines.append(str(s["raw"]))
            continue
        weight = s.get("weight", "")
        reps = s.get("reps", "")
        unit = s.get("unit", "")
        note = s.get("note", "")
        unit_part = f" {unit}" if unit else ""
        note_part = f" {note}" if note else ""
        lines.append(f"{weight}{unit_part} x {reps}{note_part}".strip())
    return "\n".join(lines)


def display_date(value: str, fmt: str = "%b %d, %Y") -> str:
    return date.fromisoformat(value).strftime(fmt)

templates.env.globals["WEEKDAYS"] = WEEKDAYS
templates.env.globals["format_sets"] = format_sets

templates.env.globals["display_date"] = display_date


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, d: str | None = None):
    on_date = parse_date(d)
    week_start = on_date - timedelta(days=on_date.weekday())
    week_end = week_start + timedelta(days=7)
    with db.get_db() as conn:
        wod = db.get_wod(conn, on_date)
        sessions = db.list_sessions(conn, limit=4)
        today_sessions = [
            dict(row) for row in conn.execute(
                "SELECT * FROM workout_session WHERE workout_date = ? ORDER BY id DESC",
                (on_date.isoformat(),),
            ).fetchall()
        ]
        activity = {
            row["workout_date"]: row["count"]
            for row in conn.execute(
                "SELECT workout_date, COUNT(*) AS count FROM workout_session "
                "WHERE workout_date >= ? AND workout_date < ? GROUP BY workout_date",
                (week_start.isoformat(), week_end.isoformat()),
            ).fetchall()
        }
        total_sessions = conn.execute("SELECT COUNT(*) FROM workout_session").fetchone()[0]
        active = db.get_active_regiment(conn)
        days = db.list_planned_days(conn, active["id"]) if active else []
    week = []
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        planned = next((day for day in days if day["weekday"] == i), None)
        week.append({
            "date": day_date.isoformat(),
            "number": day_date.day,
            "label": WEEKDAYS[i],
            "title": planned["title"] if planned else "No plan",
            "is_rest": not planned or not planned["exercises"],
            "selected": day_date == on_date,
            "is_today": day_date == date.today(),
            "logged": activity.get(day_date.isoformat(), 0),
        })
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "wod": wod,
            "on_date": on_date.isoformat(),
            "sessions": sessions,
            "today_sessions": today_sessions,
            "active": active,
            "week": week,
            "week_label": f"{week_start.strftime('%b %d')} – {(week_end - timedelta(days=1)).strftime('%b %d, %Y')}",
            "previous_week": (on_date - timedelta(days=7)).isoformat(),
            "next_week": (on_date + timedelta(days=7)).isoformat(),
            "date_label": on_date.strftime("%A, %B %d"),
            "is_today": on_date == date.today(),
            "is_current_week": week_start <= date.today() < week_end,
            "week_sessions": sum(activity.values()),
            "active_days": len(activity),
            "total_sessions": total_sessions,
        },
    )


@app.get("/regiment", response_class=HTMLResponse)
def regiment_view(request: Request):
    with db.get_db() as conn:
        active = db.get_active_regiment(conn)
        days = db.list_planned_days(conn, active["id"]) if active else []
        regiments = db.list_regiments(conn)
    return templates.TemplateResponse(
        request,
        "regiment.html",
        {"active": active, "days": days, "regiments": regiments},
    )


@app.post("/regiment/activate")
def activate_regiment(regiment_id: int = Form(...)):
    with db.get_db() as conn:
        db.set_active_regiment(conn, regiment_id)
    return RedirectResponse("/regiment", status_code=303)


@app.post("/sessions/start-wod")
def start_wod(workout_date: str = Form(...), comment: str = Form("")):
    on_date = parse_date(workout_date)
    with db.get_db() as conn:
        try:
            session = db.create_session_from_wod(conn, on_date, comment=comment)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/sessions/{session['id']}", status_code=303)


@app.post("/sessions/blank")
def start_blank(
    title: str = Form("Custom workout"),
    workout_date: str = Form(...),
    comment: str = Form(""),
):
    with db.get_db() as conn:
        session = db.create_blank_session(
            conn, title=title.strip() or "Custom workout", on_date=parse_date(workout_date), comment=comment
        )
    return RedirectResponse(f"/sessions/{session['id']}", status_code=303)


@app.get("/sessions", response_class=HTMLResponse)
def sessions_list(request: Request):
    with db.get_db() as conn:
        sessions = db.list_sessions(conn, limit=100)
    return templates.TemplateResponse(
        request, "sessions.html", {"sessions": sessions}
    )


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_detail(request: Request, session_id: int):
    with db.get_db() as conn:
        session = db.get_session(conn, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return templates.TemplateResponse(
        request, "session.html", {"session": session}
    )


@app.post("/sessions/{session_id}/comment")
def session_comment(session_id: int, comment: str = Form("")):
    with db.get_db() as conn:
        if not db.get_session(conn, session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        db.update_session_comment(conn, session_id, comment)
    return RedirectResponse(f"/sessions/{session_id}?saved=notes", status_code=303)


@app.post("/sessions/{session_id}/exercises/{exercise_id}")
def save_exercise(
    session_id: int,
    exercise_id: int,
    name: str = Form(...),
    sets_text: str = Form(""),
    comment: str = Form(""),
):
    try:
        sets = parse_sets_from_form(sets_text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid sets: {exc}") from exc

    with db.get_db() as conn:
        session = db.get_session(conn, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            db.update_exercise_log(
                conn, exercise_id, name=name.strip(), sets=sets, comment=comment
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(f"/sessions/{session_id}?saved=exercise#ex-{exercise_id}", status_code=303)


@app.post("/sessions/{session_id}/exercises")
def add_exercise(
    session_id: int,
    name: str = Form(...),
    comment: str = Form(""),
):
    with db.get_db() as conn:
        if not db.get_session(conn, session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        db.add_exercise_log(conn, session_id, name=name.strip(), comment=comment)
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@app.post("/sessions/{session_id}/delete")
def remove_session(session_id: int):
    with db.get_db() as conn:
        db.delete_session(conn, session_id)
    return RedirectResponse("/sessions", status_code=303)


def run() -> None:
    import uvicorn

    host = __import__("os").environ.get("HOST", "0.0.0.0")
    port = int(__import__("os").environ.get("PORT", "8000"))
    uvicorn.run("workout_tracker.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
