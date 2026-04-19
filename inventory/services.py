from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from expenses.models import Expense, FinancialTransaction
from expenses.services import create_financial_transaction, create_supplier_payment_transaction
from reports.models import PeriodClosure
from reports.services import assert_period_open

from .models import (
    Depot,
    Product,
    ProductionOrder,
    ProductionSupplyUsage,
    Purchase,
    StockBalance,
    StockMovement,
    StockMovementItem,
    SupplierPayable,
    SupplierPayment,
    SupplyItem,
)


def get_or_create_stock_balance(depot, product):
    balance, _ = StockBalance.objects.get_or_create(
        depot=depot,
        product=product,
        defaults={"qty_packs": 0},
    )
    return balance


@transaction.atomic
def apply_stock_movement(movement: StockMovement):
    items = list(movement.items.select_related("product"))
    if not items:
        raise ValidationError("Impossible d'appliquer un mouvement sans lignes.")

    assert_period_open(
        movement.movement_date,
        PeriodClosure.SCOPE_STOCK,
        f"le mouvement de stock #{movement.id or 'nouveau'}",
    )

    for item in items:
        qty = item.qty_packs

        if movement.movement_type == StockMovement.TYPE_IN:
            balance_to = get_or_create_stock_balance(movement.depot_to, item.product)
            balance_to.qty_packs += qty
            balance_to.save()

        elif movement.movement_type == StockMovement.TYPE_OUT:
            balance_from = get_or_create_stock_balance(movement.depot_from, item.product)
            if balance_from.qty_packs < qty:
                raise ValidationError(
                    f"Stock insuffisant pour {item.product.name} dans le dépôt {movement.depot_from.name}."
                )
            balance_from.qty_packs -= qty
            balance_from.save()

        elif movement.movement_type == StockMovement.TYPE_LOSS:
            balance_from = get_or_create_stock_balance(movement.depot_from, item.product)
            if balance_from.qty_packs < qty:
                raise ValidationError(
                    f"Stock insuffisant pour enregistrer la perte de {item.product.name}."
                )
            balance_from.qty_packs -= qty
            balance_from.save()

        elif movement.movement_type == StockMovement.TYPE_TRANSFER:
            balance_from = get_or_create_stock_balance(movement.depot_from, item.product)
            if balance_from.qty_packs < qty:
                raise ValidationError(
                    f"Stock insuffisant pour transférer {item.product.name} depuis {movement.depot_from.name}."
                )
            balance_to = get_or_create_stock_balance(movement.depot_to, item.product)
            balance_from.qty_packs -= qty
            balance_to.qty_packs += qty
            balance_from.save()
            balance_to.save()

        elif movement.movement_type == StockMovement.TYPE_ADJUST:
            target_depot = movement.depot_to or movement.depot_from
            if not target_depot:
                raise ValidationError("Un ajustement doit cibler un dépôt.")
            balance = get_or_create_stock_balance(target_depot, item.product)
            balance.qty_packs += qty
            balance.save()

        else:
            raise ValidationError("Type de mouvement non supporté.")


def generate_production_number():
    last = ProductionOrder.objects.order_by("-id").first()
    next_id = 1 if last is None else last.id + 1
    return f"PROD-{next_id:05d}"


@transaction.atomic
def start_production(production, user):
    if production.status != ProductionOrder.STATUS_DRAFT:
        raise ValueError("Seule une production brouillon peut être démarrée.")

    assert_period_open(
        production.production_date,
        PeriodClosure.SCOPE_PRODUCTION,
        f"le démarrage de la production {production.number}",
    )

    production.status = ProductionOrder.STATUS_IN_PROGRESS
    production.save(update_fields=["status"])


@transaction.atomic
def close_production(production, user, usage_items=None):
    if production.status != ProductionOrder.STATUS_IN_PROGRESS:
        raise ValueError("Seule une production en cours peut être validée.")

    assert_period_open(
        production.production_date,
        PeriodClosure.SCOPE_PRODUCTION,
        f"la clôture de la production {production.number}",
    )
    assert_period_open(
        production.production_date,
        PeriodClosure.SCOPE_STOCK,
        f"l'entrée en stock de la production {production.number}",
    )

    net_qty = (production.actual_qty_packs or 0) - (production.loss_qty_packs or 0)
    if net_qty <= 0:
        raise ValueError("La quantité nette produite doit être supérieure à 0.")

    production.net_qty_packs = net_qty
    production.supply_usages.all().delete()

    supply_total_cost = Decimal("0.00")

    if production.cost_mode == ProductionOrder.COST_MODE_MANUAL:
        total_cost = production.manual_total_cost or Decimal("0.00")
        if total_cost <= 0:
            raise ValueError("Le coût total de production doit être supérieur à 0.")
    else:
        usage_items = usage_items or []
        has_usage = False

        for usage in usage_items:
            supply_item = SupplyItem.objects.select_for_update().get(pk=usage["supply_item"].id)
            qty_units = usage["qty_units"]

            if qty_units <= 0:
                continue

            if supply_item.current_qty < qty_units:
                raise ValueError(
                    f"Stock intrant insuffisant pour {supply_item.name}. "
                    f"Disponible : {supply_item.current_qty}, demandé : {qty_units}."
                )

            unit_cost_snapshot = supply_item.average_unit_cost or supply_item.last_unit_cost or Decimal("0.00")
            line_total = qty_units * unit_cost_snapshot

            ProductionSupplyUsage.objects.create(
                production=production,
                supply_item_id_value=supply_item.id,
                supply_item_name=supply_item.name,
                qty_units=qty_units,
                unit_cost_snapshot=unit_cost_snapshot,
                total_cost=line_total,
            )

            supply_item.current_qty = supply_item.current_qty - qty_units
            supply_item.save(update_fields=["current_qty"])

            supply_total_cost += line_total
            has_usage = True

        other_costs = (
            (production.labor_cost or Decimal("0.00")) +
            (production.energy_cost or Decimal("0.00")) +
            (production.packaging_cost or Decimal("0.00")) +
            (production.other_cost or Decimal("0.00"))
        )

        total_cost = supply_total_cost + other_costs

        if not has_usage and total_cost <= 0:
            raise ValueError(
                "En mode semi-automatique, veuillez saisir au moins un intrant utilisé ou un autre coût."
            )

    production.total_production_cost = total_cost
    production.unit_production_cost = total_cost / Decimal(net_qty)
    production.status = ProductionOrder.STATUS_DONE
    production.validated_by = user
    production.validated_at = timezone.now()

    depot = Depot.objects.get(pk=production.depot_id_value)
    product = Product.objects.get(pk=production.product_id_value)

    movement = StockMovement.objects.create(
        movement_date=production.production_date,
        movement_type=StockMovement.TYPE_IN,
        depot_from=None,
        depot_to=depot,
        ref_type=StockMovement.REF_PRODUCTION,
        ref_id=production.id,
        reason=f"Validation production {production.number}",
        created_by=user,
    )

    StockMovementItem.objects.create(
        movement=movement,
        product=product,
        qty_packs=production.net_qty_packs,
        unit_cost=production.unit_production_cost,
    )

    apply_stock_movement(movement)

    production.stock_movement_id_value = movement.id
    production.save(
        update_fields=[
            "net_qty_packs",
            "total_production_cost",
            "unit_production_cost",
            "status",
            "validated_by",
            "validated_at",
            "stock_movement_id_value",
        ]
    )

    return production


def generate_purchase_number():
    last = Purchase.objects.order_by("-id").first()
    next_id = 1 if last is None else last.id + 1
    return f"ACH-{next_id:05d}"


def generate_supplier_payable_number():
    last = SupplierPayable.objects.order_by("-id").first()
    next_id = 1 if last is None else last.id + 1
    return f"DET-{next_id:05d}"


def recompute_purchase_totals(purchase):
    subtotal = Decimal("0.00")

    for item in purchase.items.all():
        qty_units = item.qty_units or Decimal("0.000")
        unit_cost = item.unit_cost or Decimal("0.00")
        item.line_total = qty_units * unit_cost
        item.save(update_fields=["line_total"])
        subtotal += item.line_total

    purchase.subtotal = subtotal
    purchase.total = subtotal
    purchase.save(update_fields=["subtotal", "total"])


@transaction.atomic
def receive_purchase(purchase, user):
    if purchase.status == Purchase.STATUS_RECEIVED:
        raise ValueError("Cet achat a déjà été réceptionné.")

    assert_period_open(
        purchase.ordered_at,
        PeriodClosure.SCOPE_PURCHASE,
        f"la réception de l'achat {purchase.number}",
    )
    assert_period_open(
        timezone.now(),
        PeriodClosure.SCOPE_STOCK,
        f"l'entrée stock de l'achat {purchase.number}",
    )

    for item in purchase.items.all():
        supply_item = SupplyItem.objects.select_for_update().get(pk=item.supply_item_id_value)

        old_qty = supply_item.current_qty or Decimal("0.000")
        incoming_qty = item.qty_units or Decimal("0.000")
        old_avg_cost = supply_item.average_unit_cost or Decimal("0.00")
        incoming_unit_cost = item.unit_cost or Decimal("0.00")

        new_qty = old_qty + incoming_qty

        if new_qty > 0:
            weighted_total = (old_qty * old_avg_cost) + (incoming_qty * incoming_unit_cost)
            new_avg_cost = weighted_total / new_qty
        else:
            new_avg_cost = Decimal("0.00")

        supply_item.current_qty = new_qty
        supply_item.last_unit_cost = incoming_unit_cost
        supply_item.average_unit_cost = new_avg_cost
        supply_item.save(update_fields=["current_qty", "last_unit_cost", "average_unit_cost"])

    purchase.status = Purchase.STATUS_RECEIVED
    purchase.received_at = timezone.now()
    purchase.validated_by = user
    purchase.validated_at = timezone.now()
    purchase.save(
        update_fields=[
            "status",
            "received_at",
            "validated_by",
            "validated_at",
        ]
    )

    if not hasattr(purchase, "supplier_payable"):
        payable = SupplierPayable.objects.create(
            number=generate_supplier_payable_number(),
            purchase=purchase,
            supplier=purchase.supplier,
            amount_total=purchase.total,
            amount_paid=Decimal("0.00"),
            amount_due=purchase.total,
            status=SupplierPayable.STATUS_OPEN,
            payable_date=timezone.now(),
            note=f"Dette créée à la réception de l'achat {purchase.number}",
            created_by=user,
        )
        purchase.payable_created = True
        purchase.payable_id_value = payable.id
        purchase.save(update_fields=["payable_created", "payable_id_value"])

    return purchase


@transaction.atomic
def register_purchase_as_expense(purchase, *, account, category, spent_at, description, user):
    if purchase.expense_registered:
        raise ValueError("Cette dépense d'achat est déjà enregistrée.")

    assert_period_open(
        spent_at,
        PeriodClosure.SCOPE_EXPENSE,
        f"la dépense liée à l'achat {purchase.number}",
    )
    assert_period_open(
        spent_at,
        PeriodClosure.SCOPE_CASH,
        f"la sortie de trésorerie liée à l'achat {purchase.number}",
    )

    expense = Expense.objects.create(
        category=category,
        account=account,
        amount=purchase.total,
        description=description or f"Achat {purchase.number} - {purchase.supplier.name}",
        spent_at=spent_at,
        created_by=user,
    )

    create_financial_transaction(
        transaction_type=FinancialTransaction.TYPE_OUT,
        source_type=FinancialTransaction.SOURCE_EXPENSE,
        account=account,
        amount=expense.amount,
        transaction_date=expense.spent_at,
        created_by=user,
        reference=f"PUR-EXP-{purchase.id}",
        description=expense.description,
        expense=expense,
    )

    purchase.expense_registered = True
    purchase.expense_id_value = expense.id
    purchase.save(update_fields=["expense_registered", "expense_id_value"])

    return expense


@transaction.atomic
def register_supplier_payment(payable, *, account, paid_at, amount, reference, note, user):
    if payable.status == SupplierPayable.STATUS_CANCELLED:
        raise ValidationError("Impossible de payer une dette fournisseur annulée.")
    if payable.status == SupplierPayable.STATUS_PAID:
        raise ValidationError("Cette dette fournisseur est déjà entièrement payée.")
    if amount <= 0:
        raise ValidationError("Le montant du paiement fournisseur doit être supérieur à zéro.")
    if amount > payable.amount_due:
        raise ValidationError(
            f"Le montant saisi dépasse le solde restant dû ({payable.amount_due} FC)."
        )

    assert_period_open(
        paid_at,
        PeriodClosure.SCOPE_CASH,
        f"le paiement fournisseur {payable.number}",
    )
    assert_period_open(
        paid_at,
        PeriodClosure.SCOPE_PURCHASE,
        f"la mise à jour de dette fournisseur {payable.number}",
    )

    payment = SupplierPayment(
        payable=payable,
        account_id_value=account.id,
        account_name=account.name,
        paid_at=paid_at,
        amount=amount,
        reference=reference,
        note=note,
        created_by=user,
    )
    payment.full_clean()
    payment.save()

    payable.amount_paid = (payable.amount_paid or Decimal("0.00")) + amount
    payable.amount_due = payable.amount_total - payable.amount_paid

    if payable.amount_due <= Decimal("0.00"):
        payable.amount_due = Decimal("0.00")
        payable.status = SupplierPayable.STATUS_PAID
    elif payable.amount_paid > Decimal("0.00"):
        payable.status = SupplierPayable.STATUS_PARTIAL
    else:
        payable.status = SupplierPayable.STATUS_OPEN

    payable.full_clean()
    payable.save(update_fields=["amount_paid", "amount_due", "status"])

    create_supplier_payment_transaction(
        account=account,
        amount=amount,
        transaction_date=paid_at,
        created_by=user,
        reference=f"SUP-PAY-{payment.id}",
        description=f"Paiement fournisseur {payable.supplier.name} / {payable.number}",
    )

    return payment