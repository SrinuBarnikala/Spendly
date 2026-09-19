"""
Tests for Step 7 (Add Expense): see .claude/specs/07-add-expense.md.

Scope
-----
`/expenses/add` gains a real GET+POST handler (previously a GET-only stub
returning a placeholder string). GET renders a form; POST validates
amount/category/date/description and either inserts a new row into
`expenses` and redirects to `/profile`, or re-renders the form with an
error and the submitted values retained.

The 7 fixed categories are reproduced here as an independent ground truth
(not imported from `database.db.CATEGORIES`) so the dropdown-completeness
assertion doesn't just check the implementation against itself.
"""

import pytest

from database.db import get_db
from database.queries import get_transaction_count, insert_expense

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def _fetch_expense(user_id, description):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND description = ?",
            (user_id, description),
        ).fetchone()
    finally:
        conn.close()


# ======================================================================= #
# DB layer: database/queries.py::insert_expense                          #
# ======================================================================= #


def test_insert_expense_creates_row_with_expected_values(demo_user_id):
    insert_expense(demo_user_id, 50.0, "Food", "2026-03-20", "Test Lunch Insert")

    row = _fetch_expense(demo_user_id, "Test Lunch Insert")
    assert row is not None
    assert row["user_id"] == demo_user_id
    assert row["amount"] == 50.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"


def test_insert_expense_with_no_description_stores_null(demo_user_id):
    insert_expense(demo_user_id, 12.0, "Bills", "2026-03-21", None)

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ?",
            (demo_user_id, "2026-03-21"),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["description"] is None


# ======================================================================= #
# Route: /expenses/add — auth guard                                      #
# ======================================================================= #


def test_get_add_expense_unauthenticated_redirects_to_login(client):
    response = client.get("/expenses/add")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_post_add_expense_unauthenticated_redirects_to_login(client):
    response = client.post(
        "/expenses/add",
        data={"amount": "10", "category": "Food", "date": "2026-03-20", "description": ""},
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ======================================================================= #
# Route: GET /expenses/add — happy path                                  #
# ======================================================================= #


def test_get_add_expense_authenticated_shows_form(logged_in_client):
    response = logged_in_client.get("/expenses/add")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "<form" in body
    assert 'method="POST"' in body
    for category in CATEGORIES:
        assert category in body
    assert body.count("<option") == len(CATEGORIES)


# ======================================================================= #
# Route: POST /expenses/add — happy paths                                #
# ======================================================================= #


def test_post_add_expense_valid_data_redirects_and_inserts_row(
    empty_logged_in_client, empty_user_id
):
    response = empty_logged_in_client.post(
        "/expenses/add",
        data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        },
    )
    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]

    row = _fetch_expense(empty_user_id, "Lunch")
    assert row is not None
    assert row["amount"] == 50.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"


def test_post_add_expense_no_description_succeeds_with_null(
    empty_logged_in_client, empty_user_id
):
    response = empty_logged_in_client.post(
        "/expenses/add",
        data={"amount": "20.0", "category": "Other", "date": "2026-03-22"},
    )
    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ?",
            (empty_user_id, "2026-03-22"),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["description"] is None


# ======================================================================= #
# Route: POST /expenses/add — validation                                 #
# ======================================================================= #

VALID_PAYLOAD = {
    "amount": "25.0",
    "category": "Food",
    "date": "2026-03-20",
    "description": "Snacks",
}

@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": ""},
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "abc"},
        {"category": "Groceries"},
        {"date": "not-a-date"},
        {"date": "2024-13-40"},
    ],
    ids=[
        "missing_amount",
        "zero_amount",
        "negative_amount",
        "non_numeric_amount",
        "invalid_category",
        "invalid_date",
        "out_of_range_date",
    ],
)
def test_post_add_expense_invalid_input_rerenders_with_error(
    empty_logged_in_client, empty_user_id, overrides
):
    payload = {**VALID_PAYLOAD, **overrides}

    before = get_transaction_count(empty_user_id)
    response = empty_logged_in_client.post("/expenses/add", data=payload)
    after = get_transaction_count(empty_user_id)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "auth-error" in body
    assert after == before
