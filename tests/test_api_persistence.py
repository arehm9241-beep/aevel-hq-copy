"""
Verification tests for API persistence, scoping, and error handling.
Run with: python -m pytest tests/test_api_persistence.py -v
Or: python -m unittest tests.test_api_persistence
"""
import os
import sys
import tempfile
import unittest

# Use in-memory or temp DB so we don't touch dev data
os.environ.setdefault("SECRET_KEY", "test-secret")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Point app to a temp DB
import app as app_module
_app_db_before = getattr(app_module, "DB_FILE", None)


def setUpModule():
    global _app_db_before
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app_module.DB_FILE = path
    app_module.init_db()
    app_module.migrate_db()
    # Create test user so we can log in in setUp
    from werkzeug.security import generate_password_hash
    conn = app_module.get_db()
    conn.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        ("test@example.com", generate_password_hash("testpass123")),
    )
    conn.commit()
    conn.close()


def tearDownModule():
    global _app_db_before
    if getattr(app_module, "DB_FILE", None) and app_module.DB_FILE != _app_db_before:
        try:
            os.unlink(app_module.DB_FILE)
        except Exception:
            pass
    app_module.DB_FILE = _app_db_before


class TestApiPersistence(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.client.environ_base["HTTP_HOST"] = "localhost"
        # Log in so session has user_id
        r = self.client.post(
            "/login",
            data={"email": "test@example.com", "password": "testpass123"},
            follow_redirects=True,
        )
        self.assertIn(r.status_code, (200, 302), "Login should succeed")

    def test_workspace_create_list_scope(self):
        r = self.client.post(
            "/api/workspace",
            json={"title": "My Page", "body": "Content"},
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        self.assertIn("id", data)
        pid = data["id"]
        r2 = self.client.get("/api/workspace")
        self.assertEqual(r2.status_code, 200)
        pages = r2.get_json().get("pages", [])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["title"], "My Page")

    def test_workspace_update_delete(self):
        r = self.client.post("/api/workspace", json={"title": "To Update", "body": ""})
        self.assertEqual(r.status_code, 201)
        pid = r.get_json()["id"]
        r2 = self.client.patch(
            "/api/workspace/" + pid,
            json={"title": "Updated", "body": "New body"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["title"], "Updated")
        r3 = self.client.delete("/api/workspace/" + pid)
        self.assertEqual(r3.status_code, 200)
        r4 = self.client.get("/api/workspace")
        pages = r4.get_json()["pages"]
        self.assertNotIn(pid, [p["id"] for p in pages], "Deleted page should not appear in list")

    def test_flowcharts_create_list_scope(self):
        r = self.client.post(
            "/api/flowcharts",
            json={"title": "Flow 1", "mermaid_text": "graph A-->B"},
        )
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        self.assertIn("id", data)
        r2 = self.client.get("/api/flowcharts")
        self.assertEqual(r2.status_code, 200)
        items = r2.get_json().get("flowcharts", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Flow 1")

    def test_events_create_list_delete(self):
        r = self.client.post(
            "/api/events",
            json={"date": "2026-02-02", "title": "Meeting"},
        )
        self.assertEqual(r.status_code, 201)
        eid = r.get_json()["id"]
        r2 = self.client.get("/api/events")
        self.assertEqual(r2.status_code, 200)
        events = r2.get_json().get("events", [])
        self.assertTrue(any(e["id"] == eid for e in events))
        r3 = self.client.patch("/api/events/" + eid, json={"date": "2026-02-03", "title": "Meeting updated"})
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.get_json()["title"], "Meeting updated")
        self.assertEqual(r3.get_json()["date"], "2026-02-03")
        r4 = self.client.delete("/api/events/" + eid)
        self.assertEqual(r4.status_code, 200)
        r5 = self.client.get("/api/events")
        self.assertFalse(any(e["id"] == eid for e in r5.get_json().get("events", [])))

    def test_activity_recent_and_batch_delete(self):
        r = self.client.get("/api/activity/recent")
        self.assertEqual(r.status_code, 200)
        self.assertIn("items", r.get_json())
        r2 = self.client.post("/api/tasks", json={"text": "Batch one"})
        tid1 = r2.get_json()["id"]
        r3 = self.client.post("/api/tasks", json={"text": "Batch two"})
        tid2 = r3.get_json()["id"]
        r4 = self.client.post("/api/tasks/batch-delete", json={"ids": [tid1, tid2]})
        self.assertEqual(r4.status_code, 200)
        self.assertEqual(r4.get_json().get("deleted"), 2)
        r5 = self.client.get("/api/tasks")
        self.assertFalse(any(t["id"] == tid1 for t in r5.get_json().get("tasks", [])))
        self.assertFalse(any(t["id"] == tid2 for t in r5.get_json().get("tasks", [])))

    def test_tasks_create_list_patch_delete(self):
        r = self.client.post(
            "/api/tasks",
            json={"text": "Test task", "urgency": "high"},
        )
        self.assertEqual(r.status_code, 201)
        tid = r.get_json()["id"]
        r2 = self.client.get("/api/tasks")
        tasks = r2.get_json().get("tasks", [])
        self.assertTrue(any(t["id"] == tid for t in tasks))
        r3 = self.client.patch("/api/tasks/" + tid, json={"done": True})
        self.assertEqual(r3.status_code, 200)
        r4 = self.client.delete("/api/tasks/" + tid)
        self.assertEqual(r4.status_code, 200)

    def test_notes_create_delete(self):
        r = self.client.post(
            "/api/notes",
            json={"title": "Note 1", "body": "Body"},
        )
        self.assertEqual(r.status_code, 201)
        nid = r.get_json()["id"]
        r2 = self.client.delete("/api/notes/" + nid)
        self.assertEqual(r2.status_code, 200)

    def test_community_notes_create_delete(self):
        r = self.client.post(
            "/api/community-notes",
            json={"title": "Idea", "body": "Text"},
        )
        self.assertEqual(r.status_code, 201)
        nid = r.get_json()["id"]
        r2 = self.client.delete("/api/community-notes/" + nid)
        self.assertEqual(r2.status_code, 200)

    def test_activity_log_created(self):
        """Ensure activity_log receives entries for key actions."""
        conn = app_module.get_db()
        before = conn.execute("SELECT COUNT(*) as c FROM activity_log").fetchone()["c"]
        conn.close()
        self.client.post("/api/tasks", json={"text": "Log me"})
        conn = app_module.get_db()
        after = conn.execute("SELECT COUNT(*) as c FROM activity_log").fetchone()["c"]
        conn.close()
        self.assertGreater(after, before)

    def test_404_on_other_users_workspace(self):
        """Workspace/flowcharts are user-scoped; 404 on wrong id or other user."""
        r = self.client.get("/api/workspace/nonexistent-id-12345")
        self.assertEqual(r.status_code, 404)
        r2 = self.client.patch("/api/workspace/nonexistent-id-12345", json={"title": "X"})
        self.assertEqual(r2.status_code, 404)
        r3 = self.client.delete("/api/workspace/nonexistent-id-12345")
        self.assertEqual(r3.status_code, 404)


if __name__ == "__main__":
    unittest.main()
