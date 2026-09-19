"""
Tests for Step 5 (Backend Connection): the /profile route and its
database/queries.py helpers.

Fixtures (see conftest.py):
- demo_user_id / empty_user_id — seeded demo user vs. a freshly created
  user with zero expenses
- client / logged_in_client / empty_logged_in_client — Flask test client,
  optionally with session["user_id"] pre-set

Assertions here are computed from the fixture's actual seed data
(database/db.py's seed_db()), not hardcoded against the spec's stale
example numbers.
"""

from database import db as db_module
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


def test_get_user_by_id_returns_user(demo_user_id):
    user = get_user_by_id(demo_user_id)
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert user["member_since"]


def test_get_user_by_id_missing_user_returns_none(test_db):
    assert get_user_by_id(999999) is None


def test_profile_redirects_when_not_logged_in(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_ok_when_logged_in(logged_in_client):
    response = logged_in_client.get("/profile")
    assert response.status_code == 200


# ---- transaction history tests (subagent 1) ----


def test_get_recent_transactions_returns_ordered_results(demo_user_id):
    transactions = get_recent_transactions(demo_user_id)

    assert len(transactions) > 0

    dates = [t["date"] for t in transactions]
    assert dates == sorted(dates, reverse=True)

    for t in transactions:
        assert set(t.keys()) == {"date", "description", "category", "amount"}
        assert isinstance(t["amount"], (int, float))


def test_get_recent_transactions_empty_user_returns_empty_list(empty_user_id):
    assert get_recent_transactions(empty_user_id) == []


def test_profile_route_shows_seeded_transaction(logged_in_client):
    response = logged_in_client.get("/profile")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    seeded_descriptions = [
        "Groceries",
        "Lunch",
        "Gas",
        "Internet bill",
        "Pharmacy",
        "Movie ticket",
        "New shoes",
        "Misc",
    ]
    assert any(description in body for description in seeded_descriptions)


# ---- summary stats tests (subagent 2) ----


def test_get_summary_stats_demo_user(demo_user_id):
    # Computed from database/db.py's seed_db() sample_expenses:
    #   Food: 12.50 + 8.75 = 21.25
    #   Transport: 25.00
    #   Bills: 60.00
    #   Health: 45.00
    #   Entertainment: 15.00
    #   Shopping: 89.99  <- highest single-category total
    #   Other: 20.00
    # total = 21.25 + 25.00 + 60.00 + 45.00 + 15.00 + 89.99 + 20.00 = 276.24
    # count = 8 rows
    stats = get_summary_stats(demo_user_id)
    assert stats["total_spent"] == 276.24
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Shopping"


def test_get_summary_stats_empty_user(empty_user_id):
    stats = get_summary_stats(empty_user_id)
    assert stats["total_spent"] == 0.0
    assert stats["transaction_count"] == 0
    assert stats["top_category"] == "—"


def test_profile_route_ok_with_stats(logged_in_client):
    response = logged_in_client.get("/profile")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "₹" in body


# ---- category breakdown tests (subagent 3) ----


def test_get_category_breakdown_demo_user_ordered_and_sums_to_100(demo_user_id):
    breakdown = get_category_breakdown(demo_user_id)

    assert len(breakdown) > 0

    amounts = [c["amount"] for c in breakdown]
    assert amounts == sorted(amounts, reverse=True)

    assert sum(c["pct"] for c in breakdown) == 100


def test_get_category_breakdown_empty_user_returns_empty_list(empty_user_id):
    assert get_category_breakdown(empty_user_id) == []


def test_profile_route_shows_seeded_category(logged_in_client):
    response = logged_in_client.get("/profile")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    seeded_categories = [
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    ]
    assert any(category in body for category in seeded_categories)
