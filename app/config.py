"""
SecureMoney — config.py
Application configuration loaded from environment variables.
NEVER hard-code secrets here — all sensitive values come from .env
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Flask ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ["SECRET_KEY"]
    DEBUG: bool = os.getenv("FLASK_DEBUG", "0") == "1"

    # ── Database ───────────────────────────────────────────────────────────
    DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    DB_NAME: str = os.getenv("DB_NAME", "securemoney")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # ── Cryptography (NIST SP 800-38D / FIPS PUB 197) ─────────────────────
    # Master key is 32 raw bytes derived from a 64-hex env variable.
    # The env var is hex so it is safely stored as plain text.
    MASTER_KEY_HEX: str = os.environ["MASTER_KEY_HEX"]

    @property
    def MASTER_KEY(self) -> bytes:
        """Return raw 32-byte AES-256 master key from hex env var."""
        raw = bytes.fromhex(self.MASTER_KEY_HEX)
        if len(raw) != 32:
            raise ValueError("MASTER_KEY_HEX must be exactly 64 hex characters (32 bytes)")
        return raw

    PBKDF2_ITERATIONS: int = int(os.getenv("PBKDF2_ITERATIONS", 600_000))
    PBKDF2_HASH: str = os.getenv("PBKDF2_HASH", "SHA-256")

    # ── Session ────────────────────────────────────────────────────────────
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", 15))
    SESSION_COOKIE_SECURE: bool = True          # Require HTTPS in production
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # ── OTP ────────────────────────────────────────────────────────────────
    OTP_EXPIRY_SECONDS: int = int(os.getenv("OTP_EXPIRY_SECONDS", 300))
    OTP_LENGTH: int = int(os.getenv("OTP_LENGTH", 6))

    # ── Email ──────────────────────────────────────────────────────────────
    EMAIL_SIMULATE: bool = os.getenv("EMAIL_SIMULATE", "true").lower() == "true"
    EMAIL_HOST: str = os.getenv("EMAIL_HOST", "")
    EMAIL_PORT: int = int(os.getenv("EMAIL_PORT", 587))
    EMAIL_USER: str = os.getenv("EMAIL_USER", "")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")

    # ── Rate limiting ──────────────────────────────────────────────────────
    RATELIMIT_DEFAULT: str = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI: str = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    # ── WTF CSRF ───────────────────────────────────────────────────────────
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT: int = 3600  # 1 hour


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False   # Allow HTTP during local development


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}

def get_config() -> Config:
    env = os.getenv("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)()
