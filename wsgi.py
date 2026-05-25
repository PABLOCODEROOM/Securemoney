"""
SecureMoney — wsgi.py
Production WSGI entry point for gunicorn/uWSGI.
Usage: gunicorn --workers=4 --threads=2 --bind=0.0.0.0:8000 wsgi:app
"""

import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
