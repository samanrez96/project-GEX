# Generated manually — split into add / backfill / enforce-unique so this
# applies safely to a database that already has multiple FinanceCategory
# rows (a single-step unique AddField would collide every row on '').

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0009_commissionschedule_surgerytyperateschedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='financecategory',
            name='slug',
            field=models.SlugField(
                allow_unicode=True,
                blank=True,
                default='',
                help_text='شناسه یکتا برای ارجاع پایدار به این دسته‌بندی در کد. در صورت خالی گذاشتن، خودکار از روی نام ساخته می‌شود.',
                max_length=100,
                verbose_name='شناسه یکتا (Slug)',
            ),
        ),
        migrations.AddIndex(
            model_name='financecategory',
            index=models.Index(fields=['slug'], name='idx_fc_slug'),
        ),
    ]
