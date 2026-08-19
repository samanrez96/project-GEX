from django.db import migrations

DEFAULT_EXPENSE_CATEGORIES = [
    ('هزینه دارو', 'هزینه‌های مربوط به داروها و مواد مصرفی'),
    ('هزینه تجهیزات', 'هزینه‌های خرید و نگهداری تجهیزات پزشکی'),
    ('حقوق ثابت کارمندان', 'حقوق ثابت ماهیانه کارکنان داخلی'),
    ('کمیسیون کارمندان', 'کمیسیون و پاداش کارکنان'),
    ('هزینه‌های جانبی', 'هزینه‌های متفرقه و جاری مرکز'),
    ('سایر هزینه‌ها', 'سایر هزینه‌هایی که در دسته‌های دیگر قرار نمی‌گیرند'),
]


def seed_expense_categories(apps, schema_editor):
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    for name, desc in DEFAULT_EXPENSE_CATEGORIES:
        FinanceCategory.objects.get_or_create(
            name=name,
            category_type='expense',
            defaults={'description': desc, 'is_active': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0003_expense_category_proxy'),
    ]

    operations = [
        migrations.RunPython(seed_expense_categories, migrations.RunPython.noop),
    ]
