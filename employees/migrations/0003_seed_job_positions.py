from django.db import migrations

POSITIONS = [
    ("متخصص بیهوشی", "Anesthesiologist"),
    ("پرستار",        "Nurse"),
    ("تکنسین",        "Technician"),
    ("اپراتور",       "Operator"),
    ("منشی",          "Secretary"),
    ("حسابدار",       "Accountant"),
]


def seed_positions(apps, schema_editor):
    JobPosition = apps.get_model("employees", "JobPosition")
    for name, description in POSITIONS:
        JobPosition.objects.get_or_create(
            name=name,
            defaults={"description": description, "is_active": True},
        )


def unseed_positions(apps, schema_editor):
    """Reverse: delete only positions that have no employees referencing them.

    Deleting a position that an Employee references (on_delete=PROTECT) raises
    ProtectedError.  We skip those rather than aborting the entire reverse.
    """
    JobPosition = apps.get_model("employees", "JobPosition")
    Employee    = apps.get_model("employees", "Employee")
    for name, _ in POSITIONS:
        try:
            pos = JobPosition.objects.filter(name=name).first()
            if pos is None:
                continue
            if Employee.objects.filter(job_position=pos).exists():
                continue
            pos.delete()
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0002_create_job_position"),
    ]

    operations = [
        migrations.RunPython(seed_positions, reverse_code=unseed_positions),
    ]
