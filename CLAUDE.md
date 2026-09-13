# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Spendly — a Flask expense tracker built as a step-by-step student project. Routes for
features not yet built return a placeholder string like `"Add expense — coming in Step 7"`
instead of a real implementation (see `app.py`). When asked to implement one of these,
replace the placeholder with the real route logic rather than leaving it in place.

## Commands

```bash
# Setup (venv/ is already present, but if recreating):
pip install -r requirements.txt

# Run the dev server (http://127.0.0.1:5001)
python app.py

# Run tests
pytest
pytest path/to/test_file.py::test_name   # single test
```

There is no build/lint step configured — this is a plain Flask + Jinja + static
CSS/JS app, no bundler or transpiler.

## Architecture

- `app.py` — single Flask app, all routes defined directly on `app` (no blueprints).
  `debug=True`, runs on port 5001.
- `database/db.py` — intended to own all SQLite access. Per its own header comment,
  this file should expose:
  - `get_db()` — SQLite connection with `row_factory` and foreign keys enabled
  - `init_db()` — creates tables with `CREATE TABLE IF NOT EXISTS`
  - `seed_db()` — inserts sample dev data
  Routes in `app.py` should call into this module rather than opening SQLite
  connections directly. The DB file (`expense_tracker.db`) is gitignored and
  created locally by `init_db()`.
- `templates/` — Jinja templates, all extending `templates/base.html` (defines the
  shared nav/footer and `title`/`head`/`content`/`scripts` blocks). Auth forms
  (`register.html`, `login.html`) POST to `/register` and `/login` with
  `name`/`email`/`password` fields; server-side errors are shown via an `error`
  template variable rendered back into the same page.
- `static/css/` and `static/js/` — plain CSS/JS, one file pair per page area
  (`landing.*`) plus shared `style.css`/`main.js`.

## Notes for implementing placeholder routes

- `/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`,
  `/expenses/<id>/delete` in `app.py` are stubs awaiting implementation — check
  the "coming in Step N" text to see what's expected before building beyond
  what's asked.
- No session/auth mechanism exists yet; `/register` and `/login` routes are
  GET-only render stubs even though the templates already POST to them.
