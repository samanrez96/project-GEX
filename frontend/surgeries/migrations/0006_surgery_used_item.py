import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0008_purchase_purchaseitem_purchase_idx_purchase_vendor_and_more'),
        ('surgeries', '0005_surgery_history'),
    ]

    operations = [
        migrations.CreateModel(
            name='SurgeryUsedItem',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity',    models.DecimalField(decimal_places=3, max_digits=12, verbose_name='مقدار')),
                ('unit',        models.CharField(blank=True, default='', max_length=50, verbose_name='واحد', help_text='اگر خالی باشد از محصول کپی می‌شود.')),
                ('description', models.TextField(blank=True, default='', verbose_name='توضیحات')),
                ('created_at',  models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at',  models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
                ('surgery',     models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='used_items', to='surgeries.surgeryhistory', verbose_name='تاریخچه عمل جراحی')),
                ('product',     models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='surgery_used_items', to='inventory.product', verbose_name='محصول / کالا')),
            ],
            options={
                'verbose_name':        'قلم مصرف تاریخچه عمل',
                'verbose_name_plural': 'اقلام مصرف تاریخچه عمل',
            },
        ),
        migrations.AddIndex(model_name='surgeryuseditem', index=models.Index(fields=['surgery'], name='idx_sui_surgery')),
        migrations.AddIndex(model_name='surgeryuseditem', index=models.Index(fields=['product'], name='idx_sui_product')),
    ]
