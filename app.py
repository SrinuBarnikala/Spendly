import calendar
import math
import sqlite3
from datetime import date, datetime

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import CATEGORIES, get_db, get_user_by_email, init_db, seed_db
from database.queries import get_user_by_id
from database.queries import get_recent_transactions
from database.queries import get_summary_stats
from database.queries import get_category_breakdown
from database.queries import get_transaction_count
from database.queries import insert_expense
from database.queries import get_expense_by_id
from database.queries import update_expense

app = Flask(__name__)
app.secret_key = "spendly-dev-secret-key"

TRANSACTIONS_PER_PAGE = 10


def format_currency(amount):
    return f"₹{amount:,.2f}"


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _months_before(anchor, months):
    """Returns the date `months` months before `anchor`, clamping the day
    to the target month's length (e.g. Mar 31 minus 1 month -> Feb 28)."""
    month_index = anchor.month - 1 - months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _resolve_date_filters(today, date_from_arg, date_to_arg):
    """Parses/validates date_from & date_to query args into (date_from,
    date_to, filters) for the profile page, flashing an error and falling
    back to unfiltered when the range is invalid."""
    raw_from = _parse_iso_date(date_from_arg)
    raw_to = _parse_iso_date(date_to_arg)

    if raw_from and raw_to and raw_from > raw_to:
        flash("Start date must be before end date.", "error")
        raw_from, raw_to = None, None

    has_range = bool(raw_from and raw_to)
    date_from = raw_from.isoformat() if has_range else None
    date_to = raw_to.isoformat() if has_range else None

    this_month_start = today.replace(day=1)
    this_month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    last_3_start = _months_before(today, 3)
    last_6_start = _months_before(today, 6)

    if not has_range:
        active_preset = "all_time"
    elif raw_from == this_month_start and raw_to == this_month_end:
        active_preset = "this_month"
    elif raw_from == last_3_start and raw_to == today:
        active_preset = "last_3_months"
    elif raw_from == last_6_start and raw_to == today:
        active_preset = "last_6_months"
    else:
        active_preset = "custom"

    filters = {
        "date_from": date_from,
        "date_to": date_to,
        "active": active_preset,
        "this_month": {
            "date_from": this_month_start.isoformat(),
            "date_to": this_month_end.isoformat(),
        },
        "last_3_months": {
            "date_from": last_3_start.isoformat(),
            "date_to": today.isoformat(),
        },
        "last_6_months": {
            "date_from": last_6_start.isoformat(),
            "date_to": today.isoformat(),
        },
    }

    return date_from, date_to, filters


def _resolve_pagination(page_arg, total_transactions):
    """Parses the page query arg and computes (page, offset, pagination)
    for the profile page's transaction list, clamping to a valid range."""
    try:
        page = int((page_arg or "1")[:10])
    except ValueError:
        page = 1
    if page < 1:
        page = 1

    total_pages = max(1, math.ceil(total_transactions / TRANSACTIONS_PER_PAGE))
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * TRANSACTIONS_PER_PAGE

    def _page_param(p):
        return None if p == 1 else p

    pagination = {
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": _page_param(page - 1),
        "next_page": _page_param(page + 1),
    }

    return page, offset, pagination


def _read_expense_form():
    """Reads and normalizes expense form fields from the current request."""
    return {
        "amount": request.form.get("amount", "").strip(),
        "category": request.form.get("category", "").strip(),
        "date": request.form.get("date", "").strip(),
        "description": request.form.get("description", "").strip()[:200],
    }


def _validate_expense_form(amount_raw, category, date_raw):
    """Validates the add-expense form fields, returning an error message,
    or None if the form is valid."""
    try:
        amount = float(amount_raw)
    except ValueError:
        return "Please enter a valid amount."
    if not math.isfinite(amount) or amount <= 0:
        return "Amount must be greater than 0."

    if category not in CATEGORIES:
        return "Please select a valid category."

    if _parse_iso_date(date_raw) is None:
        return "Please enter a valid date."

    return None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or not password:
        return render_template(
            "register.html", error="Please fill in all fields.", name=name, email=email
        )

    if len(password) < 8:
        return render_template(
            "register.html",
            error="Password must be at least 8 characters.",
            name=name,
            email=email,
        )

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            return render_template(
                "register.html",
                error="An account with this email already exists.",
                name=name,
                email=email,
            )

        password_hash = generate_password_hash(password)
        try:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return render_template(
                "register.html",
                error="An account with this email already exists.",
                name=name,
                email=email,
            )

        return redirect(url_for("login"))
    finally:
        conn.close()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.")

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_row = get_user_by_id(session["user_id"])
    if user_row is None:
        session.clear()
        return redirect(url_for("login"))

    name_parts = user_row["name"].split()
    if len(name_parts) >= 2:
        initials = (name_parts[0][0] + name_parts[1][0]).upper()
    else:
        initials = user_row["name"][:2].upper()

    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": initials,
        "member_since": user_row["member_since"],
    }

    date_from, date_to, filters = _resolve_date_filters(
        date.today(), request.args.get("date_from"), request.args.get("date_to")
    )

    raw_stats = get_summary_stats(session["user_id"], date_from, date_to)
    stats = {
        "total_spent": format_currency(raw_stats["total_spent"]),
        "transaction_count": raw_stats["transaction_count"],
        "top_category": raw_stats["top_category"],
    }

    total_transactions = get_transaction_count(session["user_id"], date_from, date_to)
    _, offset, pagination = _resolve_pagination(
        request.args.get("page"), total_transactions
    )

    transactions = [
        {
            "id": t["id"],
            "date": t["date"],
            "description": t["description"],
            "category": t["category"],
            "amount": format_currency(t["amount"]),
        }
        for t in get_recent_transactions(
            session["user_id"],
            limit=TRANSACTIONS_PER_PAGE,
            offset=offset,
            date_from=date_from,
            date_to=date_to,
        )
    ]

    categories = []
    for c in get_category_breakdown(session["user_id"], date_from, date_to):
        width = max(10, (c["pct"] // 10) * 10)
        categories.append(
            {
                "category": c["name"],
                "amount": format_currency(c["amount"]),
                "percent": c["pct"],
                "width_class": f"w-{width}",
            }
        )

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        filters=filters,
        pagination=pagination,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        form = {
            "amount": "",
            "category": "",
            "date": date.today().isoformat(),
            "description": "",
        }
        return render_template("add_expense.html", categories=CATEGORIES, form=form)

    form = _read_expense_form()

    error = _validate_expense_form(form["amount"], form["category"], form["date"])
    if error:
        return render_template(
            "add_expense.html", categories=CATEGORIES, form=form, error=error
        )

    description = form["description"] or None
    insert_expense(
        session["user_id"], float(form["amount"]), form["category"], form["date"], description
    )
    flash("Expense added.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "GET":
        form = {
            "amount": expense["amount"],
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"] or "",
        }
        return render_template(
            "edit_expense.html", categories=CATEGORIES, form=form, expense_id=expense["id"]
        )

    form = _read_expense_form()

    error = _validate_expense_form(form["amount"], form["category"], form["date"])
    if error:
        return render_template(
            "edit_expense.html",
            categories=CATEGORIES,
            form=form,
            expense_id=expense["id"],
            error=error,
        )

    description = form["description"] or None
    update_expense(
        expense["id"],
        session["user_id"],
        float(form["amount"]),
        form["category"],
        form["date"],
        description,
    )
    flash("Expense updated.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
