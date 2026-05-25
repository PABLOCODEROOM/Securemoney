"""
SecureMoney — run.py
Application entry point.
Usage: python run.py
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=app.config.get("DEBUG", False),
        ssl_context="adhoc",   # Self-signed TLS in dev (HTTPS enforcement NFR-07)
    )
