const loginCard = document.getElementById("login-card");
const adminPanel = document.getElementById("admin-panel");
const loginForm = document.getElementById("login-form");
const eventForm = document.getElementById("event-form");
const eventList = document.getElementById("admin-events");
const attendeesList = document.getElementById("admin-attendees");
let events = [];
let selectedEventId = null;
let editingEventId = null;

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setMessage(target, message, isError) {
  target.textContent = message;
  target.classList.toggle("is-error", Boolean(isError));
}

function formatDate(value) {
  if (!value) return "Date to be announced";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date to be announced" : new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

async function showDashboard() {
  loginCard.hidden = true;
  adminPanel.hidden = false;
  await Promise.all([loadEvents(), loadSummary()]);
}

async function loadSummary() {
  const summary = await fetchJson("/api/admin/summary");
  document.getElementById("stat-events").textContent = summary.event_count;
  document.getElementById("stat-attendees").textContent = summary.attendee_count;
  document.getElementById("stat-budget").textContent = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(summary.total_budget);
}

async function loadEvents() {
  events = await fetchJson("/api/events");
  eventList.replaceChildren();
  if (!events.length) {
    eventList.append(element("p", "empty-state", "No events yet. Plan your first gathering."));
    return;
  }
  events.forEach((event) => {
    const item = element("article", "admin-event-item");
    const details = element("div");
    details.append(
      element("h3", "", event.title),
      element("div", "admin-event-meta", `${formatDate(event.start_time)} · ${event.location} · ${event.registration_count}/${event.capacity} guests`),
      element("div", "admin-event-meta", `${event.client_name || "Gatherwell Studio"} · ${new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(event.budget || 0)}`)
    );
    const actions = element("div", "admin-event-actions");
    const select = element("button", "text-button", "Guests");
    select.type = "button";
    select.addEventListener("click", () => selectEvent(event.id));
    const edit = element("button", "text-button", "Edit");
    edit.type = "button";
    edit.addEventListener("click", () => editEvent(event.id));
    const remove = element("button", "text-button delete", "Delete");
    remove.type = "button";
    remove.addEventListener("click", () => deleteEvent(event.id));
    actions.append(select, edit, remove);
    item.append(details, actions);
    eventList.append(item);
  });
}

async function selectEvent(eventId) {
  selectedEventId = eventId;
  const event = events.find((item) => item.id === eventId);
  document.getElementById("attendee-heading").textContent = event ? `Guests · ${event.title}` : "Attendees";
  document.getElementById("btn-export").disabled = false;
  attendeesList.replaceChildren(element("p", "empty-state", "Loading guest list…"));
  try {
    const registrations = await fetchJson(`/api/admin/registrations?event_id=${encodeURIComponent(eventId)}`);
    attendeesList.replaceChildren();
    if (!registrations.length) {
      attendeesList.append(element("p", "empty-state", "No guests registered for this event yet."));
      return;
    }
    registrations.forEach((registration) => {
      const row = element("div", "attendee-item");
      const guest = element("div");
      guest.append(
        element("div", "attendee-name", registration.name),
        element("div", "attendee-email", registration.email)
      );
      if (registration.phone) guest.append(element("div", "attendee-email", registration.phone));
      row.append(guest, element("div", "attendee-date", formatDate(registration.timestamp)));
      attendeesList.append(row);
    });
  } catch (error) {
    attendeesList.replaceChildren(element("p", "empty-state", error.message));
  }
}

function resetEditor() {
  editingEventId = null;
  eventForm.reset();
  document.getElementById("ev-budget").value = "0";
  document.getElementById("ev-capacity").value = "100";
  document.getElementById("editor-heading").textContent = "Plan an event";
  document.getElementById("btn-save").innerHTML = 'Create event <span aria-hidden="true">→</span>';
  document.getElementById("btn-reset").hidden = true;
  setMessage(document.getElementById("event-message"), "", false);
}

function editEvent(eventId) {
  const event = events.find((item) => item.id === eventId);
  if (!event) return;
  editingEventId = eventId;
  document.getElementById("ev-title").value = event.title || "";
  document.getElementById("ev-desc").value = event.description || "";
  document.getElementById("ev-loc").value = event.location || "";
  document.getElementById("ev-client").value = event.client_name || "";
  document.getElementById("ev-start").value = event.start_time ? event.start_time.slice(0, 16) : "";
  document.getElementById("ev-end").value = event.end_time ? event.end_time.slice(0, 16) : "";
  document.getElementById("ev-budget").value = event.budget || 0;
  document.getElementById("ev-capacity").value = event.capacity || 100;
  document.getElementById("editor-heading").textContent = "Edit event";
  document.getElementById("btn-save").innerHTML = 'Save changes <span aria-hidden="true">→</span>';
  document.getElementById("btn-reset").hidden = false;
  setMessage(document.getElementById("event-message"), "", false);
  document.getElementById("event-editor").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteEvent(eventId) {
  const event = events.find((item) => item.id === eventId);
  if (!event || !window.confirm(`Delete "${event.title}" and its guest list? This cannot be undone.`)) return;
  try {
    await fetchJson(`/api/admin/events/${eventId}`, { method: "DELETE" });
    if (selectedEventId === eventId) {
      selectedEventId = null;
      document.getElementById("attendee-heading").textContent = "Attendees";
      document.getElementById("btn-export").disabled = true;
      attendeesList.replaceChildren(element("p", "empty-state", "Select an event to see its guests."));
    }
    if (editingEventId === eventId) resetEditor();
    await Promise.all([loadEvents(), loadSummary()]);
  } catch (error) {
    setMessage(document.getElementById("event-message"), error.message, true);
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.getElementById("login-res");
  const button = loginForm.querySelector('button[type="submit"]');
  button.disabled = true;
  setMessage(message, "Signing in…", false);
  try {
    await fetchJson("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("admin-user").value.trim(),
        password: document.getElementById("admin-pass").value
      })
    });
    await showDashboard();
  } catch (error) {
    setMessage(message, error.message, true);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("btn-logout").addEventListener("click", async () => {
  try {
    await fetchJson("/api/admin/logout", { method: "POST" });
    adminPanel.hidden = true;
    loginCard.hidden = false;
    loginForm.reset();
    setMessage(document.getElementById("login-res"), "", false);
  } catch (error) {
    window.alert(error.message);
  }
});

eventForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.getElementById("event-message");
  const button = document.getElementById("btn-save");
  const isEditing = editingEventId !== null;
  button.disabled = true;
  setMessage(message, isEditing ? "Saving changes…" : "Creating event…", false);
  const payload = {
    title: document.getElementById("ev-title").value.trim(),
    description: document.getElementById("ev-desc").value.trim(),
    location: document.getElementById("ev-loc").value.trim(),
    client_name: document.getElementById("ev-client").value.trim(),
    start_time: document.getElementById("ev-start").value,
    end_time: document.getElementById("ev-end").value,
    budget: document.getElementById("ev-budget").value,
    capacity: document.getElementById("ev-capacity").value
  };
  try {
    await fetchJson(isEditing ? `/api/admin/events/${editingEventId}` : "/api/admin/events", {
      method: isEditing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    resetEditor();
    setMessage(message, isEditing ? "Your event has been updated." : "Your event is on the calendar.", false);
    await Promise.all([loadEvents(), loadSummary()]);
    if (selectedEventId !== null) await selectEvent(selectedEventId);
  } catch (error) {
    setMessage(message, error.message, true);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("btn-reset").addEventListener("click", resetEditor);
document.getElementById("btn-export").addEventListener("click", () => {
  if (selectedEventId !== null) window.location.href = `/api/admin/export_csv?event_id=${encodeURIComponent(selectedEventId)}`;
});

fetchJson("/api/admin/session")
  .then((result) => result.authenticated ? showDashboard() : undefined)
  .catch(() => setMessage(document.getElementById("login-res"), "Unable to connect. Please refresh and try again.", true));
