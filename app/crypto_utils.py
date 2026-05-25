"""
SecureMoney — crypto_utils.py

AES-256-GCM Authenticated Encryption Engine + PBKDF2 Key Derivation.

Cryptographic standards implemented:
  • FIPS PUB 197   — Advanced Encryption Standard (AES-256)
  • NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM
  • NIST SP 800-132 — Recommendation for PBKDF2 key derivation
  • RFC 8018        — PKCS #5 v2.1 Password-Based Cryptography

References:
  • Daemen, J. & Rijmen, V. (2002). The Design of Rijndael. Springer.
  • McGrew, D. & Viega, J. (2004). The Galois/Counter Mode of Operation (GCM).
"""

import os
import base64
import hashlib
import hmac
import secrets
import struct
import time

from Crypto.Cipher import AES             # PyCryptodome — FIPS PUB 197
from Crypto.Protocol.KDF import PBKDF2    # NIST SP 800-132
from Crypto.Hash import SHA256, HMAC

# ─── Constants ───────────────────────────────────────────────────────────────
AES_KEY_BYTES   = 32        # 256-bit key — maximum AES key size (FIPS PUB 197 §6.3)
GCM_NONCE_BYTES = 12        # 96-bit nonce — NIST SP 800-38D §8.2 recommended length
GCM_TAG_BYTES   = 16        # 128-bit authentication tag (full length per NIST)
PBKDF2_DK_LEN   = 32        # Derived key length: 32 bytes = 256 bits
SALT_BYTES       = 32        # 256-bit salt for PBKDF2


# ─── Salt Generation ──────────────────────────────────────────────────────────

def generate_salt() -> bytes:
    """
    Generate a cryptographically secure 256-bit random salt.
    Uses os.urandom() which maps to CSPRNG on all supported platforms.
    Salt is unique per user to prevent rainbow table attacks.
    """
    return secrets.token_bytes(SALT_BYTES)


# ─── Password Hashing (PBKDF2-HMAC-SHA256) ───────────────────────────────────

def hash_password(password: str, salt: bytes, iterations: int = 600_000) -> bytes:
    """
    Hash a password using PBKDF2-HMAC-SHA256.

    NIST SP 800-132 recommends ≥ 1,000 iterations; OWASP recommends 600,000
    for SHA-256 as of 2023 to harden against GPU-based brute-force attacks.

    Args:
        password:   Plaintext password (unicode string).
        salt:       Per-user random salt (bytes).
        iterations: PBKDF2 iteration count — higher = slower brute force.

    Returns:
        32-byte derived key used as the stored password hash.
    """
    dk = PBKDF2(
        password=password.encode("utf-8"),
        salt=salt,
        dkLen=PBKDF2_DK_LEN,
        count=iterations,
        prf=lambda p, s: HMAC.new(p, s, SHA256).digest(),
    )
    return dk


def verify_password(password: str, salt: bytes, stored_hash: bytes, iterations: int = 600_000) -> bool:
    """
    Constant-time password verification to prevent timing side-channels.

    Computes PBKDF2 hash of the supplied password and compares it against
    the stored hash using hmac.compare_digest() (constant-time).
    """
    candidate = hash_password(password, salt, iterations)
    return hmac.compare_digest(candidate, stored_hash)


# ─── Key Derivation for Encryption ───────────────────────────────────────────

def derive_encryption_key(master_key: bytes, context: str, salt: bytes) -> bytes:
    """
    Derive a context-specific AES-256 encryption key via PBKDF2-HMAC-SHA256.

    Each sensitive field (e.g., balance, transaction amount) gets its own
    derived key by mixing the master key, a context string, and a per-record salt.
    This provides key isolation: compromise of one derived key does not expose others.

    The master key is NEVER stored in the database — only in environment variables.

    Args:
        master_key: Raw 32-byte master key from environment (Config.MASTER_KEY).
        context:    Domain separator string, e.g. "balance", "transaction_amount".
        salt:       Per-record salt (usually the user's stored salt).

    Returns:
        32-byte AES-256 derived key.
    """
    # Combine master key + context string as PBKDF2 "password"
    key_material = master_key + context.encode("utf-8")
    dk = PBKDF2(
        password=key_material,
        salt=salt,
        dkLen=AES_KEY_BYTES,
        count=10_000,           # Lower count OK here — master_key provides entropy
        prf=lambda p, s: HMAC.new(p, s, SHA256).digest(),
    )
    return dk


# ─── AES-256-GCM Encryption ──────────────────────────────────────────────────

def encrypt_aes_gcm(plaintext: str, key: bytes, aad: bytes = b"") -> str:
    """
    Encrypt plaintext using AES-256-GCM (Authenticated Encryption with
    Associated Data — AEAD) as specified in NIST SP 800-38D.

    AES-GCM provides:
      • Confidentiality: AES-CTR encrypts the plaintext.
      • Integrity/Authenticity: GHASH produces a 128-bit authentication tag.
      • Replay protection: Each call generates a unique random 96-bit nonce.

    Wire format (base64-encoded):
        [ nonce (12 bytes) | ciphertext (variable) | tag (16 bytes) ]

    The nonce is prepended to the ciphertext before base64 encoding so that
    the decryptor can extract it without out-of-band transmission.

    Args:
        plaintext: UTF-8 string to encrypt.
        key:       32-byte AES-256 key (from derive_encryption_key).
        aad:       Optional Additional Authenticated Data — authenticated but
                   not encrypted. Use to bind ciphertext to a record ID.

    Returns:
        Base64-encoded string: nonce + ciphertext + tag.

    Raises:
        ValueError: If key length is not 32 bytes.
    """
    if len(key) != AES_KEY_BYTES:
        raise ValueError(f"AES-256 requires a 32-byte key; got {len(key)} bytes.")

    # Generate a cryptographically random 96-bit nonce (NIST SP 800-38D §8.2)
    nonce = secrets.token_bytes(GCM_NONCE_BYTES)

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=GCM_TAG_BYTES)
    if aad:
        cipher.update(aad)      # Authenticate (not encrypt) the AAD

    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))

    # Concatenate: nonce ‖ ciphertext ‖ tag, then base64-encode for DB storage
    payload = nonce + ciphertext + tag
    return base64.b64encode(payload).decode("ascii")


def decrypt_aes_gcm(encoded: str, key: bytes, aad: bytes = b"") -> str:
    """
    Decrypt and verify AES-256-GCM ciphertext.

    Verifies the authentication tag before returning plaintext.
    If the tag is invalid (tampered data), raises ValueError — the caller
    must treat this as a critical security event and log it.

    Args:
        encoded: Base64-encoded string produced by encrypt_aes_gcm().
        key:     32-byte AES-256 key (must match the encryption key).
        aad:     Must match the AAD supplied during encryption.

    Returns:
        Decrypted UTF-8 string.

    Raises:
        ValueError: Authentication tag mismatch — data may be tampered.
    """
    if len(key) != AES_KEY_BYTES:
        raise ValueError(f"AES-256 requires a 32-byte key; got {len(key)} bytes.")

    payload = base64.b64decode(encoded.encode("ascii"))

    # Extract nonce, ciphertext, and tag from the wire-format payload
    nonce      = payload[:GCM_NONCE_BYTES]
    tag        = payload[-GCM_TAG_BYTES:]
    ciphertext = payload[GCM_NONCE_BYTES:-GCM_TAG_BYTES]

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=GCM_TAG_BYTES)
    if aad:
        cipher.update(aad)

    try:
        plaintext_bytes = cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as exc:
        # Authentication failure — do NOT return partial data
        raise ValueError(
            "AES-GCM authentication tag verification failed. "
            "Data may have been tampered with."
        ) from exc

    return plaintext_bytes.decode("utf-8")


# ─── High-Level Helpers ───────────────────────────────────────────────────────

def encrypt_balance(balance: float, master_key: bytes, user_salt: bytes) -> str:
    """Encrypt an account balance with a user-specific derived key."""
    key = derive_encryption_key(master_key, "account_balance", user_salt)
    return encrypt_aes_gcm(str(balance), key)


def decrypt_balance(encoded: str, master_key: bytes, user_salt: bytes) -> float:
    """Decrypt and return an account balance as a float."""
    key = derive_encryption_key(master_key, "account_balance", user_salt)
    return float(decrypt_aes_gcm(encoded, key))


def encrypt_transaction_amount(amount: float, master_key: bytes, txn_salt: bytes) -> str:
    """Encrypt a transaction amount with a transaction-specific derived key."""
    key = derive_encryption_key(master_key, "transaction_amount", txn_salt)
    return encrypt_aes_gcm(str(amount), key)


def decrypt_transaction_amount(encoded: str, master_key: bytes, txn_salt: bytes) -> float:
    """Decrypt and return a transaction amount as a float."""
    key = derive_encryption_key(master_key, "transaction_amount", txn_salt)
    return float(decrypt_aes_gcm(encoded, key))


def encrypt_personal_info(info: str, master_key: bytes, user_salt: bytes) -> str:
    """Encrypt sensitive personal information (phone, national ID, etc.)."""
    key = derive_encryption_key(master_key, "personal_info", user_salt)
    return encrypt_aes_gcm(info, key)


def decrypt_personal_info(encoded: str, master_key: bytes, user_salt: bytes) -> str:
    """Decrypt sensitive personal information."""
    key = derive_encryption_key(master_key, "personal_info", user_salt)
    return decrypt_aes_gcm(encoded, key)


# ─── Key Rotation ────────────────────────────────────────────────────────────

def rotate_encrypted_value(
    encoded: str,
    old_master_key: bytes,
    new_master_key: bytes,
    context: str,
    salt: bytes,
) -> str:
    """
    Re-encrypt a ciphertext value under a new master key WITHOUT exposing
    the plaintext any longer than necessary in memory.

    This implements key rotation: decrypt with old key → re-encrypt with new key.
    Used when MASTER_KEY_HEX is rotated in the environment. Run as a migration.

    Args:
        encoded:        Existing base64-encoded ciphertext.
        old_master_key: Previous 32-byte master key.
        new_master_key: New 32-byte master key.
        context:        Key derivation context (e.g., "account_balance").
        salt:           Per-record salt.

    Returns:
        New base64-encoded ciphertext under the new master key.
    """
    old_key = derive_encryption_key(old_master_key, context, salt)
    plaintext = decrypt_aes_gcm(encoded, old_key)

    new_key = derive_encryption_key(new_master_key, context, salt)
    return encrypt_aes_gcm(plaintext, new_key)


# ─── OTP Utilities ────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP of the given length."""
    upper = 10 ** length
    return str(secrets.randbelow(upper)).zfill(length)


def hash_otp(otp: str, salt: bytes) -> bytes:
    """Hash an OTP with SHA-256 + salt before storing in the database."""
    return hashlib.sha256(salt + otp.encode("utf-8")).digest()


def verify_otp(otp: str, salt: bytes, stored_hash: bytes) -> bool:
    """Constant-time OTP verification."""
    candidate = hash_otp(otp, salt)
    return hmac.compare_digest(candidate, stored_hash)


# ─── Performance Benchmarking (for academic testing) ─────────────────────────

def benchmark_encryption(iterations: int = 1000) -> dict:
    """
    Measure AES-256-GCM encryption/decryption throughput.
    Returns timing statistics in milliseconds.
    """
    key = secrets.token_bytes(AES_KEY_BYTES)
    sample = "TZS 500000.00"  # ~13 bytes — typical transaction amount

    # Warm up
    for _ in range(10):
        enc = encrypt_aes_gcm(sample, key)
        decrypt_aes_gcm(enc, key)

    # Encrypt benchmark
    enc_start = time.perf_counter()
    for _ in range(iterations):
        enc = encrypt_aes_gcm(sample, key)
    enc_total = (time.perf_counter() - enc_start) * 1000  # ms

    # Decrypt benchmark
    dec_start = time.perf_counter()
    for _ in range(iterations):
        decrypt_aes_gcm(enc, key)
    dec_total = (time.perf_counter() - dec_start) * 1000  # ms

    return {
        "iterations": iterations,
        "encrypt_total_ms": round(enc_total, 3),
        "decrypt_total_ms": round(dec_total, 3),
        "encrypt_avg_us": round((enc_total / iterations) * 1000, 3),
        "decrypt_avg_us": round((dec_total / iterations) * 1000, 3),
        "encrypt_ops_per_sec": round(iterations / (enc_total / 1000)),
        "decrypt_ops_per_sec": round(iterations / (dec_total / 1000)),
    }
