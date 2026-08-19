import django.db.models.deletion
from django.db import migrations, models


def backfill_specialty(apps, schema_editor):
    Doctor = apps.get_model('contacts', 'Doctor')
    DoctorSpecialty = apps.get_model('contacts', 'DoctorSpecialty')
    cache = {}
    for doctor in Doctor.objects.all():
        text = (doctor.specialty or '').strip() or 'نامشخص'
        specialty = cache.get(text)
        if specialty is None:
            specialty, _ = DoctorSpecialty.objects.get_or_create(name=text)
            cache[text] = specialty
        doctor.specialty_fk_id = specialty.pk
        doctor.save(update_fields=['specialty_fk'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0005_doctorspecialty'),
    ]

    operations = [
        migrations.AddField(
            model_name='doctor',
            name='specialty_fk',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='doctors',
                to='contacts.doctorspecialty',
                verbose_name='تخصص',
            ),
        ),
        migrations.RunPython(backfill_specialty, noop_reverse),
        migrations.RemoveField(
            model_name='doctor',
            name='specialty',
        ),
        migrations.RenameField(
            model_name='doctor',
            old_name='specialty_fk',
            new_name='specialty',
        ),
        migrations.AlterField(
            model_name='doctor',
            name='specialty',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='doctors',
                to='contacts.doctorspecialty',
                verbose_name='تخصص',
            ),
        ),
    ]
