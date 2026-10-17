# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A personal tracker for working through a year of CompTrain "2017 Open Athletes" CrossFit programming (371 days, W01 Monday … W53 Sunday). The user logs in, sees which workout is up next, reads it (with a Bulgarian explanation), and marks it done. Today there is one user (the owner); multi-user progress tracking is a planned future step, which is why progress is already stored per user.

The directory is not a git repository. Layout:

```
Comptrain_2017_Open_Athletes_.xlsx   source workbook (one-off extraction input)
data/W01..W53/{wods,desc}/*.md       workout text (EN) and descriptions (BG) — the content
app/
  main.py         FastAPI app: routes, auth dependency, template rendering
  content.py      loads data/ into an ordered list of Wod objects
  db.py           SQLite schema and queries (users, progress)
  security.py     scrypt password hashing, session signing key
  templates/      Jinja2: base, login, register, home, wod, history
  static/style.css
tests/test_app.py pytest + FastAPI TestClient, temp DB per test
instance/         runtime only: app.db, secret_key (created on first run)
requirements.txt  pinned deps (incl. pytest/httpx for tests)
```

## Commands

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload   # http://127.0.0.1:8000
.venv\Scripts\python -m pytest -q
```

Python 3.14 on Windows. No lint/format tooling is set up.

## The app

Stack: FastAPI, server-rendered Jinja2 templates, HTMX (`hx-boost` only, `htmx.org@2.0.4` vendored as `app/static/htmx.min.js`), stdlib `sqlite3` and `hashlib.scrypt`, `markdown` for rendering. No ORM, no JS build step; interactions are plain HTML forms that POST and redirect (303).

- **Content** — `app/content.py` loads every `data/W*/wods/*.md` plus its `desc/` twin once at import, sorted by week then file name, and pre-renders both to HTML. A workout's id is `W01/1-monday`, which is also its URL (`/wod/W01/1-monday`); unknown ids 404. Restart the server after editing `data/` (`--reload` only watches code).
- **Storage** — `app/db.py`, SQLite at `instance/app.db`, schema created on startup (`CREATE TABLE IF NOT EXISTS`, no migrations yet): `users` (`email` unique, lower-cased; `password_hash`) and `progress` (`user_id`, `wod_id`, `done_at` UTC; a row means done). Progress lives only here — the app never reads or writes the `done:` frontmatter.
- **Auth** — email + password, no email confirmation (a deliberate decision). `/register` (min 8-char password) is open only while there are no users, or when `ALLOW_REGISTRATION=1`, and never beyond `MAX_USERS` accounts (default 10); `/login`, POST `/logout`. Five failed logins for an email within 15 minutes lock it out (in memory, 429). Session is Starlette's signed cookie (`SameSite=Lax`, `Secure` when `SESSION_HTTPS_ONLY=1`) holding `user_id`; `current_user` dependency redirects to `/login` when missing. Signing key: `SECRET_KEY` env var, else generated once into `instance/secret_key`.
- **Hardening** — the `protect` middleware in `main.py` refuses cross-site POSTs (CSRF, via `Sec-Fetch-Site`, falling back to `Origin`) and adds security headers, including a CSP of `default-src 'self'`. So no inline scripts, inline styles or third-party URLs in templates: put JS in `app/static/app.js` (the Description toggle is a delegated `data-toggle` click handler there).
- **Pages**
  - `/` home: three cards, each wholly clickable (hover/tap highlights it) — Previous, Current, Next. Current is the first workout in program order the user has not marked done (rest days included, they are marked done like any other); Previous/Next are its neighbours in program order. Shows "N of 371 workouts done". "All done!" when nothing is left.
  - `/wod/{week}/{day}`: the workout, then a button row — Description (left; toggles the Bulgarian text below the row via `data-toggle`), Home (middle), Done / Mark not done (right; POSTs and returns home).
  - `/history`: done workouts, newest in program order first, each with an Unmark button.
  - POST `/wod/{week}/{day}` sets done from the `done` form field and redirects to `/history` when the `next` field is `/history`, else `/`.
- **Tests** — `tests/test_app.py` points `db.DB_PATH` at a temp file per test and covers content loading, login/register, closed registration, login throttling, cross-site POST refusal, security headers, the home cards, marking/unmarking, per-user isolation, 404s and the redirect guard. Keep them passing when changing behaviour.

Known gaps: login throttling is per process and resets on restart; sessions are stateless cookies, so logout cannot revoke a stolen cookie before it expires (14 days). Serve it behind HTTPS with `SESSION_HTTPS_ONLY=1` if exposed publicly.

## The extracted data

`data/W01` … `data/W53` hold one folder per sheet. Each week has two subfolders with the same seven file names, `1-monday.md` … `7-sunday.md` (the numeric prefix keeps them in week order):

- `wods/` — the workout text extracted from the workbook (English).
- `desc/` — a Bulgarian description of the matching `wods/` file.

### `wods/`

Each file starts with frontmatter:

```
---
day: Monday
week: W01
done: false
rest: false
---
```

- `done` was the user's hand-edited progress flag; progress now lives in the app's database and this field is unused (all are `false`). The extraction was a one-off; never regenerate `data/` from the workbook in a way that overwrites existing files, since the user hand-edits workout text.
- `rest: true` marks days with no programmed work: either an explicit rest cell in the workbook, or (11 days) a column that was simply empty, in which case the body is a placeholder sentence.
- The body is a `# W01 – Monday` title, then each workbook section as a `## ` heading followed by its text. Lines end in two trailing spaces (markdown hard breaks) to preserve the workout's line layout — keep them when editing.
- The text is otherwise the workbook's, apart from stray wrapping quotes being dropped; quirks such as the headings `2.` (W03 Sunday) and `1` (W10 Saturday), headings with no body under them (W35 Wednesday), skipped or repeated section numbers (W18 Tuesday, W31 Monday), and a body with no heading (W43 Wednesday) are from the source.
- The user also edits workout text by hand (W01 already differs from the workbook), so treat `wods/` as the source of truth, not the xlsx.

### `desc/`

```
---
path: W01/wods/1-monday.md
day: Monday
week: W01
rest: false
lang: bg
---
```

- `path` is relative to `data/` and points at the workout the file describes.
- The body is a `# W01 – Понеделник` title, then the same `## ` headings as the `wods/` file, verbatim and in the same order, each followed by a short Bulgarian explanation of that point (1–3 sentences, or a bullet list when the point has parts such as A/B/C or several AMRAP windows).
- Style to keep when adding or editing descriptions: exercise names stay in English (`Power Clean`, `Thruster`, `Muscle-up`), everything else is Bulgarian; abbreviations are decoded on use (`TTB (пръсти до лоста)`); loads stay as male/female pairs in `кг`; apparent errors in the source are noted in parentheses rather than silently corrected.
- When a `wods/` file changes, update its `desc/` file so the headings still match one-to-one.
- `desc/` is rendered on the workout page, so its markdown must stay valid; a missing `desc/` file just hides the Description button.

## The workbook

`Comptrain_2017_Open_Athletes_.xlsx` is a year of CompTrain "2017 Open Athletes" CrossFit programming: 53 sheets named `Week 1` … `Week 53`, with no formulas. Every cell is text except one stray numeric `1` in a heading cell (`Week 10`!F3), so coerce cell values to strings.

Every sheet uses the same grid, columns A–G only:

- Row 1: merged title across A1:G1, e.g. `2017 OPEN ATHLETES – WEEK 1` (en dash, not a hyphen).
- Row 2: day headers, `MONDAY` (A) through `SUNDAY` (G).
- Row 3 onward: alternating pairs of rows — an odd row holding numbered section headings (`1. Barbell Conditioning`, `2. Squat`, …) and the even row below it holding that section's workout text.

Things that matter when parsing it:

- A day's workout is a column, read top to bottom as heading/body pairs. Days have different numbers of sections, so shorter columns have empty cells in the lower rows.
- Sheet length varies by week (the used range ends at row 8, 10, 12, 14, or 20; row 10 is the most common), so don't hard-code a row count.
- Rest days appear as `Rest Day` / `Rest day.` in the body row with an empty heading cell above.
- Workout bodies are multi-line free text with embedded newlines, and use typographic characters (`…`, `×`, curly quotes, en dashes). Some headings are incomplete (e.g. `2. ` with no title) or carry a workout name instead of a category (`3. "Cindy"`, `4. “Harley Love”`).
- Loads are written as male/female pairs in kilograms (`43/29 kg`); box heights appear as bare inch pairs (`24/20`).
