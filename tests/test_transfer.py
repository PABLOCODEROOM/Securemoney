"""
SecureMoney — tests/test_transfer.py
Integration tests: full transfer flow, bill payments, transaction history.
Run: pytest tests/test_transfer.py -v
Requires: MySQL test database configured in conftest.py
"""

import pytest
from app.models import (
    get_account, transfer_funds, pay_bill, get_transaction_history,
    InsufficientFundsError, TransferError,
)


class TestTransferFlow:
    """Full end-to-end transfer workflow."""

    def test_transfer_creates_transaction_record(self, testdb, test_user, test_user_2):
        """FR-04: Transfer creates encrypted transaction record."""
        testdb.clear_transactions()
        testdb.set_user_balance(test_user["user_id"], 1000.0)
        testdb.set_user_balance(test_user_2["user_id"], 500.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        # Execute transfer
        txn_id = transfer_funds(
            sender_id=test_user["user_id"],
            receiver_account_number=account2["account_number"],
            amount=250.0,
            description="Test transfer",
        )

        assert txn_id > 0
        txns = get_transaction_history(test_user["user_id"])
        assert len(txns) == 1
        assert txns[0]["amount"] == 250.0
        assert txns[0]["type"] == "TRANSFER"

    def test_transfer_deducts_from_sender(self, testdb, test_user, test_user_2):
        """FR-04: Sender balance decreases by transfer amount."""
        testdb.set_user_balance(test_user["user_id"], 30_000.0)
        testdb.set_user_balance(test_user_2["user_id"], 500.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        # Before
        before = get_account(test_user["user_id"])
        assert before["balance"] == 1000.0

        # Transfer
        transfer_funds(test_user["user_id"], account2["account_number"], 250.0)

        # After
        after = get_account(test_user["user_id"])
        assert after["balance"] == 750.0

    def test_transfer_credits_receiver(self, testdb, test_user, test_user_2):
        """FR-04: Receiver balance increases by transfer amount."""
        testdb.set_user_balance(test_user["user_id"], 30_000.0)
        testdb.set_user_balance(test_user_2["user_id"], 500.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        # Before
        before = get_account(user2["user_id"])
        assert before["balance"] == 500.0

        # Transfer
        transfer_funds(test_user["user_id"], account2["account_number"], 250.0)

        # After
        after = get_account(user2["user_id"])
        assert after["balance"] == 750.0

    def test_transfer_atomic_on_insufficient_funds(self, testdb, test_user, test_user_2):
        """NFR: Transfer is atomic — both parties' balances updated or none."""
        testdb.set_user_balance(test_user["user_id"], 100.0)
        testdb.set_user_balance(test_user_2["user_id"], 500.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        sender_before = get_account(test_user["user_id"])
        receiver_before = get_account(user2["user_id"])

        with pytest.raises(InsufficientFundsError):
            transfer_funds(test_user["user_id"], account2["account_number"], 500.0)

        # Both unchanged (atomicity)
        sender_after = get_account(test_user["user_id"])
        receiver_after = get_account(user2["user_id"])
        assert sender_after["balance"] == sender_before["balance"]
        assert receiver_after["balance"] == receiver_before["balance"]

    def test_transfer_rejects_self_transfer(self, testdb, test_user):
        """Security: Cannot transfer to own account."""
        testdb.set_user_balance(test_user["user_id"], 1000.0)
        account = get_account(test_user["user_id"])

        with pytest.raises(TransferError, match="own account"):
            transfer_funds(test_user["user_id"], account["account_number"], 100.0)

    def test_transfer_rejects_invalid_recipient(self, testdb, test_user):
        """Transfer to non-existent account fails."""
        testdb.set_user_balance(test_user["user_id"], 1000.0)

        with pytest.raises(TransferError, match="not found"):
            transfer_funds(test_user["user_id"], "SM00000000", 100.0)

    def test_transfer_rejects_negative_amount(self, testdb, test_user, test_user_2):
        """Security: Cannot transfer negative amounts (credit from sender)."""
        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        with pytest.raises(TransferError, match="positive"):
            transfer_funds(test_user["user_id"], account2["account_number"], -100.0)

    def test_transfer_rejects_zero_amount(self, testdb, test_user, test_user_2):
        """Security: Cannot transfer zero amount."""
        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        with pytest.raises(TransferError, match="positive"):
            transfer_funds(test_user["user_id"], account2["account_number"], 0.0)

    def test_transfer_rejects_exceeds_limit(self, testdb, test_user, test_user_2):
        """Security: Transfers exceeding max limit are rejected."""
        testdb.set_user_balance(test_user["user_id"], 50_000_000.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        with pytest.raises(TransferError, match="exceeds maximum"):
            transfer_funds(test_user["user_id"], account2["account_number"], 50_000_000.0)


class TestBillPayment:
    """Bill payment (FR-05) tests."""

    def test_bill_payment_deducts_balance(self, testdb, test_user):
        """FR-05: Bill payment deducts from user balance."""
        testdb.set_user_balance(test_user["user_id"], 1000.0)

        before = get_account(test_user["user_id"])
        pay_bill(test_user["user_id"], "TANESCO (Electricity)", "12345678", 150.0)
        after = get_account(test_user["user_id"])

        assert after["balance"] == before["balance"] - 150.0

    def test_bill_payment_creates_record(self, testdb, test_user):
        """FR-05: Bill payment creates BILL_PAYMENT transaction record."""
        testdb.clear_transactions()
        testdb.set_user_balance(test_user["user_id"], 1000.0)

        txn_id = pay_bill(test_user["user_id"], "NHIF", "NI123456789", 25_000.0)
        assert txn_id > 0

        txns = get_transaction_history(test_user["user_id"])
        assert len(txns) == 1
        assert txns[0]["type"] == "BILL_PAYMENT"
        assert txns[0]["amount"] == 25_000.0

    def test_bill_payment_insufficient_funds(self, testdb, test_user):
        """Bill payment fails if insufficient balance."""
        testdb.set_user_balance(test_user["user_id"], 100.0)

        with pytest.raises(InsufficientFundsError):
            pay_bill(test_user["user_id"], "TANESCO", "12345", 500.0)


class TestTransactionHistory:
    """FR-07: Transaction history with decrypted amounts."""

    def test_history_shows_all_transactions(self, testdb, test_user, test_user_2):
        """FR-07: History includes transfers and bill payments."""
        testdb.clear_transactions()
        testdb.set_user_balance(test_user["user_id"], 5000.0)
        testdb.set_user_balance(test_user_2["user_id"], 1000.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        # Transfer
        transfer_funds(test_user["user_id"], account2["account_number"], 500.0)
        # Bill payment
        pay_bill(test_user["user_id"], "DAWASCO", "WC123", 100.0)

        txns = get_transaction_history(test_user["user_id"])
        assert len(txns) == 2

        types = [t["type"] for t in txns]
        assert "TRANSFER" in types
        assert "BILL_PAYMENT" in types

    def test_history_decrypts_amounts(self, testdb, test_user):
        """FR-07: Amounts in history are correctly decrypted."""
        testdb.clear_transactions()
        testdb.set_user_balance(test_user["user_id"], 2000.0)

        pay_bill(test_user["user_id"], "HESLB", "SL999", 350.50)

        txns = get_transaction_history(test_user["user_id"])
        assert len(txns) == 1
        assert txns[0]["amount"] == 350.50  # Decrypted correctly

    def test_history_marks_debits_and_credits(self, testdb, test_user, test_user_2):
        """FR-07: History distinguishes debits vs credits."""
        testdb.clear_transactions()
        testdb.set_user_balance(test_user["user_id"], 2000.0)
        testdb.set_user_balance(test_user_2["user_id"], 500.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        # Sender perspective
        transfer_funds(test_user["user_id"], account2["account_number"], 300.0)

        txns_sender = get_transaction_history(test_user["user_id"])
        assert txns_sender[0]["is_debit"] is True

        # Receiver perspective
        txns_receiver = get_transaction_history(user2["user_id"])
        assert txns_receiver[0]["is_debit"] is False


class TestEncryptionIntegrity:
    """Verify encrypted amounts are stored and retrieved correctly."""

    def test_encrypted_amounts_match_plaintext(self, testdb, test_user):
        """NFR-01: Encrypted amounts decrypt to exact plaintext values."""
        testdb.clear_transactions()
        testdb.set_user_balance(test_user["user_id"], 1_100_000.0)

        test_amounts = [0.01, 1.00, 100.00, 1_234.56, 999_999.98]

        for amt in test_amounts:
            pay_bill(test_user["user_id"], "TEST", "REF", amt)

        txns = get_transaction_history(test_user["user_id"])
        stored_amounts = list(reversed([t["amount"] for t in txns]))

        for original, stored in zip(test_amounts, stored_amounts):
            assert abs(original - stored) < 0.001, (
                f"Encryption round-trip failed: {original} != {stored}"
            )

    def test_large_balance_encrypted_correctly(self, testdb, test_user):
        """Large balance values (Tanzania's currency) encrypt correctly."""
        testdb.set_user_balance(test_user["user_id"], 999_999_999.99)
        account = get_account(test_user["user_id"])
        assert account["balance"] == 999_999_999.99


class TestAuditLog:
    """FR-07: Tamper-proof audit log."""

    def test_transfer_logged(self, testdb, test_user, test_user_2):
        """FR-07: Each transfer is recorded in audit log."""
        from app.models import get_audit_log

        testdb.set_user_balance(test_user["user_id"], 1000.0)
        testdb.set_user_balance(test_user_2["user_id"], 500.0)

        from app.models import get_user_by_email

        user2 = get_user_by_email(test_user_2["email"])
        account2 = get_account(user2["user_id"])

        transfer_funds(test_user["user_id"], account2["account_number"], 200.0)

        logs = get_audit_log()
        transfer_logs = [l for l in logs if "TRANSFER" in l["action"]]
        assert len(transfer_logs) > 0
