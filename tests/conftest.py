import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import app as app_module
from database import db as db_module
from database.db import init_db, seed_db


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_expense_tracker.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    init_db()
    seed_db()
    return db_module


@pytest.fixture
def demo_user_id(test_db):
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
    finally:
        conn.close()
    return row["id"]


@pytest.fixture
def empty_user_id(test_db):
    conn = db_module.get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Empty User", "empty@spendly.com", "not-a-real-hash"),
        )
        conn.commit()
        user_id = cursor.lastrowid
    finally:
        conn.close()
    return user_id


@pytest.fixture
def client(test_db):
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def logged_in_client(client, demo_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = demo_user_id
        sess["user_name"] = "Demo User"
    return client


@pytest.fixture
def empty_logged_in_client(client, empty_user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = empty_user_id
        sess["user_name"] = "Empty User"
    return client
