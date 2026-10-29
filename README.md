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

1. **Today** — see WOD from the regiment, start a session
2. Fill **sets** one per line, e.g. `80 kg x 5` or `135x5 @ RPE8`
3. Add **exercise comments** and a **workout comment**
4. **Regiment** — view the weekly plan
5. **History** — past sessions

First boot seeds a sample **3-Day Strength** regiment (push/pull/legs).

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
