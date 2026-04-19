from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class PeriodClosure(models.Model):
    TYPE_DAILY_CASH = "DAILY_CASH"
    TYPE_MONTHLY = "MONTHLY"
    TYPE_INVENTORY = "INVENTORY"
    TYPE_YEARLY = "YEARLY"

    TYPE_CHOICES = [
        (TYPE_DAILY_CASH, "Clôture journalière caisse"),
        (TYPE_MONTHLY, "Clôture mensuelle"),
        (TYPE_INVENTORY, "Clôture inventaire"),
        (TYPE_YEARLY, "Clôture annuelle"),
    ]

    STATUS_CLOSED = "CLOSED"
    STATUS_REOPENED = "REOPENED"

    STATUS_CHOICES = [
        (STATUS_CLOSED, "Clôturée"),
        (STATUS_REOPENED, "Rouverte"),
    ]

    SCOPE_GLOBAL = "GLOBAL"
    SCOPE_CASH = "CASH"
    SCOPE_STOCK = "STOCK"
    SCOPE_SALES = "SALES"
    SCOPE_PURCHASE = "PURCHASE"
    SCOPE_PRODUCTION = "PRODUCTION"
    SCOPE_EXPENSE = "EXPENSE"

    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_CASH, "Trésorerie"),
        (SCOPE_STOCK, "Stock"),
        (SCOPE_SALES, "Ventes"),
        (SCOPE_PURCHASE, "Achats"),
        (SCOPE_PRODUCTION, "Production"),
        (SCOPE_EXPENSE, "Dépenses"),
    ]

    id = models.BigAutoField(primary_key=True)
    closure_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_GLOBAL)

    start_date = models.DateField()
    end_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CLOSED)

    reason = models.TextField()
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="period_closures_closed",
        db_column="closed_by",
    )
    closed_at = models.DateTimeField(auto_now_add=True)

    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="period_closures_reopened",
        db_column="reopened_by",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.TextField(blank=True)

    class Meta:
        db_table = "period_closures"
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["closure_type", "scope", "status"]),
            models.Index(fields=["start_date", "end_date", "status"]),
        ]

    def __str__(self):
        return f"{self.get_closure_type_display()} [{self.start_date} -> {self.end_date}]"

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError("La date de fin ne peut pas être antérieure à la date de début.")

        if not self.reason:
            raise ValidationError("Le motif de clôture est obligatoire.")

        if self.status == self.STATUS_REOPENED:
            if not self.reopened_by_id or not self.reopened_at or not self.reopen_reason:
                raise ValidationError("Une période rouverte doit conserver qui l'a rouverte, quand et pourquoi.")