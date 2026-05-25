"""
SecureMoney — tests/test_crypto.py
Unit tests for the AES-256-GCM crypto engine and PBKDF2 key derivation.
Run: pytest tests/test_crypto.py -v
"""

import os, sys, secrets, base64, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Minimal env for tests
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("MASTER_KEY_HEX", secrets.token_hex(32))

import pytest
from app.crypto_utils import (
    generate_salt, hash_password, verify_password,
    derive_encryption_key, encrypt_aes_gcm, decrypt_aes_gcm,
    encrypt_balance, decrypt_balance,
    encrypt_transaction_amount, decrypt_transaction_amount,
    generate_otp, hash_otp, verify_otp,
    rotate_encrypted_value, benchmark_encryption,
    AES_KEY_BYTES, GCM_NONCE_BYTES, GCM_TAG_BYTES, SALT_BYTES,
)


class TestSaltGeneration:
    def test_salt_length(self):
        salt = generate_salt()
        assert len(salt) == SALT_BYTES == 32

    def test_salt_uniqueness(self):
        salts = {generate_salt() for _ in range(100)}
        assert len(salts) == 100, "Salts must be unique (CSPRNG collision)"

    def test_salt_is_bytes(self):
        assert isinstance(generate_salt(), bytes)


class TestPasswordHashing:
    def test_hash_produces_32_bytes(self):
        salt = generate_salt()
        h = hash_password("MyP@ss2026!", salt)
        assert len(h) == 32

    def test_correct_password_verifies(self):
        salt = generate_salt()
        h = hash_password("CorrectPassword!", salt)
        assert verify_password("CorrectPassword!", salt, h)

    def test_wrong_password_fails(self):
        salt = generate_salt()
        h = hash_password("CorrectPassword!", salt)
        assert not verify_password("WrongPassword!", salt, h)

    def test_different_salts_produce_different_hashes(self):
        pw = "SamePassword123!"
        h1 = hash_password(pw, generate_salt())
        h2 = hash_password(pw, generate_salt())
        assert h1 != h2

    def test_constant_time_comparison(self):
        """verify_password must use constant-time comparison."""
        import inspect
        src = inspect.getsource(verify_password)
        assert "compare_digest" in src, "Must use hmac.compare_digest() for constant-time comparison"

    def test_unicode_password(self):
        salt = generate_salt()
        pw = "Pásswörd123!@#"
        h = hash_password(pw, salt)
        assert verify_password(pw, salt, h)


class TestKeyDerivation:
    def test_derived_key_length(self):
        mk   = secrets.token_bytes(32)
        salt = generate_salt()
        dk   = derive_encryption_key(mk, "balance", salt)
        assert len(dk) == AES_KEY_BYTES == 32

    def test_different_contexts_produce_different_keys(self):
        mk   = secrets.token_bytes(32)
        salt = generate_salt()
        k1 = derive_encryption_key(mk, "balance", salt)
        k2 = derive_encryption_key(mk, "transaction_amount", salt)
        assert k1 != k2, "Context isolation failed — different contexts must yield different keys"

    def test_different_salts_produce_different_keys(self):
        mk = secrets.token_bytes(32)
        k1 = derive_encryption_key(mk, "balance", generate_salt())
        k2 = derive_encryption_key(mk, "balance", generate_salt())
        assert k1 != k2

    def test_deterministic_derivation(self):
        """Same inputs must always produce the same key."""
        mk   = secrets.token_bytes(32)
        salt = generate_salt()
        k1 = derive_encryption_key(mk, "personal_info", salt)
        k2 = derive_encryption_key(mk, "personal_info", salt)
        assert k1 == k2


class TestAESGCM:
    def setup_method(self):
        self.key = secrets.token_bytes(32)

    def test_encrypt_returns_string(self):
        ct = encrypt_aes_gcm("Hello Tanzania!", self.key)
        assert isinstance(ct, str)

    def test_decrypt_recovers_plaintext(self):
        pt = "SecureMoney Test — TZS 500,000.00"
        ct = encrypt_aes_gcm(pt, self.key)
        assert decrypt_aes_gcm(ct, self.key) == pt

    def test_unique_nonces(self):
        """Each encryption must produce a different ciphertext (unique nonce)."""
        pt = "same plaintext"
        ct1 = encrypt_aes_gcm(pt, self.key)
        ct2 = encrypt_aes_gcm(pt, self.key)
        assert ct1 != ct2, "Nonce reuse detected — critical AES-GCM vulnerability"

    def test_wrong_key_fails(self):
        ct = encrypt_aes_gcm("secret", self.key)
        wrong_key = secrets.token_bytes(32)
        with pytest.raises(ValueError):
            decrypt_aes_gcm(ct, wrong_key)

    def test_tampered_ciphertext_detected(self):
        """GCM authentication tag must detect any tampering."""
        ct = encrypt_aes_gcm("original", self.key)
        raw = base64.b64decode(ct)
        # Flip a byte in the ciphertext body
        tampered = raw[:15] + bytes([raw[15] ^ 0xFF]) + raw[16:]
        tampered_b64 = base64.b64encode(tampered).decode()
        with pytest.raises(ValueError, match="authentication tag"):
            decrypt_aes_gcm(tampered_b64, self.key)

    def test_tampered_nonce_detected(self):
        ct = encrypt_aes_gcm("test", self.key)
        raw = base64.b64decode(ct)
        tampered = bytes([raw[0] ^ 0x01]) + raw[1:]  # Flip nonce byte
        tampered_b64 = base64.b64encode(tampered).decode()
        with pytest.raises(ValueError):
            decrypt_aes_gcm(tampered_b64, self.key)

    def test_aad_binding(self):
        """Ciphertext with AAD must not decrypt under different AAD."""
        pt  = "bound data"
        aad = b"record_id=42"
        ct  = encrypt_aes_gcm(pt, self.key, aad=aad)
        # Same ciphertext, different AAD should fail
        with pytest.raises(ValueError):
            decrypt_aes_gcm(ct, self.key, aad=b"record_id=99")

    def test_empty_plaintext(self):
        ct = encrypt_aes_gcm("", self.key)
        assert decrypt_aes_gcm(ct, self.key) == ""

    def test_unicode_plaintext(self):
        pt = "Habari! Amount: TZS 1,000,000 — محفوظ"
        ct = encrypt_aes_gcm(pt, self.key)
        assert decrypt_aes_gcm(ct, self.key) == pt

    def test_short_key_rejected(self):
        with pytest.raises(ValueError):
            encrypt_aes_gcm("test", b"short_key")

    def test_nonce_length_in_payload(self):
        ct  = encrypt_aes_gcm("check", self.key)
        raw = base64.b64decode(ct)
        assert len(raw) >= GCM_NONCE_BYTES + GCM_TAG_BYTES

    def test_large_plaintext(self):
        pt = "A" * 100_000  # 100 KB
        ct = encrypt_aes_gcm(pt, self.key)
        assert decrypt_aes_gcm(ct, self.key) == pt


class TestHighLevelHelpers:
    def setup_method(self):
        self.master_key = secrets.token_bytes(32)
        self.salt       = generate_salt()

    def test_balance_encrypt_decrypt(self):
        for balance in [0.0, 500_000.0, 1_234_567.89, 0.01]:
            enc = encrypt_balance(balance, self.master_key, self.salt)
            assert decrypt_balance(enc, self.master_key, self.salt) == balance

    def test_transaction_amount_encrypt_decrypt(self):
        txn_salt = generate_salt()
        for amount in [100.0, 999_999.99, 1.0]:
            enc = encrypt_transaction_amount(amount, self.master_key, txn_salt)
            assert decrypt_transaction_amount(enc, self.master_key, txn_salt) == amount


class TestKeyRotation:
    def test_rotate_balance(self):
        old_key = secrets.token_bytes(32)
        new_key = secrets.token_bytes(32)
        salt    = generate_salt()
        balance = 123_456.78

        enc_old = encrypt_balance(balance, old_key, salt)
        enc_new = rotate_encrypted_value(enc_old, old_key, new_key, "account_balance", salt)

        # New ciphertext is different
        assert enc_old != enc_new

        # But decrypts to same value under new key
        assert decrypt_balance(enc_new, new_key, salt) == balance

        # Old ciphertext is now unreadable under new key
        with pytest.raises(ValueError):
            decrypt_balance(enc_old, new_key, salt)


class TestOTP:
    def test_otp_length(self):
        for length in [4, 6, 8]:
            otp = generate_otp(length)
            assert len(otp) == length
            assert otp.isdigit()

    def test_otp_verify_correct(self):
        salt = generate_salt()
        otp  = generate_otp(6)
        h    = hash_otp(otp, salt)
        assert verify_otp(otp, salt, h)

    def test_otp_verify_wrong(self):
        salt = generate_salt()
        otp  = generate_otp(6)
        h    = hash_otp(otp, salt)
        wrong = str(int(otp) ^ 1).zfill(6)  # One digit different
        assert not verify_otp(wrong, salt, h)

    def test_otp_uniqueness(self):
        otps = {generate_otp(6) for _ in range(1000)}
        assert len(otps) > 900, "OTP generation is not sufficiently random"


class TestPerformance:
    def test_encrypt_decrypt_under_3_seconds(self):
        """NFR-02: Transaction processing < 3 seconds."""
        key   = secrets.token_bytes(32)
        pt    = "TZS 500000.00"
        start = time.perf_counter()
        for _ in range(100):
            ct = encrypt_aes_gcm(pt, key)
            decrypt_aes_gcm(ct, key)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"100 encrypt+decrypt cycles took {elapsed:.2f}s — exceeds 3s NFR"

    def test_benchmark_report(self):
        stats = benchmark_encryption(100)
        assert stats["encrypt_ops_per_sec"] > 1000, "Encryption throughput too low"
        assert stats["decrypt_ops_per_sec"] > 1000, "Decryption throughput too low"
        print(f"\n  Benchmark: {stats['encrypt_ops_per_sec']} enc/s, "
              f"{stats['decrypt_ops_per_sec']} dec/s")


class TestSQLInjection:
    """
    Security test: encrypted fields must be opaque to SQL injection.
    Since data is base64(nonce+ciphertext+tag), SQL metacharacters
    inside plaintext become meaningless after encryption.
    """
    def test_sql_injection_payload_encrypts_safely(self):
        key  = secrets.token_bytes(32)
        malicious = "'; DROP TABLE users; --"
        ct = encrypt_aes_gcm(malicious, key)
        # Should be valid base64 with no SQL metacharacters
        decoded_bytes = base64.b64decode(ct)
        assert len(decoded_bytes) >= GCM_NONCE_BYTES + GCM_TAG_BYTES
        # Decrypts back correctly
        assert decrypt_aes_gcm(ct, key) == malicious

    def test_encrypted_value_is_base64_only(self):
        key = secrets.token_bytes(32)
        ct  = encrypt_aes_gcm("'; OR 1=1--", key)
        import re
        assert re.match(r'^[A-Za-z0-9+/=]+$', ct), "Ciphertext must be pure base64"
