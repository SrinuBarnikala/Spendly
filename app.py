import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)
app.secret_key = "spendly-dev-secret-key"


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

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "March 2025",
    }

    stats = {
        "total_spent": "₹11,820.00",
        "transaction_count": 6,
        "top_category": "Bills",
    }

    transactions = [
        {"date": "2026-09-18", "description": "Groceries", "category": "Food", "amount": "₹1,250.00"},
        {"date": "2026-09-15", "description": "Cab to airport", "category": "Transport", "amount": "₹980.00"},
        {"date": "2026-09-10", "description": "Electricity bill", "category": "Bills", "amount": "₹4,500.00"},
        {"date": "2026-09-08", "description": "Pharmacy", "category": "Health", "amount": "₹760.00"},
        {"date": "2026-09-05", "description": "Movie night", "category": "Entertainment", "amount": "₹600.00"},
        {"date": "2026-09-02", "description": "New shoes", "category": "Shopping", "amount": "₹3,230.00"},
    ]

    categories = [
        {"category": "Food", "amount": "₹1,250.00", "percent": 16, "width_class": "w-20"},
        {"category": "Transport", "amount": "₹980.00", "percent": 13, "width_class": "w-10"},
        {"category": "Bills", "amount": "₹4,500.00", "percent": 30, "width_class": "w-30"},
        {"category": "Health", "amount": "₹760.00", "percent": 10, "width_class": "w-10"},
        {"category": "Entertainment", "amount": "₹600.00", "percent": 8, "width_class": "w-10"},
        {"category": "Shopping", "amount": "₹3,230.00", "percent": 17, "width_class": "w-20"},
        {"category": "Other", "amount": "₹500.00", "percent": 6, "width_class": "w-10"},
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
