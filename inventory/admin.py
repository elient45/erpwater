from django import forms
from django.forms import inlineformset_factory

from .models import Depot, Product, StockMovement, StockMovementItem


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


# Admin classes
from django.contrib import admin


class StockMovementItemInline(admin.TabularInline):
    model = StockMovementItem
    form = StockMovementItemForm
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductForm
    list_display = ['name', 'sku', 'unit_type', 'sachets_per_pack', 'default_sale_price', 'min_stock', 'is_active']
    list_filter = ['unit_type', 'is_active']
    search_fields = ['name', 'sku']


@admin.register(Depot)
class DepotAdmin(admin.ModelAdmin):
    form = DepotForm
    list_display = ['name', 'location', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'location']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    form = StockMovementForm
    list_display = ['id', 'movement_type', 'movement_date', 'depot_from', 'depot_to', 'created_by']
    list_filter = ['movement_type', 'movement_date', 'created_by']
    search_fields = ['id', 'reason']
    inlines = [StockMovementItemInline]


@admin.register(StockMovementItem)
class StockMovementItemAdmin(admin.ModelAdmin):
    form = StockMovementItemForm
    list_display = ['movement', 'product', 'qty_packs', 'unit_cost']
    list_filter = ['product']
    search_fields = ['movement__id', 'product__name']