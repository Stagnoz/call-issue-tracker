# Call Issue Tracker

An internal web application for the team that reviews calls handled by an AI phone
assistant for medical clinics. When a reviewer finds a call where the assistant got
something wrong (a wrong booking, a wrong answer, a missed transfer to a human, a
misidentified patient, a technical failure), they record an issue against the call,
mark it resolved once it is fixed, and use the dashboard to see where problems
concentrate. The interface is available in English and Italian.

## Quick start

Requirements: Git and Docker (with Compose).

```bash
git clone https://github.com/Stagnoz/call-issue-tracker.git
cd call-issue-tracker
docker compose up
```

Open <http://localhost:8000>. On first start the database is empty, so 44 demo issues
across six fictional clinics are loaded automatically. No `.env` file or other setup
is needed.

## Using the app

- **Issues** (`/issues`): every issue, newest first, 25 per page. Search the
  description and call ID, filter by clinic, category, status and severity. Filters
  combine (AND) and live in the URL, so a filtered view can be bookmarked or shared.
  **Clear filters** resets them, and **Export CSV** downloads the filtered list.
- **Mark as resolved**: each open issue has a button that opens a small form with an
  optional "What was fixed?" note. Resolved issues show the time, the note and a
  **Reopen** button. You stay on the same filtered list.
- **Delete**: every issue has a Delete button that asks why (for example a duplicate
  or an issue created by mistake). The issue disappears from the list, the filters,
  the CSV and the dashboard, and the confirmation has an **Undo** button. Nothing is
  removed from the database (soft delete).
- **New issue** (`/issues/new`): call ID, clinic (pick an existing one or type a new
  name), category, severity and description. Invalid input is shown next to the
  field, with what you typed preserved.
- **Dashboard** (`/dashboard`), in two parts. **Right now** is the open backlog,
  whatever the period: open and open critical or high counts, the five oldest open
  critical/high issues with how long they have been open, and open issues by
  severity and by age. The **period** part (last 7, 30 or 90 days, or all time, the
  default) shows new and resolved issues with the change against the previous
  period, the median time to resolution, issues created per day, and issues by
  category and by clinic, each bar split into open and resolved. Bars link to the
  matching list (the list itself has no date filter).
- **EN / IT** in the top bar switches the interface language.
- **API docs** (`/docs`): interactive documentation of the JSON API.

## Configuration

All variables are optional. `docker-compose.yml` sets the values in the "Compose"
column, and `.env.example` lists them with a short explanation.

| Variable | Default in the app | Compose | Meaning |
|---|---|---|---|
| `DATABASE_URL` | `sqlite:///./issues.db` | `sqlite:////data/issues.db` | SQLAlchemy URL of the database. In Docker the file lives on the `issue-data` volume. |
| `SEED_ON_STARTUP` | `false` | `true` | Load the demo issues at startup, only if the database has no issues. |
| `APP_TIMEZONE` | `Europe/Rome` | `Europe/Rome` | IANA timezone used to display dates and group issues by day. Data is always stored in UTC. |

An invalid `SEED_ON_STARTUP` value or an unknown timezone stops the app at startup
with a clear error, rather than failing later.

## Architecture

```
Browser ──HTTP──▶ FastAPI (uvicorn, 1 worker)
                   ├─ routes/web.py  HTML pages (Jinja templates, plain forms)
                   └─ routes/api.py  JSON API under /api, /health, /docs
                            │
                            ▼
                   services.py  all queries and business rules
                            │
                            ▼
                   SQLAlchemy 2 ──▶ SQLite file on the issue-data Docker volume
```

Both the HTML pages and the JSON API validate input with the same Pydantic schemas
and call the same service functions, so they cannot behave differently.

```
app/
  main.py            create_app(): builds the app, creates tables, auto-seeds
  config.py          settings from environment variables
  db.py              engine, sessions, UTC datetime column type
  models.py          Clinic and Issue tables, Category/Severity/Status enums
  schemas.py         Pydantic input validation and API output models
  services.py        every query and rule: create, list, resolve, reopen, delete, stats
  routes/api.py      JSON API, /health and self-hosted /docs
  routes/web.py      HTML pages, language switch and CSV export
  i18n.py            English and Italian UI text, date and duration formatting
  seed.py            44 hand-written demo issues; python -m app.seed
  templates/         Jinja templates (layout, list, form, dashboard, 404)
  static/style.css   the only stylesheet, hand-written
  static/swagger-ui/ Swagger UI 5.33.0 files, so /docs works offline
tests/               pytest suite, one file per area
.github/workflows/   CI: lint and tests, then a Docker smoke test
Dockerfile           python:3.12 slim image, non-root user, one uvicorn worker
docker-compose.yml   the single app service, port 8000, issue-data volume
```

## Data model

**clinics**: `id`, `name` (as displayed), `name_key` (unique: trimmed, inner spaces
collapsed, case-folded).

**issues**:

| Field | Type | Notes |
|---|---|---|
| `id` | integer | primary key |
| `call_id` | text, 1-100 | not unique: one call can have several issues. Letters, digits and `- _ . :` only. |
| `clinic_id` | foreign key | the API and UI use the clinic name |
| `description` | text, 5-2000 | |
| `category` | enum | `booking`, `information`, `forwarding`, `patient_identification`, `technical`, `other` |
| `severity` | enum | `low`, `medium`, `high`, `critical` |
| `status` | enum | `open`, `resolved`; new issues are always open |
| `created_at` | UTC datetime | set by the server, never by the client |
| `resolved_at` | UTC datetime, nullable | set when resolved, cleared on reopen |
| `resolution_note` | text, 0-500, nullable | optional "what was fixed" |
| `deleted_at` | UTC datetime, nullable | set when deleted, cleared on restore; deleted issues are hidden everywhere |
| `deletion_reason` | text, 3-500, nullable | required when deleting |

Enums are stored as text with a `CHECK` constraint, so the database itself rejects
invalid values.

**Severity levels**, from the point of view of the patient and the clinic:

- **critical**: a patient could be harmed or was seriously misinformed. Examples:
  urgent symptoms not escalated to staff, preparation for a contrast exam omitted,
  another patient's appointment read out to the caller.
- **high**: a real failure without immediate risk. Examples: a booking lost or
  confirmed in a taken slot, a transfer the caller explicitly asked for never
  happened, the call dropped in the middle of a booking.
- **medium**: wrong but recoverable, causing rework for the caller or staff.
  Examples: wrong practitioner or opening hours, repeated questions, a slot moved
  manually.
- **low**: cosmetic or wording. Examples: mispronounced names, awkward date phrasing.

**Why a clinics table.** With a free-text clinic field, "Centro Medico X" and
"centro medico x " would become two clinics and split the "issues by clinic" chart.
A separate table with a unique normalized key makes that impossible at the database
level. The API still uses the clinic name, and typing a new name creates the clinic.

**Patient data.** Health data is a special category under the GDPR, and this tool has
no reason to store it. The form tells reviewers not to include patient names, phone
numbers or health details and to reference the call by `call_id`. The server enforces
part of this: text that looks like a phone number, an email address or an Italian tax
code (codice fiscale) is rejected in every free-text field. Names cannot be detected
reliably this way; see future improvements.

**Other input checks.** Every text field is trimmed and length-checked; control and
invisible characters (zero-width spaces, direction overrides) are rejected; clinic
names allow letters (accents included), digits, spaces and `. , ' - ( ) & /`.

## API

Interactive documentation: <http://localhost:8000/docs>. Invalid input returns 422
with the list of errors. The API is always in English.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/issues` | Create an issue. Body: `call_id`, `clinic`, `description`, `category`, `severity`. Sending `status`, `created_at` or unknown fields returns 422. |
| `GET` | `/api/issues` | List, newest first. Query: `q`, `clinic`, `category`, `status`, `severity`, `page` (25 per page). Returns `items`, `total`, `page`, `per_page`, `pages`. |
| `GET` | `/api/issues/{id}` | One issue, or 404. |
| `POST` | `/api/issues/{id}/resolve` | Resolve. Optional body `{"note": "..."}`. Idempotent: a second call changes nothing. |
| `POST` | `/api/issues/{id}/reopen` | Back to open; clears `resolved_at` and the note. Idempotent. |
| `POST` | `/api/issues/{id}/delete` | Soft delete. Required body `{"reason": "..."}`; returns 204. The issue is hidden (GET returns 404) but kept. Idempotent: the first reason is kept. |
| `POST` | `/api/issues/{id}/restore` | Undo a delete; the issue comes back unchanged. Idempotent. |
| `GET` | `/api/stats` | Dashboard numbers. Query: `period` = `7`, `30`, `90` or `all` (default). |
| `GET` | `/health` | `{"status": "ok"}` after a `SELECT 1`; 503 if the database is unreachable. |

HTML-only routes: `/issues`, `/issues/new`, `/issues.csv`, `/dashboard`, and the
`POST` form targets `/issues`, `/issues/{id}/resolve`, `/issues/{id}/reopen`,
`/issues/{id}/delete`, `/issues/{id}/restore`, `/language`.

Example:

```bash
curl -X POST http://localhost:8000/api/issues -H "Content-Type: application/json" \
  -d '{"call_id": "call-1234", "clinic": "Studio Dentistico Lago - Como", "description": "Assistant booked a cleaning with the orthodontist.", "category": "booking", "severity": "medium"}'
curl -X POST http://localhost:8000/api/issues/45/resolve -H "Content-Type: application/json" \
  -d '{"note": "Service mapping fixed."}'
```

## Seed data

`app/seed.py` holds 44 hand-written issues across six invented clinics (any match with
a real clinic is unintended). The distribution is deliberately uneven so the dashboard
tells a story: one clinic is noisier (14 issues) and booking and information are the
most frequent categories. Every category and severity is present, 26 issues are open
and 18 resolved (each with a note), and dates are spread over the last 60 days. Call
IDs come from `random.Random(42)`, so the same seed always produces the same data.

- **Automatic:** with `SEED_ON_STARTUP=true` (the Compose default), the demo data is
  loaded at startup if, and only if, the database has no issues. It never seeds twice
  and never touches a database with data.
- **Manual:** `docker compose exec app python -m app.seed` (prints what it did; does
  nothing on a non-empty database).
- **Reset:** `docker compose down -v` deletes the `issue-data` volume and all data;
  the next `docker compose up` starts empty and seeds again.

## Tests and CI

Run locally without Docker (Python 3.12):

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
```

(On Windows use `py -3.12 -m venv .venv` and `.venv\Scripts\` instead of `.venv/bin/`.)

With Docker only: `docker compose up -d --build`, then follow the steps of the smoke
test below by hand, or read them in `.github/workflows/ci.yml`.

Each test builds its own app on a temporary SQLite file, never the real database, and
anything time-related uses a fixed "now". The suite covers creation and validation
(including the input checks), ordering and pagination, each filter and their
combinations, search, resolve/reopen and notes, delete/restore (deleted issues left
out of every list and number), all dashboard numbers, CSV export,
seeding, persistence across a new engine and a new app instance, the HTML pages and
forms (including escaping of `<script>` in descriptions and redirect safety), and the
Italian interface.

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request to `main` and
every push to `develop`:

1. **Lint and tests**: `ruff check`, `ruff format --check`, `pytest`.
2. **Docker smoke test** (after 1): `docker compose up -d --build` with no `.env`, waits
   for `/health`, checks that the demo data loaded, creates and resolves an issue
   through the API and one through the HTML form, checks that the pages render, then
   restarts the containers and also removes and re-creates them, checking each time
   that the data is still there and was not seeded twice. It proves the Definition of
   Done (clone, `docker compose up`, use it, data persists) on a clean machine.

## Design decisions and trade-offs

- **SQLite instead of Postgres.** One file on a volume, no second service, enough for
  an internal tool with a handful of concurrent users. SQLite allows one writer at a
  time, so uvicorn runs **one worker** (sync endpoints still run in a thread pool).
  With many concurrent writers I would move to Postgres.
- **Server-rendered HTML instead of a SPA.** Jinja templates and plain forms: no build
  step, no Node, one language, and the pages use no JavaScript at all (only the
  `/docs` page does, for Swagger UI). Charts are CSS bars rendered on the server. No external resources are
  loaded: no CDN, no web fonts, and Swagger UI is shipped with the app, so it all
  works offline.
- **`create_all()` instead of migrations.** Tables are created at startup if missing.
  It does not alter existing tables: adding `resolution_note` and the delete columns
  during development meant resetting the local database. Before production I would
  add Alembic.
- **Soft delete instead of removing rows.** Deleting keeps the row with a required
  reason and hides it everywhere, so a mistaken delete can be undone and the history
  of what was recorded is not lost. It is a `POST .../delete` action rather than an
  HTTP `DELETE`, so the reason travels in a body and not in the URL.
- **Resolve as `POST /api/issues/{id}/resolve`, not a generic `PATCH`.** HTML forms
  can only send GET and POST, and resolving is an action with a rule (set
  `resolved_at` once, idempotent) rather than an arbitrary field update. State never
  changes on GET.
- **Server-controlled fields are rejected, not ignored.** A client sending `status` or
  `created_at` gets a 422, which surfaces client bugs early.
- **No authentication**, as the brief says. It also means there is no CSRF
  protection on the forms, which I would add together with login.
- **Patient-data hint plus server checks**, explained under Data model.
- **The Docker smoke test** is the most important CI job: it exercises exactly what a
  reviewer does after cloning.
- **Italian interface** from a hand-written dictionary (about 100 strings) rather than
  gettext: no extra dependency or compile step at this size. Stored data, the CSV and
  the JSON API are not translated.

## Future improvements

The next step is daily internal use: more people, more data, and issues arriving from
the systems around the assistant rather than only by hand.

**More users**

- Company SSO and roles, with `created_by` / `resolved_by` on each issue and CSRF
  tokens on forms.
- An audit log of every change. Editing issues, assignees and comments come after it,
  so the history of an issue can never be rewritten silently.

**Scale**

- Postgres with Alembic migrations, then several workers or instances behind a proxy.
- Indexes on `created_at` and the filtered columns, cursor-based pagination, and
  Unicode-aware search (SQLite folds case for ASCII letters only).

**Integration with existing systems**

- The call pipeline creates issues through the API, with a per-service key and
  deduplication by `call_id`.
- Each issue links to the call recording or transcript and to the assistant or prompt
  version, with a root-cause field (speech-to-text, LLM, text-to-speech, practice
  software integration, flow design). The dashboard then shows issues by cause and by
  release, so the team fixes the causes that produce the most issues first.
- Alerts for critical issues in the team chat, and optional sync with the ticketing tool.
- Patient data: automatic detection of names and health details (today only phone
  numbers, emails and tax codes), and a retention policy.

## How this was built

Built with Claude Code as a coding agent; I made and reviewed the decisions at each
step.
