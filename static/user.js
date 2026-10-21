const eventsList = document.getElementById("events-list");
const registrationModal = document.getElementById("register-card");
const registrationForm = document.getElementById("registration-form");
let events = [];
let selectedEvent = null;

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}

function formatDate(value, options) {
  if (!value) return "Date to be announced";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date to be announced" : new Intl.DateTimeFormat(undefined, options).format(date);
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderEvents() {
  eventsList.replaceChildren();
  if (!events.length) {
    eventsList.append(makeElement("p", "empty-state", "No events are scheduled just yet. Check back soon."));
    return;
  }

  events.forEach((event, index) => {
    const card = makeElement("article", "event-card");
    const visual = makeElement("div", `event-visual visual-${(index % 4) + 1}`);
    const date = makeElement("div", "event-date");
    const dateValue = event.start_time ? new Date(event.start_time) : null;
    date.append(
      makeElement("span", "", dateValue && !Number.isNaN(dateValue.getTime())
        ? new Intl.DateTimeFormat(undefined, { month: "short" }).format(dateValue)
        : "Soon"),
      makeElement("span", "", dateValue && !Number.isNaN(dateValue.getTime())
        ? new Intl.DateTimeFormat(undefined, { day: "2-digit" }).format(dateValue)
        : "✳")
    );
    visual.append(date);

    const body = makeElement("div", "event-body");
    const meta = makeElement("div", "event-meta");
    meta.append(
      makeElement("span", "event-venue", event.location || "Venue to be announced"),
      makeElement("span", "event-seats", `${Math.max(0, Number(event.capacity || 100) - Number(event.registration_count || 0))} seats left`)
    );
    const title = makeElement("h3", "", event.title);
    const description = makeElement("p", "event-description", event.description || "A thoughtful gathering, made for connection.");
    const bottom = makeElement("div", "event-bottom");
    const host = makeElement("span", "event-host", "HOSTED WITH");
    host.append(makeElement("strong", "", event.client_name || "Gatherwell Studio"));
    const register = makeElement("button", "button button-dark event-register", "Save your seat →");
    register.type = "button";
    register.disabled = Number(event.registration_count || 0) >= Number(event.capacity || 100);
    if (register.disabled) register.textContent = "Fully booked";
    register.addEventListener("click", () => openRegistration(event));
    bottom.append(host, register);
    body.append(meta, title, description, bottom);
    card.append(visual, body);
    eventsList.append(card);
  });
}

function openRegistration(event) {
  selectedEvent = event;
  document.getElementById("reg-evt-title").textContent = event.title;
  document.getElementById("reg-result").textContent = "";
  registrationModal.hidden = false;
  document.body.style.overflow = "hidden";
  document.getElementById("r-name").focus();
}

function closeRegistration() {
  registrationModal.hidden = true;
  document.body.style.overflow = "";
  selectedEvent = null;
}

document.getElementById("btn-cancel-register").addEventListener("click", closeRegistration);
registrationModal.addEventListener("click", (event) => {
  if (event.target === registrationModal) closeRegistration();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !registrationModal.hidden) closeRegistration();
});

registrationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedEvent) return;
  const result = document.getElementById("reg-result");
  const submit = registrationForm.querySelector('button[type="submit"]');
  result.classList.remove("is-error");
  result.textContent = "Saving your seat…";
  submit.disabled = true;
  try {
    const registration = await fetchJson("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: selectedEvent.id,
        name: document.getElementById("r-name").value.trim(),
        email: document.getElementById("r-email").value.trim(),
        phone: document.getElementById("r-phone").value.trim()
      })
    });
    result.textContent = "You're on the list! Your printable participation certificate is ready.";
    const certificate = makeElement("a", "", "View your certificate →");
    certificate.href = `/certificate/${registration.id}`;
    certificate.target = "_blank";
    certificate.rel = "noopener";
    result.append(document.createElement("br"), certificate);
    registrationForm.reset();
    events = await fetchJson("/api/events");
    renderEvents();
  } catch (error) {
    result.classList.add("is-error");
    result.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

const menuButton = document.querySelector(".menu-toggle");
menuButton.addEventListener("click", () => {
  const nav = document.querySelector(".site-nav");
  const isOpen = nav.classList.toggle("is-open");
  menuButton.setAttribute("aria-expanded", String(isOpen));
});
document.querySelectorAll(".site-nav a").forEach((link) => {
  link.addEventListener("click", () => {
    document.querySelector(".site-nav").classList.remove("is-open");
    menuButton.setAttribute("aria-expanded", "false");
  });
});

fetchJson("/api/events")
  .then((result) => {
    events = result;
    renderEvents();
  })
  .catch(() => {
    eventsList.replaceChildren(makeElement("p", "empty-state", "We couldn't load events. Please refresh the page to try again."));
  });
