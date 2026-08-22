# Generated manually — seeds ProductTypeTag with the two values
# Product.product_type has always stored, so the new tag-select dropdown
# starts with exactly what already exists in the database.

from django.db import migrations


def seed_product_type_tags(apps, schema_editor):
    ProductTypeTag = apps.get_model("inventory", "ProductTypeTag")
    ProductTypeTag.objects.get_or_create(
        value="medicine", defaults={"label": "دارو", "is_active": True},
    )
    ProductTypeTag.objects.get_or_create(
        value="equipment", defaults={"label": "تجهیزات", "is_active": True},
    )


def remove_seeded_tags(apps, schema_editor):
    ProductTypeTag = apps.get_model("inventory", "ProductTypeTag")
    ProductTypeTag.objects.filter(value__in=["medicine", "equipment"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0014_producttypetag"),
    ]

    operations = [
        migrations.RunPython(seed_product_type_tags, reverse_code=remove_seeded_tags),
    ]
