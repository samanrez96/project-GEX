from django.contrib.auth.models import User
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "roles",
        ]

    def get_roles(self, obj):
        # Prefetch groups if this serializer is used in a list view
        if hasattr(obj, 'prefetched_groups'):
            return list(obj.prefetched_groups.values_list("name", flat=True))
        return list(obj.groups.values_list("name", flat=True))