"""
SecureMoney — tests/conftest.py
Pytest fixtures: Flask test app, test database, authenticated user sessions.
"""

import os
import sys
import tempfile
import secrets

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Set up test environment before any imports
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-pytest-conftest")
os.environ.setdefault("MASTER_KEY_HEX", secrets.token_hex(32))

import pytest
from app import create_app
from app.models import get_pool, get_conn
from app.crypto_utils import generate_salt, hash_password, encrypt_balance
import mysql.connector


@pytest.fixture(scope="session")
def test_db_config():
    """Return test database configuration."""
    return {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "securemoney_test",
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }


@pytest.fixture(scope="session", autouse=True)
def setup_test_db(test_db_config):
    """Create test database schema (runs once per session)."""
    # Update env vars for test database
    os.environ["DB_HOST"] = test_db_config["host"]
    os.environ["DB_PORT"] = str(test_db_config["port"])
    os.environ["DB_NAME"] = test_db_config["database"]
    os.environ["DB_USER"] = test_db_config["user"]
    os.environ["DB_PASSWORD"] = test_db_config["password"]

    # Create test database
    try:
        conn = mysql.connector.connect(
            host=test_db_config["host"],
            user=test_db_config["user"],
            password=test_db_config["password"],
            charset="utf8mb4",
        )
        cursor = conn.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS {test_db_config['database']}")
        cursor.execute(
            f"CREATE DATABASE {test_db_config['database']} "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        print(f"[WARN] Test DB setup skipped (MySQL not available): {e}")
        pytest.skip("MySQL not available")

    # Import schema
    with open(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "setup_db.sql"),
        "r",
        encoding="utf-8",
    ) as f:
        schema = f.read()

    conn = mysql.connector.connect(**test_db_config)
    cursor = conn.cursor()
    for statement in schema.split(";"):
        stmt = statement.strip()
        upper_stmt = stmt.upper()
        if "CREATE DATABASE" in upper_stmt or upper_stmt.startswith("USE "):
            continue
        if stmt:
            cursor.execute(stmt)
            if cursor.with_rows:
                cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()

    yield

    # Cleanup (optional)
    # conn = mysql.connector.connect(...)
    # cursor.execute(f"DROP DATABASE {test_db_config['database']}")


@pytest.fixture
def app():
    """Create Flask test app."""
    from app.config import DevelopmentConfig

    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,  # Disable CSRF in tests
        SESSION_COOKIE_SECURE=False,
    )
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Flask CLI test runner."""
    return app.test_cli_runner()


@pytest.fixture
def test_user():
    """Pre-created test user (persisted in test DB)."""
    from app.models import create_user

    try:
        user_id = create_user(
            full_name="Test User",
            email="test@securemoney.tz",
            phone="+255712000000",
            password="TestPass@2026!",
        )
        return {"user_id": user_id, "email": "test@securemoney.tz", "password": "TestPass@2026!"}
    except Exception:
        # User may already exist from previous test
        from app.models import get_user_by_email
        user = get_user_by_email("test@securemoney.tz")
        return {"user_id": user["user_id"], "email": "test@securemoney.tz", "password": "TestPass@2026!"}


@pytest.fixture
def test_user_2():
    """Second test user for transfers."""
    from app.models import create_user

    try:
        user_id = create_user(
            full_name="Test Recipient",
            email="recipient@securemoney.tz",
            phone="+255712000001",
            password="TestPass@2026!",
        )
        return {"user_id": user_id, "email": "recipient@securemoney.tz", "password": "TestPass@2026!"}
    except Exception:
        from app.models import get_user_by_email
        user = get_user_by_email("recipient@securemoney.tz")
        return {"user_id": user["user_id"], "email": "recipient@securemoney.tz", "password": "TestPass@2026!"}


@pytest.fixture
def authenticated_session(client, test_user):
    """
    Return a test client with authenticated session.
    Logs in test_user and returns (client, user_id, account_number).
    """
    from app.models import get_account, get_user_by_email

    # Login
    response = client.post(
        "/auth/login",
        data={"email": test_user["email"], "password": test_user["password"]},
        follow_redirects=False,
    )

    # Get OTP from session
    with client.session_transaction() as sess:
        pending_user_id = sess.get("pending_user_id")

    # Get user and account
    user = get_user_by_email(test_user["email"])
    account = get_account(user["user_id"])

    return client, user["user_id"], account["account_number"]


class TestDB:
    """Utility class for test database operations."""

    @staticmethod
    def clear_transactions():
        """Clear all transactions from test DB."""
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transactions")
            cursor.execute("ALTER TABLE transactions AUTO_INCREMENT = 1")
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def clear_users():
        """Clear all users and related data."""
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM otp_tokens")
            cursor.execute("DELETE FROM transactions")
            cursor.execute("DELETE FROM accounts")
            cursor.execute("DELETE FROM audit_log")
            cursor.execute("DELETE FROM users")
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def set_user_balance(user_id: int, amount: float):
        """Update a user's balance directly (for test setup)."""
        from app.models import get_account
        from app.config import get_config

        cfg = get_config()
        conn = get_conn()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT salt FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"User {user_id} not found")

            import base64

            salt = base64.b64decode(row["salt"])
            enc = encrypt_balance(amount, cfg.MASTER_KEY, salt)
            cursor.execute(
                "UPDATE accounts SET balance_encrypted = %s WHERE user_id = %s",
                (enc, user_id),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()


@pytest.fixture
def testdb():
    """Access to test database utilities."""
    return TestDB
