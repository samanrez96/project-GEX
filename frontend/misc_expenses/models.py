from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class MiscellaneousExpense(models.Model):
    date = models.DateField(verbose_name="تاریخ")
    subject = models.CharField(max_length=200, verbose_name="موضوع")
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="مبلغ",
        help_text="مبلغ باید بزرگ‌تر از صفر باشد.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "هزینه متفرقه"
        verbose_name_plural = "هزینه‌های متفرقه"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.subject} — {self.date}"
