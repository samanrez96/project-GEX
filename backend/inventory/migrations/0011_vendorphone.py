from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0010_purchaseitem_manual_total"),
    ]

    operations = [
        migrations.CreateModel(
            name="VendorPhone",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("phone", models.CharField(max_length=20, verbose_name="شماره تلفن")),
                (
                    "order",
                    models.PositiveIntegerField(default=0, verbose_name="ترتیب"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد"),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="additional_phones",
                        to="inventory.vendor",
                    ),
                ),
            ],
            options={
                "verbose_name": "شماره تلفن دیگر",
                "verbose_name_plural": "شماره‌های تلفن دیگر",
                "ordering": ["order", "created_at"],
                "unique_together": {("vendor", "phone")},
            },
        ),
    ]
