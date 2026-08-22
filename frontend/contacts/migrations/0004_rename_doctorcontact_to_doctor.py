from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0003_alter_doctorcontact_rate_per_surgery'),
        ('surgeries', '0013_surgeryhistory_medical_record_code'),
    ]

    operations = [
        migrations.RenameModel(old_name='DoctorContact', new_name='Doctor'),
    ]
