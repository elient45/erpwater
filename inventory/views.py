from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    DepotForm,
    ProductForm,
    ProductionCloseForm,
    ProductionOrderForm,
    ProductionSupplyUsageFormSet,
    PurchaseExpenseForm,
    PurchaseForm,
    PurchaseItemFormSet,
    StockMovementForm,
    StockMovementItemFormSet,
    SupplierForm,
    SupplierPaymentForm,
    SupplyItemForm,
)
from .models import (
    Depot,
    Product,
    ProductionOrder,
    Purchase,
    StockBalance,
    StockMovement,
    Supplier,
    SupplierPayable,
    SupplyItem,
)
from .services import (
    apply_stock_movement,
    close_production,
    generate_production_number,
    generate_purchase_number,
    receive_purchase,
    recompute_purchase_totals,
    register_purchase_as_expense,
    register_supplier_payment,
    start_production,
)


@login_required
def product_list(request):
    products = Product.objects.all().order_by("name")
    return render(request, "inventory/product_list.html", {"products": products})


@login_required
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Produit créé avec succès.")
            return redirect("inventory:product_list")
    else:
        form = ProductForm()
    return render(request, "inventory/product_form.html", {"form": form, "title": "Nouveau produit"})


@login_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Produit modifié avec succès.")
            return redirect("inventory:product_list")
    else:
        form = ProductForm(instance=product)
    return render(request, "inventory/product_form.html", {"form": form, "title": "Modifier produit"})


@login_required
def depot_list(request):
    depots = Depot.objects.all().order_by("name")
    return render(request, "inventory/depot_list.html", {"depots": depots})


@login_required
def depot_create(request):
    if request.method == "POST":
        form = DepotForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Dépôt créé avec succès.")
            return redirect("inventory:depot_list")
    else:
        form = DepotForm()
    return render(request, "inventory/depot_form.html", {"form": form, "title": "Nouveau dépôt"})


@login_required
def depot_update(request, pk):
    depot = get_object_or_404(Depot, pk=pk)
    if request.method == "POST":
        form = DepotForm(request.POST, instance=depot)
        if form.is_valid():
            form.save()
            messages.success(request, "Dépôt modifié avec succès.")
            return redirect("inventory:depot_list")
    else:
        form = DepotForm(instance=depot)
    return render(request, "inventory/depot_form.html", {"form": form, "title": "Modifier dépôt"})


@login_required
def movement_list(request):
    movements = (
        StockMovement.objects.select_related("depot_from", "depot_to", "created_by")
        .prefetch_related("items__product")
        .order_by("-movement_date", "-id")
    )
    return render(request, "inventory/movement_list.html", {"movements": movements})


@login_required
def movement_create(request):
    if request.method == "POST":
        form = StockMovementForm(request.POST)
        formset = StockMovementItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    movement = form.save(commit=False)
                    movement.created_by = request.user
                    movement.full_clean()
                    movement.save()

                    formset.instance = movement
                    items = formset.save(commit=False)

                    has_valid_item = False
                    for item in items:
                        if item.product_id and item.qty_packs:
                            item.full_clean()
                            item.save()
                            has_valid_item = True

                    for obj in formset.deleted_objects:
                        obj.delete()

                    if not has_valid_item:
                        raise ValidationError("Veuillez ajouter au moins une ligne produit valide.")

                    apply_stock_movement(movement)

                messages.success(request, "Mouvement de stock enregistré avec succès.")
                return redirect("inventory:movement_detail", pk=movement.pk)

            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))
    else:
        form = StockMovementForm()
        formset = StockMovementItemFormSet()

    return render(
        request,
        "inventory/movement_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Nouveau mouvement de stock",
        },
    )


@login_required
def movement_detail(request, pk):
    movement = get_object_or_404(
        StockMovement.objects.select_related("depot_from", "depot_to", "created_by").prefetch_related("items__product"),
        pk=pk,
    )

    total_movement_cost = Decimal("0.00")
    for item in movement.items.all():
        if item.total_cost is not None:
            total_movement_cost += item.total_cost

    return render(
        request,
        "inventory/movement_detail.html",
        {
            "movement": movement,
            "total_movement_cost": total_movement_cost,
        },
    )


@login_required
def stock_balance_list(request):
    balances = (
        StockBalance.objects.select_related("depot", "product").order_by("depot__name", "product__name")
    )
    return render(request, "inventory/stock_balance_list.html", {"balances": balances})


@login_required
def production_list(request):
    productions = ProductionOrder.objects.select_related("created_by", "validated_by").all().order_by("-production_date", "-id")
    return render(request, "inventory/production_list.html", {"productions": productions})


@login_required
def production_create(request):
    form = ProductionOrderForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        product = form.cleaned_data["product"]
        depot = form.cleaned_data["depot"]

        production = ProductionOrder.objects.create(
            number=generate_production_number(),
            product_id_value=product.id,
            product_name=product.name,
            depot_id_value=depot.id,
            depot_name=depot.name,
            planned_qty_packs=form.cleaned_data["planned_qty_packs"],
            production_date=form.cleaned_data["production_date"],
            note=form.cleaned_data["note"],
            created_by=request.user,
            status=ProductionOrder.STATUS_DRAFT,
        )

        messages.success(request, "Ordre de production créé avec succès.")
        return redirect("inventory:production_detail", pk=production.pk)

    return render(
        request,
        "inventory/production_form.html",
        {
            "form": form,
            "title": "Nouvelle production",
        },
    )


@login_required
def production_detail(request, pk):
    production = get_object_or_404(
        ProductionOrder.objects.select_related("created_by", "validated_by"),
        pk=pk,
    )
    return render(request, "inventory/production_detail.html", {"production": production})


@login_required
def production_start(request, pk):
    production = get_object_or_404(ProductionOrder, pk=pk)

    try:
        start_production(production, request.user)
        messages.success(request, "Production démarrée.")
    except Exception as e:
        messages.error(request, str(e))

    return redirect("inventory:production_detail", pk=production.pk)


@login_required
def production_close(request, pk):
    production = get_object_or_404(ProductionOrder, pk=pk)
    form = ProductionCloseForm(request.POST or None, instance=production)
    usage_formset = ProductionSupplyUsageFormSet(request.POST or None, instance=production, prefix="usages")

    if request.method == "POST" and form.is_valid() and usage_formset.is_valid():
        try:
            production = form.save(commit=False)

            usage_items = []
            for usage_form in usage_formset:
                if not usage_form.cleaned_data:
                    continue
                if usage_form.cleaned_data.get("DELETE"):
                    continue

                supply_item = usage_form.cleaned_data.get("supply_item")
                qty_units = usage_form.cleaned_data.get("qty_units") or Decimal("0.000")

                if supply_item and qty_units > 0:
                    usage_items.append({
                        "supply_item": supply_item,
                        "qty_units": qty_units,
                    })

            close_production(production, request.user, usage_items=usage_items)
            messages.success(request, "Production validée et stock mis à jour.")
            return redirect("inventory:production_detail", pk=production.pk)

        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "inventory/production_close_form.html",
        {
            "form": form,
            "usage_formset": usage_formset,
            "production": production,
            "title": f"Clôturer la production {production.number}",
        },
    )


@login_required
def supplier_list(request):
    suppliers = Supplier.objects.all().order_by("name")
    return render(request, "inventory/supplier_list.html", {"suppliers": suppliers})


@login_required
def supplier_create(request):
    form = SupplierForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fournisseur enregistré avec succès.")
        return redirect("inventory:supplier_list")

    return render(
        request,
        "inventory/supplier_form.html",
        {
            "form": form,
            "title": "Nouveau fournisseur",
        },
    )


@login_required
def purchase_list(request):
    purchases = (
        Purchase.objects.select_related("supplier", "created_by", "validated_by")
        .all()
        .order_by("-ordered_at", "-id")
    )
    return render(request, "inventory/purchase_list.html", {"purchases": purchases})


@login_required
def purchase_create(request):
    form = PurchaseForm(request.POST or None)
    formset = PurchaseItemFormSet(request.POST or None)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            with transaction.atomic():
                supplier = form.cleaned_data["supplier"]
                depot = form.cleaned_data["depot"]

                purchase = Purchase.objects.create(
                    number=generate_purchase_number(),
                    supplier=supplier,
                    depot_id_value=depot.id,
                    depot_name=depot.name,
                    ordered_at=form.cleaned_data["ordered_at"],
                    note=form.cleaned_data["note"],
                    created_by=request.user,
                    status=Purchase.STATUS_DRAFT,
                )

                formset.instance = purchase
                items = formset.save(commit=False)

                has_valid_item = False
                for item in items:
                    if item.qty_units and item.unit_cost is not None:
                        item.purchase = purchase
                        item.save()
                        has_valid_item = True

                for obj in formset.deleted_objects:
                    obj.delete()

                if not has_valid_item:
                    raise ValidationError("Veuillez ajouter au moins une ligne d'achat valide.")

                recompute_purchase_totals(purchase)

            messages.success(request, "Achat créé avec succès.")
            return redirect("inventory:purchase_detail", pk=purchase.pk)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "inventory/purchase_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Nouvel achat",
        },
    )


@login_required
def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related("supplier", "created_by", "validated_by").prefetch_related(
            "items",
            "supplier_payable__payments",
        ),
        pk=pk,
    )
    return render(request, "inventory/purchase_detail.html", {"purchase": purchase})


@login_required
def purchase_receive(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)

    try:
        receive_purchase(purchase, request.user)
        messages.success(request, "Achat réceptionné, stock mis à jour et dette fournisseur créée.")
    except Exception as e:
        messages.error(request, str(e))

    return redirect("inventory:purchase_detail", pk=purchase.pk)


@login_required
def purchase_register_expense(request, pk):
    purchase = get_object_or_404(Purchase.objects.select_related("supplier"), pk=pk)
    form = PurchaseExpenseForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            register_purchase_as_expense(
                purchase,
                account=form.cleaned_data["account"],
                category=form.cleaned_data["category"],
                spent_at=form.cleaned_data["spent_at"],
                description=form.cleaned_data["description"],
                user=request.user,
            )
            messages.success(request, "Achat enregistré dans les dépenses.")
            return redirect("inventory:purchase_detail", pk=purchase.pk)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "inventory/purchase_expense_form.html",
        {
            "form": form,
            "purchase": purchase,
            "title": f"Passer {purchase.number} en dépense",
        },
    )


@login_required
def supplier_payable_list(request):
    payables = (
        SupplierPayable.objects.select_related("supplier", "purchase", "created_by")
        .all()
        .order_by("-payable_date", "-id")
    )
    return render(request, "inventory/supplier_payable_list.html", {"payables": payables})


@login_required
def supplier_payable_detail(request, pk):
    payable = get_object_or_404(
        SupplierPayable.objects.select_related("supplier", "purchase", "created_by").prefetch_related("payments"),
        pk=pk,
    )
    return render(request, "inventory/supplier_payable_detail.html", {"payable": payable})


@login_required
def supplier_payment_create(request, payable_pk):
    payable = get_object_or_404(
        SupplierPayable.objects.select_related("supplier", "purchase"),
        pk=payable_pk,
    )
    form = SupplierPaymentForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            register_supplier_payment(
                payable=payable,
                account=form.cleaned_data["account"],
                paid_at=form.cleaned_data["paid_at"],
                amount=form.cleaned_data["amount"],
                reference=form.cleaned_data["reference"],
                note=form.cleaned_data["note"],
                user=request.user,
            )
            messages.success(request, "Paiement fournisseur enregistré avec succès.")
            return redirect("inventory:supplier_payable_detail", pk=payable.pk)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "inventory/supplier_payment_form.html",
        {
            "form": form,
            "payable": payable,
            "title": f"Paiement fournisseur - {payable.number}",
        },
    )


@login_required
def supply_item_list(request):
    supply_items = SupplyItem.objects.all().order_by("name")
    return render(request, "inventory/supply_item_list.html", {"supply_items": supply_items})


@login_required
def supply_item_create(request):
    form = SupplyItemForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Intrant enregistré avec succès.")
        return redirect("inventory:supply_item_list")

    return render(
        request,
        "inventory/supply_item_form.html",
        {
            "form": form,
            "title": "Nouvel intrant",
        },
    )


@login_required
def supply_item_update(request, pk):
    supply_item = get_object_or_404(SupplyItem, pk=pk)
    form = SupplyItemForm(request.POST or None, instance=supply_item)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Intrant modifié avec succès.")
        return redirect("inventory:supply_item_list")

    return render(
        request,
        "inventory/supply_item_form.html",
        {
            "form": form,
            "title": "Modifier intrant",
        },
    )