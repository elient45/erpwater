from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from expenses.models import FinancialTransaction
from expenses.services import create_financial_transaction

from .forms import (
    ClientForm,
    DeliveryForm,
    InvoiceCancelForm,
    InvoiceForm,
    InvoiceItemFormSet,
    PaymentForm,
)
from .models import Client, Delivery, Invoice
from .services import (
    cancel_invoice,
    generate_invoice_number,
    recompute_invoice_totals,
    register_payment,
    user_can_cancel_invoice,
    validate_invoice,
)


@login_required
def client_list(request):
    clients = Client.objects.all().order_by("name")
    return render(request, "sales/client_list.html", {"clients": clients})


@login_required
def client_create(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client cree avec succes.")
        return redirect("sales:client_list")
    return render(request, "sales/client_form.html", {"form": form, "title": "Nouveau client"})


@login_required
def invoice_list(request):
    invoices = (
        Invoice.objects.select_related("customer", "created_by", "validated_by", "source_depot")
        .all()
        .order_by("-issue_date")
    )
    return render(request, "sales/invoice_list.html", {"invoices": invoices})


@login_required
def invoice_create(request):
    if request.method == "POST":
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    invoice = form.save(commit=False)
                    invoice.number = generate_invoice_number()
                    invoice.created_by = request.user
                    invoice.status = Invoice.STATUS_DRAFT
                    invoice.paid_amount = Decimal("0.00")
                    invoice.subtotal = Decimal("0.00")
                    invoice.total_before_tax = Decimal("0.00")
                    invoice.tax_amount = Decimal("0.00")
                    invoice.total = Decimal("0.00")

                    if not invoice.tax_rate:
                        invoice.tax_rate = Decimal("16.00")

                    invoice.save()

                    formset.instance = invoice
                    items = formset.save(commit=False)

                    has_valid_item = False
                    for item in items:
                        if item.product_id and item.qty_packs:
                            if item.unit_price is None or item.unit_price == 0:
                                item.unit_price = item.product.default_sale_price
                            item.save()
                            has_valid_item = True

                    for obj in formset.deleted_objects:
                        obj.delete()

                    if not has_valid_item:
                        raise ValidationError("Veuillez ajouter au moins une ligne produit valide.")

                    recompute_invoice_totals(invoice)
                    invoice.full_clean()

                messages.success(request, "Facture creee avec succes.")
                return redirect("sales:invoice_detail", pk=invoice.pk)

            except ValidationError as exc:
                messages.error(request, exc.message if hasattr(exc, "message") else str(exc))
    else:
        form = InvoiceForm()
        formset = InvoiceItemFormSet()

    return render(
        request,
        "sales/invoice_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Nouvelle facture",
        },
    )


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            "customer",
            "created_by",
            "validated_by",
            "source_depot",
            "cancelled_by",
        ).prefetch_related("items__product", "payments__account", "payments__received_by"),
        pk=pk,
    )

    has_delivery = hasattr(invoice, "delivery")
    can_cancel = user_can_cancel_invoice(request.user) and invoice.status in [
        Invoice.STATUS_DRAFT,
        Invoice.STATUS_VALIDATED,
    ]

    return render(
        request,
        "sales/invoice_detail.html",
        {
            "invoice": invoice,
            "has_delivery": has_delivery,
            "can_cancel_invoice": can_cancel,
        },
    )


@login_required
def invoice_validate(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("source_depot"), pk=pk)

    try:
        validate_invoice(invoice, request.user)
        messages.success(request, "Facture validee et stock sorti avec succes.")
    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, "message") else str(exc))

    return redirect("sales:invoice_detail", pk=invoice.pk)


@login_required
def invoice_cancel(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer", "source_depot", "validated_by", "cancelled_by"),
        pk=pk,
    )

    if not user_can_cancel_invoice(request.user):
        messages.error(request, "Seuls les administrateurs peuvent annuler une facture.")
        return redirect("sales:invoice_detail", pk=invoice.pk)

    form = InvoiceCancelForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            cancel_invoice(
                invoice,
                request.user,
                form.cleaned_data["cancellation_reason"],
            )
            messages.success(request, "Facture annulee avec succes.")
            return redirect("sales:invoice_detail", pk=invoice.pk)
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else str(exc))

    return render(
        request,
        "sales/invoice_cancel_form.html",
        {
            "form": form,
            "invoice": invoice,
            "title": f"Annuler la facture {invoice.number}",
        },
    )


@login_required
def payment_create(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)

    if invoice.status == Invoice.STATUS_DRAFT:
        messages.error(request, "Validez d'abord la facture avant d'enregistrer un paiement.")
        return redirect("sales:invoice_detail", pk=invoice.pk)
    if invoice.status == Invoice.STATUS_CANCELLED:
        messages.error(request, "Impossible d'enregistrer un paiement sur une facture annulee.")
        return redirect("sales:invoice_detail", pk=invoice.pk)

    form = PaymentForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                payment = register_payment(
                    invoice=invoice,
                    account=form.cleaned_data["account"],
                    user=request.user,
                    paid_at=form.cleaned_data["paid_at"],
                    amount=form.cleaned_data["amount"],
                    method=form.cleaned_data["method"],
                    reference=form.cleaned_data["reference"],
                    note=form.cleaned_data["note"],
                )

                create_financial_transaction(
                    transaction_type=FinancialTransaction.TYPE_IN,
                    source_type=FinancialTransaction.SOURCE_PAYMENT,
                    account=payment.account,
                    amount=payment.amount,
                    transaction_date=payment.paid_at,
                    created_by=request.user,
                    reference=f"PAY-{payment.id}",
                    description=f"Paiement facture {invoice.number}",
                    payment_id=payment.id,
                )

            messages.success(request, "Paiement enregistre avec succes.")
            return redirect("sales:invoice_detail", pk=invoice.pk)

        except Exception as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "sales/payment_form.html",
        {
            "form": form,
            "invoice": invoice,
            "title": f"Paiement - {invoice.number}",
        },
    )


@login_required
def invoice_print(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer", "created_by", "validated_by", "source_depot", "cancelled_by")
        .prefetch_related("items__product", "payments__account", "payments__received_by"),
        pk=pk,
    )
    return render(request, "sales/invoice_print.html", {"invoice": invoice})


@login_required
def invoice_pdf_download(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer", "created_by", "validated_by", "source_depot", "cancelled_by")
        .prefetch_related("items__product", "payments__account", "payments__received_by"),
        pk=pk,
    )

    html_string = render_to_string(
        "sales/invoice_print.html",
        {
            "invoice": invoice,
            "pdf_mode": True,
        },
        request=request,
    )

    result = BytesIO()
    pdf = pisa.CreatePDF(src=html_string, dest=result, encoding="utf-8")

    if pdf.err:
        return HttpResponse("Erreur lors de la generation du PDF.", status=500)

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="facture-{invoice.number}.pdf"'
    return response


@login_required
def delivery_list(request):
    deliveries = (
        Delivery.objects.select_related("invoice", "invoice__customer", "delivered_by")
        .all()
        .order_by("-delivery_date")
    )
    return render(request, "sales/delivery_list.html", {"deliveries": deliveries})


@login_required
def delivery_create(request, invoice_pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer"),
        pk=invoice_pk,
    )

    if invoice.status == Invoice.STATUS_DRAFT:
        messages.error(request, "Validez la facture avant de creer une livraison.")
        return redirect("sales:invoice_detail", pk=invoice.pk)
    if invoice.status == Invoice.STATUS_CANCELLED:
        messages.error(request, "Impossible de creer une livraison pour une facture annulee.")
        return redirect("sales:invoice_detail", pk=invoice.pk)

    if hasattr(invoice, "delivery"):
        messages.warning(request, "Cette facture a deja une livraison.")
        return redirect("sales:delivery_detail", pk=invoice.delivery.pk)

    form = DeliveryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        delivery = form.save(commit=False)
        delivery.invoice = invoice
        delivery.save()
        messages.success(request, "Livraison creee avec succes.")
        return redirect("sales:delivery_detail", pk=delivery.pk)

    return render(
        request,
        "sales/delivery_form.html",
        {
            "form": form,
            "invoice": invoice,
            "title": f"Nouvelle livraison - {invoice.number}",
        },
    )


@login_required
def delivery_detail(request, pk):
    delivery = get_object_or_404(
        Delivery.objects.select_related("invoice", "invoice__customer", "delivered_by"),
        pk=pk,
    )
    return render(request, "sales/delivery_detail.html", {"delivery": delivery})


@login_required
def delivery_update(request, pk):
    delivery = get_object_or_404(
        Delivery.objects.select_related("invoice", "invoice__customer"),
        pk=pk,
    )

    if delivery.invoice.status == Invoice.STATUS_CANCELLED:
        messages.error(request, "Impossible de modifier la livraison d'une facture annulee.")
        return redirect("sales:delivery_detail", pk=delivery.pk)

    form = DeliveryForm(request.POST or None, instance=delivery)

    if request.method == "POST" and form.is_valid():
        delivery = form.save(commit=False)

        if delivery.status == Delivery.STATUS_DELIVERED and not delivery.delivered_at:
            delivery.delivered_at = timezone.now()

        if delivery.status != Delivery.STATUS_DELIVERED:
            delivery.delivered_at = None

        delivery.save()
        messages.success(request, "Livraison mise a jour avec succes.")
        return redirect("sales:delivery_detail", pk=delivery.pk)

    return render(
        request,
        "sales/delivery_form.html",
        {
            "form": form,
            "invoice": delivery.invoice,
            "title": f"Modifier livraison - {delivery.invoice.number}",
        },
    )
