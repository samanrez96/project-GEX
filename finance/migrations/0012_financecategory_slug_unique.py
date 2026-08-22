from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0011_backfill_financecategory_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='financecategory',
            name='slug',
            field=models.SlugField(
                allow_unicode=True,
                blank=True,
                help_text='شناسه یکتا برای ارجاع پایدار به این دسته‌بندی در کد. در صورت خالی گذاشتن، خودکار از روی نام ساخته می‌شود.',
                max_length=100,
                unique=True,
                verbose_name='شناسه یکتا (Slug)',
            ),
        ),
    ]
