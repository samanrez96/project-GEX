from django.db import migrations


def forwards(apps, schema_editor):
    Employee = apps.get_model('employees', 'Employee')
    EmployeeDocument = apps.get_model('employees', 'EmployeeDocument')

    # Preserve any already-uploaded fixed credential images by copying them
    # (same storage name, no re-upload / no file moved on disk) into the new
    # repeatable EmployeeDocument relation, image 1 first then image 2.
    # Idempotent: re-running (e.g. a squash/replay) would create duplicate
    # rows only if EmployeeDocument rows referencing that same file name
    # don't already exist — guarded against below.
    for field_name in ('credential_image_1', 'credential_image_2'):
        qs = Employee.objects.exclude(**{field_name: ''}).exclude(**{f'{field_name}__isnull': True})
        for emp in qs:
            file_name = getattr(emp, field_name)
            if not file_name:
                continue
            already_copied = EmployeeDocument.objects.filter(
                employee=emp, file=file_name,
            ).exists()
            if not already_copied:
                EmployeeDocument.objects.create(employee=emp, file=file_name)


def backwards(apps, schema_editor):
    # Best-effort restore: the first two documents (by creation order) of
    # each employee move back onto the fixed fields. Any additional
    # documents beyond two have no home on the legacy fields and are left
    # as EmployeeDocument rows. No physical file is ever deleted by this
    # migration in either direction.
    Employee = apps.get_model('employees', 'Employee')
    EmployeeDocument = apps.get_model('employees', 'EmployeeDocument')

    for emp in Employee.objects.all():
        docs = list(EmployeeDocument.objects.filter(employee=emp).order_by('created_at', 'id')[:2])
        update_fields = []
        if len(docs) >= 1:
            emp.credential_image_1 = docs[0].file
            update_fields.append('credential_image_1')
        if len(docs) >= 2:
            emp.credential_image_2 = docs[1].file
            update_fields.append('credential_image_2')
        if update_fields:
            emp.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0007_employeedocument'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
