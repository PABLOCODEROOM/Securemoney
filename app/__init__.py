"""
SecureMoney — app/__init__.py
Flask application factory with all extensions and blueprints registered.
"""

from datetime import timedelta
from flask import Flask, session, redirect, url_for, request
from flask_wtf import CSRFProtect
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.config import get_config

csrf    = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    cfg = get_config()
    app.config.from_object(cfg)

    # ── Extensions ──────────────────────────────────────────────────────────
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # ── Session timeout ──────────────────────────────────────────────────────
    app.permanent_session_lifetime = timedelta(minutes=cfg.SESSION_TIMEOUT_MINUTES)

    @app.before_request
    def enforce_session_timeout():
        """Automatically expire sessions after configured inactivity period."""
        if "user_id" in session:
            session.permanent = True

    # ── Blueprints ───────────────────────────────────────────────────────────
    from app.auth.routes     import auth_bp
    from app.transfers.routes import transfers_bp
    from app.payments.routes  import payments_bp
    from app.main.routes      import main_bp
    from app.admin.routes     import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(transfers_bp, url_prefix="/transfers")
    app.register_blueprint(payments_bp,  url_prefix="/payments")
    app.register_blueprint(admin_bp,     url_prefix="/admin")

    # ── Error handlers ───────────────────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template("shared/error.html", code=403, msg="Access Denied"), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("shared/error.html", code=404, msg="Page Not Found"), 404

    @app.errorhandler(429)
    def rate_limited(e):
        from flask import render_template
        return render_template("shared/error.html", code=429, msg="Too Many Requests"), 429

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template("shared/error.html", code=500, msg="Internal Server Error"), 500

    return app


# ── Flask-Login user loader ──────────────────────────────────────────────────
class UserSession:
    """Minimal user object for Flask-Login."""
    def __init__(self, user_id: int, full_name: str, email: str):
        self.id        = user_id
        self.user_id   = user_id
        self.full_name = full_name
        self.email     = email
        self.is_active = True

    # Flask-Login interface
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.user_id)


@login_manager.user_loader
def load_user(user_id: str):
    from app.models import get_user_by_id
    row = get_user_by_id(int(user_id))
    if row and row["is_active"]:
        return UserSession(row["user_id"], row["full_name"], row["email"])
    return None
