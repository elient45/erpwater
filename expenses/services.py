from decimal import Decimal
from uuid import uuid4

from .models import Expense, FinancialTransaction


def create_expense(expense: Expense) -> Expense:
    expense.save()
    return expense


def create_financial_transaction(
    *,
    transaction_type: str,
    source_type: str,
    account,
    amount,
    transaction_date,
    created_by,
    reference: str = "",
    description: str = "",
    expense=None,
    payment_id=None,
    transfer_group=None,
    counter_account=None,
):
    amount = amount or Decimal("0.00")

    transaction = FinancialTransaction(
        transaction_type=transaction_type,
        source_type=source_type,
        account_id_value=account.id,
        account_name=account.name,
        amount=amount,
        transaction_date=transaction_date,
        created_by=created_by,
        reference=reference or None,
        description=description or None,
        expense_id_value=expense.id if expense else None,
        payment_id=payment_id,
        transfer_group=transfer_group,
        counter_account_id_value=counter_account.id if counter_account else None,
        counter_account_name=counter_account.name if counter_account else None,
    )

    transaction.full_clean()
    transaction.save()
    return transaction


def create_deposit(*, account, amount, transaction_date, created_by, reference="", description=""):
    return create_financial_transaction(
        transaction_type=FinancialTransaction.TYPE_IN,
        source_type=FinancialTransaction.SOURCE_DEPOSIT,
        account=account,
        amount=amount,
        transaction_date=transaction_date,
        created_by=created_by,
        reference=reference,
        description=description or f"Dépôt sur {account.name}",
    )


def create_withdrawal(*, account, amount, transaction_date, created_by, reference="", description=""):
    return create_financial_transaction(
        transaction_type=FinancialTransaction.TYPE_OUT,
        source_type=FinancialTransaction.SOURCE_WITHDRAWAL,
        account=account,
        amount=amount,
        transaction_date=transaction_date,
        created_by=created_by,
        reference=reference,
        description=description or f"Retrait depuis {account.name}",
    )


def create_transfer(*, source_account, destination_account, amount, transaction_date, created_by, reference="", description=""):
    transfer_group = f"TRF-{uuid4().hex[:12].upper()}"

    out_tx = create_financial_transaction(
        transaction_type=FinancialTransaction.TYPE_OUT,
        source_type=FinancialTransaction.SOURCE_TRANSFER,
        account=source_account,
        amount=amount,
        transaction_date=transaction_date,
        created_by=created_by,
        reference=reference or transfer_group,
        description=description or f"Transfert vers {destination_account.name}",
        transfer_group=transfer_group,
        counter_account=destination_account,
    )

    in_tx = create_financial_transaction(
        transaction_type=FinancialTransaction.TYPE_IN,
        source_type=FinancialTransaction.SOURCE_TRANSFER,
        account=destination_account,
        amount=amount,
        transaction_date=transaction_date,
        created_by=created_by,
        reference=reference or transfer_group,
        description=description or f"Transfert depuis {source_account.name}",
        transfer_group=transfer_group,
        counter_account=source_account,
    )

    return out_tx, in_tx


def create_supplier_payment_transaction(
    *,
    account,
    amount,
    transaction_date,
    created_by,
    reference="",
    description="",
):
    return create_financial_transaction(
        transaction_type=FinancialTransaction.TYPE_OUT,
        source_type=FinancialTransaction.SOURCE_SUPPLIER_PAYMENT,
        account=account,
        amount=amount,
        transaction_date=transaction_date,
        created_by=created_by,
        reference=reference,
        description=description or "Paiement fournisseur",
    )