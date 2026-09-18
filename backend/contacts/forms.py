from django import forms
from django.urls import reverse

from common.uploads import validate_image_upload
from contacts.models import Doctor, DoctorSpecialty, DoctorSurgeryRate
from surgeries.models import SurgeryType


class DoctorDocumentWidget(forms.ClearableFileInput):
    """ClearableFileInput that renders a constrained thumbnail and a
    'مشاهده فایل' link to the protected document endpoint instead of
    Django's default '<a href="{{ value.url }}">{{ value }}</a>' — which
    would both expose the raw storage filename and point at a MEDIA_URL
    path nothing actually serves (this project wires up no public media
    serving at all)."""

    clear_checkbox_label = 'حذف فایل'
    initial_text = 'فایل فعلی'
    input_text = 'جایگزینی فایل'
    template_name = 'admin/contacts/doctor/document_widget.html'

    def __init__(self, *, url_name, attrs=None):
        self.url_name = url_name
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_ctx = context['widget']
        preview_url = None
        current = widget_ctx.get('value')
        if current:
            instance = getattr(current, 'instance', None)
            if instance and instance.pk:
                preview_url = reverse(self.url_name, args=[instance.pk])
        widget_ctx['preview_url'] = preview_url
        return context


class ValidatedImageFormField(forms.FileField):
    """FileField (not Django's forms.ImageField) so that Django's own
    English "Upload a valid image..." message never pre-empts our Persian
    ones — validate_image_upload() is the single source of truth for what
    counts as a valid image, reused by the model field's `validators` (and
    therefore by DRF's auto-generated serializer field) and here."""

    def to_python(self, data):
        f = super().to_python(data)
        if f is None:
            return None
        validate_image_upload(f)
        if hasattr(f, 'seek'):
            f.seek(0)
        return f

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        if isinstance(widget, forms.FileInput) and 'accept' not in attrs:
            attrs.setdefault('accept', 'image/jpeg,image/png,image/webp')
        return attrs


class SpecialtyChoiceField(forms.ModelChoiceField):
    """Appends '(غیرفعال)' to inactive specialties so an existing Doctor's
    already-assigned inactive specialty stays recognizable in the dropdown.

    The field's queryset is deliberately restricted (see DoctorAdminForm) to
    only the active specialties plus the instance's own current one, so the
    rendered <select> never offers other inactive specialties as choices.
    That same restricted queryset would otherwise make ModelChoiceField
    reject a forged POST of any other inactive specialty's pk with Django's
    generic "not one of the available choices" message — to_python is
    overridden to resolve against the full table instead, so a forged
    assignment reaches DoctorAdminForm.clean_specialty() and gets our exact
    Persian validation message.
    """

    def label_from_instance(self, obj):
        if not obj.is_active:
            return f'{obj.name} (غیرفعال)'
        return obj.name

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            key = self.to_field_name or 'pk'
            value = DoctorSpecialty.objects.get(**{key: value})
        except (ValueError, TypeError, DoctorSpecialty.DoesNotExist):
            raise forms.ValidationError(
                self.error_messages['invalid_choice'], code='invalid_choice',
            )
        return value


class SurgeryTypeChoiceField(forms.ModelChoiceField):
    """Mirrors SpecialtyChoiceField's behavior for the DoctorSurgeryRate
    inline: appends '(غیرفعال)' for an already-assigned inactive Surgery
    Type, and resolves against the full table in to_python so a forged
    assignment of a *different* inactive Surgery Type still reaches
    DoctorSurgeryRateInlineForm.clean_surgery_type() for the exact Persian
    message instead of Django's generic 'invalid choice' one.
    """

    def label_from_instance(self, obj):
        if not obj.is_active:
            return f'{obj.name} (غیرفعال)'
        return obj.name

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            key = self.to_field_name or 'pk'
            value = SurgeryType.objects.get(**{key: value})
        except (ValueError, TypeError, SurgeryType.DoesNotExist):
            raise forms.ValidationError(
                self.error_messages['invalid_choice'], code='invalid_choice',
            )
        return value


class DoctorSurgeryRateInlineForm(forms.ModelForm):
    surgery_type = SurgeryTypeChoiceField(
        queryset=SurgeryType.objects.none(),
        label='نوع عمل',
    )

    class Meta:
        model = DoctorSurgeryRate
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = SurgeryType.objects.filter(is_active=True)
        current_id = self.instance.surgery_type_id if self.instance and self.instance.pk else None
        if current_id:
            qs = qs | SurgeryType.objects.filter(pk=current_id)
        self.fields['surgery_type'].queryset = qs.distinct().order_by('name')

    def clean_surgery_type(self):
        surgery_type = self.cleaned_data.get('surgery_type')
        if surgery_type is None:
            return surgery_type
        current_id = self.instance.surgery_type_id if self.instance and self.instance.pk else None
        if not surgery_type.is_active and surgery_type.pk != current_id:
            raise forms.ValidationError(
                'این نوع عمل غیرفعال است و برای انتساب جدید قابل انتخاب نیست.'
            )
        return surgery_type


class DoctorAdminForm(forms.ModelForm):
    specialty = SpecialtyChoiceField(
        queryset=DoctorSpecialty.objects.none(),
        required=False,
        label='تخصص',
    )
    medical_certificate_image = ValidatedImageFormField(
        required=False,
        label='مدرک پزشکی',
        widget=DoctorDocumentWidget(url_name='admin:contacts_doctor_medical_certificate'),
    )
    national_card_image = ValidatedImageFormField(
        required=False,
        label='کارت ملی',
        widget=DoctorDocumentWidget(url_name='admin:contacts_doctor_national_card'),
    )

    class Meta:
        model = Doctor
        fields = '__all__'
        # first_name/last_name are derived from full_name below (see clean())
        # rather than shown as a second identity section — excluding them
        # here (instead of just omitting them from fieldsets) also drops them
        # from ModelForm._get_validation_exclusions(), so construct_instance()
        # never overwrites the values clean() assigns directly on the instance.
        exclude = ('first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = DoctorSpecialty.objects.filter(is_active=True)
        current_id = self.instance.specialty_id if self.instance and self.instance.pk else None
        if current_id:
            qs = qs | DoctorSpecialty.objects.filter(pk=current_id)
        self.fields['specialty'].queryset = qs.distinct().order_by('name')

    def clean_full_name(self):
        value = self.cleaned_data.get('full_name', '') or ''
        value = ' '.join(value.split())  # trim + collapse internal whitespace
        if not value:
            raise forms.ValidationError('نام و نام خانوادگی الزامی است.')
        return value

    def clean(self):
        cleaned = super().clean()
        full_name = cleaned.get('full_name')
        is_new = not self.instance.pk
        name_changed = 'full_name' in self.changed_data
        # A pre-existing Doctor saved before first_name/last_name existed
        # (or via direct ORM/import) has both blank — opportunistically
        # backfill it on the next edit rather than leaving it blank forever.
        never_derived = not self.instance.first_name and not self.instance.last_name
        # Otherwise: an existing Doctor's name must not be destructively
        # re-split on every unrelated field edit — only full_name itself
        # changing (or a fresh backfill above) re-derives it.
        if full_name and (is_new or name_changed or never_derived):
            first_name, _, last_name = full_name.partition(' ')
            self.instance.first_name = first_name
            self.instance.last_name = last_name.strip()
        return cleaned

    def clean_specialty(self):
        specialty = self.cleaned_data.get('specialty')
        if specialty is None:
            return specialty
        current_id = self.instance.specialty_id if self.instance and self.instance.pk else None
        if not specialty.is_active and specialty.pk != current_id:
            raise forms.ValidationError(
                'این تخصص غیرفعال است و برای انتساب جدید قابل انتخاب نیست.'
            )
        return specialty
