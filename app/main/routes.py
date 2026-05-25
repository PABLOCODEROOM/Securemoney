"""SecureMoney — app/main/routes.py — Dashboard home."""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import get_account, get_transaction_history

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    account  = get_account(current_user.user_id)
    txns     = get_transaction_history(current_user.user_id, limit=5)
    return render_template(
        "dashboard.html",
        account=account,
        recent_txns=txns,
        user=current_user,
    )
