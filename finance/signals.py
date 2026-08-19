"""Finance signal handlers."""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='finance.CenterCommissionIncome')
def on_center_commission_income_saved(sender, instance, **kwargs):
    """Sync an income Transaction whenever a CenterCommissionIncome is saved."""
    from finance.services import SurgeryCommissionTransactionService
    SurgeryCommissionTransactionService.sync_income_transaction(instance)


@receiver(post_save, sender='finance.DoctorFeeExpense')
def on_doctor_fee_expense_saved(sender, instance, **kwargs):
    """Sync an expense Transaction whenever a DoctorFeeExpense is saved."""
    from finance.services import DoctorFeeTransactionService
    DoctorFeeTransactionService.sync_expense_transaction(instance)


@receiver(post_save, sender='surgeries.SurgeryHistory')
def on_surgery_saved(sender, instance, **kwargs):
    """Sync university commission expense when a Surgery is confirmed/cancelled."""
    from finance.services import UniversityCommissionService
    UniversityCommissionService.sync_transaction(instance)