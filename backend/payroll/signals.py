from django.db.models.signals import post_save
from django.dispatch import receiver

from employees.models import Employee
from .models import CommissionRule, CommissionTransaction, HourlyRate, MonthlyWage, PayrollPeriod, PayrollStatus, PayrollTypeConfig


@receiver(post_save, sender=Employee)
def create_payroll_config(sender, instance, created, **kwargs):
    if created:
        PayrollTypeConfig.objects.get_or_create(employee=instance)


@receiver(post_save, sender='surgeries.SurgeryHistory')
def auto_calculate_commission(sender, instance, **kwargs):
    """Trigger commission calculation whenever a SurgeryHistory is saved.

    Uses a string sender label to avoid an import-time circular dependency
    (surgeries → payroll would be circular since payroll already imports employees).
    Deferred to avoid blocking the save transaction: any IntegrityError from
    a duplicate is silently swallowed inside the service.
    """
    from payroll.services import calculate_surgery_commission
    calculate_surgery_commission(instance)


@receiver(post_save, sender=MonthlyWage)
def sync_payroll_type_config(sender, instance, **kwargs):
    config, _ = PayrollTypeConfig.objects.get_or_create(employee=instance.employee)
    has_active = MonthlyWage.objects.filter(
        employee=instance.employee,
        is_active=True,
    ).exists()
    if config.has_monthly_wage != has_active:
        config.has_monthly_wage = has_active
        config.save(update_fields=['has_monthly_wage', 'updated_at'])


@receiver(post_save, sender=HourlyRate)
def sync_hourly_payroll_type_config(sender, instance, **kwargs):
    config, _ = PayrollTypeConfig.objects.get_or_create(employee=instance.employee)
    has_active = HourlyRate.objects.filter(
        employee=instance.employee,
        is_active=True,
    ).exists()
    if config.has_hourly_wage != has_active:
        config.has_hourly_wage = has_active
        config.save(update_fields=['has_hourly_wage', 'updated_at'])


@receiver(post_save, sender=CommissionRule)
def sync_commission_config(sender, instance, **kwargs):
    employees = Employee.objects.filter(
        job_position=instance.job_position,
        is_active=True,
    )
    has_active_rule = CommissionRule.objects.filter(
        job_position=instance.job_position,
        is_active=True,
    ).exists()
    for employee in employees:
        config, _ = PayrollTypeConfig.objects.get_or_create(employee=employee)
        if config.has_commission != has_active_rule:
            config.has_commission = has_active_rule
            config.save(update_fields=['has_commission', 'updated_at'])


@receiver(post_save, sender=CommissionTransaction)
def sync_commission_finance_expense(sender, instance, **kwargs):
    """Create or update an expense Transaction for each CommissionTransaction.

    Fires after the CommissionTransaction is saved so that the finance
    module records it as a payroll-related expense.
    """
    from finance.services import PayrollFinanceService
    PayrollFinanceService.sync_commission_expense(instance)


@receiver(post_save, sender=PayrollPeriod)
def sync_salary_finance_expenses(sender, instance, **kwargs):
    """When a PayrollPeriod is closed or processed, create salary expense Transactions.

    Runs for CLOSED and PROCESSED status so that re-processing a period
    (CLOSED → PROCESSED) also triggers a re-sync.
    """
    if instance.status in (PayrollStatus.CLOSED, PayrollStatus.PROCESSED):
        from finance.services import PayrollFinanceService
        PayrollFinanceService.sync_salary_expenses(instance)
