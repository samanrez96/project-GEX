from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('surgeries', '0019_merge_20260717_1916'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='marital_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('SINGLE', 'مجرد'),
                    ('MARRIED', 'متأهل'),
                    ('DIVORCED', 'مطلقه'),
                    ('WIDOWED', 'همسر فوت شده'),
                ],
                max_length=12,
                null=True,
                verbose_name='وضعیت تأهل',
            ),
        ),
    ]
