from django.db import migrations, models


class Migration(migrations.Migration):
    """Re-adds Doctor.first_name / Doctor.last_name.

    NOTE: this migration was previously applied to the local dev database
    under this exact name (django_migrations still has a matching row) but
    its file had gone missing from the codebase, leaving the model with no
    knowledge of two NOT-NULL columns that physically exist in dev SQLite —
    every Doctor INSERT omitted them entirely, tripping a NOT NULL
    constraint failure. Recreating the migration under its original name
    lets Django recognize it as already-applied on dev (no-op there) while
    still correctly creating the columns on any database — e.g. production
    Postgres — where it has never run.
    """

    dependencies = [
        ('contacts', '0009_doctorsurgeryrate'),
    ]

    operations = [
        migrations.AddField(
            model_name='doctor',
            name='first_name',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='نام'),
        ),
        migrations.AddField(
            model_name='doctor',
            name='last_name',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='نام خانوادگی'),
        ),
    ]
