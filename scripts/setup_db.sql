-- ═══════════════════════════════════════════════════════════════════════════
--  SecureMoney — Database Schema
--  MySQL 8.0  |  Character Set: utf8mb4  |  Collation: utf8mb4_unicode_ci
--  Run: mysql -u root -p < scripts/setup_db.sql
-- ═══════════════════════════════════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS securemoney
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE securemoney;

-- ─── Users ──────────────────────────────────────────────────────────────────
-- Passwords are NEVER stored in plaintext.
-- password_hash = PBKDF2-HMAC-SHA256 (600,000 iterations), base64-encoded.
-- salt          = 256-bit random salt, base64-encoded.
CREATE TABLE IF NOT EXISTS users (
    user_id       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    full_name     VARCHAR(120)  NOT NULL,
    email         VARCHAR(254)  NOT NULL UNIQUE,
    phone         VARCHAR(20)   NOT NULL,
    password_hash VARCHAR(128)  NOT NULL COMMENT 'PBKDF2-HMAC-SHA256, base64',
    salt          VARCHAR(64)   NOT NULL COMMENT '256-bit random salt, base64',
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── Accounts ───────────────────────────────────────────────────────────────
-- balance_encrypted = AES-256-GCM ciphertext of the balance float, base64.
-- Decryption occurs in the application layer ONLY — never via SQL functions.
CREATE TABLE IF NOT EXISTS accounts (
    account_id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id           INT UNSIGNED NOT NULL,
    account_number    VARCHAR(12)  NOT NULL UNIQUE COMMENT 'Format: SM########',
    balance_encrypted TEXT         NOT NULL COMMENT 'AES-256-GCM, base64(nonce+ct+tag)',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    INDEX idx_account_number (account_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── Transactions ────────────────────────────────────────────────────────────
-- amount_encrypted = AES-256-GCM ciphertext of the transaction amount.
-- txn_salt         = per-transaction salt used to derive the encryption key.
-- nonce and auth_tag are embedded inside amount_encrypted (wire format).
CREATE TABLE IF NOT EXISTS transactions (
    txn_id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    sender_id        INT UNSIGNED     NULL COMMENT 'NULL for system credit',
    receiver_id      INT UNSIGNED     NULL COMMENT 'NULL for bill payment / debit',
    amount_encrypted TEXT         NOT NULL COMMENT 'AES-256-GCM, base64(nonce+ct+tag)',
    txn_salt         VARCHAR(64)  NOT NULL COMMENT 'Per-txn salt for key derivation, base64',
    txn_type         ENUM('TRANSFER','BILL_PAYMENT','DEPOSIT','WITHDRAWAL') NOT NULL,
    description      VARCHAR(255)     NULL,
    status           ENUM('PENDING','COMPLETED','FAILED','REVERSED') NOT NULL DEFAULT 'PENDING',
    timestamp        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id)   REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (receiver_id) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_sender   (sender_id),
    INDEX idx_receiver (receiver_id),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── Audit Log (append-only) ─────────────────────────────────────────────────
-- The application DB user should have INSERT-only on this table in production.
-- No UPDATE or DELETE — tamper-proof log per FR-07.
CREATE TABLE IF NOT EXISTS audit_log (
    log_id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED NULL,
    action      VARCHAR(500) NOT NULL,
    ip_address  VARCHAR(45)  NOT NULL COMMENT 'IPv4 or IPv6',
    timestamp   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_user_id  (user_id),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── OTP Tokens ──────────────────────────────────────────────────────────────
-- token_hash = SHA-256(salt + otp_plaintext), base64.
-- token_salt = per-OTP random salt, base64.
-- Plaintext OTP is NEVER stored — only the hash.
CREATE TABLE IF NOT EXISTS otp_tokens (
    otp_id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED NOT NULL,
    token_hash  VARCHAR(128) NOT NULL COMMENT 'SHA-256 hash of OTP, base64',
    token_salt  VARCHAR(64)  NOT NULL COMMENT '256-bit salt, base64',
    expires_at  DATETIME     NOT NULL,
    is_used     TINYINT(1)   NOT NULL DEFAULT 0,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_expires (user_id, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── Admins ──────────────────────────────────────────────────────────────────
-- Separate table — admins CANNOT view or decrypt user balances (separation of duties).
CREATE TABLE IF NOT EXISTS admins (
    admin_id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(60)  NOT NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    salt          VARCHAR(64)  NOT NULL,
    role          ENUM('superadmin','auditor') NOT NULL DEFAULT 'auditor',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── Enforce read-only audit log (run as root after setup) ───────────────────
-- In production, revoke UPDATE/DELETE on audit_log from the app user:
-- REVOKE UPDATE, DELETE ON securemoney.audit_log FROM 'securemoney_app'@'localhost';

SELECT 'SecureMoney schema created successfully.' AS status;
