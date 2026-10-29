# Workout Tracker

Small app for logging workouts against a **regiment**.

- Workout of the day (WOD) comes from the active regiment (by weekday)
- Start a session from the WOD
- Record actual sets/weight per exercise
- Comments per exercise and for the whole workout
- SQLite storage, no external services

## Quick start (Docker)

```bash
docker compose up --build
```

Open http://localhost:8000

Data lives in the `workout-data` volume.

## Quick start (local, uv)

```bash
uv sync
uv run uvicorn workout_tracker.main:app --reload --host 127.0.0.1 --port 8000
```

DB file defaults to `data/workouts.db` (override with `WORKOUT_DB_PATH`).

## How to use

1. **Overview** — see your daily workout, activity counts, and clickable weekly schedule; use the date picker to view another date
2. Fill **sets** one per line, e.g. `80 kg x 5` or `135x5 @ RPE8`
3. Add **exercise comments** and a **workout comment**
4. **My program** — view the weekly plan
5. **Workout history** — revisit and edit past sessions
6. **Create custom session** — open the dialog to start a workout outside your plan

First boot seeds a sample **3-Day Strength** regiment (push/pull/legs).

## Checks

```bash
uv sync --dev
uv run python -m unittest discover -s tests -v
uv build
```

The dashboard counts logged sessions, not completed workouts. Weekly statistics follow the selected date. Tests use a temporary SQLite database.

The bundled gym image is from [Unsplash](https://images.unsplash.com/photo-1534438327276-14e5300c3a48). Fonts load from Google Fonts with system-font fallbacks.

## Oz cloud

Designed to work with [Oz cloud agent environments](https://docs.warp.dev/platform/environments):

| Requirement | This project |
|---|---|
| glibc image (no Alpine/musl) | `python:3.12-slim-bookworm` |
| Non-root UID 1000 | `app` user in Dockerfile |
| Repeatable setup | `uv sync` |
| Health check | `GET /healthz` |

### Suggested environment

After the repo is on GitHub:

```bash
oz environment create \
  --name workout-tracker \
  --docker-image python:3.12-slim-bookworm \
  --repo YOUR_ORG/workout-tracker \
  --setup-command "curl -LsSf https://astral.sh/uv/install.sh | sh" \
  --setup-command 'export PATH="$HOME/.local/bin:$PATH" && uv sync' \
  --description "Workout tracker dev environment"
```

Or use the app image itself once published:

```bash
oz environment create \
  --name workout-tracker-app \
  --docker-image YOUR_REGISTRY/workout-tracker:latest \
  --repo YOUR_ORG/workout-tracker \
  --description "Runs with app deps preinstalled"
```

Run a cloud agent against it:

```bash
oz agent run-cloud \
  --environment <ENV_ID> \
  --prompt "Add a weekly volume summary page"
```

### Dev image alternative

Warp prebuilt web image also works:

```bash
oz environment create \
  --name workout-tracker \
  --docker-image warpdotdev/dev-web:latest \
  --repo YOUR_ORG/workout-tracker \
  --setup-command "uv sync"
```

## API surface (HTML forms + health)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | WOD + start session |
| GET | `/regiment` | Weekly plan |
| GET | `/sessions` | History |
| GET | `/sessions/{id}` | Edit logs/comments |
| GET | `/healthz` | Liveness |

## Layout

```
src/workout_tracker/
  main.py          # FastAPI + form handlers
  db.py            # SQLite schema + queries
  templates/       # Jinja HTML
  static/style.css
Dockerfile
docker-compose.yml
```
