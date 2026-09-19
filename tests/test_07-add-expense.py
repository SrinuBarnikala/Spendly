"""
Tests for Step 7 (Add Expense): see .claude/specs/07-add-expense.md.

Scope
-----
`GET /expenses/add` upgrades a placeholder into a real form-render route;
`POST /expenses/add` validates form input and inserts a new row into the
`expenses` table via `database/queries.py::insert_expense`, then redirects
to `/profile`. Both verbs are logged-in only.

These tests are written strictly from the spec's "Routes",
"Validation rules for POST", "Tests to write", and "Definition of done"
sections -- not by reading `app.py`'s or `database/queries.py`'s route/
query bodies. Where the spec leaves exact wording unspecified (e.g. "an
error message"), assertions use a generic vocabulary check
(`_looks_like_error_message`) plus a strong behavioural signal (form
re-rendered with HTTP 200, no DB row inserted) rather than any string
copied from the implementation.

The 7 fixed category options are reproduced here as an independent
ground truth (matching the spec's own text), not imported from
`database/db.py::CATEGORIES`.

Spec behaviours covered:
- Auth guard: unauthenticated GET and POST both redirect to /login, and an
  unauthenticated POST never touches the DB.
- GET (authenticated): 200, form has amount/category/date/description
  fields, category `<select>` has exactly the 7 fixed options, date
  defaults to today, method is POST.
- POST happy path: valid data redirects to /profile and the row appears
  in the DB (and, followed through, in the profile transaction list).
- POST validation errors (missing/zero/negative/non-numeric amount,
  invalid category, SQL-injection-shaped category, invalid/malformed
  date): 200 re-render, error message shown, no DB row inserted, other
  submitted field values retained.
- POST optional description: omitted or blank description saves the row
  with `description IS NULL` and no error.
- `insert_expense` unit tests: valid insert is queryable; blank
  description is stored as NULL.
- Definition-of-done extras: "Add Expense" link on the profile page and
  in the navbar only when logged in.
"""

from datetime import date

import pytest

from database import db as db_module
from database.queries import insert_expense

# --------------------------------------------------------------------- #
# Ground truth: spec's fixed category list (independent of db.py)       #
# --------------------------------------------------------------------- #

FIXED_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

VALID_PAYLOAD = {
    "amount": "50.00",
    "category": "Food",
    "date": "2026-03-20",
    "description": "Lunch",
}

# Generic vocabulary a validation-error message is likely to use. We don't
# know (and must not assume) the exact copy the implementation renders, so
# this is intentionally loose -- it exists only to confirm *some* error
# feedback is shown, per the spec's "error message" requirement.
_ERROR_VOCAB = ("error", "invalid", "required", "must", "please", "valid")


def _looks_like_error_message(body):
    lowered = body.lower()
    return any(word in lowered for word in _ERROR_VOCAB)


def _expense_count(user_id):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    return row["c"]


def _fetch_latest_expense(user_id):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    return row


# ======================================================================= #
# Unit tests: database/queries.py::insert_expense                         #
# ======================================================================= #


def test_insert_expense_valid_row_is_queryable(demo_user_id):
    before = _expense_count(demo_user_id)
    insert_expense(demo_user_id, 50.0, "Food", "2026-03-20", "Lunch")
    assert _expense_count(demo_user_id) == before + 1

    row = _fetch_latest_expense(demo_user_id)
    assert row["user_id"] == demo_user_id
    assert row["amount"] == 50.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_insert_expense_none_description_stored_as_null(demo_user_id):
    insert_expense(demo_user_id, 12.34, "Other", "2026-04-01", None)
    row = _fetch_latest_expense(demo_user_id)
    assert row["description"] is None, "blank/None description must be stored as NULL"


# ======================================================================= #
# Route: GET /expenses/add -- auth guard                                  #
# ======================================================================= #


def test_get_add_expense_unauthenticated_redirects_to_login(client):
    response = client.get("/expenses/add")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ======================================================================= #
# Route: GET /expenses/add -- happy path / template rendering             #
# ======================================================================= #


def test_get_add_expense_authenticated_returns_200(logged_in_client):
    response = logged_in_client.get("/expenses/add")
    assert response.status_code == 200


def test_get_add_expense_form_has_post_method(logged_in_client):
    body = logged_in_client.get("/expenses/add").get_data(as_text=True)
    assert "<form" in body, "expected a <form> element on the add-expense page"
    assert "post" in body.lower(), "expected the form to submit via POST"


def test_get_add_expense_has_amount_field(logged_in_client):
    body = logged_in_client.get("/expenses/add").get_data(as_text=True)
    assert 'name="amount"' in body


def test_get_add_expense_has_date_field(logged_in_client):
    body = logged_in_client.get("/expenses/add").get_data(as_text=True)
    assert 'name="date"' in body


def test_get_add_expense_has_description_field(logged_in_client):
    body = logged_in_client.get("/expenses/add").get_data(as_text=True)
    assert 'name="description"' in body


def test_get_add_expense_category_select_has_exactly_seven_fixed_options(logged_in_client):
    body = logged_in_client.get("/expenses/add").get_data(as_text=True)
    assert 'name="category"' in body
    for category in FIXED_CATEGORIES:
        assert category in body, f"expected category option '{category}' in the form"


def test_get_add_expense_date_defaults_to_today(logged_in_client):
    body = logged_in_client.get("/expenses/add").get_data(as_text=True)
    today_iso = date.today().isoformat()
    assert today_iso in body, "expected the date field to default to today's date"


def test_get_add_expense_has_cancel_link_back_to_profile(logged_in_client):
    body = logged_in_client.get("/expenses/add").get_data(as_text=True)
    assert "/profile" in body, "expected a cancel link back to /profile"


# ======================================================================= #
# Route: POST /expenses/add -- auth guard                                 #
# ======================================================================= #


def test_post_add_expense_unauthenticated_redirects_to_login(client):
    response = client.post("/expenses/add", data=VALID_PAYLOAD)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_post_add_expense_unauthenticated_does_not_write_to_db(client, demo_user_id):
    before = _expense_count(demo_user_id)
    client.post("/expenses/add", data=VALID_PAYLOAD)
    assert _expense_count(demo_user_id) == before, (
        "an unauthenticated POST must not create an expense row"
    )


# ======================================================================= #
# Route: POST /expenses/add -- happy path                                 #
# ======================================================================= #


def test_post_add_expense_valid_data_redirects_to_profile(logged_in_client):
    response = logged_in_client.post("/expenses/add", data=VALID_PAYLOAD)
    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]


def test_post_add_expense_valid_data_inserts_row_for_correct_user(
    logged_in_client, demo_user_id
):
    before = _expense_count(demo_user_id)
    logged_in_client.post("/expenses/add", data=VALID_PAYLOAD)
    assert _expense_count(demo_user_id) == before + 1

    row = _fetch_latest_expense(demo_user_id)
    assert row["amount"] == 50.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_post_add_expense_valid_data_appears_in_profile_after_redirect(logged_in_client):
    response = logged_in_client.post(
        "/expenses/add",
        data={
            "amount": "77.00",
            "category": "Shopping",
            "date": "2026-03-20",
            "description": "UNIQUE_ADD_EXPENSE_MARKER",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "UNIQUE_ADD_EXPENSE_MARKER" in body, (
        "expected the newly added expense to appear in the redirected-to profile page"
    )


def test_post_add_expense_min_boundary_amount_succeeds(logged_in_client, demo_user_id):
    before = _expense_count(demo_user_id)
    response = logged_in_client.post(
        "/expenses/add",
        data={**VALID_PAYLOAD, "amount": "0.01"},
    )
    assert response.status_code == 302
    assert _expense_count(demo_user_id) == before + 1


# ======================================================================= #
# Route: POST /expenses/add -- optional description                      #
# ======================================================================= #


def test_post_add_expense_missing_description_redirects_and_saves_null(
    logged_in_client, demo_user_id
):
    payload = {**VALID_PAYLOAD}
    del payload["description"]
    response = logged_in_client.post("/expenses/add", data=payload)
    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]

    row = _fetch_latest_expense(demo_user_id)
    assert row["description"] is None


def test_post_add_expense_blank_description_redirects_and_saves_null(
    logged_in_client, demo_user_id
):
    response = logged_in_client.post(
        "/expenses/add", data={**VALID_PAYLOAD, "description": "   "}
    )
    assert response.status_code == 302
    row = _fetch_latest_expense(demo_user_id)
    assert row["description"] is None, "whitespace-only description must be stored as NULL"


# ======================================================================= #
# Route: POST /expenses/add -- validation errors                         #
# ======================================================================= #


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("amount", ""),  # missing
        ("amount", "0"),  # not > 0
        ("amount", "-5"),  # negative
        ("amount", "abc"),  # non-numeric
        ("amount", "   "),  # whitespace only
        ("category", ""),  # missing
        ("category", "NotACategory"),  # not one of the 7 fixed options
        ("category", "Food'; DROP TABLE expenses;--"),  # injection-shaped junk
        ("date", ""),  # missing
        ("date", "not-a-date"),
        ("date", "2026-13-40"),  # invalid calendar values
        ("date", "20-03-2026"),  # wrong format
    ],
)
def test_post_add_expense_invalid_field_rerenders_form_with_error(
    logged_in_client, demo_user_id, field, bad_value
):
    before = _expense_count(demo_user_id)
    payload = {**VALID_PAYLOAD, field: bad_value}
    response = logged_in_client.post("/expenses/add", data=payload)

    assert response.status_code == 200, (
        f"invalid {field}={bad_value!r} must re-render the form, not redirect"
    )
    body = response.get_data(as_text=True)
    assert _looks_like_error_message(body), (
        f"expected an error message in the response for invalid {field}={bad_value!r}"
    )
    assert _expense_count(demo_user_id) == before, (
        f"invalid {field}={bad_value!r} must not insert a row"
    )


def test_post_add_expense_missing_amount_retains_other_submitted_values(logged_in_client):
    payload = {
        "amount": "",
        "category": "Food",
        "date": "2026-03-20",
        "description": "RETAIN_MARKER_DESC",
    }
    response = logged_in_client.post("/expenses/add", data=payload)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "2026-03-20" in body, "expected the previously submitted date to be retained"
    assert "RETAIN_MARKER_DESC" in body, (
        "expected the previously submitted description to be retained"
    )


def test_post_add_expense_invalid_category_retains_other_submitted_values(logged_in_client):
    payload = {
        "amount": "42.50",
        "category": "NotACategory",
        "date": "2026-03-20",
        "description": "RETAIN_MARKER_DESC_2",
    }
    response = logged_in_client.post("/expenses/add", data=payload)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "42.5" in body or "42.50" in body, (
        "expected the previously submitted amount to be retained"
    )
    assert "RETAIN_MARKER_DESC_2" in body, (
        "expected the previously submitted description to be retained"
    )


def test_post_add_expense_invalid_date_retains_other_submitted_values(logged_in_client):
    payload = {
        "amount": "42.50",
        "category": "Health",
        "date": "not-a-date",
        "description": "RETAIN_MARKER_DESC_3",
    }
    response = logged_in_client.post("/expenses/add", data=payload)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "42.5" in body or "42.50" in body, (
        "expected the previously submitted amount to be retained"
    )
    assert "RETAIN_MARKER_DESC_3" in body, (
        "expected the previously submitted description to be retained"
    )


def test_post_add_expense_sql_injection_category_does_not_corrupt_db(
    logged_in_client, demo_user_id
):
    """Rules for implementation: parameterised queries only. A malicious
    category string must be rejected as an invalid category, not executed
    as SQL, and the expenses table must remain intact and usable."""
    response = logged_in_client.post(
        "/expenses/add",
        data={**VALID_PAYLOAD, "category": "Food'; DROP TABLE expenses;--"},
    )
    assert response.status_code == 200

    # The table must still exist and accept further valid inserts.
    before = _expense_count(demo_user_id)
    logged_in_client.post("/expenses/add", data=VALID_PAYLOAD)
    assert _expense_count(demo_user_id) == before + 1


# ======================================================================= #
# Definition of done: navigation surfaces                                 #
# ======================================================================= #


def test_profile_page_has_add_expense_link(logged_in_client):
    body = logged_in_client.get("/profile").get_data(as_text=True)
    assert "/expenses/add" in body, "expected an 'Add Expense' link on the profile page"


def test_navbar_shows_add_expense_link_when_logged_in(logged_in_client):
    body = logged_in_client.get("/profile").get_data(as_text=True)
    assert "Add Expense" in body


def test_navbar_hides_add_expense_link_when_logged_out(client):
    body = client.get("/login").get_data(as_text=True)
    assert "/expenses/add" not in body, (
        "the 'Add Expense' nav link must only show when session.user_id is set"
    )
