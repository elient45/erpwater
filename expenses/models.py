from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExpenseCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)

    class Meta:
        db_table = "expense_categories"

    def __str__(self):
        return self.name


class Expense(models.Model):
    id = models.BigAutoField(primary_key=True)

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        db_column="category_id",
        related_name="expenses",
    )

    account = models.ForeignKey(
        "sales.FinancialAccount",
        on_delete=models.PROTECT,
        db_column="account_id",
        related_name="expenses",
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, null=True)
    spent_at = models.DateTimeField(db_column="spent_at", default=timezone.now)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="created_by",
        related_name="expenses_created",
    )
    version_number = models.IntegerField(default=1)

    class Meta:
        db_table = "expenses"
        ordering = ["-spent_at"]

    def __str__(self):
        return f"{self.category.name} - {self.amount} FC"


class FinancialTransaction(models.Model):
    TYPE_IN = "IN"
    TYPE_OUT = "OUT"

    TYPE_CHOICES = [
        (TYPE_IN, "Entrée"),
        (TYPE_OUT, "Sortie"),
    ]

    SOURCE_PAYMENT = "PAYMENT"
    SOURCE_EXPENSE = "EXPENSE"
    SOURCE_SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"
    SOURCE_MANUAL = "MANUAL"
    SOURCE_DEPOSIT = "DEPOSIT"
    SOURCE_WITHDRAWAL = "WITHDRAWAL"
    SOURCE_TRANSFER = "TRANSFER"
    SOURCE_OTHER = "OTHER"

    SOURCE_CHOICES = [
        (SOURCE_PAYMENT, "Paiement client"),
        (SOURCE_EXPENSE, "Dépense"),
        (SOURCE_SUPPLIER_PAYMENT, "Paiement fournisseur"),
        (SOURCE_MANUAL, "Manuel"),
        (SOURCE_DEPOSIT, "Dépôt"),
        (SOURCE_WITHDRAWAL, "Retrait"),
        (SOURCE_TRANSFER, "Transfert"),
        (SOURCE_OTHER, "Autre"),
    ]

    id = models.BigAutoField(primary_key=True)

    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    source_type = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_OTHER)

    account_id_value = models.BigIntegerField(db_column="account_id")
    account_name = models.CharField(max_length=150)

    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    transaction_date = models.DateTimeField()

    reference = models.CharField(max_length=120, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)

    expense_id_value = models.BigIntegerField(db_column="expense_id", null=True, blank=True)
    payment_id = models.BigIntegerField(null=True, blank=True)

    transfer_group = models.CharField(max_length=100, blank=True, null=True)
    counter_account_id_value = models.BigIntegerField(null=True, blank=True)
    counter_account_name = models.CharField(max_length=150, blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_financial_transactions",
        db_column="created_by",
    )

    class Meta:
        db_table = "financial_transactions"
        ordering = ["-transaction_date", "-id"]

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} FC"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.amount <= 0:
            raise ValidationError(
                "Le montant d'une transaction financière doit être strictement positif. "
                f"Vous avez saisi : {self.amount} FC."
            )

        if self.source_type == self.SOURCE_PAYMENT and not self.payment_id:
            raise ValidationError(
                "Une transaction de paiement client doit avoir une référence de paiement (payment_id)."
            )

        if self.source_type == self.SOURCE_EXPENSE and not self.expense_id_value:
            raise ValidationError(
                "Une transaction de dépense doit avoir une référence de dépense (expense_id)."
            )

        if self.source_type == self.SOURCE_SUPPLIER_PAYMENT and not self.reference:
            raise ValidationError(
                "Une transaction de paiement fournisseur doit avoir une référence."
            )

        if self.source_type == self.SOURCE_TRANSFER and not self.transfer_group:
            raise ValidationError(
                "Une transaction de transfert doit avoir un groupe de transfert unique."
            )


class ReconciliationLog(models.Model):
    STATUS_DETECTED = "DETECTED"
    STATUS_AUTO_FIXED = "AUTO_FIXED"
    STATUS_MANUAL_REVIEW = "MANUAL_REVIEW"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_IGNORED = "IGNORED"

    STATUS_CHOICES = [
        (STATUS_DETECTED, "Détecté"),
        (STATUS_AUTO_FIXED, "Auto-corrigé"),
        (STATUS_MANUAL_REVIEW, "Révision manuelle"),
        (STATUS_RESOLVED, "Résolu"),
        (STATUS_IGNORED, "Ignoré"),
    ]

    TYPE_INVOICE_PAYMENT_MISMATCH = "INVOICE_PAYMENT_MISMATCH"
    TYPE_STOCK_BALANCE_MISMATCH = "STOCK_BALANCE_MISMATCH"
    TYPE_EXPENSE_AMOUNT_MISMATCH = "EXPENSE_AMOUNT_MISMATCH"
    TYPE_MISSING_REFERENCE = "MISSING_REFERENCE"
    TYPE_SOFT_LINK_BROKEN = "SOFT_LINK_BROKEN"

    TYPE_CHOICES = [
        (TYPE_INVOICE_PAYMENT_MISMATCH, "Discordance paiement facture"),
        (TYPE_STOCK_BALANCE_MISMATCH, "Discordance balance stock"),
        (TYPE_EXPENSE_AMOUNT_MISMATCH, "Discordance montant dépense"),
        (TYPE_MISSING_REFERENCE, "Référence manquante"),
        (TYPE_SOFT_LINK_BROKEN, "Lien mou cassé"),
    ]

    id = models.BigAutoField(primary_key=True)

    discrepancy_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        db_column="discrepancy_type"
    )

    object_app = models.CharField(max_length=50)
    object_model = models.CharField(max_length=50)
    object_id = models.BigIntegerField()

    detail = models.JSONField()
    expected_value = models.TextField(blank=True, null=True)
    actual_value = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DETECTED
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_reconciliations"
    )

    notes = models.TextField(blank=True)

    class Meta:
        db_table = "reconciliation_logs"
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=['discrepancy_type', '-detected_at']),
            models.Index(fields=['status', '-detected_at']),
            models.Index(fields=['object_app', 'object_model', 'object_id']),
        ]

    def __str__(self):
        return f"{self.get_discrepancy_type_display()} - {self.object_model}#{self.object_id}"