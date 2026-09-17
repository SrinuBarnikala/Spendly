# Spec: Registration

## Overview
Implements account creation for Spendly. Right now `/register` is a GET-only
stub that renders `templates/register.html`, even though that template
already POSTs `name`/`email`/`password` to `/register`. This step replaces
the stub with real logic: validate the submitted form, hash the password,
insert a new row into `users`, and reject duplicate emails — turning
registration into the entry point for every feature that depends on a real
user account (login, profile, expenses).

No session/auth mechanism is introduced here. After a successful
registration the user is redirected to `/login` to sign in — session
handling belongs to the Login and Logout step (Step 3, per `app.py`'s
`# Logout — coming in Step 3`).

## Depends on
- Step 1 — Database Setup (`database/db.py`: `get_db()`, `init_db()`, the
  `users` table with its `UNIQUE` email constraint)

## Routes
- `GET /register` — renders the registration form — public (existing route,
  unchanged)
- `POST /register` — validates input, creates the user, redirects to
  `/login` on success or re-renders the form with an error on failure —
  public (new handling on the existing route; add `methods=["GET", "POST"]`)

## Database changes
No database changes. Uses the existing `users` table from `database/db.py`
as-is (`id`, `name`, `email` UNIQUE, `password_hash`, `created_at`).

## Templates
- **Create:** none
- **Modify:** `templates/register.html` — no structural changes required;
  it already posts to `/register` with `name`/`email`/`password` and already
  renders `{{ error }}` inside `.auth-error` when set

## Files to change
- `app.py` — replace the `register()` stub with real POST handling:
  - accept `methods=["GET", "POST"]`
  - on `GET`, render the form as today
  - on `POST`:
    - read `name`, `email`, `password` from `request.form`
    - validate all three are present (non-empty after `.strip()`)
    - validate `password` is at least 8 characters
    - normalize `email` (e.g. `.strip().lower()`) before checking/storing
    - check for an existing user with that email via `get_db()`
      (parameterised `SELECT`); if found, re-render `register.html` with
      `error` set and **do not** insert
    - on any validation failure, re-render `register.html` with `error` set
      and the submitted `name`/`email` preserved so the user doesn't retype
      them
    - hash the password with
      `werkzeug.security.generate_password_hash`
    - insert the new user via `get_db()` using a parameterised `INSERT`,
      commit, close the connection
    - redirect to `/login` on success

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never format values into SQL strings
- Passwords hashed with werkzeug (`generate_password_hash`); never store or
  log a plaintext password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Reuse `get_db()` from `database/db.py` for every query — don't open a raw
  `sqlite3.connect()` in `app.py`
- Always close (or otherwise release) the connection after use, on both the
  success and error paths
- Treat email as case-insensitive for the uniqueness check (normalize before
  comparing/storing)

## Definition of done
- [ ] Visiting `GET /register` still renders the form exactly as before
- [ ] Submitting valid name/email/password on `POST /register` creates one
      new row in `users` with a hashed (not plaintext) password, and
      redirects to `/login`
- [ ] Submitting an email that already exists in `users` re-renders
      `register.html` with an error message and does **not** insert a
      duplicate row
- [ ] Submitting with a missing name, email, or password re-renders the
      form with an error and inserts nothing
- [ ] Submitting a password under 8 characters re-renders the form with an
      error and inserts nothing
- [ ] Registering with `Name@Example.com` then again with
      `name@example.com` is rejected as a duplicate
- [ ] `sqlite3` inspection of `expense_tracker.db` confirms every insert
      used parameter binding (no string-built SQL anywhere in the diff)
- [ ] `python app.py` starts without errors and the full flow (register →
      redirect to login) works end to end in the browser
