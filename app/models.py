"""
SecureMoney — models.py
Database connection pool and all data-access functions.
All encryption/decryption happens HERE in the application layer — never in SQL.
"""

import base64
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from app.config import get_config
from app.crypto_utils import (
    generate_salt, hash_password, verify_password,
    encrypt_balance, decrypt_balance,
    encrypt_transaction_amount, decrypt_transaction_amount,
    encrypt_personal_info, decrypt_personal_info,
    generate_otp, hash_otp,
)

class _ConfigProxy:
    def __getattr__(self, name):
        return getattr(get_config(), name)


cfg = _ConfigProxy()

# ─── Connection Pool ──────────────────────────────────────────────────────────
_pool: Optional[MySQLConnectionPool] = None


def get_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = MySQLConnectionPool(
            pool_name="securemoney",
            pool_size=10,
            host=cfg.DB_HOST,
            port=cfg.DB_PORT,
            database=cfg.DB_NAME,
            user=cfg.DB_USER,
            password=cfg.DB_PASSWORD,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            autocommit=False,
            time_zone="+00:00",
        )
    return _pool


def get_conn():
    return get_pool().get_connection()


# ─── User Model ───────────────────────────────────────────────────────────────

class UserNotFoundError(Exception): pass
class UserExistsError(Exception): pass
class AuthenticationError(Exception): pass
class AdminAuthenticationError(Exception): pass


def create_user(full_name: str, email: str, phone: str, password: str) -> int:
    """
    Register a new user. Password is hashed with PBKDF2-HMAC-SHA256.
    A new account row is also created with an encrypted initial balance of 0.

    Returns the new user_id.
    Raises UserExistsError if email already exists.
    """
    salt = generate_salt()
    pwd_hash = hash_password(password, salt, cfg.PBKDF2_ITERATIONS)

    # Initial balance encrypted at rest
    balance_enc = encrypt_balance(0.0, cfg.MASTER_KEY, salt)

    # Generate unique account number (SM + timestamp suffix)
    account_number = _generate_account_number()

    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Check for duplicate email
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            raise UserExistsError(f"Email already registered: {email}")

        cursor.execute(
            """INSERT INTO users (full_name, email, phone, password_hash, salt, is_active, created_at)
               VALUES (%s, %s, %s, %s, %s, TRUE, NOW())""",
            (full_name, email, phone,
             base64.b64encode(pwd_hash).decode(),
             base64.b64encode(salt).decode()),
        )
        user_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO accounts (user_id, balance_encrypted, account_number)
               VALUES (%s, %s, %s)""",
            (user_id, balance_enc, account_number),
        )
        conn.commit()
        return user_id
    except mysql.connector.IntegrityError:
        conn.rollback()
        raise UserExistsError("Email already registered.")
    finally:
        cursor.close()
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[Dict]:
    """
    Verify credentials. Returns user dict on success, raises AuthenticationError on failure.
    Constant-time comparison prevents timing attacks.
    """
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, full_name, email, phone, password_hash, salt, is_active "
            "FROM users WHERE email = %s",
            (email,),
        )
        row = cursor.fetchone()
        if not row:
            # Still run hash to prevent timing oracle (user enumeration)
            dummy_salt = generate_salt()
            hash_password("dummy", dummy_salt)
            raise AuthenticationError("Invalid credentials.")

        if not row["is_active"]:
            raise AuthenticationError("Account is deactivated. Contact support.")

        salt = base64.b64decode(row["salt"])
        stored_hash = base64.b64decode(row["password_hash"])

        if not verify_password(password, salt, stored_hash, cfg.PBKDF2_ITERATIONS):
            raise AuthenticationError("Invalid credentials.")

        return {
            "user_id": row["user_id"],
            "full_name": row["full_name"],
            "email": row["email"],
            "phone": row["phone"],
        }
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, full_name, email, phone, is_active, created_at "
            "FROM users WHERE user_id = %s",
            (user_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict]:
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, full_name, email, phone, is_active FROM users WHERE email = %s",
            (email,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


# ─── Account / Balance ────────────────────────────────────────────────────────

def get_account(user_id: int) -> Optional[Dict]:
    """Return account info including DECRYPTED balance."""
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT a.account_id, a.account_number, a.balance_encrypted, u.salt "
            "FROM accounts a JOIN users u ON a.user_id = u.user_id "
            "WHERE a.user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        salt = base64.b64decode(row["salt"])
        balance = decrypt_balance(row["balance_encrypted"], cfg.MASTER_KEY, salt)
        return {
            "account_id": row["account_id"],
            "account_number": row["account_number"],
            "balance": balance,
        }
    finally:
        cursor.close()
        conn.close()


def _update_balance(cursor, user_id: int, new_balance: float, salt: bytes):
    """Internal: update encrypted balance within an existing transaction."""
    enc = encrypt_balance(new_balance, cfg.MASTER_KEY, salt)
    cursor.execute(
        "UPDATE accounts SET balance_encrypted = %s WHERE user_id = %s",
        (enc, user_id),
    )


def _get_salt(cursor, user_id: int) -> bytes:
    cursor.execute("SELECT salt FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    return base64.b64decode(row[0])


# ─── Transactions ─────────────────────────────────────────────────────────────

class InsufficientFundsError(Exception): pass
class TransferError(Exception): pass


def transfer_funds(sender_id: int, receiver_account_number: str, amount: float, description: str = "") -> int:
    """
    Atomically transfer funds between two users.
    Amount is encrypted at rest. Entire operation runs in a single DB transaction.

    Returns the new txn_id.
    Raises InsufficientFundsError, TransferError.
    """
    if amount <= 0:
        raise TransferError("Transfer amount must be positive.")
    if amount > 10_000_000:
        raise TransferError("Transfer amount exceeds maximum limit.")

    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)

        # Lock sender row
        cursor.execute(
            "SELECT u.user_id, u.salt, a.balance_encrypted, a.account_id "
            "FROM users u JOIN accounts a ON u.user_id = a.user_id "
            "WHERE u.user_id = %s FOR UPDATE",
            (sender_id,),
        )
        sender = cursor.fetchone()
        if not sender:
            raise TransferError("Sender account not found.")

        # Find receiver by account number
        cursor.execute(
            "SELECT u.user_id, u.salt, a.balance_encrypted, a.account_id "
            "FROM users u JOIN accounts a ON u.user_id = a.user_id "
            "WHERE a.account_number = %s FOR UPDATE",
            (receiver_account_number,),
        )
        receiver = cursor.fetchone()
        if not receiver:
            raise TransferError("Recipient account number not found.")

        if sender["user_id"] == receiver["user_id"]:
            raise TransferError("Cannot transfer to your own account.")

        sender_salt   = base64.b64decode(sender["salt"])
        receiver_salt = base64.b64decode(receiver["salt"])

        sender_balance   = decrypt_balance(sender["balance_encrypted"],   cfg.MASTER_KEY, sender_salt)
        receiver_balance = decrypt_balance(receiver["balance_encrypted"], cfg.MASTER_KEY, receiver_salt)

        if sender_balance < amount:
            raise InsufficientFundsError(
                f"Insufficient funds. Available: TZS {sender_balance:,.2f}"
            )

        # Update balances (encrypted)
        _update_balance(cursor, sender_id,            sender_balance - amount,   sender_salt)
        _update_balance(cursor, receiver["user_id"],  receiver_balance + amount, receiver_salt)

        # Encrypt the transaction amount with a fresh per-transaction salt
        txn_salt = generate_salt()
        amount_enc = encrypt_transaction_amount(amount, cfg.MASTER_KEY, txn_salt)

        cursor.execute(
            """INSERT INTO transactions
               (sender_id, receiver_id, amount_encrypted, txn_salt, txn_type, description, status, timestamp)
               VALUES (%s, %s, %s, %s, 'TRANSFER', %s, 'COMPLETED', NOW())""",
            (sender_id, receiver["user_id"], amount_enc,
             base64.b64encode(txn_salt).decode(), description),
        )
        txn_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO audit_log (user_id, action, ip_address, timestamp) VALUES (%s, %s, %s, NOW())",
            (sender_id, f"TRANSFER: TZS {amount:,.2f} to {receiver_account_number} | txn#{txn_id}", "system"),
        )
        conn.commit()
        return txn_id
    except (InsufficientFundsError, TransferError):
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise TransferError(f"Transfer failed: {exc}") from exc
    finally:
        cursor.close()
        conn.close()


def pay_bill(user_id: int, biller_name: str, biller_ref: str, amount: float) -> int:
    """
    Simulate a bill payment by debiting the user's account.
    Returns new txn_id.
    """
    if amount <= 0:
        raise TransferError("Payment amount must be positive.")

    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT u.salt, a.balance_encrypted FROM users u "
            "JOIN accounts a ON u.user_id = a.user_id "
            "WHERE u.user_id = %s FOR UPDATE",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise TransferError("Account not found.")

        salt    = base64.b64decode(row["salt"])
        balance = decrypt_balance(row["balance_encrypted"], cfg.MASTER_KEY, salt)
        if balance < amount:
            raise InsufficientFundsError(f"Insufficient funds. Available: TZS {balance:,.2f}")

        _update_balance(cursor, user_id, balance - amount, salt)

        txn_salt   = generate_salt()
        amount_enc = encrypt_transaction_amount(amount, cfg.MASTER_KEY, txn_salt)
        description = f"Bill payment: {biller_name} | Ref: {biller_ref}"
        cursor.execute(
            """INSERT INTO transactions
               (sender_id, receiver_id, amount_encrypted, txn_salt, txn_type, description, status, timestamp)
               VALUES (%s, NULL, %s, %s, 'BILL_PAYMENT', %s, 'COMPLETED', NOW())""",
            (user_id, amount_enc, base64.b64encode(txn_salt).decode(), description),
        )
        txn_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO audit_log (user_id, action, ip_address, timestamp) VALUES (%s, %s, %s, NOW())",
            (user_id, f"BILL_PAYMENT: {biller_name} | Ref:{biller_ref} | TZS {amount:,.2f} | txn#{txn_id}", "system"),
        )
        conn.commit()
        return txn_id
    except (InsufficientFundsError, TransferError):
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise TransferError(str(exc)) from exc
    finally:
        cursor.close()
        conn.close()


def get_transaction_history(user_id: int, limit: int = 50) -> List[Dict]:
    """
    Return the last `limit` transactions for the user with amounts DECRYPTED.
    """
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT t.txn_id, t.sender_id, t.receiver_id, t.amount_encrypted,
                      t.txn_salt, t.txn_type, t.description, t.status, t.timestamp,
                      su.full_name AS sender_name, ru.full_name AS receiver_name
               FROM transactions t
               LEFT JOIN users su ON t.sender_id   = su.user_id
               LEFT JOIN users ru ON t.receiver_id = ru.user_id
               WHERE t.sender_id = %s OR t.receiver_id = %s
               ORDER BY t.timestamp DESC
               LIMIT %s""",
            (user_id, user_id, limit),
        )
        rows = cursor.fetchall()
        results = []
        for row in rows:
            try:
                txn_salt = base64.b64decode(row["txn_salt"])
                amount = decrypt_transaction_amount(
                    row["amount_encrypted"], cfg.MASTER_KEY, txn_salt
                )
            except Exception:
                amount = 0.0  # Fail safe — log this in production

            is_debit = row["sender_id"] == user_id
            results.append({
                "txn_id":        row["txn_id"],
                "type":          row["txn_type"],
                "description":   row["description"] or "",
                "amount":        amount,
                "is_debit":      is_debit,
                "status":        row["status"],
                "timestamp":     row["timestamp"],
                "counterparty":  row["receiver_name"] if is_debit else row["sender_name"],
            })
        return results
    finally:
        cursor.close()
        conn.close()


# ─── OTP ──────────────────────────────────────────────────────────────────────

def create_otp(user_id: int) -> str:
    """
    Generate and store a hashed OTP for the given user.
    Any existing unused OTPs for this user are invalidated first.
    Returns the plaintext OTP (to be sent via email/SMS — NOT stored).
    """
    otp   = generate_otp(cfg.OTP_LENGTH)
    salt  = generate_salt()
    h     = hash_otp(otp, salt)
    expires = datetime.utcnow() + timedelta(seconds=cfg.OTP_EXPIRY_SECONDS)

    conn = get_conn()
    try:
        cursor = conn.cursor()
        # Invalidate previous OTPs
        cursor.execute(
            "UPDATE otp_tokens SET is_used = TRUE WHERE user_id = %s AND is_used = FALSE",
            (user_id,),
        )
        cursor.execute(
            """INSERT INTO otp_tokens (user_id, token_hash, token_salt, expires_at, is_used)
               VALUES (%s, %s, %s, %s, FALSE)""",
            (user_id,
             base64.b64encode(h).decode(),
             base64.b64encode(salt).decode(),
             expires),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return otp


def verify_otp_token(user_id: int, otp_input: str) -> bool:
    """
    Verify a user-submitted OTP. Marks it as used if valid.
    Returns True on success, False on failure.
    """
    from app.crypto_utils import verify_otp as _verify
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT otp_id, token_hash, token_salt, expires_at
               FROM otp_tokens
               WHERE user_id = %s AND is_used = FALSE
               ORDER BY expires_at DESC LIMIT 1""",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False
        if datetime.utcnow() > row["expires_at"]:
            return False

        salt   = base64.b64decode(row["token_salt"])
        stored = base64.b64decode(row["token_hash"])
        if not _verify(otp_input, salt, stored):
            return False

        # Mark as used (prevent replay)
        cursor.execute(
            "UPDATE otp_tokens SET is_used = TRUE WHERE otp_id = %s",
            (row["otp_id"],),
        )
        conn.commit()
        return True
    finally:
        cursor.close()
        conn.close()


# ─── Audit Log ────────────────────────────────────────────────────────────────

def log_action(user_id: Optional[int], action: str, ip_address: str):
    """
    Append an immutable entry to the audit log.
    The audit_log table should be INSERT-only (no UPDATE/DELETE privileges for app user).
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_log (user_id, action, ip_address, timestamp) VALUES (%s, %s, %s, NOW())",
            (user_id, action[:500], ip_address[:45]),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_audit_log(limit: int = 200) -> List[Dict]:
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT al.log_id, al.user_id, u.email, al.action, al.ip_address, al.timestamp
               FROM audit_log al
               LEFT JOIN users u ON al.user_id = u.user_id
               ORDER BY al.timestamp DESC LIMIT %s""",
            (limit,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# Admins

def authenticate_admin(username: str, password: str) -> Dict:
    """
    Verify admin credentials from the separate admins table.
    Returns an admin dict on success, raises AdminAuthenticationError on failure.
    """
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT admin_id, username, password_hash, salt, role FROM admins WHERE username = %s",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            dummy_salt = generate_salt()
            hash_password("dummy", dummy_salt, cfg.PBKDF2_ITERATIONS)
            raise AdminAuthenticationError("Invalid admin credentials.")

        salt = base64.b64decode(row["salt"])
        stored_hash = base64.b64decode(row["password_hash"])
        if not verify_password(password, salt, stored_hash, cfg.PBKDF2_ITERATIONS):
            raise AdminAuthenticationError("Invalid admin credentials.")

        return {
            "admin_id": row["admin_id"],
            "username": row["username"],
            "role": row["role"],
        }
    finally:
        cursor.close()
        conn.close()


def get_admin_dashboard_stats() -> Dict[str, int]:
    """Return aggregate counts for the admin dashboard without decrypting balances."""
    conn = get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total_users FROM users")
        users = cursor.fetchone()["total_users"]
        cursor.execute("SELECT COUNT(*) AS active_users FROM users WHERE is_active = TRUE")
        active_users = cursor.fetchone()["active_users"]
        cursor.execute("SELECT COUNT(*) AS total_transactions FROM transactions")
        transactions = cursor.fetchone()["total_transactions"]
        cursor.execute("SELECT COUNT(*) AS audit_events FROM audit_log")
        audit_events = cursor.fetchone()["audit_events"]
        return {
            "total_users": users,
            "active_users": active_users,
            "total_transactions": transactions,
            "audit_events": audit_events,
        }
    finally:
        cursor.close()
        conn.close()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _generate_account_number() -> str:
    """Generate a unique 10-digit account number prefixed with SM."""
    import random
    return "SM" + "".join([str(random.randint(0, 9)) for _ in range(8)])
