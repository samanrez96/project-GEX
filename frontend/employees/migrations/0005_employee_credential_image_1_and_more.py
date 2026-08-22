import common.uploads
from django.db import migrations, models


class Migration(migrations.Migration):
    """Re-adds Employee.first_name / last_name / credential_image_1 /
    credential_image_2.

    NOTE: this migration was previously applied to the local dev database
    under this exact name (django_migrations still has a matching row) but
    its file had gone missing from the codebase, leaving the model with no
    knowledge of four NOT-NULL columns that physically exist in dev SQLite —
    every Employee INSERT omitted them entirely, tripping a NOT NULL
    constraint failure on credential_image_1 (the first such column in
    column order). Recreating the migration under its original name lets
    Django recognize it as already-applied on dev (no-op there) while still
    correctly creating the columns on any database — e.g. production
    Postgres — where it has never run.

    credential_image_1 / credential_image_2 are removed again by migration
    0008 once any pre-existing non-empty values have been copied into
    EmployeeDocument by migration 0007's data migration — they are recreated
    here only so the migration graph accurately reflects what already ran.
    """

    dependencies = [
        ('employees', '0004_employee_hourly_rate_purchase_commission'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='first_name',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='نام'),
        ),
        migrations.AddField(
            model_name='employee',
            name='last_name',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='نام خانوادگی'),
        ),
        migrations.AddField(
            model_name='employee',
            name='credential_image_1',
            field=models.ImageField(blank=True, upload_to=common.uploads.employee_credential_image_1_upload_path, validators=[common.uploads.validate_image_upload], verbose_name='تصویر اول مدرک'),
        ),
        migrations.AddField(
            model_name='employee',
            name='credential_image_2',
            field=models.ImageField(blank=True, upload_to=common.uploads.employee_credential_image_2_upload_path, validators=[common.uploads.validate_image_upload], verbose_name='تصویر دوم مدرک'),
        ),
    ]
