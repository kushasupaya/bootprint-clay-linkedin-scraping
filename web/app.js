const layout = document.getElementById("layout");
const peopleEl = document.getElementById("people");
const caseEl = document.getElementById("case");
const searchEl = document.getElementById("search");
const runinfoEl = document.getElementById("runinfo");

const state = { data: null, selected: null, filter: "all", query: "", expanded: new Set() };
const refreshBtn = document.getElementById("refresh");
const refreshStatus = document.getElementById("refresh-status");
const COLLAPSIBLE = ["No change", "Skipped", "Error", "Ignored"];

const SIGNALS = ["Job change", "Possible move"];
const QUIET = ["Ignored", "No change", "Info"];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c.nodeType ? c : document.createTextNode(c));
  }
  return node;
}

function toneOf(decision) {
  if (decision === "Job change") return "job";
  if (decision === "Possible move") return "maybe";
  if (decision === "Error" || decision === "Skipped") return "err";
  return "";
}

const AVATAR_COLORS = ["#3d5afe", "#0e7490", "#c2410c", "#be185d", "#a16207", "#4338ca"];

function avatar(name, big) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  return el("span", { class: "avatar" + (big ? " big" : ""), style: `--av:${AVATAR_COLORS[h % AVATAR_COLORS.length]}`, "aria-hidden": "true" }, initials);
}

function parseTime(s) {
  return new Date(s.replace(" ", "T"));
}

function fmtDay(s) {
  const d = parseTime(s + " 00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

function fmtTime(s) {
  return parseTime(s).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function fmtChecked(s) {
  if (!s) return "Never checked";
  const d = parseTime(s);
  return `Checked ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${fmtTime(s)}`;
}

function tickClass(decision) {
  if (!decision) return "tick";
  const tone = toneOf(decision);
  return "tick " + (tone || "seen");
}

function renderRoster() {
  const q = state.query.trim().toLowerCase();
  const people = state.data.people.filter(
    (p) => !q || p.name.toLowerCase().includes(q) || p.company.toLowerCase().includes(q)
  );
  peopleEl.replaceChildren();
  if (!people.length) {
    peopleEl.append(el("li", { class: "empty" }, el("p", {}, `No one matches "${state.query}".`)));
    return;
  }
  for (const p of people) {
    const sig = p.latest_signal;
    const btn = el(
      "button",
      {
        class: "person",
        type: "button",
        "aria-current": p.slug === state.selected ? "true" : "false",
        onclick: () => select(p.slug, true),
      },
      el(
        "div",
        { class: "person-top" },
        avatar(p.name, false),
        el(
          "div",
          { class: "person-text" },
          el(
            "div",
            { class: "person-head" },
            el("span", { class: "person-name" }, p.name),
            sig && el("span", { class: "tag " + toneOf(sig.decision) }, sig.decision)
          ),
          el("div", { class: "person-role" }, [p.title, p.company].filter(Boolean).join(" at "))
        )
      ),
      el(
        "div",
        { class: "strip", role: "img", "aria-label": `Last 14 days of activity for ${p.name}` },
        p.strip.map((t, i) =>
          el("span", { class: tickClass(t.decision), style: `--i:${i}`, title: `${fmtDay(t.day)}: ${t.decision || "No activity"}` })
        )
      )
    );
    peopleEl.append(el("li", {}, btn));
  }
}

function eventNode(e) {
  const tone = toneOf(e.decision);
  const quiet = QUIET.includes(e.decision);
  return el(
    "li",
    { class: ["event", tone, quiet ? "quiet" : ""].join(" ").trim() },
    el(
      "div",
      { class: "event-head" },
      el("span", { class: "event-what" }, e.decision),
      el("span", { class: "event-when" }, `${e.source === "Post" ? "From a post" : e.source === "Profile" ? "From the profile" : e.source} at ${fmtTime(e.time)}`)
    ),
    el("p", { class: "event-detail" }, e.detail),
    e.link && el("a", { class: "event-link", href: e.link, target: "_blank", rel: "noopener noreferrer" }, "Open on LinkedIn")
  );
}

// Consecutive repeats of the same routine decision on one day collapse into one row.
function groupNode(group, key) {
  const latest = group[0];
  const open = state.expanded.has(key);
  const toggle = el(
    "button",
    {
      class: "group-toggle",
      type: "button",
      "aria-expanded": String(open),
      onclick: () => {
        if (state.expanded.has(key)) state.expanded.delete(key);
        else state.expanded.add(key);
        renderCase();
      },
    },
    open ? "Hide the individual checks" : `Show all ${group.length} checks`
  );
  const tone = toneOf(latest.decision);
  return el(
    "li",
    { class: ["event", tone, QUIET.includes(latest.decision) ? "quiet" : ""].join(" ").trim() },
    el(
      "div",
      { class: "event-head" },
      el("span", { class: "event-what" }, `${latest.decision} (${group.length} checks)`),
      el("span", { class: "event-when" }, `Latest at ${fmtTime(latest.time)}`)
    ),
    el("p", { class: "event-detail" }, latest.detail),
    toggle,
    open &&
      el(
        "ul",
        { class: "group-list" },
        group.map((g) => el("li", {}, el("span", { class: "t" }, fmtTime(g.time)), g.detail))
      )
  );
}

function renderCase() {
  const p = state.data.people.find((x) => x.slug === state.selected);
  caseEl.replaceChildren();
  if (!p) {
    caseEl.append(
      el("div", { class: "empty" }, el("strong", {}, "Pick someone to see their history"), "Every post and profile check the system has made for them shows up here, with the reason for each decision.")
    );
    return;
  }

  const events = p.events.filter((e) => {
    if (state.filter === "signals") return SIGNALS.includes(e.decision);
    if (state.filter === "problems") return e.decision === "Skipped" || e.decision === "Error";
    return true;
  });

  const filters = [
    ["all", "Everything"],
    ["signals", "Signals"],
    ["problems", "Problems"],
  ].map(([key, label]) =>
    el("button", { type: "button", "aria-pressed": String(state.filter === key), onclick: () => { state.filter = key; renderCase(); } }, label)
  );

  caseEl.append(
    el("button", { class: "back", type: "button", onclick: () => { layout.dataset.view = "roster"; } }, "Back to everyone"),
    el(
      "div",
      { class: "case-head" },
      avatar(p.name, true),
      el("div", {}, el("h2", { class: "case-name" }, p.name), el("p", { class: "case-role" }, p.title ? `${p.title} at ${p.company}` : p.company))
    ),
    el(
      "div",
      { class: "case-meta" },
      el("span", {}, fmtChecked(p.last_checked)),
      p.data_as_of && el("span", {}, `Clay data from ${parseTime(p.data_as_of + ":00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${fmtTime(p.data_as_of + ":00")}`),
      p.linkedin_url && el("a", { href: p.linkedin_url, target: "_blank", rel: "noopener noreferrer" }, "LinkedIn profile")
    ),
    el("div", { class: "filters", role: "group", "aria-label": "Filter history" }, filters)
  );

  if (!events.length) {
    const msg =
      state.filter === "all"
        ? "Nothing logged for this person yet. Their history appears after the first run."
        : "Nothing matches this filter. Try Everything.";
    caseEl.append(el("p", { class: "empty" }, msg));
    return;
  }

  const byDay = new Map();
  for (const e of events) {
    const d = e.time.slice(0, 10);
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push(e);
  }
  for (const [d, dayEvents] of byDay) {
    caseEl.append(el("h3", { class: "day" }, fmtDay(d)));
    const list = el("ol", { class: "timeline" });
    caseEl.append(list);
    for (let i = 0; i < dayEvents.length; ) {
      const e = dayEvents[i];
      let j = i + 1;
      if (COLLAPSIBLE.includes(e.decision)) {
        while (j < dayEvents.length && dayEvents[j].decision === e.decision) j++;
      }
      const group = dayEvents.slice(i, j);
      list.append(group.length > 1 ? groupNode(group, `${p.slug}|${group[group.length - 1].time}`) : eventNode(e));
      i = j;
    }
  }
}

function select(slug, openCase) {
  state.selected = slug;
  state.filter = "all";
  if (openCase) layout.dataset.view = "case";
  renderRoster();
  renderCase();
  if (openCase) window.scrollTo({ top: 0 });
}

function renderRunInfo() {
  const t = state.data.last_run;
  runinfoEl.textContent = t
    ? `Last run ${parseTime(t).toLocaleDateString(undefined, { month: "short", day: "numeric" })} at ${fmtTime(t)}`
    : "No runs yet";
}

async function loadData() {
  const res = await fetch("/api/data", { cache: "no-store" });
  if (!res.ok) throw new Error(res.status);
  state.data = await res.json();
}

function setStatus(text, bad) {
  refreshStatus.textContent = text;
  refreshStatus.classList.toggle("bad", Boolean(bad));
}

async function refresh() {
  refreshBtn.disabled = true;
  refreshBtn.textContent = "Checking\u2026";
  setStatus("");
  try {
    const res = await fetch("/api/refresh", { method: "POST", headers: { "X-Requested-With": "watchlist-page" } });
    const out = await res.json().catch(() => ({}));
    if (!res.ok || !out.ok) {
      setStatus(out.error || "The check failed. See logs/run.log.", true);
      return;
    }
    await loadData();
    renderRunInfo();
    renderRoster();
    renderCase();
    const found = out.flagged.map((f) => `${f.name}: ${f.decision}`);
    const parts = [found.length ? `New: ${found.join("; ")}.` : "No new changes."];
    if (out.notes.length) parts.push(out.notes.join(" "));
    setStatus(parts.join(" "));
  } catch {
    setStatus("Can't reach the server. Start it with python3 server.py, then try again.", true);
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.textContent = "Check for updates";
  }
}

async function init() {
  layout.dataset.view = "roster";
  refreshBtn.addEventListener("click", refresh);
  try {
    await loadData();
  } catch {
    caseEl.replaceChildren(
      el("div", { class: "empty" }, el("strong", {}, "Can't load the history"), "Start the page with python3 server.py in the project folder, then reload.")
    );
    return;
  }
  if (!state.data.people.length) {
    caseEl.replaceChildren(
      el("div", { class: "empty" }, el("strong", {}, "Your watchlist is empty"), "Add people to watchlist.json, then reload.")
    );
    return;
  }
  renderRunInfo();
  const flagged = state.data.people.find((p) => p.latest_signal);
  state.selected = (flagged || state.data.people[0]).slug;
  renderRoster();
  renderCase();
  searchEl.addEventListener("input", () => { state.query = searchEl.value; renderRoster(); });
}

init();
