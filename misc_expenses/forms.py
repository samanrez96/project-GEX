from decimal import Decimal

from django import forms

from common.admin import JalaliFormDateField, MoneyInput
from .models import MiscellaneousExpense


class MiscellaneousExpenseForm(forms.ModelForm):
    date = JalaliFormDateField(label="تاریخ")

    class Meta:
        model = MiscellaneousExpense
        fields = ["date", "subject", "amount"]
        widgets = {
            "subject": forms.TextInput(attrs={
                "placeholder": "موضوع هزینه را وارد کنید...",
                "class": "vTextField",
                "dir": "rtl",
            }),
            "amount": MoneyInput(attrs={
                "placeholder": "مبلغ به تومان",
            }),
        }
        labels = {
            "subject": "موضوع",
            "amount": "مبلغ (تومان)",
        }

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= Decimal("0"):
            raise forms.ValidationError("مبلغ باید بزرگ‌تر از صفر باشد.")
        return amount
