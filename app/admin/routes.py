"""SecureMoney admin routes."""

from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models import (
    AdminAuthenticationError,
    authenticate_admin,
    get_admin_dashboard_stats,
    get_audit_log,
)

admin_bp = Blueprint("admin", __name__, template_folder="../templates")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapped


@admin_bp.route("/", methods=["GET"])
def index():
    if "admin_id" in session:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("admin.login"))


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if "admin_id" in session:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            admin = authenticate_admin(username, password)
        except AdminAuthenticationError as exc:
            flash(str(exc), "danger")
        else:
            session.clear()
            session["admin_id"] = admin["admin_id"]
            session["admin_username"] = admin["username"]
            session["admin_role"] = admin["role"]
            flash(f"Welcome, {admin['username']}.", "success")
            return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html")


@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    stats = get_admin_dashboard_stats()
    audit_log = get_audit_log(limit=25)
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        audit_log=audit_log,
        admin_username=session.get("admin_username", "admin"),
        admin_role=session.get("admin_role", "auditor"),
    )


@admin_bp.route("/logout", methods=["GET"])
@admin_required
def logout():
    session.clear()
    flash("Admin session ended.", "info")
    return redirect(url_for("admin.login"))
