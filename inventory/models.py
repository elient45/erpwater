from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Product(models.Model):
    UNIT_TYPE_PACK = "PACK"

    UNIT_TYPE_CHOICES = [
        (UNIT_TYPE_PACK, "Pack"),
    ]

    id = models.BigAutoField(primary_key=True)
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    name = models.CharField(max_length=120)
    unit_type = models.CharField(max_length=10, choices=UNIT_TYPE_CHOICES, default=UNIT_TYPE_PACK)
    sachets_per_pack = models.PositiveIntegerField()
    default_sale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    min_stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "products"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Depot(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "depots"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockMovement(models.Model):
    TYPE_IN = "IN"
    TYPE_OUT = "OUT"
    TYPE_TRANSFER = "TRANSFER"
    TYPE_ADJUST = "ADJUST"
    TYPE_LOSS = "LOSS"

    MOVEMENT_TYPE_CHOICES = [
        (TYPE_IN, "Entrée"),
        (TYPE_OUT, "Sortie"),
        (TYPE_TRANSFER, "Transfert"),
        (TYPE_ADJUST, "Ajustement"),
        (TYPE_LOSS, "Perte"),
    ]

    REF_PRODUCTION = "PRODUCTION_LOT"
    REF_INVOICE = "INVOICE"
    REF_MANUAL = "MANUAL"

    REF_TYPE_CHOICES = [
        (REF_PRODUCTION, "Lot de production"),
        (REF_INVOICE, "Facture"),
        (REF_MANUAL, "Manuel"),
    ]

    id = models.BigAutoField(primary_key=True)
    movement_date = models.DateTimeField(default=timezone.now)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    depot_from = models.ForeignKey(
        Depot,
        on_delete=models.PROTECT,
        related_name="outgoing_movements",
        db_column="depot_from_id",
        blank=True,
        null=True,
    )
    depot_to = models.ForeignKey(
        Depot,
        on_delete=models.PROTECT,
        related_name="incoming_movements",
        db_column="depot_to_id",
        blank=True,
        null=True,
    )
    ref_type = models.CharField(max_length=20, choices=REF_TYPE_CHOICES, default=REF_MANUAL)
    ref_id = models.PositiveBigIntegerField(blank=True, null=True)
    reason = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        db_column="created_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movements"
        ordering = ["-movement_date", "-id"]

    def __str__(self):
        return f"{self.get_movement_type_display()} #{self.id}"

    def clean(self):
        if self.movement_type == self.TYPE_IN and not self.depot_to:
            raise ValidationError("Une entrée doit avoir un dépôt destination.")
        if self.movement_type in [self.TYPE_OUT, self.TYPE_LOSS] and not self.depot_from:
            raise ValidationError("Une sortie ou perte doit avoir un dépôt source.")
        if self.movement_type == self.TYPE_TRANSFER:
            if not self.depot_from or not self.depot_to:
                raise ValidationError("Un transfert doit avoir un dépôt source et destination.")
            if self.depot_from_id == self.depot_to_id:
                raise ValidationError("Le dépôt source et destination doivent être différents.")


class StockMovementItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    movement = models.ForeignKey(
        StockMovement,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="movement_id",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movement_items",
        db_column="product_id",
    )
    qty_packs = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movement_items"

    def __str__(self):
        return f"{self.product} x {self.qty_packs}"

    @property
    def total_cost(self):
        if self.unit_cost is None:
            return None
        return Decimal(self.qty_packs) * self.unit_cost


class StockBalance(models.Model):
    id = models.BigAutoField(primary_key=True)
    depot = models.ForeignKey(
        Depot,
        on_delete=models.PROTECT,
        related_name="stock_balances",
        db_column="depot_id",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_balances",
        db_column="product_id",
    )
    qty_packs = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    version_number = models.IntegerField(default=1)

    class Meta:
        db_table = "stock_balances"
        unique_together = ("depot", "product")
        ordering = ["depot__name", "product__name"]

    def __str__(self):
        return f"{self.depot} - {self.product}: {self.qty_packs}"

    @property
    def is_below_minimum(self):
        return self.qty_packs <= self.product.min_stock


class ProductionOrder(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_DONE = "DONE"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_DONE, "Terminée"),
        (STATUS_CANCELLED, "Annulée"),
    ]

    COST_MODE_MANUAL = "MANUAL"
    COST_MODE_SEMI = "SEMI"

    COST_MODE_CHOICES = [
        (COST_MODE_MANUAL, "Manuel"),
        (COST_MODE_SEMI, "Semi-automatique"),
    ]

    id = models.BigAutoField(primary_key=True)
    number = models.CharField(max_length=50, unique=True)

    product_id_value = models.BigIntegerField()
    product_name = models.CharField(max_length=255)

    depot_id_value = models.BigIntegerField()
    depot_name = models.CharField(max_length=255)

    planned_qty_packs = models.PositiveIntegerField(default=0)
    actual_qty_packs = models.PositiveIntegerField(default=0)
    loss_qty_packs = models.PositiveIntegerField(default=0)
    net_qty_packs = models.PositiveIntegerField(default=0)

    cost_mode = models.CharField(
        max_length=10,
        choices=COST_MODE_CHOICES,
        default=COST_MODE_MANUAL,
    )

    manual_total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    labor_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    energy_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    packaging_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    other_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    total_production_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    unit_production_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    production_date = models.DateTimeField()
    note = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    stock_movement_id_value = models.BigIntegerField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="production_orders_created",
        db_column="created_by",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="production_orders_validated",
        db_column="validated_by",
    )

    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "production_orders"
        ordering = ["-production_date", "-id"]

    def __str__(self):
        return self.number


class Supplier(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "suppliers"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Purchase(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_ORDERED = "ORDERED"
    STATUS_RECEIVED = "RECEIVED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_ORDERED, "Commandé"),
        (STATUS_RECEIVED, "Réceptionné"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    id = models.BigAutoField(primary_key=True)
    number = models.CharField(max_length=50, unique=True)

    supplier = models.ForeignKey(
        "inventory.Supplier",
        on_delete=models.PROTECT,
        related_name="purchases",
        db_column="supplier_id",
    )

    depot_id_value = models.BigIntegerField()
    depot_name = models.CharField(max_length=255)

    ordered_at = models.DateTimeField()
    received_at = models.DateTimeField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    stock_movement_id_value = models.BigIntegerField(null=True, blank=True)

    # Héritage de l’ancienne logique, conservé pour compatibilité MVP
    expense_registered = models.BooleanField(default=False)
    expense_id_value = models.BigIntegerField(null=True, blank=True)

    # Nouveau cycle fournisseur
    payable_created = models.BooleanField(default=False)
    payable_id_value = models.BigIntegerField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchases_created",
        db_column="created_by",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchases_validated",
        db_column="validated_by",
    )

    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "purchases"
        ordering = ["-ordered_at", "-id"]

    def __str__(self):
        return self.number

    def clean(self):
        if self.subtotal < 0:
            raise ValidationError("Le sous-total d'achat ne peut pas être négatif.")
        if self.total < 0:
            raise ValidationError("Le total d'achat ne peut pas être négatif.")

        if self.pk:
            old = Purchase.objects.get(pk=self.pk)
            if self.status == self.STATUS_CANCELLED and old.status == self.STATUS_RECEIVED and self.payable_created:
                raise ValidationError(
                    "Impossible d'annuler un achat réceptionné avec dette fournisseur active."
                )


class SupplyItem(models.Model):
    TYPE_RAW = "RAW"
    TYPE_PACKAGING = "PACKAGING"
    TYPE_CONSUMABLE = "CONSUMABLE"
    TYPE_OTHER = "OTHER"

    TYPE_CHOICES = [
        (TYPE_RAW, "Matière première"),
        (TYPE_PACKAGING, "Emballage"),
        (TYPE_CONSUMABLE, "Consommable"),
        (TYPE_OTHER, "Autre"),
    ]

    UNIT_PIECE = "PIECE"
    UNIT_ROLL = "ROLL"
    UNIT_CARTON = "CARTON"
    UNIT_KG = "KG"
    UNIT_LITER = "LITER"

    UNIT_CHOICES = [
        (UNIT_PIECE, "Pièce"),
        (UNIT_ROLL, "Rouleau"),
        (UNIT_CARTON, "Carton"),
        (UNIT_KG, "Kg"),
        (UNIT_LITER, "Litre"),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=80, unique=True)
    item_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_RAW)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default=UNIT_PIECE)

    current_qty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    min_stock = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))

    last_unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    average_unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    note = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "supply_items"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseItem(models.Model):
    id = models.BigAutoField(primary_key=True)

    purchase = models.ForeignKey(
        "inventory.Purchase",
        on_delete=models.CASCADE,
        related_name="items",
        db_column="purchase_id",
    )

    supply_item_id_value = models.BigIntegerField()
    supply_item_name = models.CharField(max_length=255)

    qty_units = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "purchase_items"

    def __str__(self):
        return f"{self.supply_item_name} x {self.qty_units}"


class ProductionSupplyUsage(models.Model):
    id = models.BigAutoField(primary_key=True)

    production = models.ForeignKey(
        "inventory.ProductionOrder",
        on_delete=models.CASCADE,
        related_name="supply_usages",
        db_column="production_id",
    )

    supply_item_id_value = models.BigIntegerField()
    supply_item_name = models.CharField(max_length=255)

    qty_units = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    unit_cost_snapshot = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "production_supply_usages"
        ordering = ["id"]

    def __str__(self):
        return f"{self.supply_item_name} x {self.qty_units}"


class SupplierPayable(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_PAID = "PAID"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Ouverte"),
        (STATUS_PARTIAL, "Partiellement payée"),
        (STATUS_PAID, "Payée"),
        (STATUS_CANCELLED, "Annulée"),
    ]

    id = models.BigAutoField(primary_key=True)
    number = models.CharField(max_length=50, unique=True)

    purchase = models.OneToOneField(
        "inventory.Purchase",
        on_delete=models.PROTECT,
        related_name="supplier_payable",
        db_column="purchase_id",
    )

    supplier = models.ForeignKey(
        "inventory.Supplier",
        on_delete=models.PROTECT,
        related_name="payables",
        db_column="supplier_id",
    )

    amount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_due = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    payable_date = models.DateTimeField(default=timezone.now)
    note = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="supplier_payables_created",
        db_column="created_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "supplier_payables"
        ordering = ["-payable_date", "-id"]

    def __str__(self):
        return self.number

    def clean(self):
        if self.amount_total < 0 or self.amount_paid < 0 or self.amount_due < 0:
            raise ValidationError("Les montants fournisseur ne peuvent pas être négatifs.")
        if self.amount_paid > self.amount_total:
            raise ValidationError("Le montant payé ne peut pas dépasser le montant total de la dette.")


class SupplierPayment(models.Model):
    id = models.BigAutoField(primary_key=True)

    payable = models.ForeignKey(
        "inventory.SupplierPayable",
        on_delete=models.PROTECT,
        related_name="payments",
        db_column="payable_id",
    )

    account_id_value = models.BigIntegerField()
    account_name = models.CharField(max_length=255)

    paid_at = models.DateTimeField(default=timezone.now)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    reference = models.CharField(max_length=120, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="supplier_payments_created",
        db_column="created_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "supplier_payments"
        ordering = ["-paid_at", "-id"]

    def __str__(self):
        return f"{self.payable.number} - {self.amount} FC"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Le montant du paiement fournisseur doit être supérieur à zéro.")