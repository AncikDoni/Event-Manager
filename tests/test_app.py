import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as event_app


class EventManagementTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        data_directory = Path(self.temporary_directory.name)
        self.path_patches = [
            patch.object(event_app, "DATA_DIR", data_directory),
            patch.object(event_app, "EVENTS_PATH", data_directory / "events.json"),
            patch.object(event_app, "REGISTRATIONS_PATH", data_directory / "registrations.json"),
            patch.object(event_app, "USERS_PATH", data_directory / "users.json"),
        ]
        for path_patch in self.path_patches:
            path_patch.start()
        event_app.initialize_data()
        event_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = event_app.app.test_client()

    def tearDown(self):
        for path_patch in reversed(self.path_patches):
            path_patch.stop()
        self.temporary_directory.cleanup()

    def sign_in(self):
        return self.client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "admin123"},
        )

    def event_payload(self, **updates):
        payload = {
            "title": "Community supper",
            "description": "An evening together.",
            "location": "Riverside Hall",
            "client_name": "Good Neighbors",
            "start_time": "2027-08-05T18:00",
            "end_time": "2027-08-05T21:00",
            "budget": 1250,
            "capacity": 1,
        }
        payload.update(updates)
        return payload

    def test_public_pages_and_seed_events_load(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 200)
        events = self.client.get("/api/events").get_json()
        self.assertEqual(len(events), 2)
        self.assertIn("registration_count", events[0])

    def test_legacy_events_receive_planning_defaults(self):
        event_app.write_json(
            event_app.EVENTS_PATH,
            [{"id": 1, "title": "Legacy event", "location": "Main Hall"}],
        )
        event = self.client.get("/api/events").get_json()[0]
        self.assertEqual(event["capacity"], 100)
        self.assertEqual(event["budget"], 0)
        self.assertEqual(event["client_name"], "")

    def test_admin_can_create_update_and_delete_event(self):
        self.assertEqual(
            self.client.post("/api/admin/events", json=self.event_payload()).status_code,
            401,
        )
        self.assertEqual(self.sign_in().status_code, 200)
        created = self.client.post("/api/admin/events", json=self.event_payload())
        self.assertEqual(created.status_code, 201)
        event_id = created.get_json()["id"]

        updated = self.client.put(
            f"/api/admin/events/{event_id}",
            json=self.event_payload(title="Community dinner", capacity=2),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["title"], "Community dinner")

        deleted = self.client.delete(f"/api/admin/events/{event_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/events/{event_id}").status_code, 404)

    def test_event_validation_rejects_bad_schedule_and_budget(self):
        self.sign_in()
        bad_schedule = self.client.post(
            "/api/admin/events",
            json=self.event_payload(end_time="2027-08-05T17:00"),
        )
        self.assertEqual(bad_schedule.status_code, 400)
        bad_budget = self.client.post(
            "/api/admin/events",
            json=self.event_payload(budget=float("inf")),
        )
        self.assertEqual(bad_budget.status_code, 400)

    def test_registration_prevents_duplicates_and_overbooking(self):
        self.sign_in()
        event_id = self.client.post(
            "/api/admin/events", json=self.event_payload()
        ).get_json()["id"]
        registration = {
            "event_id": event_id,
            "name": "Jordan Lee",
            "email": "Jordan@example.com",
        }
        first = self.client.post("/api/register", json=registration)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.client.get(f"/certificate/{first.get_json()['id']}").status_code, 200)

        duplicate = self.client.post(
            "/api/register",
            json={**registration, "email": "jordan@example.com"},
        )
        self.assertEqual(duplicate.status_code, 409)
        full = self.client.post(
            "/api/register",
            json={**registration, "email": "another@example.com"},
        )
        self.assertEqual(full.status_code, 409)

    def test_capacity_cannot_be_reduced_below_existing_registrations(self):
        self.sign_in()
        event_id = self.client.post(
            "/api/admin/events", json=self.event_payload(capacity=2)
        ).get_json()["id"]
        self.client.post(
            "/api/register",
            json={"event_id": event_id, "name": "Jordan Lee", "email": "jordan@example.com"},
        )
        update = self.client.put(
            f"/api/admin/events/{event_id}",
            json=self.event_payload(capacity=0),
        )
        self.assertEqual(update.status_code, 400)
        update = self.client.put(
            f"/api/admin/events/{event_id}",
            json=self.event_payload(capacity=1),
        )
        self.assertEqual(update.status_code, 200)

    def test_attendee_export_is_admin_only_and_csv(self):
        self.sign_in()
        event_id = self.client.post(
            "/api/admin/events", json=self.event_payload()
        ).get_json()["id"]
        self.client.post(
            "/api/register",
            json={"event_id": event_id, "name": "Jordan Lee", "email": "jordan@example.com"},
        )
        response = self.client.get(f"/api/admin/export_csv?event_id={event_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn("jordan@example.com", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
