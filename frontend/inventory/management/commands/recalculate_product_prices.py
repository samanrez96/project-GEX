"""Recalculate Product.purchase_price from the latest non-cancelled purchase.

Usage:
    python manage.py recalculate_product_prices --dry-run   # report without changes
    python manage.py recalculate_product_prices --apply     # fix incorrect prices

Dry-run reports:
  - Product id / code / name
  - current price stored in DB
  - expected price from latest non-cancelled purchase (PENDING or CONFIRMED)
  - latest purchase id / status / date
  - count of products requiring changes

Apply mode:
  - Updates only products whose purchase_price does not match the latest non-cancelled
    PurchaseItem.unit_price.
  - Does not touch stock, purchases, PurchaseItems, Finance, or ProductVendor history.

The authoritative ordering for "latest" is:
  purchase_date DESC, purchase.pk DESC, PurchaseItem.pk DESC

CANCELLED purchases are excluded; PENDING and CONFIRMED purchases both qualify.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Recalculate Product.purchase_price from confirmed purchase history."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--dry-run",
            action="store_true",
            help="Report products with incorrect price without making changes.",
        )
        group.add_argument(
            "--apply",
            action="store_true",
            help="Update Product.purchase_price to match latest confirmed purchase.",
        )

    def handle(self, *args, **options):
        from inventory.models import Product, PurchaseItem, PurchaseStatus

        products = Product.objects.only("id", "name", "internal_code", "purchase_price")
        needs_update = []

        for product in products:
            latest_item = (
                PurchaseItem.objects
                .filter(
                    product_id=product.pk,
                    unit_price__gt=0,
                )
                .exclude(purchase__status=PurchaseStatus.CANCELLED)
                .select_related("purchase")
                .order_by("-purchase__purchase_date", "-purchase__pk", "-pk")
                .first()
            )

            if latest_item is None:
                # No confirmed purchase — current price is the authoritative initial price.
                continue

            expected = latest_item.unit_price
            if product.purchase_price == expected:
                continue

            needs_update.append({
                "product":         product,
                "current":         product.purchase_price,
                "expected":        expected,
                "purchase_id":     latest_item.purchase_id,
                "purchase_status": latest_item.purchase.status,
                "purchase_date":   latest_item.purchase.purchase_date,
            })

        if not needs_update:
            self.stdout.write(self.style.SUCCESS(
                "همه قیمت‌های محصول با آخرین خرید تأیید‌شده مطابقت دارند. تغییری لازم نیست."
            ))
            return

        self.stdout.write(
            f"محصولات نیازمند به‌روزرسانی: {len(needs_update)} مورد\n"
        )
        self.stdout.write(
            f"{'ID':>5}  {'کد':>10}  {'نام':<28}  {'قیمت فعلی':>15}  "
            f"{'قیمت مورد انتظار':>18}  {'خرید':>6}  {'وضعیت':<10}  {'تاریخ'}"
        )
        self.stdout.write("-" * 115)

        for row in needs_update:
            p = row["product"]
            date_str = str(row["purchase_date"])[:10]
            self.stdout.write(
                f"{p.pk:>5}  {p.internal_code:>10}  {p.name:<28}  "
                f"{row['current']:>15}  {row['expected']:>18}  "
                f"#{row['purchase_id']:>5}  {row['purchase_status']:<10}  {date_str}"
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                f"\n[dry-run] {len(needs_update)} محصول نیاز به اصلاح دارد. "
                "تغییری اعمال نشد. برای اصلاح با --apply اجرا کنید."
            ))
            return

        # --apply: update only the mismatched products
        updated = 0
        with transaction.atomic():
            for row in needs_update:
                Product.objects.filter(pk=row["product"].pk).update(
                    purchase_price=row["expected"]
                )
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n{updated} قیمت محصول با موفقیت به‌روزرسانی شد."
        ))
