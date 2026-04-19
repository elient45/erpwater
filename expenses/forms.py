from django import forms
from .models import Expense, ExpenseCategory
from sales.models import FinancialAccount


class FinancialAccountForm(forms.ModelForm):
    class Meta:
        model = FinancialAccount
        fields = ["name", "account_type", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "account_type": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }


class ExpenseForm(forms.ModelForm):
    spent_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"})
)
    class Meta:
        model = Expense
        fields = [
            "category",
            "account",
            "amount",
            "description",
            "spent_at",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "account": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
        }

from django import forms
from django.utils import timezone

from sales.models import FinancialAccount


class DepositForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compte",
    )
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
        label="Montant",
    )
    transaction_date = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        label="Date",
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Référence",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Description",
    )


class WithdrawalForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compte",
    )
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
        label="Montant",
    )
    transaction_date = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        label="Date",
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Référence",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Description",
    )


class TransferForm(forms.Form):
    source_account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compte source",
    )
    destination_account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.filter(is_active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Compte destination",
    )
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
        label="Montant",
    )
    transaction_date = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        label="Date",
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Référence",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Description",
    )

    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get("source_account")
        destination = cleaned_data.get("destination_account")

        if source and destination and source.id == destination.id:
            raise forms.ValidationError("Le compte source et le compte destination doivent être différents.")

        return cleaned_data