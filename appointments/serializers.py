from rest_framework import serializers

from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    doctor_name          = serializers.CharField(source='doctor.full_name', read_only=True)
    patient_display_name = serializers.SerializerMethodField(read_only=True)
    status_display        = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'doctor', 'doctor_name',
            'patient', 'patient_name', 'patient_phone', 'patient_display_name',
            'visit_date', 'start_time', 'duration_minutes',
            'status', 'status_display',
            'reason', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_patient_display_name(self, obj) -> str:
        return obj.display_patient_name

    def validate(self, attrs):
        patient = attrs.get('patient', getattr(self.instance, 'patient', None))
        patient_name = attrs.get('patient_name', getattr(self.instance, 'patient_name', ''))
        if not patient and not (patient_name or '').strip():
            raise serializers.ValidationError(
                'باید یا یک بیمار ثبت‌شده انتخاب شود یا نام بیمار وارد شود.'
            )
        duration = attrs.get('duration_minutes', getattr(self.instance, 'duration_minutes', None))
        if duration is not None and duration <= 0:
            raise serializers.ValidationError({'duration_minutes': 'مدت زمان باید بزرگ‌تر از صفر باشد.'})
        return attrs
