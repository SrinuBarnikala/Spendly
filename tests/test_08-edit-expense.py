"""
Tests for Step 8 (Edit Expense): see .claude/specs/08-edit-expense.md.

Scope
-----
`GET /expenses/<id>/edit` renders a form pre-populated with an existing
expense's values; `POST /expenses/<id>/edit` validates the submission and
updates the row in place via `database/queries.py::update_expense`, then
redirects to `/profile`. Both verbs are logged-in only, and ownership is
enforced: a user may only view/edit their own expenses (404 otherwise, and
404 for a non-existent id). Two new query helpers, `get_expense_by_id` and
`update_expense`, are unit-tested directly, mirroring how `insert_expense`
is unit-tested in `tests/test_07-add-expense.py`.

These tests are written strictly from the spec's "Routes", "Rules for
implementation", "Tests to write", and "Definition of done" sections --
NOT by reading the already-implemented route/query bodies in `app.py` /
`database/queries.py`. Where the spec leaves exact wording unspecified
(e.g. "an error message"), assertions use a generic vocabulary check
(`_looks_like_error_message`) plus a strong behavioural signal (form
re-rendered with HTTP 200, DB row left unchanged) rather than any string
copied from the implementation. Where the spec names an exact literal
(the "Save Changes" submit button text), that literal is asserted as
given by the spec.

The 7 fixed category options are reproduced here as an independent ground
truth (matching the spec's own text and `test_07-add-expense.py`), not
imported from `database/db.py::CATEGORIES`.

Spec behaviours covered:
- Unit tests for `get_expense_by_id` (owner match, wrong user -> None,
  non-existent id -> None) and `update_expense` (valid update persists;
  wrong user_id is a no-op ownership guard, no error raised).
- Unit test that `get_recent_transactions` now includes `id` (required so
  `profile.html` can build per-row edit links).
- Auth guard: unauthenticated GET and POST both redirect to /login; an
  unauthenticated POST never touches the DB.
- GET (authenticated, own expense): 200, form pre-filled with the
  expense's current amount/date/description, category `<select>` has the
  current category pre-selected, cancel link back to /profile, "Save
  Changes" submit button.
- GET/POST (authenticated, other user's expense or non-existent id): 404,
  and a failed/blocked POST never mutates the DB.
- POST happy path: valid data redirects to /profile and the row's values
  are updated in the DB.
- POST validation errors (missing/zero/non-numeric amount, invalid
  category, invalid date -- "identical to add expense" per spec):
  200 re-render, error message shown, DB row left unchanged, and the
  submitted (not original) values are retained in the re-rendered form.
- POST optional description: blank description saves the row with
  `description IS NULL` and no error.
- Definition-of-done extra: each profile transaction row has an "Edit"
  link pointing at `/expenses/<id>/edit`, and the table has an "Actions"
  column header.
"""

import re

import pytest

from database import db as db_module
from database.queries import (
    get_expense_by_id,
    get_recent_transactions,
    insert_expense,
    update_expense,
)

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

ORIGINAL = {
    "amount": 42.50,
    "category": "Food",
    "date": "2026-01-15",
    "description": "ORIGINAL_DESC_MARKER",
}

VALID_UPDATE_PAYLOAD = {
    "amount": "99.00",
    "category": "Transport",
    "date": "2026-02-02",
    "description": "UPDATED_DESC_MARKER",
}

# Generic vocabulary a validation-error message is likely to use. We don't
# know (and must not assume) the exact copy the implementation renders, so
# this is intentionally loose -- it exists only to confirm *some* error
# feedback is shown, per the spec's "error message" requirement.
_ERROR_VOCAB = ("error", "invalid", "required", "must", "please", "valid")


def _looks_like_error_message(body):
    lowered = body.lower()
    return any(word in lowered for word in _ERROR_VOCAB)


def _fetch_expense_row(expense_id):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()
    return row


def _category_option_is_selected(body, category):
    """Loosely detect that `category` is the pre-selected <option> in a
    <select name="category">, tolerant of either attribute order
    (`selected` before or after `value="..."`)."""
    escaped = re.escape(category)
    pattern = re.compile(
        rf'<option[^>]*value="{escaped}"[^>]*selected'
        rf'|<option[^>]*selected[^>]*value="{escaped}"',
        re.IGNORECASE,
    )
    return bool(pattern.search(body))


# --------------------------------------------------------------------- #
# Fixtures: seed one expense per user for edit/ownership tests          #
# --------------------------------------------------------------------- #


@pytest.fixture
def demo_expense_id(demo_user_id):
    return insert_expense(
        demo_user_id,
        ORIGINAL["amount"],
        ORIGINAL["category"],
        ORIGINAL["date"],
        ORIGINAL["description"],
    )


@pytest.fixture
def other_user_expense_id(empty_user_id):
    return insert_expense(
        empty_user_id, 15.00, "Bills", "2026-02-20", "OTHER_USERS_EXPENSE"
    )


# ======================================================================= #
# Unit tests: database/queries.py::get_expense_by_id                      #
# ======================================================================= #


def test_get_expense_by_id_returns_row_for_owner(demo_user_id, demo_expense_id):
    row = get_expense_by_id(demo_expense_id, demo_user_id)
    assert row is not None, "expected the owner to be able to fetch their own expense"
    assert row["id"] == demo_expense_id
    assert row["amount"] == ORIGINAL["amount"]
    assert row["category"] == ORIGINAL["category"]
    assert row["date"] == ORIGINAL["date"]
    assert row["description"] == ORIGINAL["description"]


def test_get_expense_by_id_returns_none_for_wrong_user(empty_user_id, demo_expense_id):
    assert get_expense_by_id(demo_expense_id, empty_user_id) is None, (
        "a user must not be able to fetch another user's expense"
    )


def test_get_expense_by_id_returns_none_for_nonexistent_id(demo_user_id):
    assert get_expense_by_id(999999, demo_user_id) is None


# ======================================================================= #
# Unit tests: database/queries.py::update_expense                         #
# ======================================================================= #


def test_update_expense_valid_owner_updates_row(demo_user_id, demo_expense_id):
    update_expense(
        demo_expense_id, demo_user_id, 99.0, "Transport", "2026-02-02", "UPDATED"
    )
    row = _fetch_expense_row(demo_expense_id)
    assert row["amount"] == 99.0
    assert row["category"] == "Transport"
    assert row["date"] == "2026-02-02"
    assert row["description"] == "UPDATED"


def test_update_expense_wrong_user_leaves_row_unchanged(
    demo_user_id, empty_user_id, demo_expense_id
):
    before = _fetch_expense_row(demo_expense_id)

    # Must not raise, and must not touch the row -- it belongs to demo_user_id.
    update_expense(
        demo_expense_id, empty_user_id, 999.0, "Bills", "2026-03-03", "SHOULD_NOT_APPLY"
    )

    after = _fetch_expense_row(demo_expense_id)
    assert after["amount"] == before["amount"]
    assert after["category"] == before["category"]
    assert after["date"] == before["date"]
    assert after["description"] == before["description"]


# ======================================================================= #
# Unit test: database/queries.py::get_recent_transactions includes id     #
# ======================================================================= #


def test_get_recent_transactions_includes_id_field(demo_user_id, demo_expense_id):
    transactions = get_recent_transactions(demo_user_id, limit=50)
    assert any(tx["id"] == demo_expense_id for tx in transactions), (
        "get_recent_transactions must return each row's id so templates "
        "can build per-row edit links"
    )


# ======================================================================= #
# Route: GET /expenses/<id>/edit -- auth guard                            #
# ======================================================================= #


def test_get_edit_expense_unauthenticated_redirects_to_login(client, demo_expense_id):
    response = client.get(f"/expenses/{demo_expense_id}/edit")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ======================================================================= #
# Route: GET /expenses/<id>/edit -- happy path / template rendering       #
# ======================================================================= #


def test_get_edit_expense_authenticated_own_expense_returns_200(
    logged_in_client, demo_expense_id
):
    response = logged_in_client.get(f"/expenses/{demo_expense_id}/edit")
    assert response.status_code == 200


def test_get_edit_expense_form_has_post_method_to_correct_action(
    logged_in_client, demo_expense_id
):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    assert "<form" in body, "expected a <form> element on the edit-expense page"
    assert "post" in body.lower(), "expected the form to submit via POST"


def test_get_edit_expense_prefills_amount(logged_in_client, demo_expense_id):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    assert "42.5" in body or "42.50" in body, (
        "expected the form to be pre-filled with the expense's current amount"
    )


def test_get_edit_expense_prefills_date(logged_in_client, demo_expense_id):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    assert ORIGINAL["date"] in body, (
        "expected the form to be pre-filled with the expense's current date"
    )


def test_get_edit_expense_prefills_description(logged_in_client, demo_expense_id):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    assert ORIGINAL["description"] in body, (
        "expected the form to be pre-filled with the expense's current description"
    )


def test_get_edit_expense_category_select_has_current_category_preselected(
    logged_in_client, demo_expense_id
):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    assert 'name="category"' in body
    assert _category_option_is_selected(body, ORIGINAL["category"]), (
        "expected the category <select> to have the expense's current "
        f"category ({ORIGINAL['category']!r}) pre-selected"
    )


def test_get_edit_expense_category_select_has_all_seven_fixed_options(
    logged_in_client, demo_expense_id
):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    for category in FIXED_CATEGORIES:
        assert category in body, f"expected category option {category!r} in the form"


def test_get_edit_expense_has_cancel_link_back_to_profile(logged_in_client, demo_expense_id):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    assert "/profile" in body, "expected a cancel link back to /profile"


def test_get_edit_expense_has_save_changes_submit_button(logged_in_client, demo_expense_id):
    body = logged_in_client.get(f"/expenses/{demo_expense_id}/edit").get_data(as_text=True)
    assert "Save Changes" in body, 'spec requires a submit button labelled "Save Changes"'


# ======================================================================= #
# Route: GET /expenses/<id>/edit -- ownership / not-found                 #
# ======================================================================= #


def test_get_edit_expense_other_users_expense_returns_404(
    logged_in_client, other_user_expense_id
):
    response = logged_in_client.get(f"/expenses/{other_user_expense_id}/edit")
    assert response.status_code == 404


def test_get_edit_expense_nonexistent_id_returns_404(logged_in_client):
    response = logged_in_client.get("/expenses/999999/edit")
    assert response.status_code == 404


# ======================================================================= #
# Route: POST /expenses/<id>/edit -- auth guard                           #
# ======================================================================= #


def test_post_edit_expense_unauthenticated_redirects_to_login(client, demo_expense_id):
    response = client.post(
        f"/expenses/{demo_expense_id}/edit", data=VALID_UPDATE_PAYLOAD
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_post_edit_expense_unauthenticated_does_not_write_to_db(client, demo_expense_id):
    before = _fetch_expense_row(demo_expense_id)
    client.post(f"/expenses/{demo_expense_id}/edit", data=VALID_UPDATE_PAYLOAD)
    after = _fetch_expense_row(demo_expense_id)
    assert after["amount"] == before["amount"], (
        "an unauthenticated POST must not update the expense row"
    )


# ======================================================================= #
# Route: POST /expenses/<id>/edit -- happy path                           #
# ======================================================================= #


def test_post_edit_expense_valid_data_redirects_to_profile(
    logged_in_client, demo_expense_id
):
    response = logged_in_client.post(
        f"/expenses/{demo_expense_id}/edit", data=VALID_UPDATE_PAYLOAD
    )
    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]


def test_post_edit_expense_valid_data_updates_db_row(logged_in_client, demo_expense_id):
    logged_in_client.post(f"/expenses/{demo_expense_id}/edit", data=VALID_UPDATE_PAYLOAD)
    row = _fetch_expense_row(demo_expense_id)
    assert row["amount"] == 99.0
    assert row["category"] == "Transport"
    assert row["date"] == "2026-02-02"
    assert row["description"] == "UPDATED_DESC_MARKER"


def test_post_edit_expense_valid_data_appears_in_profile_after_redirect(
    logged_in_client, demo_expense_id
):
    response = logged_in_client.post(
        f"/expenses/{demo_expense_id}/edit",
        data=VALID_UPDATE_PAYLOAD,
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "UPDATED_DESC_MARKER" in body, (
        "expected the updated expense to appear in the redirected-to profile page"
    )


# ======================================================================= #
# Route: POST /expenses/<id>/edit -- ownership / not-found                #
# ======================================================================= #


def test_post_edit_expense_other_users_expense_returns_404(
    logged_in_client, other_user_expense_id
):
    response = logged_in_client.post(
        f"/expenses/{other_user_expense_id}/edit", data=VALID_UPDATE_PAYLOAD
    )
    assert response.status_code == 404


def test_post_edit_expense_other_users_expense_does_not_modify_row(
    logged_in_client, other_user_expense_id
):
    before = _fetch_expense_row(other_user_expense_id)
    logged_in_client.post(
        f"/expenses/{other_user_expense_id}/edit", data=VALID_UPDATE_PAYLOAD
    )
    after = _fetch_expense_row(other_user_expense_id)
    assert after["amount"] == before["amount"]
    assert after["category"] == before["category"]
    assert after["date"] == before["date"]
    assert after["description"] == before["description"]


def test_post_edit_expense_nonexistent_id_returns_404(logged_in_client):
    response = logged_in_client.post("/expenses/999999/edit", data=VALID_UPDATE_PAYLOAD)
    assert response.status_code == 404


# ======================================================================= #
# Route: POST /expenses/<id>/edit -- optional description                 #
# ======================================================================= #


def test_post_edit_expense_missing_description_redirects_and_saves_null(
    logged_in_client, demo_expense_id
):
    payload = {**VALID_UPDATE_PAYLOAD}
    del payload["description"]
    response = logged_in_client.post(f"/expenses/{demo_expense_id}/edit", data=payload)
    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]

    row = _fetch_expense_row(demo_expense_id)
    assert row["description"] is None


def test_post_edit_expense_blank_description_redirects_and_saves_null(
    logged_in_client, demo_expense_id
):
    response = logged_in_client.post(
        f"/expenses/{demo_expense_id}/edit",
        data={**VALID_UPDATE_PAYLOAD, "description": "   "},
    )
    assert response.status_code == 302
    row = _fetch_expense_row(demo_expense_id)
    assert row["description"] is None, "whitespace-only description must be stored as NULL"


# ======================================================================= #
# Route: POST /expenses/<id>/edit -- validation errors                    #
# ======================================================================= #


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("amount", ""),  # missing
        ("amount", "0"),  # not > 0
        ("amount", "abc"),  # non-numeric
        ("category", ""),  # missing
        ("category", "NotACategory"),  # not one of the 7 fixed options
        ("date", ""),  # missing
        ("date", "not-a-date"),  # invalid/malformed date string
    ],
)
def test_post_edit_expense_invalid_field_rerenders_form_with_error(
    logged_in_client, demo_expense_id, field, bad_value
):
    payload = {**VALID_UPDATE_PAYLOAD, field: bad_value}
    response = logged_in_client.post(f"/expenses/{demo_expense_id}/edit", data=payload)

    assert response.status_code == 200, (
        f"invalid {field}={bad_value!r} must re-render the form, not redirect"
    )
    body = response.get_data(as_text=True)
    assert _looks_like_error_message(body), (
        f"expected an error message in the response for invalid {field}={bad_value!r}"
    )

    row = _fetch_expense_row(demo_expense_id)
    assert row["amount"] == ORIGINAL["amount"], (
        f"invalid {field}={bad_value!r} must not update the row"
    )
    assert row["category"] == ORIGINAL["category"]
    assert row["date"] == ORIGINAL["date"]


def test_post_edit_expense_missing_amount_retains_submitted_values_not_original(
    logged_in_client, demo_expense_id
):
    payload = {
        "amount": "",
        "category": "Health",
        "date": "2026-05-05",
        "description": "RETAIN_MARKER_EDIT",
    }
    response = logged_in_client.post(f"/expenses/{demo_expense_id}/edit", data=payload)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "2026-05-05" in body, "expected the submitted date to be retained"
    assert "RETAIN_MARKER_EDIT" in body, "expected the submitted description to be retained"
    assert _category_option_is_selected(body, "Health"), (
        "expected the submitted category ('Health'), not the original ('Food'), "
        "to be pre-selected"
    )
    assert ORIGINAL["description"] not in body, (
        "the re-rendered form must show the submitted values, not the original ones"
    )


def test_post_edit_expense_invalid_category_retains_submitted_values(
    logged_in_client, demo_expense_id
):
    payload = {
        "amount": "55.25",
        "category": "NotACategory",
        "date": "2026-06-06",
        "description": "RETAIN_MARKER_EDIT_2",
    }
    response = logged_in_client.post(f"/expenses/{demo_expense_id}/edit", data=payload)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "55.25" in body, "expected the submitted amount to be retained"
    assert "RETAIN_MARKER_EDIT_2" in body, "expected the submitted description to be retained"


def test_post_edit_expense_invalid_date_retains_submitted_values(
    logged_in_client, demo_expense_id
):
    payload = {
        "amount": "55.25",
        "category": "Entertainment",
        "date": "not-a-date",
        "description": "RETAIN_MARKER_EDIT_3",
    }
    response = logged_in_client.post(f"/expenses/{demo_expense_id}/edit", data=payload)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "55.25" in body, "expected the submitted amount to be retained"
    assert "RETAIN_MARKER_EDIT_3" in body, "expected the submitted description to be retained"
    assert _category_option_is_selected(body, "Entertainment"), (
        "expected the submitted category to remain selected after a date validation error"
    )


# ======================================================================= #
# Definition of done: profile page "Edit" links                           #
# ======================================================================= #


def test_profile_transaction_row_has_edit_link_to_correct_url(
    logged_in_client, demo_expense_id
):
    body = logged_in_client.get("/profile").get_data(as_text=True)
    assert f"/expenses/{demo_expense_id}/edit" in body, (
        "expected the profile page's transaction row to link to the correct edit URL"
    )


def test_profile_transactions_table_has_actions_column_header(
    logged_in_client, demo_expense_id
):
    body = logged_in_client.get("/profile").get_data(as_text=True)
    assert "Actions" in body, 'expected an "Actions" column header on the transactions table'
