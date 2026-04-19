from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from accounts.models import UserProfile
from inventory.models import StockMovement, StockMovementItem
from inventory.services import apply_stock_movement

from .models import Delivery, Invoice, InvoiceStockLink, Payment
from reports.models import PeriodClosure
from reports.services import assert_period_open

def generate_invoice_number():
    today = timezone.now()
    prefix = f"FAC-{today.strftime('%Y%m%d')}"
    last_invoice = Invoice.objects.filter(number__startswith=prefix).order_by("-id").first()

    if not last_invoice:
        return f"{prefix}-001"

    try:
        last_seq = int(last_invoice.number.split("-")[-1])
    except (ValueError, IndexError):
        last_seq = last_invoice.id

    return f"{prefix}-{last_seq + 1:03d}"

def recompute_invoice_totals(invoice: Invoice):
    subtotal = Decimal("0.00")

    for item in invoice.items.all():
        line_total = (Decimal(item.qty_packs) * item.unit_price) - item.discount
        if line_total < 0:
            line_total = Decimal("0.00")

        item.line_total = line_total
        item.save(update_fields=["line_total"])
        subtotal += line_total

    total_ttc = subtotal - (invoice.discount or Decimal("0.00"))
    if total_ttc < 0:
        total_ttc = Decimal("0.00")

    tax_rate = invoice.tax_rate or Decimal("0.00")
    tax_amount = (total_ttc * tax_rate) / Decimal("100.00")
    total_before_tax = total_ttc - tax_amount

    if total_before_tax < 0:
        total_before_tax = Decimal("0.00")

    invoice.subtotal = subtotal
    invoice.total_before_tax = total_before_tax
    invoice.tax_amount = tax_amount
    invoice.total = total_ttc

    if invoice.paid_amount == 0:
        invoice.status = Invoice.STATUS_DRAFT
    elif invoice.paid_amount >= invoice.total and invoice.total > 0:
        invoice.status = Invoice.STATUS_PAID
    elif invoice.paid_amount > 0:
        invoice.status = Invoice.STATUS_PARTIAL

    invoice.save(
        update_fields=[
            "subtotal",
            "total_before_tax",
            "tax_amount",
            "total",
            "status",
            "updated_at",
        ]
    )
    
@transaction.atomic
def validate_invoice(invoice: Invoice, user):

    assert_period_open(invoice.issue_date, PeriodClosure.SCOPE_SALES, f"la validation de la facture {invoice.number}")
    assert_period_open(timezone.now(), PeriodClosure.SCOPE_STOCK, f"la sortie de stock de la facture {invoice.number}")


    if invoice.status in [Invoice.STATUS_VALIDATED, Invoice.STATUS_PARTIAL, Invoice.STATUS_PAID]:
        raise ValidationError("Cette facture est deja validee.")
    if invoice.status == Invoice.STATUS_CANCELLED:
        raise ValidationError("Une facture annulee ne peut pas etre validee.")
    if not invoice.source_depot_id:
        raise ValidationError("Veuillez renseigner le depot source avant de valider la facture.")
    if not invoice.source_depot.is_active:
        raise ValidationError("Le depot source selectionne est inactif.")

    items = list(invoice.items.select_related("product"))
    if not items:
        raise ValidationError("Impossible de valider une facture sans lignes.")

    stock_movement = StockMovement.objects.create(
        movement_date=timezone.now(),
        movement_type=StockMovement.TYPE_OUT,
        depot_from=invoice.source_depot,
        depot_to=None,
        ref_type=StockMovement.REF_INVOICE,
        ref_id=invoice.id,
        reason=f"Sortie stock pour facture {invoice.number}",
        created_by=user,
    )

    for item in items:
        StockMovementItem.objects.create(
            movement=stock_movement,
            product=item.product,
            qty_packs=item.qty_packs,
            unit_cost=None,
        )

    apply_stock_movement(stock_movement)

    InvoiceStockLink.objects.create(
        invoice=invoice,
        stock_movement=stock_movement,
    )

    invoice.status = Invoice.STATUS_VALIDATED
    invoice.validated_by = user
    invoice.validated_at = timezone.now()
    invoice.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])


def user_can_cancel_invoice(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.role == UserProfile.ROLE_ADMIN)


@transaction.atomic
def cancel_invoice(invoice: Invoice, user, reason: str):

    assert_period_open(invoice.issue_date, PeriodClosure.SCOPE_SALES, f"l'annulation de la facture {invoice.number}")
    if invoice.validated_at:
        assert_period_open(invoice.validated_at, PeriodClosure.SCOPE_STOCK, f"la contre-sortie de stock de la facture {invoice.number}")


    reason = (reason or "").strip()

    if not user_can_cancel_invoice(user):
        raise ValidationError("Seuls les administrateurs peuvent annuler une facture.")
    if not reason:
        raise ValidationError("Le motif d'annulation est obligatoire.")
    if invoice.status == Invoice.STATUS_CANCELLED:
        raise ValidationError("Cette facture est deja annulee.")
    if invoice.payments.exists() or invoice.paid_amount > 0:
        raise ValidationError("Impossible d'annuler une facture qui a deja des paiements enregistres.")

    delivery = getattr(invoice, "delivery", None)
    if delivery and delivery.status == Delivery.STATUS_DELIVERED:
        raise ValidationError("Impossible d'annuler une facture deja livree sans gerer un retour client.")

    if invoice.status in [Invoice.STATUS_VALIDATED, Invoice.STATUS_PARTIAL, Invoice.STATUS_PAID]:
        stock_link = getattr(invoice, "stock_link", None)
        if not stock_link:
            raise ValidationError("Cette facture ne possede pas de mouvement de stock exploitable.")

        original_movement = stock_link.stock_movement
        if original_movement.movement_type != StockMovement.TYPE_OUT or not original_movement.depot_from_id:
            raise ValidationError("Le mouvement de stock lie a cette facture ne permet pas une annulation automatique.")

        reversal_movement = StockMovement.objects.create(
            movement_date=timezone.now(),
            movement_type=StockMovement.TYPE_IN,
            depot_from=None,
            depot_to=original_movement.depot_from,
            ref_type=StockMovement.REF_INVOICE,
            ref_id=invoice.id,
            reason=f"Reintegration stock apres annulation facture {invoice.number}",
            created_by=user,
        )

        for item in original_movement.items.select_related("product"):
            StockMovementItem.objects.create(
                movement=reversal_movement,
                product=item.product,
                qty_packs=item.qty_packs,
                unit_cost=item.unit_cost,
            )

        apply_stock_movement(reversal_movement)

    invoice.status = Invoice.STATUS_CANCELLED
    invoice.cancelled_by = user
    invoice.cancelled_at = timezone.now()
    invoice.cancellation_reason = reason
    invoice.full_clean()
    invoice.save(
        update_fields=[
            "status",
            "cancelled_by",
            "cancelled_at",
            "cancellation_reason",
            "updated_at",
        ]
    )
    return invoice


@transaction.atomic
def register_payment(invoice: Invoice, account, user, paid_at, amount, method, reference=None, note=None):
    assert_period_open(paid_at, PeriodClosure.SCOPE_CASH, f"l'encaissement client sur la facture {invoice.number}")
    if amount <= 0:
        raise ValidationError("Le montant du paiement doit etre superieur a zero.")
    if invoice.status == Invoice.STATUS_DRAFT:
        raise ValidationError("Impossible d'enregistrer un paiement sur une facture brouillon.")
    if invoice.status == Invoice.STATUS_CANCELLED:
        raise ValidationError("Impossible d'enregistrer un paiement sur une facture annulee.")

    total_paid = invoice.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
    if total_paid + amount > invoice.total:
        raise ValidationError(
            f"Le montant du paiement ({amount} FC) ferait depasser le total "
            f"de la facture ({invoice.total} FC). "
            f"Montant restant a payer : {invoice.total - total_paid} FC."
        )

    payment = Payment(
        invoice=invoice,
        account=account,
        received_by=user,
        paid_at=paid_at,
        amount=amount,
        method=method,
        reference=reference,
        note=note,
    )
    payment.full_clean()
    payment.save()

    total_paid = invoice.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
    invoice.paid_amount = total_paid

    if invoice.paid_amount >= invoice.total and invoice.total > 0:
        invoice.status = Invoice.STATUS_PAID
    elif invoice.paid_amount > 0:
        invoice.status = Invoice.STATUS_PARTIAL

    invoice.save(update_fields=["paid_amount", "status", "updated_at"])
    return payment
