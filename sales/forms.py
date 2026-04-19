from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone


from .models import Client, Delivery, FinancialAccount, Invoice, InvoiceItem, Payment

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "client_type", "phone", "address", "nif_rccm", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "client_type": forms.Select(attrs={"class": "form-select"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "nif_rccm": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

class InvoiceForm(forms.ModelForm):
    issue_date = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    class Meta:
        model = Invoice
        fields = ["customer", "source_depot", "issue_date", "due_date", "sale_mode", "discount", "tax_rate", "note"]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "source_depot": forms.Select(attrs={"class": "form-select"}),
            "sale_mode": forms.Select(attrs={"class": "form-select"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "tax_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "value": "16.00"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Note interne ou précision sur la facture"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get("tax_rate"):
            self.initial["tax_rate"] = Decimal("16.00")


class InvoiceCancelForm(forms.Form):
    cancellation_reason = forms.CharField(
        label="Motif d'annulation",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Expliquez pourquoi cette facture doit etre annulee.",
            }
        ),
    )

    def clean_cancellation_reason(self):
        reason = (self.cleaned_data.get("cancellation_reason") or "").strip()
        if not reason:
            raise forms.ValidationError("Le motif d'annulation est obligatoire.")
        return reason


            
class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ["product", "description", "qty_packs", "unit_price", "discount"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "Description optionnelle"}),
            "qty_packs": forms.NumberInput(attrs={"class": "form-control"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    extra=1,
    can_delete=True,
)


class PaymentForm(forms.ModelForm):
    paid_at = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
    )

    class Meta:
        model = Payment
        fields = ["account", "paid_at", "amount", "method", "reference", "note"]
        widgets = {
            "account": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "method": forms.Select(attrs={"class": "form-select"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }
class DeliveryForm(forms.ModelForm):
    delivery_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"})
    )
    delivered_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"})
    )

    class Meta:
        model = Delivery
        fields = [
            "delivered_by",
            "delivery_date",
            "status",
            "address",
            "recipient_name",
            "recipient_phone",
            "note",
            "delivered_at",
        ]
        widgets = {
            "delivered_by": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "recipient_name": forms.TextInput(attrs={"class": "form-control"}),
            "recipient_phone": forms.TextInput(attrs={"class": "form-control"}),
            "note": forms.TextInput(attrs={"class": "form-control"}),
        }
