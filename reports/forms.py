from django import forms
from django.utils import timezone

from .models import PeriodClosure


class PeriodClosureForm(forms.ModelForm):
    class Meta:
        model = PeriodClosure
        fields = ["closure_type", "scope", "start_date", "end_date", "reason"]
        widgets = {
            "closure_type": forms.Select(attrs={"class": "form-select"}),
            "scope": forms.Select(attrs={"class": "form-select"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class PeriodReopenForm(forms.Form):
    reopen_reason = forms.CharField(
        label="Motif de réouverture",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    def clean_reopen_reason(self):
        value = (self.cleaned_data.get("reopen_reason") or "").strip()
        if not value:
            raise forms.ValidationError("Le motif de réouverture est obligatoire.")
        return value