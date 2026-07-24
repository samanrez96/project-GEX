"""Management command to find and repair CONFIRMED purchases that have no items.

Usage:
    python manage.py repair_zero_item_purchases --dry-run   # report only
    python manage.py repair_zero_item_purchases --apply     # reset to PENDING

A CONFIRMED purchase with zero items is an invalid state that can prevent
the user from adding items or confirming again.  This command resets such
purchases to PENDING so the normal workflow can continue.
"""

from django.core.management.base import BaseCommand

from inventory.models import Purchase, PurchaseStatus


class Command(BaseCommand):
    help = "Find CONFIRMED purchases with zero items and reset them to PENDING."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--dry-run",
            action="store_true",
            help="Report affected purchases without making any changes.",
        )
        group.add_argument(
            "--apply",
            action="store_true",
            help="Reset affected purchases to PENDING (stock_applied=False).",
        )

    def handle(self, *args, **options):
        qs = (
            Purchase.objects
            .filter(status=PurchaseStatus.CONFIRMED)
            .prefetch_related("items")
        )
        # Filter to those with zero items in Python (avoids subquery complexity)
        affected = [p for p in qs if not p.items.exists()]

        if not affected:
            self.stdout.write(self.style.SUCCESS(
                "هیچ خرید تأیید‌شده‌ای با صفر قلم یافت نشد."
            ))
            return

        self.stdout.write(
            f"خریدهای تأیید‌شده با صفر قلم: {len(affected)} مورد"
        )
        for p in affected:
            self.stdout.write(f"  • خرید #{p.pk}  |  فروشنده: {p.vendor.name}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                "\n[dry-run] تغییری اعمال نشد. "
                "برای اصلاح، دوباره با --apply اجرا کنید."
            ))
            return

        # --apply: reset all affected purchases to PENDING
        for p in affected:
            p.status = PurchaseStatus.PENDING
            p.stock_applied = False
            p.save(update_fields=["status", "stock_applied", "updated_at"])
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ خرید #{p.pk} به «در انتظار» بازگردانده شد."
            ))

        self.stdout.write(self.style.SUCCESS(
            f"\n{len(affected)} خرید با موفقیت اصلاح شد."
        ))
