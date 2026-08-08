"""Contacts service layer.

DoctorRateService — authoritative lookup for a Doctor's fee on a specific
Surgery Type, backed exclusively by DoctorSurgeryRate (the legacy flat
Doctor.rate_per_surgery field is never consulted here).
"""


class DoctorRateService:

    @staticmethod
    def get_rate(doctor, surgery_type):
        """Return the exact DoctorSurgeryRate.rate for (doctor, surgery_type),
        or None if no such rate row exists."""
        if doctor is None or surgery_type is None:
            return None
        from contacts.models import DoctorSurgeryRate
        row = DoctorSurgeryRate.objects.filter(
            doctor=doctor, surgery_type=surgery_type,
        ).only('rate').first()
        return row.rate if row else None
