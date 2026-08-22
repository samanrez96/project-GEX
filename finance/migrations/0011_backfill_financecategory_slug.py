from django.db import migrations
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    seen = set(
        FinanceCategory.objects.exclude(slug='').values_list('slug', flat=True)
    )
    for category in FinanceCategory.objects.filter(slug='').order_by('pk'):
        base = slugify(category.name, allow_unicode=True) or f'category-{category.category_type}'
        base = base[:90]
        candidate = base
        suffix = 2
        while candidate in seen:
            candidate = f'{base}-{suffix}'
            suffix += 1
        seen.add(candidate)
        category.slug = candidate
        category.save(update_fields=['slug'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0010_financecategory_slug'),
    ]

    operations = [
        migrations.RunPython(backfill_slugs, noop),
    ]
