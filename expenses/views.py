from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db import transaction

from .forms import ExpenseForm, FinancialAccountForm, ExpenseCategoryForm
from .models import Expense, ExpenseCategory
from sales.models import FinancialAccount
from .services import create_expense
from .services import create_financial_transaction
from .models import FinancialTransaction

from decimal import Decimal

from django.db.models import Sum, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce

from .forms import DepositForm, WithdrawalForm, TransferForm
from .services import create_deposit, create_withdrawal, create_transfer
from reports.models import PeriodClosure
from reports.services import assert_period_open


@login_required
def account_list(request):
    accounts = FinancialAccount.objects.all()
    return render(request, "expenses/account_list.html", {"accounts": accounts})
@login_required
def financial_transaction_list(request):
    transactions = (
        FinancialTransaction.objects.select_related("created_by")
        .all()
        .order_by("-transaction_date", "-id")
    )

    # Flux réels uniquement : on exclut les transferts internes
    real_in = FinancialTransaction.objects.filter(
        transaction_type=FinancialTransaction.TYPE_IN
    ).exclude(
        source_type=FinancialTransaction.SOURCE_TRANSFER
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"] or Decimal("0.00")

    real_out = FinancialTransaction.objects.filter(
        transaction_type=FinancialTransaction.TYPE_OUT
    ).exclude(
        source_type=FinancialTransaction.SOURCE_TRANSFER
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"] or Decimal("0.00")

    # Transferts internes : visibles séparément
    transfer_in = FinancialTransaction.objects.filter(
        transaction_type=FinancialTransaction.TYPE_IN,
        source_type=FinancialTransaction.SOURCE_TRANSFER,
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"] or Decimal("0.00")

    transfer_out = FinancialTransaction.objects.filter(
        transaction_type=FinancialTransaction.TYPE_OUT,
        source_type=FinancialTransaction.SOURCE_TRANSFER,
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"] or Decimal("0.00")

    # Solde global de trésorerie (réel)
    net_cash_flow = real_in - real_out

    # Résumé par compte : ici on garde tout, y compris transferts,
    # parce qu'un compte individuel doit bien montrer ses mouvements internes.
    account_summaries = (
        FinancialTransaction.objects.values("account_id_value", "account_name")
        .annotate(
            total_in=Coalesce(
                Sum(
                    Case(
                        When(transaction_type=FinancialTransaction.TYPE_IN, then="amount"),
                        default=Value(Decimal("0.00")),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ),
                Decimal("0.00"),
            ),
            total_out=Coalesce(
                Sum(
                    Case(
                        When(transaction_type=FinancialTransaction.TYPE_OUT, then="amount"),
                        default=Value(Decimal("0.00")),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                ),
                Decimal("0.00"),
            ),
        )
        .order_by("account_name")
    )

    for row in account_summaries:
        row["balance"] = row["total_in"] - row["total_out"]

    context = {
        "transactions": transactions,

        # Flux réels
        "real_in": real_in,
        "real_out": real_out,
        "net_cash_flow": net_cash_flow,

        # Transferts internes
        "transfer_in": transfer_in,
        "transfer_out": transfer_out,

        "account_summaries": account_summaries,
    }
    return render(request, "expenses/financial_transaction_list.html", context)
def account_create(request):
    form = FinancialAccountForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Compte créé.")
        return redirect("expenses:account_list")

    return render(request, "expenses/account_form.html", {"form": form})


@login_required
def expense_list(request):
    expenses = Expense.objects.select_related("category", "account").all()
    return render(request, "expenses/expense_list.html", {"expenses": expenses})


@login_required
def expense_create(request):
    form = ExpenseForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                expense = form.save(commit=False)
                expense.created_by = request.user
                assert_period_open(expense.spent_at, PeriodClosure.SCOPE_EXPENSE, "l'enregistrement de cette dépense")
                assert_period_open(expense.spent_at, PeriodClosure.SCOPE_CASH, "la sortie de trésorerie liée à cette dépense")
                # Cette fonction doit enregistrer la dépense
                create_expense(expense)

                # Une fois la dépense enregistrée, on crée la transaction financière
                create_financial_transaction(
                    transaction_type=FinancialTransaction.TYPE_OUT,
                    source_type=FinancialTransaction.SOURCE_EXPENSE,
                    account=expense.account,
                    amount=expense.amount,
                    transaction_date=expense.spent_at,
                    created_by=request.user,
                    reference=f"EXP-{expense.id}",
                    description=expense.description or f"Dépense {expense.category.name}",
                    expense=expense,
                )

            messages.success(request, "Dépense enregistrée.")
            return redirect("expenses:expense_list")

        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "expenses/expense_form.html",
        {
            "form": form,
        },
    )
@login_required
def category_list(request):
    categories = ExpenseCategory.objects.all().order_by("name")
    return render(request, "expenses/category_list.html", {"categories": categories})


@login_required
def category_create(request):
    form = ExpenseCategoryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Catégorie créée.")
        return redirect("expenses:category_list")

    return render(request, "expenses/category_form.html", {"form": form})
@login_required
def deposit_create(request):
    form = DepositForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                assert_period_open(form.cleaned_data["transaction_date"], PeriodClosure.SCOPE_CASH, "ce dépôt")
                create_deposit(
                    account=form.cleaned_data["account"],
                    amount=form.cleaned_data["amount"],
                    transaction_date=form.cleaned_data["transaction_date"],
                    created_by=request.user,
                    reference=form.cleaned_data["reference"],
                    description=form.cleaned_data["description"],
                )
            messages.success(request, "Dépôt enregistré avec succès.")
            return redirect("expenses:financial_transaction_list")
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "expenses/finance_operation_form.html",
        {
            "form": form,
            "title": "Nouveau dépôt",
            "subtitle": "Enregistrer une entrée manuelle sur un compte financier.",
        },
    )


@login_required
def withdrawal_create(request):
    form = WithdrawalForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                assert_period_open(form.cleaned_data["transaction_date"], PeriodClosure.SCOPE_CASH, "ce retrait")
                create_withdrawal(
                    account=form.cleaned_data["account"],
                    amount=form.cleaned_data["amount"],
                    transaction_date=form.cleaned_data["transaction_date"],
                    created_by=request.user,
                    reference=form.cleaned_data["reference"],
                    description=form.cleaned_data["description"],
                )
            messages.success(request, "Retrait enregistré avec succès.")
            return redirect("expenses:financial_transaction_list")
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "expenses/finance_operation_form.html",
        {
            "form": form,
            "title": "Nouveau retrait",
            "subtitle": "Enregistrer une sortie manuelle depuis un compte financier.",
        },
    )


@login_required
def transfer_create(request):
    form = TransferForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                assert_period_open(form.cleaned_data["transaction_date"], PeriodClosure.SCOPE_CASH, "ce transfert")
                create_transfer(
                    source_account=form.cleaned_data["source_account"],
                    destination_account=form.cleaned_data["destination_account"],
                    amount=form.cleaned_data["amount"],
                    transaction_date=form.cleaned_data["transaction_date"],
                    created_by=request.user,
                    reference=form.cleaned_data["reference"],
                    description=form.cleaned_data["description"],
                )
            messages.success(request, "Transfert enregistré avec succès.")
            return redirect("expenses:financial_transaction_list")
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "expenses/finance_transfer_form.html",
        {
            "form": form,
            "title": "Nouveau transfert",
            "subtitle": "Déplacer de l'argent d'un compte vers un autre.",
        },
    )