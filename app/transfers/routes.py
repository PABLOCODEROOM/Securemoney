"""SecureMoney — app/transfers/routes.py — Money transfer blueprint."""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import (
    transfer_funds, get_account, get_transaction_history,
    InsufficientFundsError, TransferError,
)
from app import limiter

transfers_bp = Blueprint("transfers", __name__)


@transfers_bp.route("/send", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")
def send():
    account = get_account(current_user.user_id)

    if request.method == "POST":
        to_account = request.form.get("to_account", "").strip().upper()
        amount_str = request.form.get("amount", "").strip()
        description = request.form.get("description", "").strip()

        try:
            amount = float(amount_str)
        except ValueError:
            flash("Please enter a valid amount.", "danger")
            return render_template("transfers/send.html", account=account)

        try:
            txn_id = transfer_funds(
                current_user.user_id, to_account, amount, description
            )
            flash(f"Transfer successful! Transaction ID: {txn_id}", "success")
            return redirect(url_for("transfers.history"))
        except InsufficientFundsError as exc:
            flash(str(exc), "warning")
        except TransferError as exc:
            flash(str(exc), "danger")

    return render_template("transfers/send.html", account=account)


@transfers_bp.route("/history")
@login_required
def history():
    txns    = get_transaction_history(current_user.user_id, limit=50)
    account = get_account(current_user.user_id)
    return render_template("transfers/history.html", txns=txns, account=account)
