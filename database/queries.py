from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?", [user_id]
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created_at.strftime("%B %Y"),
    }


def _date_range_clause(date_from, date_to):
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", [date_from, date_to]
    return "", []


def get_recent_transactions(user_id, limit=10, offset=0, date_from=None, date_to=None):
    conn = get_db()
    try:
        clause, extra = _date_range_clause(date_from, date_to)
        rows = conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + clause + " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
            [user_id, *extra, limit, offset],
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_transaction_count(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        clause, extra = _date_range_clause(date_from, date_to)
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM expenses WHERE user_id = ?" + clause,
            [user_id, *extra],
        ).fetchone()
    finally:
        conn.close()

    return row["count"]


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        clause, extra = _date_range_clause(date_from, date_to)
        totals_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE user_id = ?" + clause,
            [user_id, *extra],
        ).fetchone()

        top_row = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + clause
            + " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            [user_id, *extra],
        ).fetchone()
    finally:
        conn.close()

    top_category = top_row["category"] if top_row is not None else "—"

    return {
        "total_spent": float(totals_row["total"]),
        "transaction_count": totals_row["count"],
        "top_category": top_category,
    }


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        clause, extra = _date_range_clause(date_from, date_to)
        rows = conn.execute(
            "SELECT category, SUM(amount) AS amount FROM expenses "
            "WHERE user_id = ?" + clause + " GROUP BY category ORDER BY amount DESC",
            [user_id, *extra],
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    total = sum(row["amount"] for row in rows)

    breakdown = [
        {"name": row["category"], "amount": row["amount"], "pct": round(row["amount"] / total * 100)}
        for row in rows
    ]

    diff = 100 - sum(c["pct"] for c in breakdown)
    if diff:
        largest = max(breakdown, key=lambda c: c["amount"])
        largest["pct"] += diff

    return breakdown


def insert_expense(user_id, amount, category, expense_date, description):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_expense_by_id(expense_id, user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return {
        "id": row["id"],
        "amount": row["amount"],
        "category": row["category"],
        "date": row["date"],
        "description": row["description"],
    }


def update_expense(expense_id, user_id, amount, category, expense_date, description):
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? "
            "WHERE id = ? AND user_id = ?",
            (amount, category, expense_date, description, expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_expense(expense_id, user_id):
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
