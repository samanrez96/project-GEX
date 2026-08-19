from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect

from employees.models import Employee
from surgeries.models import AnesthesiaType, Patient, SurgeryHistory


class PatientAdminForm(forms.ModelForm):
    """age/gender are nullable at the model level (existing Patient rows
    predate these fields and have no safe value to backfill), but every
    *new* registration through this form must supply both — enforced here,
    not on the model, so historical rows stay valid and readable."""

    class Meta:
        model = Patient
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['age'].required = True
        self.fields['gender'].required = True

# These are duties performed *during* a surgery, not separate jobs — any
# active Employee may be assigned to any of them regardless of JobPosition.
# second_assistant_surgeon is Employee-based like the rest — the label
# "کمک دوم جراح" ("second surgeon's assistant") is a duty label, not a
# statement that only a Doctor can fill it.
EMPLOYEE_ROLE_FIELDS = (
    'assistant_surgeon',
    'second_assistant_surgeon',
    'scrub_employee',
    'circulator_employee',
    'anesthesiologist',
    'anesthesia_technician',
    'operating_room_manager',
    'service_employee',
)

_ROLE_LABELS = {
    'assistant_surgeon': 'کمک اول جراح',
    'second_assistant_surgeon': 'کمک دوم جراح',
    'scrub_employee': 'اسکراب',
    'circulator_employee': 'سیرکولر',
    'anesthesiologist': 'متخصص بیهوشی',
    'anesthesia_technician': 'تکنسین بیهوشی',
    'operating_room_manager': 'مسئول اتاق عمل',
    'service_employee': 'خدمات',
}


class EmployeeRoleChoiceField(forms.ModelChoiceField):
    """ModelChoiceField for an Employee-FK role field on SurgeryHistory.

    These fields are duties performed during a surgery, not separate jobs —
    any active Employee is selectable, regardless of JobPosition. Mirrors
    SpecialtyChoiceField/SurgeryTypeChoiceField (contacts/forms.py): the
    queryset offered in the <select> is restricted (by SurgeryHistoryAdminForm
    below) to active employees, but to_python here resolves against the FULL
    Employee table — so a forged POST assigning an inactive employee still
    reaches SurgeryHistoryAdminForm._clean_employee_role() for the exact
    Persian validation message instead of Django's generic 'invalid choice' one.
    """

    def label_from_instance(self, obj):
        label = f'{obj.full_name} — {obj.job_position}'
        return label if obj.is_active else f'{label} (غیرفعال)'

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            key = self.to_field_name or 'pk'
            value = Employee.objects.get(**{key: value})
        except (ValueError, TypeError, Employee.DoesNotExist):
            raise forms.ValidationError(
                self.error_messages['invalid_choice'], code='invalid_choice',
            )
        return value


class AnesthesiaTypeChoiceField(forms.ModelChoiceField):
    """Mirrors SpecialtyChoiceField (contacts/forms.py) for AnesthesiaType."""

    def label_from_instance(self, obj):
        return obj.name if obj.is_active else f'{obj.name} (غیرفعال)'

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            key = self.to_field_name or 'pk'
            value = AnesthesiaType.objects.get(**{key: value})
        except (ValueError, TypeError, AnesthesiaType.DoesNotExist):
            raise forms.ValidationError(
                self.error_messages['invalid_choice'], code='invalid_choice',
            )
        return value


def _autocomplete_widget(field_name):
    """AutocompleteSelect (Select2, searchable) for a SurgeryHistory FK field
    that is explicitly declared below — declared form fields bypass
    ModelAdmin.formfield_for_foreignkey()/autocomplete_fields entirely, so
    the widget has to be wired here directly instead. Matches how 'patient'
    and 'clinical_doctor' (not explicitly declared) already get theirs via
    SurgeryHistoryAdmin.autocomplete_fields.
    """
    return AutocompleteSelect(SurgeryHistory._meta.get_field(field_name), admin.site)


class SurgeryHistoryAdminForm(forms.ModelForm):
    assistant_surgeon = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['assistant_surgeon'],
        widget=_autocomplete_widget('assistant_surgeon'),
    )
    scrub_employee = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['scrub_employee'],
        widget=_autocomplete_widget('scrub_employee'),
    )
    circulator_employee = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['circulator_employee'],
        widget=_autocomplete_widget('circulator_employee'),
    )
    anesthesiologist = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['anesthesiologist'],
        widget=_autocomplete_widget('anesthesiologist'),
    )
    anesthesia_technician = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['anesthesia_technician'],
        widget=_autocomplete_widget('anesthesia_technician'),
    )
    operating_room_manager = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['operating_room_manager'],
        widget=_autocomplete_widget('operating_room_manager'),
    )
    service_employee = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['service_employee'],
        widget=_autocomplete_widget('service_employee'),
    )
    second_assistant_surgeon = EmployeeRoleChoiceField(
        queryset=Employee.objects.none(), required=False, label=_ROLE_LABELS['second_assistant_surgeon'],
        widget=_autocomplete_widget('second_assistant_surgeon'),
    )
    anesthesia_type = AnesthesiaTypeChoiceField(
        queryset=AnesthesiaType.objects.none(), required=False, label='نوع بیهوشی',
    )

    class Meta:
        model = SurgeryHistory
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in EMPLOYEE_ROLE_FIELDS:
            qs = Employee.objects.filter(is_active=True)
            current_id = getattr(self.instance, f'{field_name}_id', None)
            if current_id:
                qs = qs | Employee.objects.filter(pk=current_id)
            self.fields[field_name].queryset = qs.distinct().order_by('full_name')

        anesthesia_qs = AnesthesiaType.objects.filter(is_active=True)
        current_anesthesia_id = self.instance.anesthesia_type_id if self.instance and self.instance.pk else None
        if current_anesthesia_id:
            anesthesia_qs = anesthesia_qs | AnesthesiaType.objects.filter(pk=current_anesthesia_id)
        self.fields['anesthesia_type'].queryset = anesthesia_qs.distinct().order_by('name')

    def _clean_employee_role(self, field_name):
        employee = self.cleaned_data.get(field_name)
        if employee is None:
            return employee
        current_id = getattr(self.instance, f'{field_name}_id', None) if self.instance and self.instance.pk else None
        if employee.pk == current_id:
            # Unchanged from the saved value — stays valid even if the
            # employee's active status changed afterward.
            return employee
        if not employee.is_active:
            raise forms.ValidationError('این کارمند غیرفعال است و برای انتساب جدید قابل انتخاب نیست.')
        return employee

    def clean_assistant_surgeon(self):
        return self._clean_employee_role('assistant_surgeon')

    def clean_scrub_employee(self):
        return self._clean_employee_role('scrub_employee')

    def clean_circulator_employee(self):
        return self._clean_employee_role('circulator_employee')

    def clean_anesthesiologist(self):
        return self._clean_employee_role('anesthesiologist')

    def clean_anesthesia_technician(self):
        return self._clean_employee_role('anesthesia_technician')

    def clean_operating_room_manager(self):
        return self._clean_employee_role('operating_room_manager')

    def clean_service_employee(self):
        return self._clean_employee_role('service_employee')

    def clean_second_assistant_surgeon(self):
        return self._clean_employee_role('second_assistant_surgeon')

    def clean_anesthesia_type(self):
        anesthesia_type = self.cleaned_data.get('anesthesia_type')
        if anesthesia_type is None:
            return anesthesia_type
        current_id = self.instance.anesthesia_type_id if self.instance and self.instance.pk else None
        if not anesthesia_type.is_active and anesthesia_type.pk != current_id:
            raise forms.ValidationError(
                'این نوع بیهوشی غیرفعال است و برای انتساب جدید قابل انتخاب نیست.'
            )
        return anesthesia_type
