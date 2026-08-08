from rest_framework.routers import DefaultRouter

from contacts.views import DoctorViewSet, EmployeeContactViewSet

app_name = 'contacts'

router = DefaultRouter()
router.register('doctors', DoctorViewSet, basename='doctor')
router.register('employees', EmployeeContactViewSet, basename='employee-contact')

urlpatterns = router.urls
