from django.urls import reverse
from rest_framework import serializers

from contacts.models import Doctor
from employees.models import Employee

_DOCUMENT_FIELD_URL_NAMES = {
    'medical_certificate_image': 'admin:contacts_doctor_medical_certificate',
    'national_card_image': 'admin:contacts_doctor_national_card',
}


class DoctorDocumentURLMixin:
    """Swaps the raw storage URL for the two document ImageFields with the
    protected admin document endpoint on read, so the API never returns a
    local filesystem/storage path — this project wires up no public
    MEDIA_URL serving, so the raw `.url` wouldn't resolve to anything
    anyway. Shared by both Doctor serializers so list and detail responses
    behave identically. Fields remain writable: multipart uploads still go
    through the model's own validators (auto-inherited by DRF)."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        for field_name, url_name in _DOCUMENT_FIELD_URL_NAMES.items():
            if field_name not in data:
                continue
            field_file = getattr(instance, field_name)
            if field_file and field_file.name:
                url = reverse(url_name, args=[instance.pk])
                data[field_name] = request.build_absolute_uri(url) if request else url
            else:
                data[field_name] = None
        return data


class DoctorListSerializer(DoctorDocumentURLMixin, serializers.ModelSerializer):
    cooperation_status_display = serializers.CharField(
        source='get_cooperation_status_display', read_only=True
    )
    specialty_name = serializers.CharField(source='specialty.name', read_only=True)

    class Meta:
        model = Doctor
        fields = [
            'id', 'full_name', 'specialty', 'specialty_name', 'phone_number', 'email',
            'national_id', 'medical_system_number', 'clinic_phone',
            'collaboration_start_date', 'license_last_renewal_date',
            'medical_certificate_image', 'national_card_image',
            'center_commission_percent', 'rate_per_surgery',
            'cooperation_status', 'cooperation_status_display', 'is_active',
        ]


class DoctorSerializer(DoctorDocumentURLMixin, serializers.ModelSerializer):
    cooperation_status_display = serializers.CharField(
        source='get_cooperation_status_display', read_only=True
    )
    specialty_name = serializers.CharField(source='specialty.name', read_only=True)

    class Meta:
        model = Doctor
        fields = [
            'id', 'full_name', 'specialty', 'specialty_name', 'phone_number', 'email',
            'national_id', 'medical_system_number', 'clinic_phone',
            'collaboration_start_date', 'license_last_renewal_date',
            'medical_certificate_image', 'national_card_image',
            'address', 'center_commission_percent', 'rate_per_surgery',
            'cooperation_status', 'cooperation_status_display',
            'notes', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_center_commission_percent(self, value):
        if value is not None and (value < 0 or value > 100):
            raise serializers.ValidationError(
                "درصد کمیسیون مرکز باید بین ۰ تا ۱۰۰ باشد."
            )
        return value

    def validate_specialty(self, value):
        if value is None:
            return value
        if not value.is_active:
            current_id = self.instance.specialty_id if self.instance else None
            if value.pk != current_id:
                raise serializers.ValidationError(
                    "این تخصص غیرفعال است و برای انتساب جدید قابل انتخاب نیست."
                )
        return value


class EmployeeContactSerializer(serializers.ModelSerializer):
    job_position_name = serializers.CharField(source='job_position.name', read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'full_name', 'job_position', 'job_position_name',
            'personal_phone', 'email', 'emergency_contact_phone', 'is_active',
        ]
