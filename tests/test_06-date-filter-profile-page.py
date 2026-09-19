"""
Tests for Step 6 (Date Filter for Profile Page): see
.claude/specs/06-date-filter-profile-page.md.

Scope
-----
The spec adds NO new routes: `GET /profile` gains two optional query
params, `date_from` / `date_to` (ISO `YYYY-MM-DD`, inclusive bounds), that
are threaded through the three existing `database/queries.py` helpers
(`get_summary_stats`, `get_recent_transactions`, `get_category_breakdown`).

These tests are written strictly from the spec, not from reading
`app.py`'s `profile()` body or the SQL in `database/queries.py`. The only
implementation detail relied on is `database/db.py`'s `seed_db()`, which
the task explicitly says to read: it inserts 8 expenses for the demo user,
all dated in the *current* calendar month on fixed days (01, 02, 05, 08,
10, 12, 14, 18). Those (day, category, amount, description) tuples are
reproduced below as an independent ground truth so expected totals/counts
can be computed in this file rather than copied from query results.

All "preset" date-window math (this month / last 3 months / last 6 months
/ all time) is (re)computed here from `date.today()` using plain
`datetime`/`calendar` arithmetic, independent of any private helper in
`app.py`, so the suite stays correct regardless of which day it runs on.

Spec behaviours covered:
- No query params => unfiltered (Step 5 baseline) view.
- Each of the four presets: This Month, Last 3 Months, Last 6 Months, All
  Time.
- A valid custom `date_from`/`date_to` range.
- An empty-result range: 0 transactions, ₹0.00 total, empty breakdown, no
  errors.
- Auth guard: unauthenticated `GET /profile` is rejected.
- Validation: malformed date strings and a `date_from > date_to` range both
  fall back to the unfiltered view; the latter also flashes the exact
  message "Start date must be before end date." (quoted verbatim in the
  spec).
- DB-layer: `get_summary_stats` / `get_recent_transactions` /
  `get_category_breakdown` filter correctly by date range, and behave
  identically to their unfiltered (Step 5) form when both dates are
  omitted.
"""

import calendar
from datetime import date

import pytest

from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# --------------------------------------------------------------------- #
# Ground truth: database/db.py's seed_db() demo-user expenses           #
# (day-of-month, category, amount, description), all in the current     #
# calendar month.                                                       #
# --------------------------------------------------------------------- #

SEED_EXPENSES = [
    (1, "Bills", 60.00, "Internet bill"),
    (2, "Food", 12.50, "Groceries"),
    (5, "Transport", 25.00, "Gas"),
    (8, "Entertainment", 15.00, "Movie ticket"),
    (10, "Health", 45.00, "Pharmacy"),
    (12, "Shopping", 89.99, "New shoes"),
    (14, "Food", 8.75, "Lunch"),
    (18, "Other", 20.00, "Misc"),
]

TODAY = date.today()
YM = TODAY.strftime("%Y-%m")


def _date_str(day):
    return f"{YM}-{day:02d}"


def _category_totals(rows):
    totals = {}
    for _, category, amount, _ in rows:
        totals[category] = round(totals.get(category, 0.0) + amount, 2)
    return totals


def _top_category(rows):
    totals = _category_totals(rows)
    return max(totals, key=totals.get)


def _month_bounds(d):
    start = d.replace(day=1)
    end = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return start, end


def _add_months(d, delta):
    """Independent month-arithmetic helper (not imported from app.py)."""
    month_index = d.month - 1 + delta
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


THIS_MONTH_START, THIS_MONTH_END = _month_bounds(TODAY)
LAST_3_MONTHS_START = _add_months(TODAY, -3)
LAST_6_MONTHS_START = _add_months(TODAY, -6)
NEXT_MONTH_START, NEXT_MONTH_END = _month_bounds(_add_months(TODAY, 1))

# All seed rows are dated within the current month, so a full-month range
# (or "All Time") always includes every row.
ALL_TOTAL = round(sum(amount for _, _, amount, _ in SEED_EXPENSES), 2)
ALL_COUNT = len(SEED_EXPENSES)
ALL_TOP_CATEGORY = _top_category(SEED_EXPENSES)
ALL_DESCRIPTIONS = [desc for *_, desc in SEED_EXPENSES]
ALL_CATEGORIES = sorted({category for _, category, _, _ in SEED_EXPENSES})

# A "last N months ending today" range never pushes its lower bound past
# the start of the current month (3 or 6 months back always precedes it),
# so the only thing that can exclude a seed row is the upper bound, today.
ROWS_LE_TODAY = [row for row in SEED_EXPENSES if row[0] <= TODAY.day]
ROWS_GT_TODAY = [row for row in SEED_EXPENSES if row[0] > TODAY.day]

# A custom range fully inside the seed month, independent of "today":
# days 2-10 inclusive => Groceries, Gas, Movie ticket, Pharmacy.
CUSTOM_START_DAY, CUSTOM_END_DAY = 2, 10
CUSTOM_ROWS = [row for row in SEED_EXPENSES if CUSTOM_START_DAY <= row[0] <= CUSTOM_END_DAY]
CUSTOM_OUTSIDE_ROWS = [row for row in SEED_EXPENSES if row not in CUSTOM_ROWS]
CUSTOM_TOTAL = round(sum(amount for _, _, amount, _ in CUSTOM_ROWS), 2)
CUSTOM_COUNT = len(CUSTOM_ROWS)
CUSTOM_TOP_CATEGORY = _top_category(CUSTOM_ROWS)
CUSTOM_CATEGORIES = sorted({category for _, category, _, _ in CUSTOM_ROWS})
CUSTOM_EXCLUDED_CATEGORIES = sorted(
    {category for _, category, _, _ in CUSTOM_OUTSIDE_ROWS} - set(CUSTOM_CATEGORIES)
)


# ======================================================================= #
# DB layer: database/queries.py date-range filtering                      #
# ======================================================================= #


def test_get_summary_stats_no_dates_returns_unfiltered_totals(demo_user_id):
    stats = get_summary_stats(demo_user_id)
    assert stats["total_spent"] == ALL_TOTAL
    assert stats["transaction_count"] == ALL_COUNT
    assert stats["top_category"] == ALL_TOP_CATEGORY


def test_get_summary_stats_explicit_none_matches_omitted_args(demo_user_id):
    assert get_summary_stats(demo_user_id, None, None) == get_summary_stats(demo_user_id)


def test_get_summary_stats_full_month_range_matches_unfiltered(demo_user_id):
    stats = get_summary_stats(
        demo_user_id, THIS_MONTH_START.isoformat(), THIS_MONTH_END.isoformat()
    )
    assert stats["total_spent"] == ALL_TOTAL
    assert stats["transaction_count"] == ALL_COUNT
    assert stats["top_category"] == ALL_TOP_CATEGORY


def test_get_summary_stats_custom_range_filters_totals(demo_user_id):
    stats = get_summary_stats(
        demo_user_id, date_from=_date_str(CUSTOM_START_DAY), date_to=_date_str(CUSTOM_END_DAY)
    )
    assert stats["total_spent"] == CUSTOM_TOTAL
    assert stats["transaction_count"] == CUSTOM_COUNT
    assert stats["top_category"] == CUSTOM_TOP_CATEGORY


def test_get_summary_stats_empty_range_returns_zero(demo_user_id):
    stats = get_summary_stats(
        demo_user_id,
        date_from=NEXT_MONTH_START.isoformat(),
        date_to=NEXT_MONTH_END.isoformat(),
    )
    assert stats["total_spent"] == 0.0
    assert stats["transaction_count"] == 0


def test_get_summary_stats_empty_user_with_range_returns_zero(empty_user_id):
    stats = get_summary_stats(
        empty_user_id,
        date_from=THIS_MONTH_START.isoformat(),
        date_to=THIS_MONTH_END.isoformat(),
    )
    assert stats["total_spent"] == 0.0
    assert stats["transaction_count"] == 0


def test_get_recent_transactions_no_dates_returns_all(demo_user_id):
    transactions = get_recent_transactions(demo_user_id)
    assert len(transactions) == ALL_COUNT
    assert {t["description"] for t in transactions} == set(ALL_DESCRIPTIONS)


def test_get_recent_transactions_custom_range_returns_only_in_range_rows(demo_user_id):
    transactions = get_recent_transactions(
        demo_user_id,
        date_from=_date_str(CUSTOM_START_DAY),
        date_to=_date_str(CUSTOM_END_DAY),
    )
    assert len(transactions) == CUSTOM_COUNT
    assert {t["description"] for t in transactions} == {desc for *_, desc in CUSTOM_ROWS}


def test_get_recent_transactions_empty_range_returns_empty_list(demo_user_id):
    transactions = get_recent_transactions(
        demo_user_id,
        date_from=NEXT_MONTH_START.isoformat(),
        date_to=NEXT_MONTH_END.isoformat(),
    )
    assert transactions == []


def test_get_recent_transactions_limit_respected_within_range(demo_user_id):
    transactions = get_recent_transactions(
        demo_user_id,
        limit=1,
        date_from=_date_str(CUSTOM_START_DAY),
        date_to=_date_str(CUSTOM_END_DAY),
    )
    assert len(transactions) == 1
    assert transactions[0]["description"] in {desc for *_, desc in CUSTOM_ROWS}


def test_get_category_breakdown_no_dates_includes_every_category(demo_user_id):
    breakdown = get_category_breakdown(demo_user_id)
    assert sorted(c["name"] for c in breakdown) == ALL_CATEGORIES
    assert sum(c["pct"] for c in breakdown) == 100


def test_get_category_breakdown_custom_range_only_includes_range_categories(demo_user_id):
    breakdown = get_category_breakdown(
        demo_user_id,
        date_from=_date_str(CUSTOM_START_DAY),
        date_to=_date_str(CUSTOM_END_DAY),
    )
    assert sorted(c["name"] for c in breakdown) == CUSTOM_CATEGORIES
    assert sum(c["pct"] for c in breakdown) == 100

    expected_amounts = _category_totals(CUSTOM_ROWS)
    actual_amounts = {c["name"]: c["amount"] for c in breakdown}
    for category, expected_amount in expected_amounts.items():
        assert actual_amounts[category] == pytest.approx(expected_amount)


def test_get_category_breakdown_empty_range_returns_empty_list(demo_user_id):
    breakdown = get_category_breakdown(
        demo_user_id,
        date_from=NEXT_MONTH_START.isoformat(),
        date_to=NEXT_MONTH_END.isoformat(),
    )
    assert breakdown == []


def test_get_category_breakdown_empty_user_returns_empty_list(empty_user_id):
    assert get_category_breakdown(empty_user_id) == []


def test_query_helpers_agree_between_omitted_and_none_date_args(demo_user_id):
    """Spec: 'when date_from and date_to are both absent, all three query
    helpers must behave identically to their Step 5 (unfiltered) behaviour.'
    """
    assert get_summary_stats(demo_user_id) == get_summary_stats(demo_user_id, None, None)
    assert get_recent_transactions(demo_user_id) == get_recent_transactions(
        demo_user_id, date_from=None, date_to=None
    )
    assert get_category_breakdown(demo_user_id) == get_category_breakdown(
        demo_user_id, None, None
    )


# ======================================================================= #
# Route: GET /profile — auth guard                                        #
# ======================================================================= #


def test_profile_unauthenticated_redirects_to_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_unauthenticated_with_filter_params_still_redirects(client):
    response = client.get(
        f"/profile?date_from={THIS_MONTH_START.isoformat()}&date_to={THIS_MONTH_END.isoformat()}"
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ======================================================================= #
# Route: GET /profile — happy paths                                       #
# ======================================================================= #


def test_profile_no_query_params_shows_unfiltered_data(logged_in_client):
    response = logged_in_client.get("/profile")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for desc in ALL_DESCRIPTIONS:
        assert desc in body, f"expected unfiltered view to include '{desc}'"
    assert "₹" in body


def test_profile_all_time_preset_is_a_clean_url_and_shows_everything(logged_in_client):
    # Spec: "The 'All Time' preset must pass no query params (clean /profile
    # URL)". Simulate arriving from a narrowed view, then clearing the filter.
    logged_in_client.get(
        f"/profile?date_from={_date_str(CUSTOM_START_DAY)}&date_to={_date_str(CUSTOM_END_DAY)}"
    )
    response = logged_in_client.get("/profile")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for desc in ALL_DESCRIPTIONS:
        assert desc in body


@pytest.mark.parametrize(
    "label, date_from, date_to, included_rows, excluded_rows",
    [
        (
            "this_month",
            THIS_MONTH_START.isoformat(),
            THIS_MONTH_END.isoformat(),
            SEED_EXPENSES,
            [],
        ),
        (
            "last_3_months",
            LAST_3_MONTHS_START.isoformat(),
            TODAY.isoformat(),
            ROWS_LE_TODAY,
            ROWS_GT_TODAY,
        ),
        (
            "last_6_months",
            LAST_6_MONTHS_START.isoformat(),
            TODAY.isoformat(),
            ROWS_LE_TODAY,
            ROWS_GT_TODAY,
        ),
    ],
)
def test_profile_preset_ranges_filter_visible_transactions(
    logged_in_client, label, date_from, date_to, included_rows, excluded_rows
):
    response = logged_in_client.get(f"/profile?date_from={date_from}&date_to={date_to}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    for *_, desc in included_rows:
        assert desc in body, f"[{label}] expected '{desc}' to be visible"
    for *_, desc in excluded_rows:
        assert desc not in body, f"[{label}] expected '{desc}' to be filtered out"


def test_profile_custom_range_filters_all_sections(logged_in_client):
    response = logged_in_client.get(
        f"/profile?date_from={_date_str(CUSTOM_START_DAY)}&date_to={_date_str(CUSTOM_END_DAY)}"
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    for *_, desc in CUSTOM_ROWS:
        assert desc in body, f"expected in-range '{desc}' to be visible"
    for *_, desc in CUSTOM_OUTSIDE_ROWS:
        assert desc not in body, f"expected out-of-range '{desc}' to be filtered out"

    for category in CUSTOM_EXCLUDED_CATEGORIES:
        assert category not in body, (
            f"expected out-of-range category '{category}' to be excluded"
            " from the breakdown"
        )


def test_profile_empty_result_range_shows_zero_state_without_errors(logged_in_client):
    response = logged_in_client.get(
        f"/profile?date_from={NEXT_MONTH_START.isoformat()}&date_to={NEXT_MONTH_END.isoformat()}"
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    # Spec DoD: "sees ₹0.00 total spent, 0 transactions, and an empty
    # category breakdown — no errors".
    assert "₹0.00" in body
    for desc in ALL_DESCRIPTIONS:
        assert desc not in body


def test_profile_empty_user_full_range_shows_zero_state(empty_logged_in_client):
    response = empty_logged_in_client.get("/profile")
    assert response.status_code == 200
    assert "₹0.00" in response.get_data(as_text=True)


# ======================================================================= #
# Route: GET /profile — validation                                        #
# ======================================================================= #


@pytest.mark.parametrize(
    "query_string",
    [
        f"date_from=not-a-date&date_to={_date_str(CUSTOM_END_DAY)}",
        f"date_from={_date_str(CUSTOM_START_DAY)}&date_to=also-not-a-date",
        "date_from=not-a-date&date_to=also-not-a-date",
        f"date_from={_date_str(CUSTOM_START_DAY)}",  # date_to entirely absent
        f"date_to={_date_str(CUSTOM_END_DAY)}",  # date_from entirely absent
        "date_from=&date_to=",  # both present but empty
        "date_from=2024-13-40&date_to=2024-01-01",  # out-of-range calendar values
        "date_from=1%27%20OR%20%271%27%3D%271&date_to=2024-01-01",  # injection-shaped junk (percent-encoded)
    ],
)
def test_profile_malformed_or_partial_dates_fall_back_to_unfiltered(
    logged_in_client, query_string
):
    response = logged_in_client.get(f"/profile?{query_string}")
    assert response.status_code == 200, "malformed date params must not crash the app"
    body = response.get_data(as_text=True)
    assert "Start date must be before end date." not in body
    for desc in ALL_DESCRIPTIONS:
        assert desc in body, f"expected fallback to unfiltered view for '{query_string}'"


def test_profile_start_after_end_flashes_error_and_falls_back(logged_in_client):
    response = logged_in_client.get(
        f"/profile?date_from={_date_str(CUSTOM_END_DAY)}&date_to={_date_str(CUSTOM_START_DAY)}"
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Start date must be before end date." in body
    for desc in ALL_DESCRIPTIONS:
        assert desc in body, "expected fallback to the unfiltered view after the flash"


def test_profile_start_equals_end_is_a_valid_single_day_range(logged_in_client):
    # date_from == date_to is a valid (non-empty) range, not a validation error.
    single_day = _date_str(CUSTOM_START_DAY)
    response = logged_in_client.get(f"/profile?date_from={single_day}&date_to={single_day}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Start date must be before end date." not in body
    single_day_descs = {desc for day, _, _, desc in SEED_EXPENSES if day == CUSTOM_START_DAY}
    for desc in single_day_descs:
        assert desc in body
