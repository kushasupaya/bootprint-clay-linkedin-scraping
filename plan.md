# LinkedIn Job-Change Watchlist (Slack Daily Digest + Local History Page)

> This spec is designed to be used as context for a new Claude Code session. Drop it in a project folder and begin building from here.

## Outcome

> **Update 2026-10-26:** LinkedIn offers no email option for these notifications (job-change notifications are in-app and push only). The posts path (Gmail bell emails, post labeling) is parked. Version 1 detects job changes through Clay only. Revisit if Clay can return post text.
A personal tool for a recruiter (the builder, using it for themselves) that watches about 5 specific people on LinkedIn and alerts them on Slack when one of them changes jobs. The system uses two kinds of signals: a person's own LinkedIn posts announcing a move (caught through LinkedIn's free bell-notification emails), and a change in their current company or job title (checked through Clay and compared with what was saved last time). Once a day it sends one Slack direct message summarizing what it found, with a "why this matters" line for each item. A simple page on the user's laptop lets them look up the history for each person. "Done" means the user hears about a job change from this system before they would have noticed it on their own.

## Success Signal
The system catches a watched person's job change before the user noticed it themselves. (Early target: 5 people watched. Later versions may grow this.)

## Inputs
- **LinkedIn notification emails (posts):** the emails LinkedIn sends when a watched person posts (bell notification turned on for each of the ~5 people) — from the user's email inbox — freshness: the last 48 hours, read once a day
- **Current job title and company (profile changes):** for each watched person — from Clay (the user sets up the 5 people in Clay) — freshness: refreshed once a day before the comparison
- **Watchlist:** the ~5 people being watched (name, company, LinkedIn profile link) — from the user, kept in a simple list — freshness: updated by hand when the user adds or removes someone
- **Memory (last-known state):** each person's last-known title and company, the date last checked, and which posts were already reported — from a small local file the system writes itself — freshness: updated at the end of every run

Notes on the data:
- LinkedIn emails usually show only the first few lines of a post. The system judges only what it can see.
- Only LinkedIn notification emails are read from the inbox. Nothing else is opened or used.
- Notifications from anyone not on the watchlist are ignored.
- Clay only knows what is true today, so detecting a change requires comparing against the saved memory.
- What Clay can return and what it costs per refresh (credits) must be checked early. Whether Clay can return post text is unconfirmed; the plan does not depend on it.
- "Open to Work" is out of scope (Clay does not provide it).

## Logic
- **Trigger:** a daily schedule at **10 PM Eastern**, running on the user's laptop. If the laptop is closed at 10 PM, the system runs as soon as the laptop next opens, and the Slack message says it is a late summary.
- **Decision points:**
  1. **Posts path:** Is this email a LinkedIn notification about someone on the watchlist? (If not, ignore.)
  2. Is the post less than 48 hours old? (If not, ignore.)
  3. Was this post already reported in an earlier summary? (If yes, ignore, so repeats stop.)
  4. Is the post the person's own announcement of leaving or joining a job?
     - **Job change:** clear announcement, e.g. "Today was my last day at…" or "I'm excited to share I'm joining…"
     - **Possible move:** vague hint with no company named, e.g. "Excited for what's next!" Also used when the AI can't decide.
     - **Not a signal (ignore):** an article the person shared about career moves, a post about someone else's job, or anything unrelated.
  5. **Profile path:** Did Clay return usable data for this person? (If blank or an error, skip the comparison for today and say so in Slack. Never treat blank data as a job change.)
  6. Does the company differ from the saved one in a real way? (Yes: **Job change.** Differences that are only spelling, like "Acme" vs. "Acme Inc.", are ignored.)
  7. Does the title differ while the company is the same? (Yes: **Possible move** at most, since it is usually a promotion.)
  8. Were any LinkedIn emails received at all in the last 48 hours? (If zero, send a warning instead of a "quiet day" message.)
  9. Was anything flagged today? (If nothing, send a short "nothing today" message.)
- **Rules:**
  - Only read LinkedIn notification emails from the inbox; never touch other mail.
  - Only report on the watched people.
  - No false alarms: be strict. Anything unclear goes to "Possible move" rather than being called a confirmed job change.
  - Never treat missing or blank Clay data as a job change.
  - Posts older than 48 hours are ignored.
  - A post already reported is not reported again. Repeats should stop; the log shows when one was suppressed.
  - A single profile or post can produce both a post signal and a profile-change signal; show them together under the person's name.
- **Human-in-the-loop (added 2026-10-27):** outbound email to a person who has moved. The system drafts a congratulate-and-reach-out email from a template, shows it to the user, and sends only after the user edits it and clicks Send. This works on the history page now and in Slack later (an approve button on the alert). The recipient's address comes from Clay. Never send automatically; one email per signal.

## Output
- **Produces:**
  - **Slack direct message, once a day.** Each flagged item shows the person's name and company, a label (Job change or Possible move), what was seen (the post text, or "Company changed from A to B" / "Title changed from X to Y"), a "why this matters" line (e.g. "She's likely available now. Reach out this week."), and a link to the post or profile. "Possible move" items appear in a separate section.
    - Quiet day: a short "nothing today" message.
    - Broken-pipe day: if no LinkedIn emails arrive for 48 hours, a warning: "No LinkedIn emails received. Check your notification settings."
    - Clay problem: a line such as "Couldn't check Sarah's profile today."
    - Late run: the message says it is a late summary.
  - **A local history page (read-only), version 1.** A page that opens in the browser on the user's laptop only, showing history **by person**: current title and company, when they were last checked, and a timeline of every post seen and every profile change, with what the system decided and why (including skipped items). Its only actions are the manual refresh and the approved outreach email.
- **Consumer:** the user — Slack direct message to themselves, and the local page on their own laptop. No one else can see either.
- **Storage:**
  - A small local memory file (last-known title and company per person, date checked, posts already reported).
  - The log file (see Logging). The local page reads from the log and the memory file.
  - Both live in the project folder and are excluded from GitHub.

## Version Control
- **Repo:** GitHub (private by default). The user will create the repo later; set it up before or at the start of the build.
- **`.gitignore` must exclude:** `.env`, API keys, Slack access details, email login details, Clay access details, `logs/`, the local memory file, any local data files, any secrets
- **Commit cadence:** at least one commit per working milestone; push regularly
- **Why:** one rollback-able safety net is worth more than any other guardrail in early builds

## Logging (Phase 1 Guardrail)
- **Log location:** `logs/run.log` at project root
- **What gets logged:** run start and end times; every LinkedIn email looked at; every Clay lookup (with status); the decision made on each item (Job change, Possible move, or ignored) **with the reason, including for ignored items**; every Slack message sent (with success or failure); every AI call with status; every error with context; whether the run was on time or a late run
- **Format:** human-readable lines so a non-technical user can open the file and understand what happened. **Every line that concerns a person includes that person's name**, so the local history page can show things by person.
- **Why:** in version one, this is the single best tool for debugging when something goes wrong, and for tuning how strict the system is

## High-Stakes Actions & Approval Gates
**Outbound email to a watched person is gated.** The only action that contacts a candidate is the outreach email, and it requires the user to review the draft and click Send on the page (Slack approval later). The rest is read-only: it reads Clay data, sends a private Slack message to the user, and does not change anything on LinkedIn or edit records in Clay or elsewhere.

## System Edges
- **Edge 1:** The laptop is closed at 10 PM → the system runs when the laptop next opens, and the message is labeled as a late summary.
- **Edge 2:** LinkedIn stops sending emails (a notification gets turned off, or LinkedIn changes its email format) → if zero LinkedIn emails are found in 48 hours, send a warning ("No LinkedIn emails received. Check your notification settings.") instead of "quiet day," so a broken system doesn't look like a calm one.
- **Edge 3:** The AI can't decide about a post, or Slack fails to send → an undecided post is listed as "Possible move" and never silently dropped; a failed Slack send is retried once, then the failure is written to the log.
- **Edge 4:** A post is cut off in the email → the system judges only what it can see, and every flagged post links back to LinkedIn so the user can read the full text.
- **Edge 5:** Clay is down, out of credits, or returns blank data for someone → never treat blank data as a job change; skip that person's comparison for the day, say so in the Slack message ("Couldn't check Sarah's profile today"), and keep the posts path running.

## System Diagram
See `diagram.html` for the visual flow.

## Suggested Tech Stack (High-Level)
- A way to read the user's LinkedIn notification emails from their inbox
- Clay (named by the user) as the source of each person's current title and company, set up with the 5 people and refreshed daily
- An AI step that reads each post and labels it (Job change, Possible move, or ignore) and writes the "why this matters" line
- A Slack connection that sends a direct message to the user
- A daily scheduler on the user's laptop (10 PM Eastern), with catch-up when the laptop reopens
- A small local memory file and a plain-text log file
- A simple local page, read-only, that shows history by person
- A simple watchlist file (names, companies, profile links)

## Open Questions
- **Check Clay first:** before building, confirm in Clay what it returns for the 5 people (title, company), how fresh it is, whether it can be refreshed daily, how many credits each refresh costs, and whether it can return post text at all (if it can, the email path for posts could be dropped later).
- **How the system reads Clay:** confirm what the Clay connection exposes, and whether data is read from a Clay table or fetched directly.
- **Verify LinkedIn email behavior early:** confirm that bell notifications for each of the 5 people actually arrive as emails (not just in-app), and check what the emails contain, before building the filtering.
- **Strict vs. complete:** "no false alarms" means an unusually worded real announcement may be missed. Use the log's skipped-item reasons to tune this after a few weeks.
- **Spelling-only company differences:** decide how strictly to match company names (e.g. "Acme" vs. "Acme Inc.") once real data from Clay is visible.
- **First run:** the first time the system runs it has nothing saved to compare against. It should save today's values as the starting point and not report changes that day.
- **Laptop dependency:** the system and the local page only work when the laptop is on. If misses become frequent, consider a different place to run it. A password-protected online version of the history page was deliberately left for later (it would store candidate notes off the laptop).
- **History page views:** version 1 is by person. A day-by-day view of what each daily summary contained may be added later (not yet decided).
- **Scope for later versions:** "Open to Work" and anything else that needs a richer data source; other user types (AEs, VC/PE).
- **GitHub repo:** the user will create it later. Set it up before the first commit of real work.
- **Time zone:** 10 PM Eastern. Confirm how daylight saving and travel should be handled.
- **Slack is for alerts only, not the record:** the free Slack plan only keeps about the last 90 days of messages visible, so older alerts will disappear. The log file and the local history page are the source of truth. Use a free Slack workspace of your own (company workspaces often block custom apps), and check Slack's current free-plan terms before building.
