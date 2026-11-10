# Eventra AI

### *Your Smart Event Companion*

Eventra AI is an intelligent AI-powered event planning and management platform that helps users organize events efficiently with smart AI assistance.

## Project overview

Eventra AI is a web app where college students and organizers plan events with the help of AI: create events, get them approved,
track tasks, optimise the budget, pick a venue, spot risks, generate a proposal PDF, and ask a chatbot about the
college's own event rules (in English or Tamil).

Built with **Python, Flask (Blueprints), SQLite, ChromaDB (RAG), the Groq API, ReportLab and plain HTML/CSS/JavaScript**.

---

## Branding

| | |
|---|---|
| **Name** | Eventra AI |
| **Tagline** | Your Smart Event Companion |
| **Logo** | An "E" mark with a spark on an indigo → violet → cyan tile (`#i-eventra` in `app/templates/partials/icons.html`, favicon in `app/static/img/favicon.svg`) |
| **Colours** | Indigo `#6366f1`, violet `#8b5cf6`, cyan `#06b6d4` on a deep navy sidebar (design tokens at the top of `app/static/css/design-system.css`) |
| **Typography** | Inter (falls back to Segoe UI / system fonts); wordmark in extra-bold with a gradient "AI" |

The name appears in the browser tab title, sidebar and mobile top bar, login/register/reset pages, About page, footer,
password-reset emails and PDF footers. Technical identifiers (the `eventai.db` file name, environment variable names, routes and API endpoints) were
deliberately **not** renamed, so existing data and deployments keep working.

**Suggested GitHub repository settings**
- *Name:* `eventra-ai`
- *About / description:* Eventra AI is an intelligent AI-powered event planning and management platform that helps users organize events efficiently with smart AI assistance.
- *Short tagline for the website field or social preview:* Your Smart Event Companion
- *Topics:* `eventra-ai` `event-management` `event-planning` `ai-assistant` `flask` `python` `rag` `chromadb` `groq` `llm` `sqlite`

---

## Contents
1. [Features](#1-features)
2. [Tech stack](#2-tech-stack)
3. [Architecture](#3-architecture)
4. [Project structure](#4-project-structure)
5. [Installation](#5-installation)
6. [Environment variables](#6-environment-variables)
7. [Database](#7-database)
8. [Run the app](#8-run-the-app)
9. [Testing](#9-testing)
10. [Deploy to Render](#10-deploy-to-render)
11. [Security](#11-security)
12. [How the main rules work](#12-how-the-main-rules-work)
13. [Routes](#13-routes)
14. [What has and has not been verified](#14-what-has-and-has-not-been-verified)
15. [Known limits and next steps](#15-known-limits-and-next-steps)

---

## 1. Features

**Accounts and roles**
- Register, log in, log out, forgot/reset password, profile (name, department, language), change password.
- Three roles with separate dashboards and navigation: **student**, **organizer** (both chosen at sign-up) and **admin**. Admins have their **own sign-in page (`/admin/login`)** and console (`/admin/dashboard`). They are created by the `seed-admin` command (credentials from environment variables), the one-time start-up setting in section 6, or by another admin; **never** from the public sign-up form, which offers only Student and Event organizer.

**Student dashboard** – browse approved events · search and filter (text, type, date range, seats available, include past) · event details with schedule · register / cancel (duplicates and full events are refused) · My Registered Events · calendar of approved events · AI Event Assistant (answers "what events are coming up?" from the real database, and college-rule questions from the RAG knowledge base, English or Tamil) · notifications inbox · profile.

**Organizer dashboard** – create, edit and delete own events · submit for admin approval · **approval tracker** (draft / pending / approved / rejected counts) with the admin's rejection reason and a "correct and resubmit" link · tasks · AI schedule generator, AI budget planner, AI venue recommendations, risk analysis and proposal PDF · registered students per event (table, CSV export, send an update to them) · event analytics and PDF reports.

**Admin console** (sidebar: Overview · Event Approvals · All Events · Students · Organizers · Venues · Activity Logs · Log out) – Overview with Total Students, Total Organizers, Total Events, Pending Approvals, Approved and Rejected Events · **Event Approvals** with Pending / Approved / Rejected tabs, full event details and organizer information, Approve, or Reject with a required reason, and a per-event review history · All Events (search, filter, paging) · student, organizer and admin account management (create accounts, change roles, activate/deactivate) · venue management · activity logs with search and paging.

**Event approval workflow**
`draft → pending → approved | rejected`. The organizer submits; an admin (never the owner, and never an admin assigned to one of its tasks) approves or rejects; a rejection needs a reason and returns the event to the organizer, who corrects and resubmits. Only **approved** events are visible to students. Editing an approved event sends it back to pending (hidden from students until re-approved; already-registered students are told when it is re-approved).

**Notifications** – admins get every new approval request; organizers get approval / rejection (with the reason); students get registration confirmations, cancellations, organizer updates, re-approval, completion and event-cancelled notices. A badge in the sidebar shows unread items.

**Events**
- Dashboard with totals, upcoming events, pending tasks and a recent-activity feed; event detail page with schedule and tasks; calendar view.
- Tasks with assignee (organizers and admins), deadline and status (to do / in progress / done); search and filter on events and tasks.

**AI tools** (all need a Groq API key)
| Tool | What it does |
|---|---|
| Event planner | Objectives, arrangements, equipment, team roles, expense estimate, preparation steps |
| Name generator, description writer | Event names with taglines; poster-ready descriptions |
| Schedule and checklist | Time-ordered schedule; before / during / after checklist |
| Permission letter | Formal letter to principal, HOD, etc. (uses only the facts you give) |
| **Budget optimizer** | Splits the budget over venue, food, decoration, equipment, guests, transport and an emergency reserve. You can edit every amount; totals and remaining budget are calculated by Python, not the AI |
| **Venue recommendation** | Ranks venues from the college's own list by capacity, cost and facilities. It never invents venues and never claims a venue is free (availability is not tracked) |
| **Risk analysis** | Rule-based warnings from your saved data plus AI-written risks with prevention steps |
| **Improvement suggestions** | Ideas to raise the quality of the event |
| **Proposal generator** | Cover page, introduction, objectives, description, participants, schedule, budget, resources, committee, outcomes, as a **PDF**. Schedule and budget come from your saved data |

**Other**
- **AI Assistant (RAG chatbot)** answers from the college policy files in `data/`. If nothing relevant is found it says so instead of guessing. English and Tamil, chat history, copy, retry, clear, suggested questions.
- **Budget calculator** (the original tool) and an **Event Policies** page built from the same files the chatbot reads.
- **Analytics** by year: totals, events per month, budget per month, categories, status split, budget vs saved breakdown, plus a PDF report for the year and a PDF report per event.
- **Look and feel:** dark/light mode, Tamil/English interface, responsive layout, toasts, confirm dialogs, loading animations, inline form validation, friendly error pages.

---

## 2. Tech stack

| Area | Choice | Why |
|---|---|---|
| Backend | Python 3.12, Flask 3, Blueprints, app factory | Simple, explicit, easy to explain |
| Database | SQLite through Python's `sqlite3`, numbered SQL migrations | Zero setup; every query uses `?` placeholders (no SQL injection); easy to move to PostgreSQL later |
| AI | Groq API (Llama models) | Fast and free tier available |
| Chatbot memory | ChromaDB (local vector store) + RAG | Answers come from your own documents |
| PDF | ReportLab | Pure Python, no external service |
| Frontend | HTML, CSS design system, vanilla JavaScript, Chart.js (CDN) | No build step, no React |
| Tests | pytest | 300+ tests, AI calls mocked |
| Hosting | Gunicorn on Render | See section 10 |

> **Why not SQLAlchemy / Flask-Login / Flask-WTF?** They could not be installed in the environment this project was built in
> (no network), so the same jobs are done with the standard library and Werkzeug: `sqlite3`, signed cookie sessions and a
> small CSRF check. The code is isolated in `app/db.py`, `app/security.py` and `app/models/`, so swapping them is possible later.

---

## 3. Architecture

```
 Browser (HTML + CSS + JS, Chart.js)
      │   pages (Jinja templates)            JSON (fetch, with CSRF header)
      ▼
 Flask app  ── before_request: login gate + CSRF check ── after_request: security headers
      │
      ├── Blueprints (HTTP only: read input, call a service, return a page or JSON)
      │     auth · main · events · tasks · chat · budget · ai · planning · analytics · admin
      │
      ├── Services (the rules and the AI)
      │     events_logic   who may do what, status flow
      │     validation     every input is cleaned and range-checked
      │     insights       deterministic maths: budget split, venue scoring, risk rules
      │     ai_features    build prompt → call Groq → validate the answer → shape it
      │     prompts, llm   all prompt text; one Groq wrapper with error translation
      │     rag            ChromaDB search, relevance cut-off, "not enough information" guard
      │     pdf, proposal  ReportLab documents
      │
      └── Models (SQL only)  users · tokens · events · registrations · notifications · tasks · activity · planning · analytics
               │
          SQLite file (instance/eventai.db)         ChromaDB folder (chroma_db/)
```

**The key design rule:** the AI writes words, Python does the facts. Totals, remaining budget, venue lists, schedule and
budget in the proposal, risk levels and permissions are all calculated or checked in Python, and anything the AI
returns is validated before it is shown (for example, a venue id the AI makes up is ignored). User text sent to the AI is
wrapped in `<user_input>` tags and the model is told it is data, not instructions.

---

## 4. Project structure

```
project18_event_assistant/
├── run.py                 entry point (python run.py / gunicorn run:app)
├── config.py              all settings, read from environment variables
├── seed_admin.py          creates the first admin from ADMIN_* environment variables
├── ingest.py              builds the chatbot knowledge base from data/*.txt
├── render.yaml            Render deployment blueprint     Dockerfile  Procfile  (other hosts)
├── requirements.txt       .env.example   .gitignore
├── data/                  policy documents the chatbot reads (3 are SAMPLES, replace them)
├── app/
│   ├── __init__.py        app factory, error pages, security headers, create-admin / seed-admin commands
│   ├── db.py              connection + migration runner      security.py   login gate, CSRF, sessions
│   ├── migrations/        001_users … 005_indexes.sql  (numbered, run once, backed up first)
│   ├── blueprints/        auth main events student notifications tasks chat budget ai planning analytics admin
│   ├── models/            SQL queries, one file per topic
│   ├── services/          rules, AI, RAG, PDF (see section 3)
│   ├── templates/         Jinja pages and partials
│   └── static/            css/design-system.css   js/*.js   img/favicon.svg
└── tests/                 pytest suite
```

---

## 5. Installation

You need **Python 3.12** (newer versions should work too) and a free **Groq API key** from https://console.groq.com.

**Windows (PowerShell)**
```powershell
cd project18_event_assistant
python -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked:  Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env              # then open .env and set SECRET_KEY and GROQ_API_KEY
```

**macOS / Linux**
```bash
cd project18_event_assistant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # then edit .env: SECRET_KEY and GROQ_API_KEY
```

Build the chatbot knowledge base (run again whenever you change files in `data/`):
```bash
python ingest.py
```
The first run downloads a small embedding model (about 80 MB), so it needs internet and a minute or two.

---

## 6. Environment variables

Settings live in `.env` (local) or in your host's dashboard (production). `.env.example` lists all of them with comments.
**Never put real keys in code, JavaScript, or Git.** `.env` is already in `.gitignore`, and the Groq key is only ever used on the server.

| Variable | Needed? | Meaning |
|---|---|---|
| `SECRET_KEY` | **yes** (required in production) | Signs login cookies. Make one: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GROQ_API_KEY` | yes for AI features | Your Groq key |
| `GROQ_MODEL`, `GROQ_MODEL_TAMIL` | no | Model names. If Groq retires a model, change it here |
| `APP_ENV` | no | `development` (default) or `production` |
| `APP_BASE_URL` | production | Public address, used in reset emails |
| `COLLEGE_NAME` | no | Printed on proposal covers |
| `DATABASE_PATH`, `CHROMA_DIR` | no | Where the SQLite file and vector store live |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` | no | Creates the first admin at start-up, only while no admin exists. Delete `ADMIN_PASSWORD` afterwards |
| `SMTP_*`, `MAIL_FROM` | no | Email for password resets. Without it, the reset link is printed in the terminal |
| `RAG_MAX_DISTANCE`, `RAG_TOP_K` | no | Chatbot relevance tuning (see troubleshooting) |
| `MAX_FAILED_LOGINS`, `LOCKOUT_SECONDS`, `RESET_TOKEN_MINUTES`, `TRUST_PROXY` | no | Security tuning |

---

## 7. Database

SQLite, created automatically at `instance/eventai.db` the first time the app starts. (The file name `eventai.db` is a technical name kept from the old project name so existing databases keep working; you never see it in the app.)

**Migrations** are numbered SQL files in `app/migrations/`; each one runs once and the version is stored in the database (`PRAGMA user_version`). To add a change, add `006_something.sql`. There is nothing to run by hand. They are built to protect existing data:
- Before an existing database is upgraded, a consistent copy is written next to it as `eventai.db.pre-v<N>.bak`.
- Each migration runs in **one transaction** with its version bump; if any statement fails the whole step is rolled back and the database stays as it was.
- Migrations only add tables, columns and indexes. No user or event is deleted. (One data fix: students who already owned events are promoted to *organizer*, so they keep control of what they created.)

| Version | What it adds |
|---|---|
| 001 | `users`, `password_reset_tokens` |
| 002 | `events`, `event_schedule_items`, `tasks`, `activities` |
| 003 | `venues`, `event_budget_items`, `ai_results`, `proposals` |
| 004 | approval audit columns on `events` (`submitted_at`, `reviewed_by`, `reviewed_at`), `registrations`, `notifications` |
| 005 | indexes for the approval queue, browsing, activity log |

Main tables: `users`, `events`, `registrations` (unique per event + student, so duplicates are impossible), `notifications`, `tasks`, `activities`, `venues`, `event_schedule_items`, `event_budget_items`, `ai_results`, `proposals`, `password_reset_tokens`. Foreign keys are enforced (`PRAGMA foreign_keys = ON`).

**Back up:** copy `instance/eventai.db` while the app is stopped. **Start fresh:** delete the `instance/` folder.
**Moving to PostgreSQL later:** queries are plain SQL with placeholders in `app/models/`, and the migrations are SQL, so the change is mostly the connection code in `app/db.py` and a few SQLite-specific bits (`PRAGMA`, `COLLATE NOCASE`, `AUTOINCREMENT`).

---

## 8. Run the app

```bash
python run.py                       # http://127.0.0.1:5000
```
Create your first admin (the website cannot do this). Credentials come from environment variables; there is no default account or password:
```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='a-long-passphrase-1' ADMIN_NAME='Your Name' flask --app run seed-admin
# or:  python seed_admin.py        (same thing; reads ADMIN_* from the environment or .env)
# add --promote to turn an existing student/organizer account into an admin (its password is not changed)
flask --app run create-admin        # alternative: asks for email, name and password interactively
```
Then open **`/admin/login`** (the public `/login` page refuses admin accounts), and remove `ADMIN_PASSWORD` from your environment. Admin passwords need at least 10 characters, a letter and a number. Further admins are created by an existing admin under *Admin Accounts*.

Useful things to know:
- **Venues:** *Admin → Venues* holds the list used by venue recommendations. The two starter venues have no facilities listed; add the real ones.
- **Password reset without SMTP:** the reset link appears in the terminal where the app runs.
- **Production-style run:** `APP_ENV=production SECRET_KEY=... gunicorn run:app --workers 1 --threads 4 --timeout 120`

---

## 9. Testing

```bash
python -m pytest -q
```
The suite (490+ tests) covers login and permission rules for all three roles, CSRF, input validation, the full approval workflow, registrations (duplicates, capacity, a concurrent-registration race, cancel and re-register), notifications, migrations (legacy upgrade, backup, rollback), role-policy coverage of every route, a no-crash sweep of every page for every role, every AI endpoint
(with the AI **mocked**, so it needs no key and no internet), venue scoring, budget maths, PDF generation, analytics numbers,
error pages, and production settings. Tests use a temporary database each time and never touch your real data.

**Smoke test with the real AI (5 minutes, on your machine):**
1. `python ingest.py`, then `python run.py`.
2. Assistant → ask "What is the Auditorium capacity?" (should answer 300 and cite a source). Ask something unrelated; it should say it has not enough information.
3. Switch to தமிழ் and ask a question in Tamil.
4. Create an event, open **AI tools**, and try each tab. Save a budget breakdown, then generate a proposal and download the PDF.
5. Analytics → check the charts load (needs internet for Chart.js).

---

## 10. Deploy to Render

1. Push the project to a **private** GitHub repository. Check that `.env` is **not** in it (`git status` should not list it).
2. On https://render.com choose **New → Blueprint**, pick the repository. Render reads `render.yaml` (service name `eventra-ai`, so the default address is `https://eventra-ai.onrender.com` if that name is free).
3. When asked, fill in: `GROQ_API_KEY`, `APP_BASE_URL` (your future `https://<name>.onrender.com`), optionally `COLLEGE_NAME`, and
   `ADMIN_EMAIL` + `ADMIN_PASSWORD` for the first admin. `SECRET_KEY` is generated for you.
4. Deploy. The build installs packages and runs `python ingest.py`; the health check is `/healthz`.
5. Open `/admin/login`, sign in with the admin email and password, then **delete `ADMIN_PASSWORD`** in the Render dashboard.

Things to know before you rely on it:
- **Free plan forgets data.** The free plan has no permanent disk: the SQLite database is reset on every redeploy or restart, and the service sleeps when idle. Fine for a demo. For real use, use a paid plan with a disk (uncomment the `disk:` and the two path variables in `render.yaml`), or move to PostgreSQL.
- **Memory.** ChromaDB and its embedding model are heavy. If the free 512 MB instance runs out of memory, use a larger plan.
- **One worker.** The start command uses one Gunicorn worker on purpose (login-lockout counters are kept in memory and SQLite allows one writer). It uses threads to serve several people at once.
- The app trusts Render's proxy headers (`TRUST_PROXY`), sets secure cookies and HSTS in production, and refuses to start in production without `SECRET_KEY`.
- Without SMTP, password-reset links are only written to the server log. Set `SMTP_*` for real emails.

### Docker (any host)
```bash
docker build -t eventra-ai .
docker run -p 8000:8000 -v eventra-data:/data \
  -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  -e GROQ_API_KEY=your_key -e ADMIN_EMAIL=you@example.com -e ADMIN_PASSWORD='a-long-passphrase-1' eventra-ai
```
Open http://localhost:8000. A `Procfile` is included for Heroku-style hosts. Upgrading an old deployment: just deploy the new version; the database is migrated automatically and a `.pre-v<N>.bak` copy is written first.

---

## 11. Security

- **Passwords:** hashed with scrypt (Werkzeug); 8+ characters with a letter and a digit; never logged.
- **Sessions:** signed cookies, `HttpOnly`, `SameSite=Lax`, `Secure` in production; the session is cleared on login (no fixation); changing a password or deactivating an account signs out other sessions.
- **Login protection:** 5 wrong tries per email+IP lock that pair for 10 minutes; error messages never say whether the email exists.
- **Password reset:** one-time tokens stored only as SHA-256 hashes, expire in 30 minutes.
- **CSRF:** every POST needs a token (form field or `X-CSRF-Token` header).
- **Role-based access control (backend):** every page and API requires login except login/register/reset and `/healthz`. `app/security.py` holds one policy table (blueprint → allowed roles) checked in `before_request` for **every** request, and anything not listed is **denied by default**. Students reach only the student area, organizers the organizer area, admins the admin area; the admin routes also carry `@role_required("admin")`. A test fails if any route has no policy. Hiding a menu item is never the only protection.
- **Ownership:** organizers can open, edit, delete and see registrations of their own events only (others answer 404). Nobody, including an admin, can approve or reject their own event or one they are assigned a task on. Admin sign-in has its own login-lockout counter, and student/organizer credentials never open an admin session. Students see only approved events (drafts, pending and rejected answer 404).
- **Registrations:** the capacity check and insert happen in one `BEGIN IMMEDIATE` transaction, with a UNIQUE constraint as a second guard; a concurrency test confirms the limit holds. CSV exports neutralise spreadsheet formulas (`=`, `+`, `-`, `@`).
- **SQL injection:** all queries use `?` placeholders. **XSS:** templates escape output and JavaScript builds the page with safe text nodes.
- **Open redirects** after login are blocked. **Headers:** `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS.
- **Secrets:** only in environment variables; the Groq key never reaches the browser. A test fails if a key-like string appears in static files.
- **AI safety:** user text is fenced in `<user_input>` tags; AI output is validated; the AI never does the arithmetic or decides permissions.

Not included (worth adding for a large deployment): a Content-Security-Policy header, a shared (not in-memory) rate limiter, email verification, and audit exports.

---

## 12. How the main rules work

- **Event status:** `draft → pending` (owner submits) `→ approved / rejected` (an admin, never the owner) `→ completed`. Editing an approved event sends it back to pending; editing a rejected one back to draft. Pending and completed events are locked.
- **Registration:** only students, only for approved events that have not happened yet, once per student, while seats remain. Cancelling frees the seat; registering again re-uses the same row. An organizer cannot lower the capacity below the number of students already registered.
- **Tasks:** belong to the organizing team; they can only be assigned to organizers or admins.
- **Venue recommendation:** venues that cannot hold the participants are removed first. The rest are scored: 40% facilities matched, 35% low cost relative to your budget, 25% how well the hall is filled. The AI only ranks and explains.
- **Budget optimizer:** the AI gives percentages; Python scales them to at most 100%, converts to rupees and calculates total and remaining.
- **Risk level:** computed from the rule-based warnings and the AI risks' likelihood × impact.
- **Chatbot:** the question is searched in ChromaDB; chunks beyond `RAG_MAX_DISTANCE` are ignored; if nothing remains, the bot says it has not enough information and the AI is not called.

---

## 13. Routes

Pages (GET), grouped by who may open them:

| Role | Pages |
|---|---|
| everyone logged in | `/` (role dashboard) · `/calendar` · `/assistant` · `/notifications` · `/policies` · `/about` · `/profile` |
| student | `/browse` · `/browse/<id>` · `/my-registrations` (POST: `/browse/<id>/register`, `/registrations/<id>/cancel`) |
| organizer (and admin) | `/events`, `/events/new`, `/events/<id>`, `/events/<id>/edit`, `/events/<id>/registrations` (+ `.csv`, POST `/announce`) · `/tasks` · `/ai-studio` · `/events/<id>/ai` · `/budget` · `/analytics` |
| admin | `/admin/login` (public sign-in form) · `/admin/dashboard` · `/admin/event-approvals` · `/admin/events` (+ `/admin/events/<id>`) · POST `/admin/events/<id>/approve` and `/reject` · `/admin/students` · `/admin/organizers` · `/admin/admins` · `/admin/users` · `/admin/venues` · `/admin/activity-logs` · POST `/admin/logout` (`/admin/approvals` and `/admin/activity` still work) |
| public | `/login`, `/register`, `/forgot-password`, `/reset-password/<token>` · `/healthz` |

Workflow actions (POST, `/events/<id>/status`, field `action`): `submit`, `withdraw`, `complete` (owner) · `approve`, `reject` + `note` (an admin who is not the owner or a task assignee of the event). Admins normally use the dedicated POST routes `/admin/events/<id>/approve` and `/admin/events/<id>/reject`, which apply the same rules.

Downloads – `/events/<id>/proposal.pdf` · `/events/<id>/report.pdf` · `/analytics/report.pdf?year=YYYY`

JSON API (POST, login + CSRF required):

| Endpoint | Purpose |
|---|---|
| `/api/chat` | RAG chatbot |
| `/api/budget` | Budget calculator |
| `/api/ai/plan` `names` `description` `schedule` `checklist` `letter` `budget` | AI Studio tools |
| `/api/events/<id>/ai/budget` `venues` `risks` `improve` `proposal` | Per-event AI tools (owner only) |
| `/api/events/<id>/budget` | Save the budget breakdown |
| `/api/events/<id>/schedule`, `/tasks/bulk` | Save schedule, add several tasks |

Errors on `/api/...` are JSON `{"error": "..."}`; page errors show a friendly HTML page.

---

## 14. What has and has not been verified

**Verified (automated tests + Chromium walkthroughs at desktop and phone width):** all permission rules for student / organizer / admin, the complete approval workflow including rejection reasons, resubmission and re-approval, registrations (duplicate, capacity, concurrent race, cancel), notifications for all four recipients, schema migrations on a legacy database (data kept, backup written, failed migration rolled back), CSRF, validation, every page for every role (no server errors), existing AI endpoints (with the AI **mocked**), PDFs, analytics, dark mode, Tamil/English switching.

**Not verified here – please check on your machine:**
- Real calls to the **Groq API** (the build environment had no network or `groq` package, so AI features were tested with mocks, as before).
- The real **ChromaDB** ingest and search, and whether `RAG_MAX_DISTANCE=1.0` suits your documents.
- **Chart.js** drawing real charts from the CDN.
- The exact **`gunicorn run:app ...`** command and an actual **Render** / Docker deployment.
- Python 3.12 specifically (development and tests ran on 3.13).

---

## 15. Known limits and next steps

- Chat history is stored in the browser, not on the server.
- Venue **availability** is not tracked, so it is never claimed.
- Proposal and report PDFs are English only and write money as "Rs." (the built-in PDF fonts have no ₹ or Tamil letters; bundling a Unicode font would fix this).
- There is no "actual spending" field, so analytics compares the estimated budget with the saved breakdown.
- Notifications are in-app only (no email); there is no waiting list when an event is full.
- Ideas: PostgreSQL, a shared rate limiter, email notifications, waiting lists, approval comments, a CSP header, uploading a college logo for proposals.

**Sample policies:** `data/guest_speaker_guidelines.txt`, `sponsorship_rules.txt` and `safety_and_volunteers.txt` are marked SAMPLE.
Replace them with your college's real rules and run `python ingest.py` again.
