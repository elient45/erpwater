from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from expenses.models import Expense, FinancialTransaction
from inventory.models import (
    Product,
    ProductionOrder,
    Purchase,
    StockBalance,
    StockMovement,
    SupplierPayable,
    SupplierPayment,
)
from sales.models import Invoice, InvoiceItem, Payment

from .forms import PeriodClosureForm, PeriodReopenForm
from .models import PeriodClosure
from .services import get_closure_warnings, user_can_manage_closures


def _build_local_datetime_range(start_date, end_date):
    """
    Construit une vraie plage datetime locale [début inclus, fin exclue]
    pour éviter les bugs de filtrage avec __date et UTC.
    """
    current_tz = timezone.get_current_timezone()

    start_dt = timezone.make_aware(
        datetime.combine(start_date, time.min),
        current_tz,
    )

    end_dt = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
        current_tz,
    )

    return start_dt, end_dt

@login_required
def dashboard(request):
    total_stock_items = StockBalance.objects.aggregate(
        total=Coalesce(Sum("qty_packs"), 0)
    )["total"]

    sales_base = Invoice.objects.exclude(status=Invoice.STATUS_CANCELLED)

    sales_totals = sales_base.aggregate(
        total_ht=Coalesce(Sum("total_before_tax"), Decimal("0.00")),
        total_tax=Coalesce(Sum("tax_amount"), Decimal("0.00")),
        total_ttc=Coalesce(Sum("total"), Decimal("0.00")),
        total_paid=Coalesce(Sum("paid_amount"), Decimal("0.00")),
        count=Coalesce(Count("id"), 0),
    )
    sales_totals["total_due"] = sales_totals["total_ttc"] - sales_totals["total_paid"]

    purchase_expense_ids = Purchase.objects.filter(
        status=Purchase.STATUS_RECEIVED,
        expense_registered=True,
        expense_id_value__isnull=False,
    ).values_list("expense_id_value", flat=True)

    expenses = Expense.objects.exclude(id__in=purchase_expense_ids)

    expense_totals = expenses.aggregate(
        count=Coalesce(Count("id"), 0),
        total=Coalesce(Sum("amount"), Decimal("0.00")),
    )

    productions = ProductionOrder.objects.filter(status=ProductionOrder.STATUS_DONE)

    production_totals = productions.aggregate(
        count=Coalesce(Count("id"), 0),
        total_net_qty=Coalesce(Sum("net_qty_packs"), 0),
        total_cost=Coalesce(Sum("total_production_cost"), Decimal("0.00")),
    )

    purchases = Purchase.objects.filter(status=Purchase.STATUS_RECEIVED)

    purchase_totals = purchases.aggregate(
        count=Coalesce(Count("id"), 0),
        total=Coalesce(Sum("total"), Decimal("0.00")),
    )

    supplier_payment_totals = SupplierPayment.objects.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )

    supplier_payable_totals = SupplierPayable.objects.exclude(
        status=SupplierPayable.STATUS_CANCELLED
    ).aggregate(
        total_due=Coalesce(Sum("amount_due"), Decimal("0.00"))
    )

    total_clients = Invoice.objects.values("customer").distinct().count()
    total_products = Product.objects.count()

    low_stock_products = StockBalance.objects.select_related("product", "depot").filter(
        qty_packs__lte=F("product__min_stock")
    ).order_by("product__name")[:10]

    top_products = (
        InvoiceItem.objects.values("product__name")
        .annotate(total_qty=Coalesce(Sum("qty_packs"), 0))
        .order_by("-total_qty")[:10]
    )

    recent_invoices = (
        Invoice.objects.select_related("customer", "created_by")
        .order_by("-issue_date")[:5]
    )

    recent_movements = (
        StockMovement.objects.select_related("created_by", "depot_from", "depot_to")
        .order_by("-movement_date")[:5]
    )

    cost_per_unit = Decimal("0.00")
    if production_totals["total_net_qty"] > 0:
        cost_per_unit = production_totals["total_cost"] / production_totals["total_net_qty"]

    context = {
        "total_stock_items": total_stock_items,

        "sales_totals": sales_totals,
        "expense_totals": expense_totals,
        "production_totals": production_totals,
        "purchase_totals": purchase_totals,
        "supplier_payment_totals": supplier_payment_totals,
        "supplier_payable_totals": supplier_payable_totals,

        "cost_per_unit": cost_per_unit,

        "total_clients": total_clients,
        "total_products": total_products,

        "low_stock_products": low_stock_products,
        "top_products": top_products,
        "recent_invoices": recent_invoices,
        "recent_movements": recent_movements,
    }
    return render(request, "dashboard.html", context)


@login_required
def sales_report(request):
    invoices = (
        Invoice.objects.select_related("customer", "created_by", "validated_by")
        .all()
        .order_by("-issue_date")
    )

    totals = invoices.exclude(status=Invoice.STATUS_CANCELLED).aggregate(
        total_sales_ht=Coalesce(Sum("total_before_tax"), Decimal("0.00")),
        total_tax=Coalesce(Sum("tax_amount"), Decimal("0.00")),
        total_sales_ttc=Coalesce(Sum("total"), Decimal("0.00")),
        total_paid=Coalesce(Sum("paid_amount"), Decimal("0.00")),
    )
    totals["total_due"] = (totals["total_sales_ttc"] or Decimal("0.00")) - (totals["total_paid"] or Decimal("0.00"))

    top_clients = (
        Invoice.objects.values("customer__name")
        .annotate(
            invoice_count=Count("id"),
            total_ht=Coalesce(Sum("total_before_tax"), Decimal("0.00")),
            total_tax=Coalesce(Sum("tax_amount"), Decimal("0.00")),
            total_ttc=Coalesce(Sum("total"), Decimal("0.00")),
            paid=Coalesce(Sum("paid_amount"), Decimal("0.00"))
        )
        .order_by("-total_ttc")[:10]
    )

    top_products = (
        InvoiceItem.objects.values("product__name")
        .annotate(
            total_qty=Coalesce(Sum("qty_packs"), 0),
            total_amount=Coalesce(Sum("line_total"), Decimal("0.00"))
        )
        .order_by("-total_qty")[:10]
    )

    context = {
        "invoices": invoices,
        "totals": totals,
        "top_clients": top_clients,
        "top_products": top_products,
    }
    return render(request, "reports/sales_report.html", context)


@login_required
def expenses_report(request):
    expenses = (
        Expense.objects.select_related("category", "account", "created_by")
        .all()
        .order_by("-spent_at")
    )

    total_expenses = expenses.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    by_category = (
        Expense.objects.values("category__name")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0.00")))
        .order_by("-total")
    )

    by_account = (
        Expense.objects.values("account__name")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0.00")))
        .order_by("-total")
    )

    context = {
        "expenses": expenses,
        "total_expenses": total_expenses,
        "by_category": by_category,
        "by_account": by_account,
    }
    return render(request, "reports/expenses_report.html", context)


@login_required
def stock_report(request):
    balances = (
        StockBalance.objects.select_related("product", "depot")
        .all()
        .order_by("depot__name", "product__name")
    )

    low_stock_products = balances.filter(
        qty_packs__lte=F("product__min_stock")
    )

    total_stock = balances.aggregate(
        total=Coalesce(Sum("qty_packs"), 0)
    )["total"]

    context = {
        "balances": balances,
        "low_stock_products": low_stock_products,
        "total_stock": total_stock,
    }
    return render(request, "reports/stock_report.html", context)


@login_required
def payments_report(request):
    payments = (
        Payment.objects.select_related("invoice", "invoice__customer", "account", "received_by")
        .all()
        .order_by("-paid_at")
    )

    total_payments = payments.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    by_method = (
        Payment.objects.values("method")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0.00")))
        .order_by("-total")
    )

    by_account = (
        Payment.objects.values("account__name")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0.00")))
        .order_by("-total")
    )

    context = {
        "payments": payments,
        "total_payments": total_payments,
        "by_method": by_method,
        "by_account": by_account,
    }
    return render(request, "reports/payments_report.html", context)


@login_required
def monthly_summary(request):
    today = timezone.localdate()
    current_tz = timezone.get_current_timezone()

    try:
        month = int(request.GET.get("month", today.month))
    except (TypeError, ValueError):
        month = today.month

    try:
        year = int(request.GET.get("year", today.year))
    except (TypeError, ValueError):
        year = today.year

    if month < 1 or month > 12:
        month = today.month

    start_local = timezone.make_aware(
        datetime(year, month, 1, 0, 0, 0),
        current_tz,
    )

    if month == 12:
        next_start_local = timezone.make_aware(
            datetime(year + 1, 1, 1, 0, 0, 0),
            current_tz,
        )
    else:
        next_start_local = timezone.make_aware(
            datetime(year, month + 1, 1, 0, 0, 0),
            current_tz,
        )

    invoices = (
        Invoice.objects.filter(
            issue_date__gte=start_local,
            issue_date__lt=next_start_local,
        )
        .exclude(status=Invoice.STATUS_CANCELLED)
        .select_related("customer", "created_by")
        .order_by("-issue_date")
    )

    sales_totals = invoices.aggregate(
        count=Coalesce(Count("id"), 0),
        total_ht=Coalesce(Sum("total_before_tax"), Decimal("0.00")),
        total_tax=Coalesce(Sum("tax_amount"), Decimal("0.00")),
        total_ttc=Coalesce(Sum("total"), Decimal("0.00")),
        total_paid=Coalesce(Sum("paid_amount"), Decimal("0.00")),
    )
    sales_totals["total_due"] = sales_totals["total_ttc"] - sales_totals["total_paid"]

    purchase_expense_ids = Purchase.objects.filter(
        ordered_at__gte=start_local,
        ordered_at__lt=next_start_local,
        status=Purchase.STATUS_RECEIVED,
        expense_registered=True,
        expense_id_value__isnull=False,
    ).values_list("expense_id_value", flat=True)

    expenses = (
        Expense.objects.filter(
            spent_at__gte=start_local,
            spent_at__lt=next_start_local,
        )
        .exclude(id__in=purchase_expense_ids)
        .select_related("category", "account", "created_by")
        .order_by("-spent_at")
    )

    expense_totals = expenses.aggregate(
        count=Coalesce(Count("id"), 0),
        total=Coalesce(Sum("amount"), Decimal("0.00")),
    )

    productions = (
        ProductionOrder.objects.filter(
            production_date__gte=start_local,
            production_date__lt=next_start_local,
            status=ProductionOrder.STATUS_DONE,
        )
        .select_related("created_by")
        .order_by("-production_date")
    )

    production_totals = productions.aggregate(
        count=Coalesce(Count("id"), 0),
        total_net_qty=Coalesce(Sum("net_qty_packs"), 0),
        total_cost=Coalesce(Sum("total_production_cost"), Decimal("0.00")),
    )

    purchases = (
        Purchase.objects.filter(
            ordered_at__gte=start_local,
            ordered_at__lt=next_start_local,
            status=Purchase.STATUS_RECEIVED,
        )
        .select_related("supplier", "created_by")
        .order_by("-ordered_at")
    )

    purchase_totals = purchases.aggregate(
        count=Coalesce(Count("id"), 0),
        total=Coalesce(Sum("total"), Decimal("0.00")),
    )

    supplier_payment_totals = SupplierPayment.objects.filter(
        paid_at__gte=start_local,
        paid_at__lt=next_start_local,
    ).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )

    supplier_payable_totals = SupplierPayable.objects.exclude(
        status=SupplierPayable.STATUS_CANCELLED
    ).aggregate(
        total_due=Coalesce(Sum("amount_due"), Decimal("0.00"))
    )

    stock_movements = (
        StockMovement.objects.filter(
            created_at__gte=start_local,
            created_at__lt=next_start_local,
        )
        .select_related("depot_from", "depot_to", "created_by")
        .prefetch_related("items__product")
        .order_by("-created_at")[:50]
    )

    cost_per_unit = Decimal("0.00")
    if production_totals["total_net_qty"] > 0:
        cost_per_unit = production_totals["total_cost"] / production_totals["total_net_qty"]

    context = {
        "selected_month": month,
        "selected_year": year,
        "start_date": start_local,
        "end_date": next_start_local,
        "sales_totals": sales_totals,
        "invoices": invoices,
        "expense_totals": expense_totals,
        "expenses": expenses,
        "production_totals": production_totals,
        "productions": productions,
        "purchase_totals": purchase_totals,
        "purchases": purchases,
        "supplier_payment_totals": supplier_payment_totals,
        "supplier_payable_totals": supplier_payable_totals,
        "stock_movements": stock_movements,
        "cost_per_unit": cost_per_unit,
        "month_choices": list(range(1, 13)),
        "year_choices": list(range(today.year - 3, today.year + 2)),
    }

    return render(request, "reports/monthly_summary.html", context)


@login_required
def period_closure_list(request):
    closures = PeriodClosure.objects.select_related("closed_by", "reopened_by").all().order_by("-start_date", "-id")
    return render(request, "reports/period_closure_list.html", {"closures": closures})


@login_required
def period_closure_create(request):
    if not user_can_manage_closures(request.user):
        messages.error(request, "Vous n'êtes pas autorisé à clôturer une période.")
        return redirect("reports:period_closure_list")

    form = PeriodClosureForm(request.POST or None)
    warnings = []

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                closure = form.save(commit=False)
                closure.closed_by = request.user
                closure.status = PeriodClosure.STATUS_CLOSED
                closure.full_clean()
                closure.save()

            messages.success(request, "Période clôturée avec succès.")
            return redirect("reports:period_closure_detail", pk=closure.pk)
        except ValidationError as exc:
            messages.error(request, str(exc))

    if form.is_bound and form.is_valid():
        warnings = get_closure_warnings(
            form.cleaned_data["start_date"],
            form.cleaned_data["end_date"],
        )

    return render(
        request,
        "reports/period_closure_form.html",
        {
            "form": form,
            "warnings": warnings,
            "title": "Nouvelle clôture",
        },
    )


@login_required
def period_closure_detail(request, pk):
    closure = get_object_or_404(
        PeriodClosure.objects.select_related("closed_by", "reopened_by"),
        pk=pk,
    )

    warnings = get_closure_warnings(closure.start_date, closure.end_date)

    start_dt, end_dt = _build_local_datetime_range(closure.start_date, closure.end_date)

    transactions = FinancialTransaction.objects.filter(
        transaction_date__gte=start_dt,
        transaction_date__lt=end_dt,
    ).select_related("created_by").order_by("-transaction_date", "-id")

    real_in_qs = transactions.filter(
        transaction_type=FinancialTransaction.TYPE_IN
    ).exclude(
        source_type=FinancialTransaction.SOURCE_TRANSFER
    )

    real_out_qs = transactions.filter(
        transaction_type=FinancialTransaction.TYPE_OUT
    ).exclude(
        source_type=FinancialTransaction.SOURCE_TRANSFER
    )

    total_real_in = real_in_qs.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"] or Decimal("0.00")

    total_real_out = real_out_qs.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"] or Decimal("0.00")

    customer_payments = transactions.filter(
        source_type=FinancialTransaction.SOURCE_PAYMENT
    )

    supplier_payments = transactions.filter(
        source_type=FinancialTransaction.SOURCE_SUPPLIER_PAYMENT
    )

    expense_transactions = transactions.filter(
        source_type=FinancialTransaction.SOURCE_EXPENSE
    )

    deposit_transactions = transactions.filter(
        source_type=FinancialTransaction.SOURCE_DEPOSIT
    )

    withdrawal_transactions = transactions.filter(
        source_type=FinancialTransaction.SOURCE_WITHDRAWAL
    )

    transfer_transactions = transactions.filter(
        source_type=FinancialTransaction.SOURCE_TRANSFER
    )

    invoices = Invoice.objects.filter(
        issue_date__gte=start_dt,
        issue_date__lt=end_dt,
    ).select_related("customer", "created_by").order_by("-issue_date", "-id")

    payments = Payment.objects.filter(
        paid_at__gte=start_dt,
        paid_at__lt=end_dt,
    ).select_related("invoice", "invoice__customer", "account", "received_by").order_by("-paid_at", "-id")

    purchases = Purchase.objects.filter(
        ordered_at__gte=start_dt,
        ordered_at__lt=end_dt,
    ).select_related("supplier", "created_by", "validated_by").order_by("-ordered_at", "-id")

    productions = ProductionOrder.objects.filter(
        production_date__gte=start_dt,
        production_date__lt=end_dt,
    ).select_related("created_by", "validated_by").order_by("-production_date", "-id")

    stock_movements = StockMovement.objects.filter(
        movement_date__gte=start_dt,
        movement_date__lt=end_dt,
    ).select_related("depot_from", "depot_to", "created_by").prefetch_related("items__product").order_by("-movement_date", "-id")

    monthly_summary_url = None
    if (
        closure.closure_type == PeriodClosure.TYPE_MONTHLY
        and closure.start_date.month == closure.end_date.month
        and closure.start_date.year == closure.end_date.year
    ):
        monthly_summary_url = f"/reports/monthly-summary/?month={closure.start_date.month}&year={closure.start_date.year}"

    context = {
        "closure": closure,
        "warnings": warnings,
        "can_manage_closures": user_can_manage_closures(request.user),

        "total_real_in": total_real_in,
        "total_real_out": total_real_out,
        "net_cash_flow": total_real_in - total_real_out,

        "customer_payments": customer_payments,
        "supplier_payments": supplier_payments,
        "expense_transactions": expense_transactions,
        "deposit_transactions": deposit_transactions,
        "withdrawal_transactions": withdrawal_transactions,
        "transfer_transactions": transfer_transactions,

        "invoices": invoices,
        "payments": payments,
        "purchases": purchases,
        "productions": productions,
        "stock_movements": stock_movements,

        "monthly_summary_url": monthly_summary_url,
    }
    return render(request, "reports/period_closure_detail.html", context)


@login_required
def period_closure_reopen(request, pk):
    closure = get_object_or_404(PeriodClosure, pk=pk)

    if not user_can_manage_closures(request.user):
        messages.error(request, "Vous n'êtes pas autorisé à rouvrir une période.")
        return redirect("reports:period_closure_detail", pk=closure.pk)

    if closure.status == PeriodClosure.STATUS_REOPENED:
        messages.error(request, "Cette période est déjà rouverte.")
        return redirect("reports:period_closure_detail", pk=closure.pk)

    form = PeriodReopenForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        closure.status = PeriodClosure.STATUS_REOPENED
        closure.reopened_by = request.user
        closure.reopened_at = timezone.now()
        closure.reopen_reason = form.cleaned_data["reopen_reason"]
        closure.full_clean()
        closure.save(
            update_fields=["status", "reopened_by", "reopened_at", "reopen_reason"]
        )
        messages.success(request, "Période rouverte avec succès.")
        return redirect("reports:period_closure_detail", pk=closure.pk)

    return render(
        request,
        "reports/period_closure_reopen_form.html",
        {
            "form": form,
            "closure": closure,
            "title": f"Rouvrir la période {closure.start_date} - {closure.end_date}",
        },
    )