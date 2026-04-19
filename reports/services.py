from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import UserProfile
from .models import PeriodClosure


def user_can_manage_closures(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    return bool(profile and profile.role == UserProfile.ROLE_ADMIN)


def normalize_to_date(value):
    if value is None:
        raise ValidationError("Date de contrôle manquante pour la vérification de clôture.")

    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()

    if isinstance(value, date):
        return value

    raise ValidationError("Type de date invalide pour la vérification de clôture.")


def get_matching_active_closures(target_date, scope):
    target_date = normalize_to_date(target_date)

    closures = PeriodClosure.objects.filter(
        status=PeriodClosure.STATUS_CLOSED,
        start_date__lte=target_date,
        end_date__gte=target_date,
    )

    allowed_scopes = [PeriodClosure.SCOPE_GLOBAL]

    if scope == PeriodClosure.SCOPE_CASH:
        allowed_scopes += [PeriodClosure.SCOPE_CASH]
    elif scope == PeriodClosure.SCOPE_STOCK:
        allowed_scopes += [PeriodClosure.SCOPE_STOCK]
    elif scope == PeriodClosure.SCOPE_SALES:
        allowed_scopes += [PeriodClosure.SCOPE_SALES]
    elif scope == PeriodClosure.SCOPE_PURCHASE:
        allowed_scopes += [PeriodClosure.SCOPE_PURCHASE]
    elif scope == PeriodClosure.SCOPE_PRODUCTION:
        allowed_scopes += [PeriodClosure.SCOPE_PRODUCTION]
    elif scope == PeriodClosure.SCOPE_EXPENSE:
        allowed_scopes += [PeriodClosure.SCOPE_EXPENSE]

    closures = closures.filter(scope__in=allowed_scopes)

    # logique métier par type
    filtered = []
    for closure in closures:
        if closure.closure_type == PeriodClosure.TYPE_MONTHLY:
            filtered.append(closure)
        elif closure.closure_type == PeriodClosure.TYPE_YEARLY:
            filtered.append(closure)
        elif closure.closure_type == PeriodClosure.TYPE_DAILY_CASH and scope == PeriodClosure.SCOPE_CASH:
            filtered.append(closure)
        elif closure.closure_type == PeriodClosure.TYPE_INVENTORY and scope == PeriodClosure.SCOPE_STOCK:
            filtered.append(closure)

    return filtered


def assert_period_open(target_date, scope, action_label="cette opération"):
    closures = get_matching_active_closures(target_date, scope)
    if closures:
        first = closures[0]
        raise ValidationError(
            f"Impossible d'effectuer {action_label}. "
            f"La période du {first.start_date} au {first.end_date} est clôturée "
            f"({first.get_closure_type_display()} / {first.get_scope_display()})."
        )


def get_closure_warnings(start_date, end_date):
    warnings = []

    # Ici on prépare l'avenir. On avertit seulement, sans bloquer.
    # Tu pourras durcir plus tard si l'entreprise le veut.
    from sales.models import Invoice
    from expenses.models import Expense
    from inventory.models import Purchase, ProductionOrder

    unpaid_invoices = Invoice.objects.filter(
        issue_date__date__gte=start_date,
        issue_date__date__lte=end_date,
    ).exclude(status=Invoice.STATUS_CANCELLED).exclude(status=Invoice.STATUS_PAID).count()

    open_purchases = Purchase.objects.filter(
        ordered_at__date__gte=start_date,
        ordered_at__date__lte=end_date,
    ).exclude(status=Purchase.STATUS_RECEIVED).exclude(status=Purchase.STATUS_CANCELLED).count()

    draft_productions = ProductionOrder.objects.filter(
        production_date__date__gte=start_date,
        production_date__date__lte=end_date,
    ).exclude(status=ProductionOrder.STATUS_DONE).exclude(status=ProductionOrder.STATUS_CANCELLED).count()

    expense_count = Expense.objects.filter(
        spent_at__date__gte=start_date,
        spent_at__date__lte=end_date,
    ).count()

    if unpaid_invoices:
        warnings.append(f"{unpaid_invoices} facture(s) non totalement réglée(s).")
    if open_purchases:
        warnings.append(f"{open_purchases} achat(s) non réceptionné(s).")
    if draft_productions:
        warnings.append(f"{draft_productions} production(s) non finalisée(s).")
    warnings.append(f"{expense_count} dépense(s) sur la période.")

    return warnings