"""Seed migration: inserts 8 default commission rules.

Forward: get_or_create on (job_position, surgery_type) — idempotent.
  Skips any position or surgery type that doesn't exist in the DB
  (defensive — won't fail in stripped-down environments).

Reverse: deactivates seeded rules (set is_active=False).
  Records are preserved for audit trail; never deleted.
  Re-running the forward migration after a reverse will NOT re-activate
  them because the get_or_create lookup finds the existing inactive rows.
"""

import datetime

from django.db import migrations

COMMISSION_RULES = [
    # (position_name, surgery_code, percent)
    ('متخصص بیهوشی', 'nose',    15),
    ('متخصص بیهوشی', 'stomach', 25),
    ('متخصص بیهوشی', 'lift',    20),
    ('متخصص بیهوشی', 'beauty',  15),
    ('پرستار',        'nose',    10),
    ('پرستار',        'stomach', 15),
    ('تکنسین',        'nose',     8),
    ('تکنسین',        'stomach', 12),
]


def seed_commission_rules(apps, schema_editor):
    JobPosition    = apps.get_model('employees', 'JobPosition')
    SurgeryType    = apps.get_model('surgeries', 'SurgeryType')
    CommissionRule = apps.get_model('payroll', 'CommissionRule')
    today          = datetime.date.today()

    for position_name, surgery_code, percent in COMMISSION_RULES:
        try:
            position     = JobPosition.objects.get(name=position_name)
            surgery_type = SurgeryType.objects.get(code=surgery_code)
        except (JobPosition.DoesNotExist, SurgeryType.DoesNotExist):
            continue
        CommissionRule.objects.get_or_create(
            job_position=position,
            surgery_type=surgery_type,
            defaults={
                'commission_percent': percent,
                'start_date':         today,
                'is_active':          True,
            },
        )


def reverse_seed(apps, schema_editor):
    JobPosition    = apps.get_model('employees', 'JobPosition')
    SurgeryType    = apps.get_model('surgeries', 'SurgeryType')
    CommissionRule = apps.get_model('payroll', 'CommissionRule')

    for position_name, surgery_code, _ in COMMISSION_RULES:
        try:
            position     = JobPosition.objects.get(name=position_name)
            surgery_type = SurgeryType.objects.get(code=surgery_code)
        except (JobPosition.DoesNotExist, SurgeryType.DoesNotExist):
            continue
        CommissionRule.objects.filter(
            job_position=position,
            surgery_type=surgery_type,
        ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('payroll',    '0004_add_commission_rule'),
        ('employees',  '0003_seed_job_positions'),
        ('surgeries',  '0003_seed_surgery_types'),
    ]

    operations = [
        migrations.RunPython(seed_commission_rules, reverse_code=reverse_seed),
    ]
