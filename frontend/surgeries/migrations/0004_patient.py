from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surgeries', '0003_seed_surgery_types'),
    ]

    operations = [
        migrations.CreateModel(
            name='Patient',
            fields=[
                ('id',           models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name',    models.CharField(max_length=200, verbose_name='نام و نام خانوادگی')),
                ('case_code',    models.CharField(max_length=50, unique=True, verbose_name='کد پرونده', help_text='کد پرونده باید منحصربه‌فرد باشد.')),
                ('phone_number', models.CharField(max_length=20, verbose_name='شماره تلفن')),
                ('description',  models.TextField(blank=True, default='', verbose_name='توضیحات')),
                ('created_at',   models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at',   models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
            ],
            options={
                'verbose_name':        'بیمار',
                'verbose_name_plural': 'بیماران',
                'ordering':            ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='patient',
            index=models.Index(fields=['case_code'],    name='idx_patient_case_code'),
        ),
        migrations.AddIndex(
            model_name='patient',
            index=models.Index(fields=['phone_number'], name='idx_patient_phone'),
        ),
    ]
