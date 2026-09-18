"""
Management command: setup_roles

Creates the four standard Django Groups used for role-based access control
in the surgery-clinic project. Safe to run multiple times — existing groups
are left untouched.

Usage:
    python manage.py setup_roles
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

ROLES = [
    "admin",
    "finance_user",
    "inventory_user",
    "employee_manager",
]


class Command(BaseCommand):
    help = "Create the default role groups (admin, finance_user, inventory_user, employee_manager)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Setting up role groups...\n"))

        for role_name in ROLES:
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  [+] Created group: '{role_name}'")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  [-] Already exists: '{role_name}'")
                )

        self.stdout.write(self.style.SUCCESS("\nRole setup complete."))
