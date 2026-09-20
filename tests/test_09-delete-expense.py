"""
Tests for Step 9 (Delete Expense): see .claude/specs/09-delete-expense.md.

Scope
-----
`POST /expenses/<id>/delete` verifies ownership via `get_expense_by_id`
(reused from Step 8), removes the row via `database/queries.py::delete_expense`,
and redirects to `/profile`. There is no GET handler -- deleting must not be
triggerable by a plain link visit or prefetch, so a bare `GET` to the URL
must return 405. Ownership is enforced: a user may only delete their own
expenses (404 for another user's expense, and 404 for a non-existent id).

These tests are written strictly from the spec's "Routes", "Rules for
implementation", "Tests to write", and "Definition of done" sections --
NOT by reading the already-implemented route/query bodies in `app.py` /
`database/queries.py`, following the same approach as
`tests/test_08-edit-expense.py`.

Spec behaviours covered:
- Unit tests for `delete_expense` (owner match removes the row; wrong
  user_id is a no-op ownership guard, no error raised; non-existent id is
  a no-op, no error raised).
- Auth guard: unauthenticated POST redirects to /login and never touches
  the DB.
- POST (authenticated, other user's expense or non-existent id): 404, and
  the row (if it exists) is left unchanged.
- POST happy path: valid delete redirects to /profile and the row no
  longer exists in the DB; the deleted expense no longer appears on the
  redirected-to profile page.
- GET /expenses/<id>/delete: 405 (Method Not Allowed) for any user.
- Definition-of-done extra: each profile transaction row's Actions cell
  contains a delete form posting to the correct URL.
"""

import pytest

from database import db as db_module
from database.queries import delete_expense, insert_expense

ORIGINAL = {
    "amount": 42.50,
    "category": "Food",
    "date": "2026-01-15",
    "description": "ORIGINAL_DESC_MARKER",
}


def _fetch_expense_row(expense_id):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()
    return row


# --------------------------------------------------------------------- #
# Fixtures: seed one expense per user for delete/ownership tests        #
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
# Unit tests: database/queries.py::delete_expense                         #
# ======================================================================= #


def test_delete_expense_valid_owner_removes_row(demo_user_id, demo_expense_id):
    delete_expense(demo_expense_id, demo_user_id)
    assert _fetch_expense_row(demo_expense_id) is None


def test_delete_expense_wrong_user_leaves_row_unchanged(
    demo_user_id, empty_user_id, demo_expense_id
):
    # Must not raise, and must not touch the row -- it belongs to demo_user_id.
    delete_expense(demo_expense_id, empty_user_id)

    row = _fetch_expense_row(demo_expense_id)
    assert row is not None, "a wrong user_id must not delete another user's expense"
    assert row["amount"] == ORIGINAL["amount"]


def test_delete_expense_nonexistent_id_is_noop(demo_user_id):
    # Must not raise even though no row matches.
    delete_expense(999999, demo_user_id)


# ======================================================================= #
# Route: POST /expenses/<id>/delete -- auth guard                         #
# ======================================================================= #


def test_post_delete_expense_unauthenticated_redirects_to_login(client, demo_expense_id):
    response = client.post(f"/expenses/{demo_expense_id}/delete")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_post_delete_expense_unauthenticated_does_not_delete_row(client, demo_expense_id):
    client.post(f"/expenses/{demo_expense_id}/delete")
    assert _fetch_expense_row(demo_expense_id) is not None, (
        "an unauthenticated POST must not delete the expense row"
    )


# ======================================================================= #
# Route: POST /expenses/<id>/delete -- happy path                         #
# ======================================================================= #


def test_post_delete_expense_own_expense_redirects_to_profile(
    logged_in_client, demo_expense_id
):
    response = logged_in_client.post(f"/expenses/{demo_expense_id}/delete")
    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]


def test_post_delete_expense_own_expense_removes_row_from_db(
    logged_in_client, demo_expense_id
):
    logged_in_client.post(f"/expenses/{demo_expense_id}/delete")
    assert _fetch_expense_row(demo_expense_id) is None


def test_post_delete_expense_own_expense_no_longer_in_profile_after_redirect(
    logged_in_client, demo_expense_id
):
    response = logged_in_client.post(
        f"/expenses/{demo_expense_id}/delete", follow_redirects=True
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert ORIGINAL["description"] not in body, (
        "expected the deleted expense to no longer appear on the redirected-to profile page"
    )


# ======================================================================= #
# Route: POST /expenses/<id>/delete -- ownership / not-found              #
# ======================================================================= #


def test_post_delete_expense_other_users_expense_returns_404(
    logged_in_client, other_user_expense_id
):
    response = logged_in_client.post(f"/expenses/{other_user_expense_id}/delete")
    assert response.status_code == 404


def test_post_delete_expense_other_users_expense_row_survives(
    logged_in_client, other_user_expense_id
):
    logged_in_client.post(f"/expenses/{other_user_expense_id}/delete")
    assert _fetch_expense_row(other_user_expense_id) is not None, (
        "deleting another user's expense must not remove it"
    )


def test_post_delete_expense_nonexistent_id_returns_404(logged_in_client):
    response = logged_in_client.post("/expenses/999999/delete")
    assert response.status_code == 404


# ======================================================================= #
# Route: GET /expenses/<id>/delete -- not allowed                         #
# ======================================================================= #


def test_get_delete_expense_returns_405(logged_in_client, demo_expense_id):
    response = logged_in_client.get(f"/expenses/{demo_expense_id}/delete")
    assert response.status_code == 405


def test_get_delete_expense_unauthenticated_returns_405(client, demo_expense_id):
    response = client.get(f"/expenses/{demo_expense_id}/delete")
    assert response.status_code == 405


# ======================================================================= #
# Definition of done: profile page delete form                            #
# ======================================================================= #


def test_profile_transaction_row_has_delete_form_to_correct_url(
    logged_in_client, demo_expense_id
):
    body = logged_in_client.get("/profile").get_data(as_text=True)
    assert f"/expenses/{demo_expense_id}/delete" in body, (
        "expected the profile page's transaction row to have a delete form/link "
        "posting to the correct delete URL"
    )
