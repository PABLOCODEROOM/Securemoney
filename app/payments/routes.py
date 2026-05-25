"""SecureMoney — app/payments/routes.py — Bill payment blueprint."""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import (
    pay_bill, get_account, InsufficientFundsError, TransferError,
)
from app import limiter

payments_bp = Blueprint("payments", __name__)

BILLERS = [
    {"id": "TANESCO",  "name": "TANESCO (Electricity)"},
    {"id": "DAWASCO",  "name": "DAWASCO (Water)"},
    {"id": "TTCL",     "name": "TTCL (Landline)"},
    {"id": "NHIF",     "name": "NHIF (Health Insurance)"},
    {"id": "HESLB",    "name": "HESLB (Student Loan)"},
    {"id": "LUKU",     "name": "LUKU (Prepaid Electricity)"},
]


@payments_bp.route("/pay", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour")
def pay():
    account = get_account(current_user.user_id)

    if request.method == "POST":
        biller_id  = request.form.get("biller", "").strip()
        biller_ref = request.form.get("reference", "").strip()
        amount_str = request.form.get("amount", "").strip()

        biller_name = next((b["name"] for b in BILLERS if b["id"] == biller_id), None)
        if not biller_name:
            flash("Invalid biller selected.", "danger")
            return render_template("payments/pay.html", account=account, billers=BILLERS)

        try:
            amount = float(amount_str)
        except ValueError:
            flash("Please enter a valid amount.", "danger")
            return render_template("payments/pay.html", account=account, billers=BILLERS)

        try:
            txn_id = pay_bill(current_user.user_id, biller_name, biller_ref, amount)
            flash(f"Bill payment successful! Transaction ID: {txn_id}", "success")
            return redirect(url_for("transfers.history"))
        except InsufficientFundsError as exc:
            flash(str(exc), "warning")
        except TransferError as exc:
            flash(str(exc), "danger")

    return render_template("payments/pay.html", account=account, billers=BILLERS)
