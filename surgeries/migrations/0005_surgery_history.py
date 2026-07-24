import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0003_seed_job_positions'),
        ('surgeries', '0004_patient'),
    ]

    operations = [
        migrations.CreateModel(
            name='SurgeryHistory',
            fields=[
                ('id',             models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('case_code',      models.CharField(max_length=50, verbose_name='کد پرونده', help_text='کد پرونده بیمار هنگام ثبت (کپی از بیمار برای آرشیو).')),
                ('phone_number',   models.CharField(max_length=20, verbose_name='شماره تلفن', help_text='شماره تماس هنگام ثبت (کپی از بیمار برای آرشیو).')),
                ('surgery_date',   models.DateTimeField(default=django.utils.timezone.now, verbose_name='تاریخ عمل')),
                ('amount',         models.DecimalField(decimal_places=2, max_digits=14, verbose_name='مبلغ', help_text='هزینه عمل جراحی به ریال.')),
                ('payment_status', models.CharField(choices=[('PENDING', 'در انتظار پرداخت'), ('PARTIAL', 'پرداخت ناقص'), ('PAID', 'پرداخت شده')], default='PENDING', max_length=10, verbose_name='وضعیت پرداخت')),
                ('description',    models.TextField(blank=True, default='', verbose_name='توضیحات')),
                ('status',         models.CharField(choices=[('PLANNED', 'برنامه‌ریزی شده'), ('IN_PROGRESS', 'در حال انجام'), ('COMPLETED', 'انجام شده'), ('CANCELLED', 'لغو شده')], default='PLANNED', max_length=20, verbose_name='وضعیت عمل')),
                ('created_at',     models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at',     models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
                ('patient',        models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='surgery_histories', to='surgeries.patient', verbose_name='بیمار')),
                ('doctor_or_therapist', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='surgery_histories', to='employees.employee', verbose_name='دکتر / درمانگر')),
                ('surgery_type',   models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='surgery_histories', to='surgeries.surgerytype', verbose_name='نوع عمل')),
            ],
            options={
                'verbose_name':        'تاریخچه عمل جراحی',
                'verbose_name_plural': 'تاریخچه اعمال جراحی',
                'ordering':            ['-surgery_date', '-created_at'],
            },
        ),
        migrations.AddIndex(model_name='surgeryhistory', index=models.Index(fields=['patient'],        name='idx_sh_patient')),
        migrations.AddIndex(model_name='surgeryhistory', index=models.Index(fields=['surgery_type'],   name='idx_sh_surgery_type')),
        migrations.AddIndex(model_name='surgeryhistory', index=models.Index(fields=['surgery_date'],   name='idx_sh_surgery_date')),
        migrations.AddIndex(model_name='surgeryhistory', index=models.Index(fields=['status'],         name='idx_sh_status')),
        migrations.AddIndex(model_name='surgeryhistory', index=models.Index(fields=['payment_status'], name='idx_sh_payment_status')),
    ]
