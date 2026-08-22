from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_remove_unique_product_vendor'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseitem',
            name='manual_total',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='اگر خالی باشد، جمع ردیف به‌صورت خودکار (مقدار × قیمت واحد) محاسبه می‌شود.',
                max_digits=14,
                null=True,
                verbose_name='جمع ردیف دستی',
            ),
        ),
    ]
