from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from expenses.models import ExpenseCategory
from sales.models import FinancialAccount

from .models import (
    Depot,
    Product,
    ProductionOrder,
    ProductionSupplyUsage,
    Purchase,
    PurchaseItem,
    StockMovement,
    StockMovementItem,
    Supplier,
    SupplierPayable,
    SupplyItem,
)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "unit_type",
            "sachets_per_pack",
            "default_sale_price",
            "min_stock",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "sku": forms.TextInput(attrs={"class": "form-control"}),
            "unit_type": forms.Select(attrs={"class": "form-select"}),
            "sachets_per_pack": forms.NumberInput(attrs={"class": "form-control"}),
            "default_sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "min_stock": forms.NumberInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class DepotForm(forms.ModelForm):
    class Meta:
        model = Depot
        fields = ["name", "location", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = [
            "movement_date",
            "movement_type",
            "depot_from",
            "depot_to",
            "ref_type",
            "ref_id",
            "reason",
        ]
        widgets = {
            "movement_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "movement_type": forms.Select(attrs={"class": "form-select"}),
            "depot_from": forms.Select(attrs={"class": "form-select"}),
            "depot_to": forms.Select(attrs={"class": "form-select"}),
            "ref_type": forms.Select(attrs={"class": "form-select"}),
            "ref_id": forms.NumberInput(attrs={"class": "form-control"}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
        }


class StockMovementItemForm(forms.ModelForm):
    class Meta:
        model = StockMovementItem
        fields = ["product", "qty_packs", "unit_cost"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "qty_packs": forms.NumberInput(attrs={"class": "form-control"}),
            "unit_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


StockMovementItemFormSet = inlineformset_factory(
    StockMovement,
    StockMovementItem,
    form=StockMovementItemForm,
    extra=3,
    can_delete=True,
)


class ProductionOrderForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Produit fini",
    )
    depot = forms.ModelChoiceField(
        queryset=Depot.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Dépôt destination",
    )
    planned_qty_packs = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
        label="Quantité prévue (packs)",
    )
    production_date = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        label="Date de production",
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Note",
    )


class ProductionCloseForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = [
            "actual_qty_packs",
            "loss_qty_packs",
            "cost_mode",
            "manual_total_cost",
            "labor_cost",
            "energy_cost",
            "packaging_cost",
            "other_cost",
            "note",
        ]
        widgets = {
            "actual_qty_packs": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "loss_qty_packs": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "cost_mode": forms.Select(attrs={"class": "form-select", "id": "id_cost_mode"}),
            "manual_total_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "labor_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "energy_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "packaging_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "other_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manual_total_cost"].required = False
        self.fields["labor_cost"].required = False
        self.fields["energy_cost"].required = False
        self.fields["packaging_cost"].required = False
        self.fields["other_cost"].required = False

    def clean(self):
        cleaned_data = super().clean()
        actual_qty = cleaned_data.get("actual_qty_packs") or 0
        loss_qty = cleaned_data.get("loss_qty_packs") or 0
        cost_mode = cleaned_data.get("cost_mode")
        manual_total_cost = cleaned_data.get("manual_total_cost") or Decimal("0.00")

        if loss_qty > actual_qty:
            raise forms.ValidationError("La quantité perdue ne peut pas dépasser la quantité produite.")

        if actual_qty <= 0:
            raise forms.ValidationError("La quantité produite doit être supérieure à 0.")

        if cost_mode == ProductionOrder.COST_MODE_MANUAL and manual_total_cost <= 0:
            self.add_error(
                "manual_total_cost",
                "En mode manuel, le coût total de production doit être supérieur à 0."
            )

        if cost_mode not in [ProductionOrder.COST_MODE_MANUAL, ProductionOrder.COST_MODE_SEMI]:
            raise forms.ValidationError("Mode de coût invalide.")

        return cleaned_data


class ProductionStartForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = []


class ProductionSupplyUsageForm(forms.ModelForm):
    supply_item = forms.ModelChoiceField(
        queryset=SupplyItem.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Intrant",
        required=False,
    )

    class Meta:
        model = ProductionSupplyUsage
        fields = ["supply_item", "qty_units"]
        widgets = {
            "qty_units": forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "min": "0.001"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        supply_item = self.cleaned_data.get("supply_item")

        if supply_item:
            instance.supply_item_id_value = supply_item.id
            instance.supply_item_name = supply_item.name

        if commit:
            instance.save()

        return instance


ProductionSupplyUsageFormSet = inlineformset_factory(
    ProductionOrder,
    ProductionSupplyUsage,
    form=ProductionSupplyUsageForm,
    extra=3,
    can_delete=True,
)


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "phone", "address", "note", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SupplyItemForm(forms.ModelForm):
    class Meta:
        model = SupplyItem
        fields = [
            "name",
            "code",
            "item_type",
            "unit",
            "min_stock",
            "note",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "item_type": forms.Select(attrs={"class": "form-select"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "min_stock": forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "min": "0"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PurchaseForm(forms.Form):
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Fournisseur",
    )
    depot = forms.ModelChoiceField(
        queryset=Depot.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Dépôt de réception",
    )
    ordered_at = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        label="Date de commande",
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Note",
    )


class PurchaseItemForm(forms.ModelForm):
    supply_item = forms.ModelChoiceField(
        queryset=SupplyItem.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Intrant",
    )

    class Meta:
        model = PurchaseItem
        fields = ["supply_item", "qty_units", "unit_cost"]
        widgets = {
            "qty_units": forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "min": "0.001"}),
            "unit_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        supply_item = self.cleaned_data.get("supply_item")

        if supply_item:
            instance.supply_item_id_value = supply_item.id
            instance.supply_item_name = supply_item.name

        qty_units = instance.qty_units or Decimal("0.000")
        unit_cost = instance.unit_cost or Decimal("0.00")
        instance.line_total = qty_units * unit_cost

        if commit:
            instance.save()
        return instance


PurchaseItemFormSet = inlineformset_factory(
    Purchase,
    PurchaseItem,
    form=PurchaseItemForm,
    extra=3,
    can_delete=True,
)


class PurchaseExpenseForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compte financier",
    )
    category = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Catégorie de dépense",
    )
    spent_at = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        label="Date de dépense",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Description",
    )


class SupplierPaymentForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compte financier",
    )
    paid_at = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        label="Date de paiement",
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=14,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
        label="Montant payé",
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Référence",
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Note",
    )