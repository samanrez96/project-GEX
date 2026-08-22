import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0003_seed_job_positions'),
        ('payroll',   '0005_seed_commission_rules'),
        ('surgeries', '0005_surgery_history'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommissionTransaction',
            fields=[
                ('id',       models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount',   models.DecimalField(decimal_places=2, max_digits=14, verbose_name='مبلغ کمیسیون', help_text='مبلغ کمیسیون = مبلغ عمل × درصد کمیسیون / ۱۰۰')),
                ('notes',    models.TextField(blank=True, default='', verbose_name='توضیحات')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
                ('surgery',         models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,  related_name='commission_transactions', to='surgeries.surgeryhistory', verbose_name='تاریخچه عمل')),
                ('employee',        models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,  related_name='commission_transactions', to='employees.employee',        verbose_name='کارمند')),
                ('commission_rule', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,  related_name='transactions',            to='payroll.commissionrule',   verbose_name='قانون کمیسیون')),
            ],
            options={
                'verbose_name':        'تراکنش کمیسیون',
                'verbose_name_plural': 'تراکنش‌های کمیسیون',
                'ordering':            ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='commissiontransaction',
            constraint=models.UniqueConstraint(
                fields=['surgery', 'employee', 'commission_rule'],
                name='unique_surgery_employee_rule',
            ),
        ),
        migrations.AddIndex(model_name='commissiontransaction', index=models.Index(fields=['surgery'],    name='idx_ct_surgery')),
        migrations.AddIndex(model_name='commissiontransaction', index=models.Index(fields=['employee'],   name='idx_ct_employee')),
        migrations.AddIndex(model_name='commissiontransaction', index=models.Index(fields=['created_at'], name='idx_ct_created_at')),
    ]
