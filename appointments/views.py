from django.db.models import Q
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from common.pagination import StandardPagination

from .models import Appointment
from .serializers import AppointmentSerializer


class AppointmentViewSet(viewsets.ModelViewSet):
    """CRUD viewset for patient-visit appointments.

    GET/POST             /api/v1/appointments/appointments/
    GET/PUT/PATCH/DELETE /api/v1/appointments/appointments/{id}/

    Filters (?doctor=&status=&visit_date=&visit_date__gte=&visit_date__lte=):
      doctor, status, visit_date (exact/gte/lte)

    Search (?search=):
      patient full name, patient_name, reason

    Ordering (?ordering=):
      visit_date, start_time  (default: visit_date, start_time)
    """

    permission_classes = [IsAuthenticated]
    serializer_class    = AppointmentSerializer
    pagination_class    = StandardPagination
    filterset_fields    = {
        'doctor':     ['exact'],
        'status':     ['exact'],
        'visit_date': ['exact', 'gte', 'lte'],
    }
    search_fields   = ['patient__full_name', 'patient_name', 'reason']
    ordering_fields = ['visit_date', 'start_time', 'created_at']
    ordering        = ['visit_date', 'start_time']

    def get_queryset(self):
        # Hidden Patients must not leak through the appointment's patient FK
        # — same visibility rule as everywhere else Patient is exposed.
        return (
            Appointment.objects
            .select_related('doctor', 'patient')
            .filter(Q(patient__isnull=True) | Q(patient__is_hidden=False))
        )
