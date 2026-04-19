from decimal import Decimal

from django.conf import settings
from django.db import models


class Client(models.Model):
    CLIENT_TYPE_RETAIL = "RETAIL"
    CLIENT_TYPE_WHOLESALE = "WHOLESALE"
    CLIENT_TYPE_INSTITUTION = "INSTITUTION"
    CLIENT_TYPE_OTHER = "OTHER"

    CLIENT_TYPE_CHOICES = [
        (CLIENT_TYPE_RETAIL, "Détail"),
        (CLIENT_TYPE_WHOLESALE, "Grossiste"),
        (CLIENT_TYPE_INSTITUTION, "Institution"),
        (CLIENT_TYPE_OTHER, "Autre"),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    client_type = models.CharField(max_length=20, choices=CLIENT_TYPE_CHOICES, default=CLIENT_TYPE_OTHER)
    phone = models.CharField(max_length=30, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    nif_rccm = models.CharField(max_length=80, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clients"
        ordering = ["name"]

    def __str__(self):
        return self.name
class Invoice(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_VALIDATED = "VALIDATED"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_PAID = "PAID"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_VALIDATED, "Validée"),
        (STATUS_PARTIAL, "Partiellement payée"),
        (STATUS_PAID, "Payée"),
        (STATUS_CANCELLED, "Annulée"),
    ]

    SALE_MODE_ORDER = "ORDER"
    SALE_MODE_SELLER_OUT = "SELLER_OUT"
    SALE_MODE_DELIVERY = "DELIVERY"
    SALE_MODE_DIRECT = "DIRECT"

    SALE_MODE_CHOICES = [
        (SALE_MODE_ORDER, "Commande"),
        (SALE_MODE_SELLER_OUT, "Sortie vendeur"),
        (SALE_MODE_DELIVERY, "Livraison"),
        (SALE_MODE_DIRECT, "Vente directe"),
    ]

    id = models.BigAutoField(primary_key=True)
    number = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="invoices",
        db_column="customer_id",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_invoices",
        db_column="created_by",
    )
    source_depot = models.ForeignKey(
        "inventory.Depot",
        on_delete=models.PROTECT,
        related_name="source_invoices",
        db_column="source_depot_id",
        blank=True,
        null=True,
    )
    issue_date = models.DateTimeField()
    due_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    sale_mode = models.CharField(max_length=20, choices=SALE_MODE_CHOICES, default=SALE_MODE_DIRECT)

    # Montants métier
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    total_before_tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("16.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # total = TTC pour ne pas casser le flux existant
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    note = models.CharField(max_length=255, blank=True, null=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="validated_invoices",
        db_column="validated_by",
        blank=True,
        null=True,
    )
    validated_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cancelled_invoices",
        db_column="cancelled_by",
        blank=True,
        null=True,
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version_number = models.IntegerField(default=1)

    class Meta:
        db_table = "invoices"
        ordering = ["-issue_date", "-id"]

    def __str__(self):
        return self.number

    @property
    def balance_due(self):
        return self.total - self.paid_amount

    @property
    def total_ht(self):
        return self.total_before_tax

    @property
    def total_ttc(self):
        return self.total

    def clean(self):
        from django.core.exceptions import ValidationError

        # Validation 1 : interdire la modification de statut vers DRAFT
        if self.pk:
            old_invoice = Invoice.objects.get(pk=self.pk)
            old_status = old_invoice.status
            if self.status == self.STATUS_DRAFT and old_status != self.STATUS_DRAFT:
                raise ValidationError("Impossible de revenir à un brouillon une fois validée.")
            if (
                old_status in [self.STATUS_VALIDATED, self.STATUS_PARTIAL, self.STATUS_PAID, self.STATUS_CANCELLED]
                and self.source_depot_id != old_invoice.source_depot_id
            ):
                raise ValidationError("Impossible de modifier le dépôt source après validation ou annulation.")

        # Validation 2 : montants ne doivent pas être négatifs
        if self.subtotal < 0:
            raise ValidationError("Le sous-total ne peut pas être négatif.")
        if self.discount < 0:
            raise ValidationError("La remise ne peut pas être négative.")
        if self.tax_amount < 0:
            raise ValidationError("La taxe ne peut pas être négative.")
        if self.total < 0:
            raise ValidationError("Le total TTC ne peut pas être négatif.")
        if self.paid_amount < 0:
            raise ValidationError("Le montant payé ne peut pas être négatif.")

        # Validation 3 : cohérence des calculs
        expected_total = self.subtotal - self.discount
        if expected_total < 0:
            expected_total = Decimal("0.00")

        expected_tax_amount = (expected_total * (self.tax_rate or Decimal("0.00"))) / Decimal("100.00")
        expected_before_tax = expected_total - expected_tax_amount

        if expected_before_tax < 0:
            expected_before_tax = Decimal("0.00")

        if abs(self.total - expected_total) > Decimal("0.01"):
            raise ValidationError(
                f"Incohérence détectée : total TTC calculé ({expected_total}) "
                f"ne correspond pas au total TTC stocké ({self.total})."
            )

        if abs(self.tax_amount - expected_tax_amount) > Decimal("0.01"):
            raise ValidationError(
                f"Incohérence détectée : taxe calculée ({expected_tax_amount}) "
                f"ne correspond pas à la taxe stockée ({self.tax_amount})."
            )

        if abs(self.total_before_tax - expected_before_tax) > Decimal("0.01"):
            raise ValidationError(
                f"Incohérence détectée : total HT calculé ({expected_before_tax}) "
                f"ne correspond pas au total HT stocké ({self.total_before_tax})."
            )

        # Validation 4 : dépôt source obligatoire dès qu'une facture impacte le stock ou l'encours client
        if self.status in [self.STATUS_VALIDATED, self.STATUS_PARTIAL, self.STATUS_PAID] and not self.source_depot_id:
            raise ValidationError("Le dépôt source est obligatoire pour une facture validée ou payée.")

        # Validation 5 : une facture annulée doit porter sa traçabilité minimale
        if self.status == self.STATUS_CANCELLED:
            if not self.cancellation_reason:
                raise ValidationError("Le motif d'annulation est obligatoire.")
            if not self.cancelled_by_id or not self.cancelled_at:
                raise ValidationError("Une facture annulée doit conserver qui l'a annulée et quand.")

        # Validation 6 : le montant payé ne peut pas dépasser le total
        if self.paid_amount > self.total + Decimal("0.01"):
            raise ValidationError(
                f"Le montant payé ({self.paid_amount} FC) ne peut pas dépasser "
                f"le total de la facture ({self.total} FC)."
            )

class InvoiceItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="invoice_id",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="invoice_items",
        db_column="product_id",
    )
    description = models.CharField(max_length=255, blank=True, null=True)
    qty_packs = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoice_items"

    def __str__(self):
        return f"{self.product} x {self.qty_packs}"


class FinancialAccount(models.Model):
    ACCOUNT_TYPE_CASH = "CASH"
    ACCOUNT_TYPE_BANK = "BANK"

    ACCOUNT_TYPE_CHOICES = [
        (ACCOUNT_TYPE_CASH, "Caisse"),
        (ACCOUNT_TYPE_BANK, "Banque"),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "financial_accounts"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Payment(models.Model):
    METHOD_CASH = "CASH"
    METHOD_MOBILE_MONEY = "MOBILE_MONEY"
    METHOD_BANK_TRANSFER = "BANK_TRANSFER"
    METHOD_CHEQUE = "CHEQUE"
    METHOD_OTHER = "OTHER"

    METHOD_CHOICES = [
        (METHOD_CASH, "Cash"),
        (METHOD_MOBILE_MONEY, "Mobile Money"),
        (METHOD_BANK_TRANSFER, "Virement bancaire"),
        (METHOD_CHEQUE, "Chèque"),
        (METHOD_OTHER, "Autre"),
    ]

    id = models.BigAutoField(primary_key=True)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
        db_column="invoice_id",
    )
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="payments",
        db_column="account_id",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_payments",
        db_column="received_by",
    )

    paid_at = models.DateTimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_CASH)
    reference = models.CharField(max_length=120, blank=True, null=True)
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "payments"
        ordering = ["-paid_at", "-id"]

    def __str__(self):
        return f"Paiement {self.amount} FC - {self.invoice.number}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.amount <= 0:
            raise ValidationError("Le montant du paiement doit être supérieur à zéro.")
        
        # Une facture doit être validée avant tout encaissement, et ne peut plus recevoir de paiement si elle est annulée.
        if hasattr(self, 'invoice') and self.invoice:
            if self.invoice.status == Invoice.STATUS_DRAFT:
                raise ValidationError("Impossible d'enregistrer un paiement sur une facture brouillon.")
            if self.invoice.status == Invoice.STATUS_CANCELLED:
                raise ValidationError("Impossible d'enregistrer un paiement sur une facture annulée.")

            total_paid = self.invoice.payments.exclude(pk=self.pk).aggregate(
                total=models.Sum("amount")
            )["total"] or Decimal("0.00")
            
            if total_paid + self.amount > self.invoice.total:
                raise ValidationError(
                    f"Le montant du paiement ({self.amount} FC) ferait dépasser le total "
                    f"de la facture ({self.invoice.total} FC). "
                    f"Montant restant à payer : {self.invoice.total - total_paid} FC."
                )


class InvoiceStockLink(models.Model):
    invoice = models.OneToOneField(
        Invoice,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="invoice_id",
        related_name="stock_link",
    )
    stock_movement = models.OneToOneField(
        "inventory.StockMovement",
        on_delete=models.PROTECT,
        db_column="stock_movement_id",
        related_name="invoice_link",
    )

    class Meta:
        db_table = "invoice_stock_links"

    def __str__(self):
        return f"{self.invoice.number} -> Mouvement #{self.stock_movement_id}"
class Delivery(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_IN_TRANSIT = "IN_TRANSIT"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_IN_TRANSIT, "En cours de livraison"),
        (STATUS_DELIVERED, "Livrée"),
        (STATUS_FAILED, "Échec"),
    ]

    id = models.BigAutoField(primary_key=True)
    invoice = models.OneToOneField(
        Invoice,
        on_delete=models.CASCADE,
        related_name="delivery",
        db_column="invoice_id",
    )
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="deliveries",
        db_column="delivered_by",
    )
    delivery_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    address = models.CharField(max_length=255, blank=True, null=True)
    recipient_name = models.CharField(max_length=150, blank=True, null=True)
    recipient_phone = models.CharField(max_length=30, blank=True, null=True)
    note = models.CharField(max_length=255, blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "deliveries"
        ordering = ["-delivery_date", "-id"]

    def __str__(self):
        return f"Livraison - {self.invoice.number}"
