from django.db import migrations

DEFAULT_INCOME_CATEGORIES = [
    ('کمیسیون مرکز از اعمال جراحی', 'سهم مرکز از درآمد اعمال جراحی — مهم‌ترین منبع درآمد'),
    ('سایر درآمدها', 'سایر درآمدهایی که در دسته‌های دیگر قرار نمی‌گیرند'),
]


def seed_income_categories(apps, schema_editor):
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    for name, desc in DEFAULT_INCOME_CATEGORIES:
        FinanceCategory.objects.get_or_create(
            name=name,
            category_type='income',
            defaults={'description': desc, 'is_active': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_income_category_proxy'),
    ]

    operations = [
        migrations.RunPython(seed_income_categories, migrations.RunPython.noop),
    ]
