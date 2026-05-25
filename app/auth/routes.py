"""
SecureMoney — app/auth/routes.py
Authentication blueprint: register, login, OTP verification, logout.
"""

from flask import (
    Blueprint, render_template, redirect, url_for,
    request, flash, session,
)
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.models import (
    create_user, authenticate_user, UserExistsError, AuthenticationError,
    create_otp, verify_otp_token, log_action, get_user_by_id,
)
from app import UserSession, limiter

auth_bp = Blueprint("auth", __name__)


def _send_otp(user_id: int, email: str) -> str:
    """Create OTP, store in session for display, and simulate sending."""
    from app.config import get_config
    from flask import session
    otp = create_otp(user_id)
    cfg = get_config()
    
    # Store OTP in session for display on verify page (development only)
    session["dev_otp"] = otp
    print(f"[DEBUG] OTP stored in session: {otp}")  # Debug line
    
    if cfg.EMAIL_SIMULATE:
        # Print with clear formatting for visibility
        print("\n" + "=" * 60)
        print(f"  🔐 SECUREMONEY OTP VERIFICATION")
        print(f"  Email: {email}")
        print(f"  📮 Your OTP Code: {otp}")
        print(f"  ⏰ Valid for: {cfg.OTP_EXPIRY_SECONDS} seconds")
        print("=" * 60 + "\n")
    # TODO: hook real SMTP/SMS gateway here for production
    return otp


# ─── Registration ────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email     = request.form.get("email", "").strip().lower()
        phone     = request.form.get("phone", "").strip()
        password  = request.form.get("password", "")
        confirm   = request.form.get("confirm_password", "")

        # Validation
        errors = []
        if not full_name or len(full_name) < 3:
            errors.append("Full name must be at least 3 characters.")
        if not email or "@" not in email:
            errors.append("Please enter a valid email address.")
        if not phone or len(phone) < 10:
            errors.append("Please enter a valid phone number.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("auth/register.html",
                                   full_name=full_name, email=email, phone=phone)

        try:
            user_id = create_user(full_name, email, phone, password)
            log_action(user_id, f"REGISTER: new account created for {email}", request.remote_addr)
            flash("Account created! Please log in.", "success")
            return redirect(url_for("auth.login"))
        except UserExistsError:
            flash("An account with that email already exists.", "danger")
        except Exception as exc:
            flash("Registration failed. Please try again.", "danger")
            print(f"[ERROR] Registration: {exc}")

    return render_template("auth/register.html")


# ─── Login ────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        try:
            user = authenticate_user(email, password)
            # Store user_id in session pending OTP verification (not logged in yet)
            session["pending_user_id"]   = user["user_id"]
            session["pending_user_name"] = user["full_name"]
            session["pending_email"]     = user["email"]

            _send_otp(user["user_id"], user["email"])
            log_action(user["user_id"], f"LOGIN_ATTEMPT: OTP sent to {email}", request.remote_addr)
            return redirect(url_for("auth.verify_otp"))

        except AuthenticationError as exc:
            flash(str(exc), "danger")
            log_action(None, f"LOGIN_FAIL: invalid credentials for {email}", request.remote_addr)

    return render_template("auth/login.html")


# ─── OTP Verification ────────────────────────────────────────────────────────

@auth_bp.route("/verify-otp", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def verify_otp():
    if "pending_user_id" not in session:
        return redirect(url_for("auth.login"))

    # Debug: Print session values on GET request
    if request.method == "GET":
        dev_otp = session.get("dev_otp", "NOT SET")
        print(f"[DEBUG] verify_otp GET - dev_otp in session: {dev_otp}")

    if request.method == "POST":
        otp_input = request.form.get("otp", "").strip()
        user_id   = session["pending_user_id"]

        if verify_otp_token(user_id, otp_input):
            # OTP valid — complete login
            row  = get_user_by_id(user_id)
            user_obj = UserSession(row["user_id"], row["full_name"], row["email"])
            login_user(user_obj, remember=False)
            session.pop("pending_user_id",   None)
            session.pop("pending_user_name", None)
            session.pop("pending_email",     None)
            log_action(user_id, "LOGIN_SUCCESS: 2FA passed", request.remote_addr)
            flash(f"Welcome back, {user_obj.full_name}!", "success")
            return redirect(url_for("main.dashboard"))
        else:
            log_action(user_id, "LOGIN_FAIL: invalid OTP", request.remote_addr)
            flash("Invalid or expired OTP. Please try again.", "danger")

    return render_template("auth/verify_otp.html",
                           email=session.get("pending_email", ""))


# ─── Logout ──────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    log_action(current_user.user_id, "LOGOUT", request.remote_addr)
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
