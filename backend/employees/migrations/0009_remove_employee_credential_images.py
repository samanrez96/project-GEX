from django.db import migrations


class Migration(migrations.Migration):
    """Removes the legacy fixed credential_image_1 / credential_image_2
    fields. Safe only because migration 0008 already copied any
    pre-existing non-empty values into EmployeeDocument first — this
    migration never runs before that one (see its dependency below), and
    removing a column never deletes the underlying physical file in
    storage, only the database reference to its name.
    """

    dependencies = [
        ('employees', '0008_migrate_legacy_credential_images'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='employee',
            name='credential_image_1',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='credential_image_2',
        ),
    ]
