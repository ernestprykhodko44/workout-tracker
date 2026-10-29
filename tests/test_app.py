import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from workout_tracker import db
from workout_tracker.main import app, templates


class WorkoutUITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DEFAULT_DB_PATH", Path(self.directory.name) / "test.db")
        self.db_patch.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.db_patch.stop()
        self.directory.cleanup()

    def start_workout(self, workout_date="2026-10-26"):
        return self.client.post(
            "/sessions/start-wod",
            data={"workout_date": workout_date, "comment": "Ready to go"},
        )

    def test_templates_compile(self):
        for name in templates.env.list_templates():
            templates.env.get_template(name)

    def test_dashboard_empty_state_and_week_navigation(self):
        response = self.client.get("/?d=2026-10-26")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Your story starts with one workout.", response.text)
        self.assertIn("Bench Press", response.text)
        self.assertIn("3 × 5", response.text)
        self.assertIn('href="/?d=2026-10-19"', response.text)
        self.assertIn('href="/?d=2026-11-02"', response.text)
        self.assertEqual(len(response.context["week"]), 7)
        self.assertEqual(response.context["total_sessions"], 0)
        self.assertTrue(response.context["week"][0]["selected"])

    def test_week_handles_month_and_year_boundaries(self):
        response = self.client.get("/?d=2027-01-01")
        self.assertEqual(response.context["week"][0]["date"], "2026-12-28")
        self.assertEqual(response.context["week"][-1]["date"], "2027-01-03")

    def test_activity_is_real_and_date_scoped(self):
        self.start_workout()
        self.start_workout()
        self.start_workout("2026-10-27")
        self.start_workout("2026-10-19")
        response = self.client.get("/?d=2026-10-26")
        self.assertEqual(response.context["week_sessions"], 3)
        self.assertEqual(response.context["active_days"], 2)
        self.assertEqual(response.context["total_sessions"], 4)
        self.assertEqual(len(response.context["today_sessions"]), 2)
        self.assertTrue(response.context["week"][0]["logged"])
        self.assertIn("Continue latest", response.text)

    def test_selected_day_sessions_are_not_limited_to_recent_list(self):
        self.start_workout("2026-10-19")
        for _ in range(12):
            self.start_workout()
        response = self.client.get("/?d=2026-10-19")
        self.assertEqual(len(response.context["today_sessions"]), 1)
        self.assertEqual(len(response.context["sessions"]), 4)

    def test_rest_day_and_no_active_program(self):
        response = self.client.get("/?d=2026-11-01")
        self.assertIn("Recovery is part of the plan.", response.text)
        self.assertNotIn('action="/sessions/start-wod"', response.text)
        with db.get_db() as conn:
            conn.execute("UPDATE regiment SET is_active = 0")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("No workout planned for this date.", response.text)
        self.assertEqual(self.client.get("/regiment").status_code, 200)

    def test_full_logging_flow(self):
        response = self.start_workout()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["session"]["exercises"]), 5)
        session = response.context["session"]
        exercise = session["exercises"][0]
        response = self.client.post(
            f"/sessions/{session['id']}/exercises/{exercise['id']}",
            data={"name": "Bench Press", "sets_text": "60 kg x 5\n70 kg x 5", "comment": "Good form"},
        )
        self.assertIn("Exercise saved.", response.text)
        self.assertEqual(len(response.context["session"]["exercises"][0]["sets"]), 2)
        response = self.client.post(
            f"/sessions/{session['id']}/comment", data={"comment": "Feeling stronger"}
        )
        self.assertIn("Session notes saved.", response.text)
        self.assertEqual(response.context["session"]["comment"], "Feeling stronger")
        response = self.client.post(
            f"/sessions/{session['id']}/exercises", data={"name": "Cable fly"}
        )
        self.assertEqual(len(response.context["session"]["exercises"]), 6)
        self.assertIn("Feeling stronger", self.client.get("/sessions").text)
        self.client.post(f"/sessions/{session['id']}/delete")
        self.assertEqual(self.client.get(f"/sessions/{session['id']}").status_code, 404)

    def test_custom_session_and_escaped_content(self):
        response = self.client.post(
            "/sessions/blank",
            data={"title": "<script>alert(1)</script>", "workout_date": "2026-10-26"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", response.text)
        self.assertEqual(response.context["session"]["exercises"], [])

    def test_invalid_date_returns_helpful_error(self):
        for value in ["not-a-date", "2026-02-30"]:
            response = self.client.get("/", params={"d": value})
            self.assertEqual(response.status_code, 400)

    def test_navigation_and_static_assets(self):
        for path, label in [("/", "Overview"), ("/regiment", "My program"), ("/sessions", "Workout history")]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('aria-current="page"', response.text)
            self.assertIn(label, response.text)
        for path in ["/static/style.css", "/static/app.js", "/static/gym.jpg"]:
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
