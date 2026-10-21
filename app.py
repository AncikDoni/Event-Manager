import csv
import io
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EVENTS_PATH = DATA_DIR / "events.json"
REGISTRATIONS_PATH = DATA_DIR / "registrations.json"
USERS_PATH = DATA_DIR / "users.json"

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.config["JSON_SORT_KEYS"] = False


def read_json(path, default):
    if not path.exists() or not path.stat().st_size:
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


def next_id(items):
    return max((item.get("id", 0) for item in items), default=0) + 1


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return jsonify({"error": "Please sign in as an administrator."}), 401
        return function(*args, **kwargs)

    return wrapper


def initialize_data():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not EVENTS_PATH.exists() or not EVENTS_PATH.stat().st_size:
        events = [
            {
                "id": 1,
                "title": "The Creative Summit",
                "description": "A day of thoughtful talks, hands-on workshops, and new connections for the creative community.",
                "location": "The Glasshouse, Brooklyn",
                "start_time": "2027-05-18T09:00",
                "end_time": "2027-05-18T17:00",
                "budget": 8500,
                "capacity": 180,
                "client_name": "Northstar Studio",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": 2,
                "title": "Summer Table",
                "description": "An intimate outdoor dinner celebrating local food, seasonal ingredients, and the people who grow them.",
                "location": "Juniper Garden, Queens",
                "start_time": "2027-07-09T18:30",
                "end_time": "2027-07-09T22:00",
                "budget": 4200,
                "capacity": 80,
                "client_name": "Common Ground",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        write_json(EVENTS_PATH, events)
    for path in (REGISTRATIONS_PATH, USERS_PATH):
        if not path.exists() or not path.stat().st_size:
            write_json(path, [])
    users = read_json(USERS_PATH, [])
    if not users:
        write_json(
            USERS_PATH,
            [
                {
                    "username": "admin",
                    "password_hash": generate_password_hash("admin123"),
                    "is_admin": True,
                }
            ],
        )


initialize_data()


def registration_count(event_id):
    return sum(1 for item in read_json(REGISTRATIONS_PATH, []) if item["event_id"] == event_id)


def event_with_count(event):
    result = dict(event)
    result.setdefault("budget", 0)
    result.setdefault("capacity", 100)
    result.setdefault("client_name", "")
    result["registration_count"] = registration_count(event["id"])
    return result


def parse_event_payload(body, current=None):
    body = body if isinstance(body, dict) else {}
    current = current or {}
    title = body.get("title", current.get("title", ""))
    location = body.get("location", current.get("location", ""))
    description = body.get("description", current.get("description", ""))
    client_name = body.get("client_name", current.get("client_name", ""))
    start_time = body.get("start_time", current.get("start_time", ""))
    end_time = body.get("end_time", current.get("end_time", ""))
    try:
        budget = float(body.get("budget", current.get("budget", 0)))
        capacity_value = body.get("capacity", current.get("capacity", 100))
        capacity = int(capacity_value)
        if isinstance(capacity_value, bool) or float(capacity_value) != capacity:
            raise ValueError
    except (TypeError, ValueError):
        return None, "Budget must be a number and capacity must be a whole number."
    if not isinstance(title, str) or not title.strip():
        return None, "Please enter an event name."
    if not isinstance(location, str) or not location.strip():
        return None, "Please enter a venue."
    if not math.isfinite(budget) or budget < 0 or capacity < 1:
        return None, "Budget cannot be negative and capacity must be at least one."
    try:
        start = datetime.fromisoformat(start_time) if start_time else None
        end = datetime.fromisoformat(end_time) if end_time else None
    except (TypeError, ValueError):
        return None, "Enter a valid start and end date."
    if start and end and end <= start:
        return None, "The end time must be after the start time."
    return {
        "title": title.strip(),
        "description": description.strip() if isinstance(description, str) else "",
        "location": location.strip(),
        "start_time": start_time,
        "end_time": end_time,
        "budget": budget,
        "capacity": capacity,
        "client_name": client_name.strip() if isinstance(client_name, str) else "",
    }, None


@app.route("/")
def user_page():
    return render_template("user.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.get("/api/events")
def api_events():
    events = read_json(EVENTS_PATH, [])
    events.sort(key=lambda event: event.get("start_time") or "")
    return jsonify([event_with_count(event) for event in events])


@app.get("/api/events/<int:event_id>")
def api_event(event_id):
    event = next((item for item in read_json(EVENTS_PATH, []) if item["id"] == event_id), None)
    if event is None:
        return jsonify({"error": "Event not found."}), 404
    return jsonify(event_with_count(event))


@app.post("/api/register")
def api_register():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Invalid registration details."}), 400
    name = body.get("name", "").strip() if isinstance(body.get("name"), str) else ""
    email = body.get("email", "").strip().lower() if isinstance(body.get("email"), str) else ""
    phone = body.get("phone", "").strip() if isinstance(body.get("phone"), str) else ""
    try:
        event_id = int(body.get("event_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a valid event."}), 400
    if not name or not email or "@" not in email:
        return jsonify({"error": "Enter your name and a valid email address."}), 400
    events = read_json(EVENTS_PATH, [])
    event = next((item for item in events if item["id"] == event_id), None)
    if event is None:
        return jsonify({"error": "This event is no longer available."}), 404
    registrations = read_json(REGISTRATIONS_PATH, [])
    if any(item["event_id"] == event_id and item["email"].lower() == email for item in registrations):
        return jsonify({"error": "This email is already registered for the event."}), 409
    if registration_count(event_id) >= int(event.get("capacity", 100)):
        return jsonify({"error": "This event has reached its registration limit."}), 409
    registration = {
        "id": next_id(registrations),
        "event_id": event_id,
        "name": name,
        "email": email,
        "phone": phone,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    registrations.append(registration)
    write_json(REGISTRATIONS_PATH, registrations)
    return jsonify(registration), 201


@app.post("/api/admin/login")
def api_admin_login():
    body = request.get_json(silent=True) or {}
    username = body.get("username") if isinstance(body, dict) else None
    password = body.get("password") if isinstance(body, dict) else None
    user = next(
        (
            item
            for item in read_json(USERS_PATH, [])
            if item.get("username") == username and item.get("is_admin")
        ),
        None,
    )
    if user and isinstance(password, str) and check_password_hash(user["password_hash"], password):
        session.clear()
        session["admin"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "The username or password is incorrect."}), 401


@app.post("/api/admin/logout")
def api_admin_logout():
    session.pop("admin", None)
    return jsonify({"ok": True})


@app.get("/api/admin/session")
def api_admin_session():
    return jsonify({"authenticated": bool(session.get("admin"))})


@app.get("/api/admin/summary")
@admin_required
def api_admin_summary():
    events = read_json(EVENTS_PATH, [])
    registrations = read_json(REGISTRATIONS_PATH, [])
    return jsonify(
        {
            "event_count": len(events),
            "attendee_count": len(registrations),
            "total_budget": sum(float(event.get("budget", 0)) for event in events),
        }
    )


@app.post("/api/admin/events")
@admin_required
def api_admin_create_event():
    payload, error = parse_event_payload(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400
    events = read_json(EVENTS_PATH, [])
    event = {
        "id": next_id(events),
        **payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    events.append(event)
    write_json(EVENTS_PATH, events)
    return jsonify(event_with_count(event)), 201


@app.put("/api/admin/events/<int:event_id>")
@admin_required
def api_admin_update_event(event_id):
    events = read_json(EVENTS_PATH, [])
    event = next((item for item in events if item["id"] == event_id), None)
    if event is None:
        return jsonify({"error": "Event not found."}), 404
    payload, error = parse_event_payload(request.get_json(silent=True), event)
    if error:
        return jsonify({"error": error}), 400
    if payload["capacity"] < registration_count(event_id):
        return jsonify({"error": "Capacity cannot be lower than the number of registered guests."}), 400
    event.update(payload)
    write_json(EVENTS_PATH, events)
    return jsonify(event_with_count(event))


@app.delete("/api/admin/events/<int:event_id>")
@admin_required
def api_admin_delete_event(event_id):
    events = read_json(EVENTS_PATH, [])
    if not any(item["id"] == event_id for item in events):
        return jsonify({"error": "Event not found."}), 404
    write_json(EVENTS_PATH, [item for item in events if item["id"] != event_id])
    registrations = read_json(REGISTRATIONS_PATH, [])
    write_json(
        REGISTRATIONS_PATH,
        [item for item in registrations if item["event_id"] != event_id],
    )
    return jsonify({"ok": True})


@app.get("/api/admin/registrations")
@admin_required
def api_admin_registrations():
    event_id = request.args.get("event_id", type=int)
    registrations = read_json(REGISTRATIONS_PATH, [])
    if event_id is not None:
        registrations = [item for item in registrations if item["event_id"] == event_id]
    return jsonify(registrations)


@app.get("/api/admin/export_csv")
@admin_required
def api_admin_export_csv():
    event_id = request.args.get("event_id", type=int)
    if event_id is None:
        return jsonify({"error": "Choose an event to export."}), 400
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email", "phone", "timestamp"])
    for item in read_json(REGISTRATIONS_PATH, []):
        if item["event_id"] == event_id:
            writer.writerow(
                [item.get("id"), item.get("name"), item.get("email"), item.get("phone"), item.get("timestamp")]
            )
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=attendees_event_{event_id}.csv"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    return response


@app.get("/certificate/<int:registration_id>")
def certificate_page(registration_id):
    registrations = read_json(REGISTRATIONS_PATH, [])
    registration = next((item for item in registrations if item["id"] == registration_id), None)
    if registration is None:
        abort(404)
    event = next(
        (item for item in read_json(EVENTS_PATH, []) if item["id"] == registration["event_id"]),
        None,
    )
    return render_template("certificate.html", registration=registration, event=event)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
