#!/usr/bin/env python3
"""
SecureMoney — scripts/seed_demo.py
Seed the database with demo users using the actual crypto engine.
Run from the project root: python scripts/seed_demo.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Validate env before importing models
required = ["SECRET_KEY", "MASTER_KEY_HEX"]
for k in required:
    if not os.getenv(k):
        print(f"ERROR: {k} not set in .env"); sys.exit(1)

import base64
import mysql.connector
from app.config import get_config
from app.crypto_utils import (
    generate_salt, hash_password,
    encrypt_balance, generate_otp,
)

cfg = get_config()

conn = mysql.connector.connect(
    host=cfg.DB_HOST, port=cfg.DB_PORT, database=cfg.DB_NAME,
    user=cfg.DB_USER, password=cfg.DB_PASSWORD, autocommit=False,
)
cur = conn.cursor()


def seed_user(full_name, email, phone, password, initial_balance, account_number):
    cur.execute(
        "SELECT u.user_id FROM users u "
        "JOIN accounts a ON a.user_id = u.user_id "
        "WHERE a.account_number = %s",
        (account_number,),
    )
    existing = cur.fetchone()

    salt     = generate_salt()
    pwd_hash = hash_password(password, salt, cfg.PBKDF2_ITERATIONS)
    bal_enc  = encrypt_balance(initial_balance, cfg.MASTER_KEY, salt)

    if existing:
        user_id = existing[0]
        cur.execute(
            "UPDATE users SET full_name = %s, email = %s, phone = %s, "
            "password_hash = %s, salt = %s, is_active = TRUE WHERE user_id = %s",
            (full_name, email, phone,
             base64.b64encode(pwd_hash).decode(),
             base64.b64encode(salt).decode(),
             user_id),
        )
        cur.execute(
            "UPDATE accounts SET balance_encrypted = %s WHERE user_id = %s",
            (bal_enc, user_id),
        )
        print(f"  [OK]   Updated user: {email} | Balance: TZS {initial_balance:,.2f} | Acc: {account_number}")
        return

    cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        print(f"  [SKIP] User already exists with different account: {email}")
        return

    cur.execute(
        "INSERT INTO users (full_name, email, phone, password_hash, salt, is_active) "
        "VALUES (%s, %s, %s, %s, %s, TRUE)",
        (full_name, email, phone,
         base64.b64encode(pwd_hash).decode(),
         base64.b64encode(salt).decode()),
    )
    user_id = cur.lastrowid
    cur.execute(
        "INSERT INTO accounts (user_id, balance_encrypted, account_number) VALUES (%s, %s, %s)",
        (user_id, bal_enc, account_number),
    )
    print(f"  [OK]   Created user: {email} | Balance: TZS {initial_balance:,.2f} | Acc: {account_number}")
    return user_id


def seed_admin(username, password, role="superadmin"):
    cur.execute("SELECT admin_id FROM admins WHERE username = %s", (username,))
    row = cur.fetchone()
    salt     = generate_salt()
    pwd_hash = hash_password(password, salt, cfg.PBKDF2_ITERATIONS)

    if row:
        cur.execute(
            "UPDATE admins SET password_hash = %s, salt = %s, role = %s WHERE username = %s",
            (
                base64.b64encode(pwd_hash).decode(),
                base64.b64encode(salt).decode(),
                role,
                username,
            ),
        )
        print(f"  [OK]   Refreshed admin credentials: {username} | Role: {role}")
        return

    cur.execute(
        "INSERT INTO admins (username, password_hash, salt, role) VALUES (%s, %s, %s, %s)",
        (username,
         base64.b64encode(pwd_hash).decode(),
         base64.b64encode(salt).decode(),
         role),
    )
    print(f"  [OK]   Created admin: {username} | Role: {role}")


print("\n=== SecureMoney Demo Data Seed ===\n")
print("Seeding users...")

seed_user("Esau Magaro",  "Esau.magaro@securemoney.tz", "+255712000001", "Esau.magaro", 500_000.0, "SM10000001")
seed_user("Jane Smith",   "jane.smith@securemoney.tz", "+255712000002", "TestPass@2026!", 250_000.0, "SM10000002")
seed_user("Bob Mwangi",   "bob.mwangi@securemoney.tz", "+255712000003", "TestPass@2026!", 100_000.0, "SM10000003")
seed_user("Esau Tanzania", "esau.tz@securemoney.tz",   "+255712000004", "Esau@2026!", 1_000_000.0, "SM10000004")

print("\nSeeding admins...")
seed_admin("admin", "Admin@SecureMoney2026!", "superadmin")

conn.commit()
cur.close()
conn.close()

print("\nSeed complete.")
print("\nDemo credentials:")
print("  User:   Esau.magaro@securemoney.tz / Esau.magaro")
print("  User:   jane.smith@securemoney.tz / TestPass@2026!")
print("  Admin:  admin / Admin@SecureMoney2026!")
print()
