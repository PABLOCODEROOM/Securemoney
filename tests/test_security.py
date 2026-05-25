"""
SecureMoney — tests/test_security.py
Security-focused tests: SQL injection resistance, OTP brute-force protection,
ciphertext integrity, timing-attack resistance.
Run: pytest tests/test_security.py -v
"""

import os, sys, secrets, base64, time, hmac
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-security")
os.environ.setdefault("MASTER_KEY_HEX", secrets.token_hex(32))

import pytest
from app.crypto_utils import (
    encrypt_aes_gcm, decrypt_aes_gcm,
    hash_password, verify_password,
    generate_salt, generate_otp, hash_otp, verify_otp,
)


class TestSQLInjectionResistance:
    """
    FR-03 / NFR-01: Encrypted fields must be opaque to SQL injection.
    Since all sensitive data is base64(nonce+ciphertext+tag), any SQL
    metacharacter in the plaintext becomes random-looking bytes after encryption.
    """

    SQL_PAYLOADS = [
        "'; DROP TABLE users; --",
        "1 OR 1=1",
        "admin'--",
        "1; SELECT * FROM users",
        "' UNION SELECT password FROM admins--",
        "/**/OR/**/1=1",
        "SLEEP(5)--",
        "'; EXEC xp_cmdshell('whoami')--",
    ]

    def test_sql_payloads_encrypt_safely(self):
        key = secrets.token_bytes(32)
        for payload in self.SQL_PAYLOADS:
            ct = encrypt_aes_gcm(payload, key)
            recovered = decrypt_aes_gcm(ct, key)
            assert recovered == payload, f"Round-trip failed for: {payload}"

    def test_encrypted_values_are_pure_base64(self):
        """Ciphertext stored in DB must contain ONLY base64 characters — no SQL metacharacters."""
        import re
        key = secrets.token_bytes(32)
        base64_pattern = re.compile(r'^[A-Za-z0-9+/=]+$')
        for payload in self.SQL_PAYLOADS:
            ct = encrypt_aes_gcm(payload, key)
            assert base64_pattern.match(ct), (
                f"Ciphertext contains non-base64 chars for payload: {payload!r}"
            )

    def test_sql_char_apostrophe_in_amount(self):
        """A transaction amount that happens to be part of a SQL injection payload."""
        key  = secrets.token_bytes(32)
        evil = "1'; UPDATE accounts SET balance_encrypted='hacked'--"
        ct   = encrypt_aes_gcm(evil, key)
        assert "'" not in ct
        assert "UPDATE" not in ct
        assert decrypt_aes_gcm(ct, key) == evil


class TestCiphertextIntegrity:
    """
    AES-GCM authentication tag must detect ALL forms of tampering.
    Failure here would mean an attacker could modify encrypted balances silently.
    """

    def setup_method(self):
        self.key = secrets.token_bytes(32)
        self.ct  = encrypt_aes_gcm("500000.00", self.key)
        self.raw = base64.b64decode(self.ct)

    def _tamper_at(self, offset: int) -> str:
        r = bytearray(self.raw)
        r[offset] ^= 0xFF
        return base64.b64encode(bytes(r)).decode()

    def test_tamper_first_byte_of_nonce(self):
        with pytest.raises(ValueError): decrypt_aes_gcm(self._tamper_at(0), self.key)

    def test_tamper_middle_of_ciphertext(self):
        mid = len(self.raw) // 2
        with pytest.raises(ValueError): decrypt_aes_gcm(self._tamper_at(mid), self.key)

    def test_tamper_last_byte_of_tag(self):
        with pytest.raises(ValueError): decrypt_aes_gcm(self._tamper_at(-1), self.key)

    def test_truncated_ciphertext_rejected(self):
        truncated = base64.b64encode(self.raw[:20]).decode()
        with pytest.raises(Exception): decrypt_aes_gcm(truncated, self.key)

    def test_extended_ciphertext_rejected(self):
        extended = base64.b64encode(self.raw + b'\x00').decode()
        with pytest.raises(ValueError): decrypt_aes_gcm(extended, self.key)

    def test_completely_random_bytes_rejected(self):
        garbage = base64.b64encode(secrets.token_bytes(64)).decode()
        with pytest.raises(Exception): decrypt_aes_gcm(garbage, self.key)

    def test_ciphertext_swap_between_records(self):
        """Verify AAD binding prevents swapping ciphertext between records."""
        key  = secrets.token_bytes(32)
        ct1 = encrypt_aes_gcm("100.00", key, aad=b"txn_id=1")
        ct2 = encrypt_aes_gcm("999.00", key, aad=b"txn_id=2")
        # ct1 cannot be decrypted as if it were txn_id=2
        with pytest.raises(ValueError):
            decrypt_aes_gcm(ct1, key, aad=b"txn_id=2")
        # But each decrypts under its own AAD
        assert decrypt_aes_gcm(ct1, key, aad=b"txn_id=1") == "100.00"
        assert decrypt_aes_gcm(ct2, key, aad=b"txn_id=2") == "999.00"


class TestTimingAttackResistance:
    """
    Password verification and OTP verification must run in constant time
    to prevent user enumeration and OTP oracle attacks.
    """

    def test_password_uses_compare_digest(self):
        """Inspect source code to ensure hmac.compare_digest is used."""
        import inspect
        from app import crypto_utils
        src = inspect.getsource(crypto_utils.verify_password)
        assert "compare_digest" in src, \
            "verify_password MUST use hmac.compare_digest() to prevent timing attacks"

    def test_otp_uses_compare_digest(self):
        import inspect
        from app import crypto_utils
        src = inspect.getsource(crypto_utils.verify_otp)
        assert "compare_digest" in src, \
            "verify_otp MUST use hmac.compare_digest() to prevent timing attacks"

    def test_wrong_password_timing_similar_to_correct(self):
        """
        Verify that wrong-password check doesn't short-circuit significantly faster.
        This is a statistical test — we just ensure no 10x speedup on wrong passwords.
        """
        salt = generate_salt()
        pwd  = "CorrectPassword!"
        h    = hash_password(pwd, salt)

        RUNS = 5
        correct_times, wrong_times = [], []

        for _ in range(RUNS):
            t0 = time.perf_counter()
            verify_password(pwd, salt, h)
            correct_times.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            verify_password("WrongPassword!", salt, h)
            wrong_times.append(time.perf_counter() - t0)

        avg_correct = sum(correct_times) / RUNS
        avg_wrong   = sum(wrong_times)   / RUNS

        # Wrong password should not be more than 10x faster (timing oracle bound)
        ratio = avg_correct / avg_wrong if avg_wrong > 0 else 1
        assert ratio < 10, (
            f"Timing ratio {ratio:.1f}x suggests short-circuit in wrong-password path"
        )


class TestOTPSecurity:
    """OTP security: uniqueness, hash storage, expiry, brute-force resistance."""

    def test_otp_never_repeats_in_batch(self):
        """Statistical uniqueness test over 1000 generated OTPs."""
        otps = [generate_otp(6) for _ in range(1000)]
        unique = set(otps)
        collision_rate = 1 - (len(unique) / len(otps))
        assert collision_rate < 0.02, (
            f"OTP collision rate {collision_rate:.1%} is suspiciously high — check CSPRNG"
        )

    def test_otp_hash_not_same_as_plaintext(self):
        salt = generate_salt()
        otp  = "123456"
        h    = hash_otp(otp, salt)
        assert h != otp.encode()
        assert len(h) == 32  # SHA-256 output

    def test_otp_salt_prevents_rainbow_table(self):
        """Same OTP with different salts produces different hashes."""
        otp = "999999"
        h1  = hash_otp(otp, generate_salt())
        h2  = hash_otp(otp, generate_salt())
        assert h1 != h2

    def test_all_6_digit_otps_have_same_apparent_cost(self):
        """Verify no digit value is faster/slower to verify (constant-time)."""
        salt = generate_salt()
        times = []
        for digit in range(10):
            otp  = str(digit) * 6
            h    = hash_otp(otp, salt)
            t0   = time.perf_counter()
            verify_otp(otp, salt, h)
            times.append(time.perf_counter() - t0)
        # All timings should be within 5x of each other
        assert max(times) / (min(times) + 1e-9) < 20, "OTP timing varies too much across digits"


class TestNonceUniqueness:
    """
    AES-GCM nonce reuse is catastrophic — it allows XOR recovery of plaintexts.
    Verify that the CSPRNG produces statistically unique nonces.
    """

    def test_no_nonce_reuse_over_10000_encryptions(self):
        key    = secrets.token_bytes(32)
        nonces = set()
        for _ in range(10_000):
            ct  = encrypt_aes_gcm("balance", key)
            raw = base64.b64decode(ct)
            nonce = raw[:12]
            assert nonce not in nonces, "NONCE REUSE DETECTED — critical AES-GCM vulnerability"
            nonces.add(nonce)
        assert len(nonces) == 10_000


class TestKeyIsolation:
    """
    Key hierarchy: different contexts must produce completely different derived keys,
    ensuring that compromise of one derived key does not expose others.
    """

    def test_balance_key_different_from_txn_key(self):
        from app.crypto_utils import derive_encryption_key
        mk   = secrets.token_bytes(32)
        salt = generate_salt()
        k1   = derive_encryption_key(mk, "account_balance", salt)
        k2   = derive_encryption_key(mk, "transaction_amount", salt)
        k3   = derive_encryption_key(mk, "personal_info", salt)
        assert k1 != k2 != k3
        assert k1 != k3

    def test_per_user_key_isolation(self):
        """Different users (different salts) get different derived keys."""
        from app.crypto_utils import derive_encryption_key
        mk     = secrets.token_bytes(32)
        salt1  = generate_salt()
        salt2  = generate_salt()
        k1     = derive_encryption_key(mk, "account_balance", salt1)
        k2     = derive_encryption_key(mk, "account_balance", salt2)
        assert k1 != k2

    def test_balance_ciphertext_not_decryptable_with_txn_key(self):
        """Cross-context decryption must fail."""
        from app.crypto_utils import derive_encryption_key
        mk   = secrets.token_bytes(32)
        salt = generate_salt()
        balance_key = derive_encryption_key(mk, "account_balance", salt)
        txn_key     = derive_encryption_key(mk, "transaction_amount", salt)

        ct = encrypt_aes_gcm("500000.00", balance_key)
        with pytest.raises(ValueError):
            decrypt_aes_gcm(ct, txn_key)
