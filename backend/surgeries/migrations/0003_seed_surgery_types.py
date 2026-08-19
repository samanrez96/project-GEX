"""Seed migration: inserts the 5 default surgery types.

Design notes:
  - Uses get_or_create (idempotent): re-running the forward migration never
    duplicates rows.
  - reverse_code is a no-op: existing records (and any customized base_rates)
    are preserved on --reverse. Re-applying the forward migration will not
    overwrite those customizations because get_or_create skips existing rows.
"""

from django.db import migrations

SURGERY_TYPES = [
    ('عمل بینی',  'nose',    5_000_000),
    ('عمل معده', 'stomach', 8_000_000),
    ('لیفت',      'lift',    6_000_000),
    ('زیبایی',   'beauty',  4_000_000),
    ('سایر',      'other',   0),
]


def seed_surgery_types(apps, schema_editor):
    SurgeryType = apps.get_model('surgeries', 'SurgeryType')
    for name, code, base_rate in SURGERY_TYPES:
        SurgeryType.objects.get_or_create(
            code=code,
            defaults={'name': name, 'base_rate': base_rate},
        )


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('surgeries', '0002_add_surgery_type'),
    ]

    operations = [
        migrations.RunPython(seed_surgery_types, reverse_code=reverse_seed),
    ]
