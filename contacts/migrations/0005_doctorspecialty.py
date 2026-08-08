from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0004_rename_doctorcontact_to_doctor'),
    ]

    operations = [
        migrations.CreateModel(
            name='DoctorSpecialty',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='عنوان تخصص')),
                ('is_active', models.BooleanField(default=True, verbose_name='فعال')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
            ],
            options={
                'verbose_name': 'تخصص پزشک',
                'verbose_name_plural': 'تخصص‌های پزشکان',
                'ordering': ['name'],
            },
        ),
    ]
