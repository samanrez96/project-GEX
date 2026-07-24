from django.db import migrations

NEW_EXPENSE_CATEGORIES = [
    ('هزینه ماهانه متخصصان بیهوشی', 'هزینه ماهانه مربوط به متخصصان بیهوشی'),
    ('هزینه ماهانه ملزومات روزمره', 'هزینه ماهانه ملزومات و مواد مصرفی روزمره'),
]


def seed_monthly_expense_categories(apps, schema_editor):
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    for name, desc in NEW_EXPENSE_CATEGORIES:
        FinanceCategory.objects.get_or_create(
            name=name,
            category_type='expense',
            defaults={'description': desc, 'is_active': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0006_seed_income_categories'),
    ]

    operations = [
        migrations.RunPython(seed_monthly_expense_categories, migrations.RunPython.noop),
    ]
