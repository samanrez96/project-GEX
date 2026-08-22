"""Centralized stock mutation service.

This module is the single public entry point for all stock change operations.
Any code that needs to alter Product.current_stock — purchases, surgery
consumption, manual adjustments, returns — must go through StockService
rather than calling Product._apply_stock_delta() directly.

Benefits over direct model calls:
  - Atomicity: movement record + stock update in one DB transaction
  - Audit trail: every change is backed by an immutable StockMovement row
  - Validation: quantity > 0 enforced before any DB write
  - Documentation: a single, well-named method is easier to discover and grep

Concurrency safety is handled inside Product._apply_stock_delta(), which
uses SELECT FOR UPDATE on databases that support it (PostgreSQL, MySQL).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


class PriceService:
    """Keep Product.purchase_price and ProductVendor.unit_price in sync with
    confirmed purchase history.

    All methods are static — no instantiation needed.

    Design rules
    ------------
    - "Latest purchase" = highest purchase_date, purchase.pk as tie-breaker.
    - Only CONFIRMED purchases are considered (PENDING / CANCELLED are ignored).
    - Items with zero or null unit_price are always skipped.
    - Product.purchase_price is updated via .update() to bypass the stock guard.
    - ProductVendor rows are updated via update_or_create so that a new vendor
      relation is created automatically when it does not yet exist, without ever
      producing duplicate (product, vendor) pairs.
    """

    @staticmethod
    def recalculate_product_price(product_id: int) -> None:
        """Set Product.purchase_price to the unit_price of the latest non-cancelled
        PurchaseItem for this product.

        Both PENDING and CONFIRMED purchases qualify — only CANCELLED purchases are
        excluded.  'Latest' is determined by purchase_date DESC, then purchase PK
        DESC, then PurchaseItem PK DESC as tiebreakers.  Items with zero/null
        unit_price are excluded.  If no qualifying item exists the product price is
        left unchanged (no regression to zero).
        """
        from inventory.models import Product, PurchaseItem, PurchaseStatus

        latest_item = (
            PurchaseItem.objects
            .filter(
                product_id=product_id,
                unit_price__gt=0,
            )
            .exclude(purchase__status=PurchaseStatus.CANCELLED)
            .select_related("purchase")
            .order_by("-purchase__purchase_date", "-purchase__pk", "-pk")
            .first()
        )
        if latest_item is None:
            return  # no valid purchase — leave price unchanged

        # .update() bypasses Product.save() stock guard (only purchase_price changes).
        Product.objects.filter(pk=product_id).update(
            purchase_price=latest_item.unit_price
        )

    @staticmethod
    def ensure_vendor_product_link(purchase) -> None:
        """Create a ProductVendor row for each purchase item that has no link yet.

        Called after every purchase save (any status) so the vendor page shows
        purchased products immediately — even for PENDING purchases.

        Only creates a row when no (product, vendor) pair exists at all; it does
        NOT update prices (price sync is deferred to confirm via
        sync_purchase_vendor_price).
        """
        from inventory.models import ProductVendor

        items = list(purchase.items.select_related("product").all())
        for item in items:
            if ProductVendor.objects.filter(
                product_id=item.product_id,
                vendor=purchase.vendor,
            ).exists():
                continue  # relationship already recorded
            ProductVendor.objects.create(
                product_id=item.product_id,
                vendor=purchase.vendor,
                unit_price=item.unit_price if item.unit_price else Decimal("0"),
            )

    @staticmethod
    def sync_purchase_vendor_price(purchase, items) -> None:
        """Update or create ProductVendor.unit_price for the purchase's vendor.

        For every PurchaseItem in *items* (non-zero unit_price only):
          - Existing (product, vendor) row → update the most-recently-used row's
            unit_price and last_price_date.
          - No row yet → create one with those values and model-default fields.

        Now that the unique_product_vendor DB constraint has been removed, multiple
        rows per (product, vendor) are possible.  We update the row with the
        highest pk (most recently added) to keep the "current price" visible on
        the vendor page.
        """
        from inventory.models import ProductVendor

        purchase_date_val = None
        if purchase.purchase_date:
            d = purchase.purchase_date
            purchase_date_val = d.date() if hasattr(d, "date") else d

        for item in items:
            if not item.unit_price or item.unit_price <= 0:
                continue

            existing_qs = ProductVendor.objects.filter(
                product_id=item.product_id,
                vendor=purchase.vendor,
            ).order_by("-pk")

            if existing_qs.exists():
                pv = existing_qs.first()
                pv.unit_price = item.unit_price
                pv.last_price_date = purchase_date_val
                pv.save(update_fields=["unit_price", "last_price_date", "updated_at"])
            else:
                ProductVendor.objects.create(
                    product_id=item.product_id,
                    vendor=purchase.vendor,
                    unit_price=item.unit_price,
                    last_price_date=purchase_date_val,
                )


class VendorService:
    """Aggregate queries for vendor-facing data."""

    @staticmethod
    def get_vendor_purchased_products(vendor_id: int):
        """Return an annotated Product queryset for CONFIRMED purchases from this vendor.

        Annotations (computed in-DB, no Python loops):
          purchase_count     — distinct confirmed Purchase records containing product
          total_quantity     — sum of PurchaseItem.quantity across confirmed purchases
          last_purchase_date — most recent confirmed purchase_date
          last_unit_price    — unit_price from the most-recent confirmed PurchaseItem
                               (ordered by purchase_date DESC, purchase PK DESC, item PK DESC)

        No N+1: a single queryset with annotations; the Subquery adds one correlated
        query that the DB runs once per result row in the same round-trip.
        """
        from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum
        from inventory.models import Product, PurchaseItem, PurchaseStatus

        latest_price_sq = (
            PurchaseItem.objects
            .filter(
                product=OuterRef("pk"),
                purchase__vendor_id=vendor_id,
                purchase__status=PurchaseStatus.CONFIRMED,
                unit_price__gt=0,
            )
            .order_by("-purchase__purchase_date", "-purchase__pk", "-pk")
            .values("unit_price")[:1]
        )

        confirmed_product_ids = (
            PurchaseItem.objects
            .filter(
                purchase__vendor_id=vendor_id,
                purchase__status=PurchaseStatus.CONFIRMED,
            )
            .values_list("product_id", flat=True)
            .distinct()
        )

        vendor_confirmed_q = Q(
            purchase_items__purchase__vendor_id=vendor_id,
            purchase_items__purchase__status=PurchaseStatus.CONFIRMED,
        )

        return (
            Product.objects
            .filter(pk__in=confirmed_product_ids)
            .annotate(
                purchase_count=Count(
                    "purchase_items__purchase",
                    filter=vendor_confirmed_q,
                    distinct=True,
                ),
                total_quantity=Sum(
                    "purchase_items__quantity",
                    filter=vendor_confirmed_q,
                ),
                last_purchase_date=Max(
                    "purchase_items__purchase__purchase_date",
                    filter=vendor_confirmed_q,
                ),
                last_unit_price=Subquery(latest_price_sq),
            )
            .order_by("-last_purchase_date", "internal_code")
        )


class StockService:
    """Service class for all stock movement operations.

    All methods are static — instantiation is not needed.
    """

    @staticmethod
    @transaction.atomic
    def create_movement(
        *,
        product,
        quantity,
        movement_type,
        source_type,
        reference_id="",
        description="",
        movement_date=None,
        allow_negative=False,
    ):
        """Create a StockMovement record and update Product.current_stock atomically.

        Args:
            product: Product instance or integer PK.
            quantity: Positive numeric value (Decimal, int, str, or float).
                      Internally converted to Decimal.
            movement_type: MovementType.IN / OUT / ADJUSTMENT.
            source_type: SourceType.PURCHASE / SURGERY_CONSUMPTION /
                         MANUAL_ADJUSTMENT / RETURN / OTHER.
            reference_id: str — identifier of the source object for traceability
                          (e.g., str(purchase.pk), str(surgery.pk)).
            description: Human-readable note stored on the movement record.
            movement_date: Actual event datetime; defaults to timezone.now().
                           May differ from the record's created_at timestamp.

        Returns:
            StockMovement instance (already saved; product stock already updated).

        Raises:
            Product.DoesNotExist if product PK not found.
            ValidationError if quantity <= 0.
            ValidationError if movement_type OUT would cause negative stock
              (when ALLOW_NEGATIVE_STOCK is False — the project default).
        """
        # Lazy import to prevent circular imports (models → services → models)
        from inventory.models import Product, StockMovement

        if isinstance(product, int):
            product = Product.objects.get(pk=product)

        quantity = Decimal(str(quantity))
        if quantity <= 0:
            raise ValidationError({"quantity": "مقدار باید بزرگ‌تر از صفر باشد."})

        movement = StockMovement(
            product=product,
            quantity=quantity,
            movement_type=movement_type,
            source_type=source_type,
            reference_id=str(reference_id) if reference_id else "",
            description=description or "",
            movement_date=movement_date or timezone.now(),
        )
        if allow_negative:
            movement._allow_negative_stock = True
        # StockMovement.save() calls product._apply_stock_delta() atomically.
        # _apply_stock_delta() uses SELECT FOR UPDATE on supported databases.
        movement.save()
        return movement

    @staticmethod
    @transaction.atomic
    def adjust_to_quantity(*, product, desired_quantity, reason="", user=None, reference_id=""):
        """Reconcile Product.current_stock to *desired_quantity* through a
        single MANUAL_ADJUSTMENT StockMovement — the one sanctioned way to
        correct stock from an administrative form (Product change page) or
        a future API action. Never assign to Product.current_stock directly;
        this is the canonical path purchases/surgery consumption already use
        (create_movement above), applied in the other direction: from a
        desired end state rather than a known delta.

        Locks the Product row (SELECT FOR UPDATE where supported) and
        re-reads its current stock from the database before computing the
        delta, so a Purchase or Surgery consumption that happened after the
        page was rendered is never lost or silently overwritten — the
        caller's desired_quantity is always reconciled against the true,
        current-at-save-time stock, not whatever was on screen when the
        form was opened.

        Args:
            product: Product instance or integer PK.
            desired_quantity: The stock level the caller wants after this
                              call returns. Must be >= 0.
            reason: Optional human-readable adjustment reason. Product has
                    no field of its own for this — it is stored only on the
                    created StockMovement's description, the sole place
                    this information lives. Falls back to a generic
                    "اصلاح دستی موجودی" label when left blank.
            user: The acting user, if any. StockMovement has no dedicated
                  "performed by" column, so this is folded into the
                  description text instead of silently dropped.
            reference_id: Optional override; defaults to a stable
                          per-Product marker.

        Returns:
            The created StockMovement, or None if desired_quantity already
            equals the current stock — a zero delta creates no movement.

        Raises:
            ValidationError if desired_quantity < 0.
        """
        from django.db import connection

        from inventory.models import MovementType, Product, SourceType

        if isinstance(product, int):
            product = Product.objects.get(pk=product)

        desired = Decimal(str(desired_quantity))
        if desired < 0:
            raise ValidationError({"desired_quantity": "موجودی نمی‌تواند منفی باشد."})

        qs = Product.objects.filter(pk=product.pk)
        if connection.features.has_select_for_update:
            qs = qs.select_for_update()
        current = qs.values_list("current_stock", flat=True).get()

        delta = desired - current
        if delta == 0:
            return None

        # A reason is optional — fall back to a generic but still useful
        # label rather than saving an empty/meaningless description.
        description = (reason or "").strip() or "اصلاح دستی موجودی"
        if user is not None:
            username = user.get_username() if hasattr(user, "get_username") else str(user)
            description = f"{description} — توسط {username}"

        movement_type = MovementType.IN if delta > 0 else MovementType.OUT
        return StockService.create_movement(
            product=product,
            quantity=abs(delta),
            movement_type=movement_type,
            source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id=reference_id or f"manual-adjustment-{product.pk}",
            description=description,
        )


class ProductPurgeService:
    """The single canonical path for permanently destroying a Product.

    StockMovement, PurchaseItem, SurgeryUsedItem and SurgeryConsumptionItem
    all point at Product with on_delete=PROTECT specifically so that a
    Product can never disappear out from under its history by accident —
    the only way to remove one is to go through preview()/purge() here.
    Do not call Product.delete() directly and do not reimplement this
    logic elsewhere (admin, DRF views, signals, etc).

    Restricted to the main administrator — see
    accounts.permissions.is_main_administrator(). purge() re-checks this
    itself so a caller can never reach the destructive path by skipping a
    permission check upstream.

    Deleting rows here goes through plain QuerySet.delete() calls, never
    through SurgeryUsedItemViewSet/SurgeryConsumptionItemViewSet or the
    Purchase DRF destroy() action — those are the paths that create
    *compensating* stock movements or block deletion outright for normal,
    single-row user edits. That behavior does not apply here: the Product
    itself is being destroyed, so there is nothing left to reverse or
    protect. PurchaseItem deletion still goes through the ORM (not raw
    SQL) specifically so the existing post_delete signal
    (inventory/signals.py) fires and keeps Purchase Finance Transactions
    in sync for every category that still has surviving items — purge()
    only has to handle the one gap that signal leaves: a category that
    lost *all* of its items (see _reconcile_vanished_categories).
    """

    @staticmethod
    def _affected_purchase_rows(product):
        """Purchases containing *product*, with pre/post-purge totals."""
        from inventory.models import Purchase, PurchaseItem

        purchase_ids = (
            PurchaseItem.objects.filter(product=product)
            .values_list("purchase_id", flat=True).distinct()
        )
        rows = []
        for purchase in Purchase.objects.filter(pk__in=purchase_ids):
            items = list(purchase.items.select_related("product").all())
            current_total = sum((i.effective_total for i in items), Decimal("0"))
            remaining = [i for i in items if i.product_id != product.pk]
            new_total = sum((i.effective_total for i in remaining), Decimal("0"))
            rows.append({
                "id": purchase.pk,
                "reference_number": purchase.reference_number,
                "status": purchase.status,
                "current_total": current_total,
                "new_total": new_total,
                "will_be_emptied": len(remaining) == 0,
            })
        return rows

    @staticmethod
    def preview(product) -> dict:
        """Read-only dependency-graph snapshot shown on the confirmation page.

        Recomputes everything from the database on every call — never
        trust a client-provided count (see purge(), which recomputes this
        again inside the final transaction before touching anything).
        """
        from inventory.models import ProductVendor, PurchaseItem, StockMovement
        from surgeries.models import SurgeryConsumptionItem, SurgeryUsedItem

        used_items_qs = SurgeryUsedItem.objects.filter(product=product)
        consumption_items_qs = SurgeryConsumptionItem.objects.filter(product=product)
        purchase_items_qs = PurchaseItem.objects.filter(product=product)

        return {
            "product": {
                "id": product.pk,
                "internal_code": product.internal_code,
                "name": product.name,
                "product_type": product.get_product_type_display(),
                "current_stock": product.current_stock,
            },
            "stock_movements_count": StockMovement.objects.filter(product=product).count(),
            "surgery_used_items_count": used_items_qs.count(),
            "affected_surgery_history_count": (
                used_items_qs.values("surgery_id").distinct().count()
            ),
            "surgery_consumption_items_count": consumption_items_qs.count(),
            "affected_legacy_surgery_count": (
                consumption_items_qs.values("surgery_id").distinct().count()
            ),
            "purchase_items_count": purchase_items_qs.count(),
            "affected_purchases": ProductPurgeService._affected_purchase_rows(product),
            "product_vendor_count": ProductVendor.objects.filter(product=product).count(),
        }

    @staticmethod
    def _reconcile_vanished_categories(purchase) -> None:
        """Cancel the expense Transaction for any product_type category that
        lost every one of its PurchaseItems.

        PurchaseFinanceService.sync_purchase_expenses() (already triggered
        automatically by the post_delete signal on PurchaseItem) only
        updates categories present in the *surviving* items — a category
        that disappeared entirely is never visited, so its old Transaction
        would otherwise keep showing a stale amount. Reuses the same
        "cancel, never delete" convention sync_purchase_expenses already
        uses for a fully-cancelled purchase, applied per-category instead.
        """
        from django.contrib.contenttypes.models import ContentType

        from finance.models import Transaction, TransactionPaymentStatus, TransactionType
        from finance.services import PurchaseFinanceService
        from inventory.models import ProductType, PurchaseStatus

        if purchase.status != PurchaseStatus.CONFIRMED:
            return

        surviving_types = set(
            purchase.items.values_list("product__product_type", flat=True).distinct()
        )
        type_to_cat_name = {
            ProductType.MEDICINE: PurchaseFinanceService.MEDICINE_CATEGORY_NAME,
            ProductType.EQUIPMENT: PurchaseFinanceService.EQUIPMENT_CATEGORY_NAME,
        }
        stale_cat_names = [
            name for ptype, name in type_to_cat_name.items()
            if ptype not in surviving_types
        ]
        if not stale_cat_names:
            return

        purchase_ct = ContentType.objects.get_for_model(purchase)
        Transaction.objects.filter(
            content_type=purchase_ct,
            object_id=purchase.pk,
            transaction_type=TransactionType.EXPENSE,
            category__name__in=stale_cat_names,
        ).exclude(
            payment_status=TransactionPaymentStatus.CANCELLED,
        ).update(payment_status=TransactionPaymentStatus.CANCELLED)

    @staticmethod
    def _log_purge(user, product_repr: dict, summary: dict) -> None:
        """Record the purge in Django's built-in admin LogEntry.

        Uses content_type + object_id (a plain integer column, not an FK)
        exactly like every other admin deletion — so the audit row is
        still valid and readable after the Product row it refers to is
        gone, with no required FK to a now-deleted Product.
        """
        from django.contrib.admin.models import DELETION, LogEntry
        from django.contrib.contenttypes.models import ContentType

        from inventory.models import Product

        message = (
            f"حذف کامل محصول «{product_repr['name']}» (کد {product_repr['internal_code']}). "
            f"{summary['surgery_used_items_deleted']} قلم مصرف تاریخچه عمل، "
            f"{summary['surgery_consumption_items_deleted']} قلم مصرف عمل (قدیمی)، "
            f"{summary['stock_movements_deleted']} حرکت انبار، "
            f"{summary['purchase_items_deleted']} ردیف خرید و "
            f"{summary['product_vendors_deleted']} ارتباط فروشنده حذف شد. "
            f"خریدهای لغوشده: {summary['purchases_cancelled'] or '—'}. "
            f"خریدهای بازمحاسبه‌شده: {summary['purchases_recalculated'] or '—'}."
        )
        LogEntry.objects.log_action(
            user_id=user.pk,
            content_type_id=ContentType.objects.get_for_model(Product).pk,
            object_id=product_repr["id"],
            object_repr=f"{product_repr['internal_code']} — {product_repr['name']}",
            action_flag=DELETION,
            change_message=message,
        )

    @staticmethod
    @transaction.atomic
    def purge(product, user) -> dict:
        """Permanently delete *product* and every row that exists only
        because of it, synchronizing every Purchase/Finance record its
        removal touches. Atomic: any failure rolls back everything — the
        Product, its history, and every recalculated total are left
        exactly as they were before the call.

        Re-fetches *product* with select_for_update() and recomputes the
        whole dependency graph itself rather than trusting counts computed
        by an earlier preview() call, so a stale confirmation page can
        never apply against a dependency graph that has since changed.
        """
        from django.core.exceptions import PermissionDenied
        from django.db import connection

        from accounts.permissions import is_main_administrator
        from inventory.models import (
            Product,
            ProductVendor,
            Purchase,
            PurchaseItem,
            PurchaseStatus,
            StockMovement,
        )
        from surgeries.models import SurgeryConsumptionItem, SurgeryUsedItem

        if not is_main_administrator(user):
            raise PermissionDenied(
                "فقط مدیر اصلی سامانه می‌تواند محصول را به‌طور کامل حذف کند."
            )

        product_qs = Product.objects.filter(pk=product.pk)
        if connection.features.has_select_for_update:
            product_qs = product_qs.select_for_update()
        product = product_qs.get()

        product_repr = {
            "id": product.pk,
            "internal_code": product.internal_code,
            "name": product.name,
        }

        # Snapshot + lock affected Purchases up front so a concurrent edit
        # can't slip in between the item deletions below and the
        # recalculation pass that reads purchase.items afterward.
        affected_purchase_ids = list(
            PurchaseItem.objects.filter(product=product)
            .values_list("purchase_id", flat=True).distinct()
        )
        purchase_lock_qs = Purchase.objects.filter(pk__in=affected_purchase_ids)
        if connection.features.has_select_for_update:
            purchase_lock_qs = purchase_lock_qs.select_for_update()
        list(purchase_lock_qs)

        # ── Surgery consumed-item history (new SurgeryHistory workflow) ──
        # Deleted via a plain QuerySet.delete() — NOT through
        # SurgeryUsedItemViewSet.perform_destroy(), which calls
        # SurgeryInventoryService.reverse_consumption() to create a
        # compensating IN movement for a normal single-row user delete.
        # That would be wrong here: the Product is being destroyed, its
        # StockMovements are all being deleted below anyway, and there is
        # no requirement to "restore" stock for a Product that no longer
        # exists. SurgeryUsedItem has no delete signal of its own, so a
        # direct QuerySet delete is the correct, minimal action.
        affected_surgery_history_ids = list(
            SurgeryUsedItem.objects.filter(product=product)
            .values_list("surgery_id", flat=True).distinct()
        )
        surgery_used_items_deleted = SurgeryUsedItem.objects.filter(product=product).count()
        SurgeryUsedItem.objects.filter(product=product).delete()

        # ── Surgery consumed-item history (legacy Surgery workflow) ──
        # SurgeryConsumptionItem has no reversal-on-delete behavior at all
        # (SurgeryConsumptionItemViewSet has no perform_destroy override),
        # so a direct delete matches its normal deletion semantics exactly.
        affected_legacy_surgery_ids = list(
            SurgeryConsumptionItem.objects.filter(product=product)
            .values_list("surgery_id", flat=True).distinct()
        )
        consumption_items_deleted = SurgeryConsumptionItem.objects.filter(product=product).count()
        SurgeryConsumptionItem.objects.filter(product=product).delete()

        # ── Purchase items ──
        # Deleted per-row via the ORM (not a raw bulk query) so the
        # existing post_delete signal on PurchaseItem fires for each one,
        # re-running PurchaseFinanceService.sync_purchase_expenses() and
        # PriceService.recalculate_product_price() exactly as it already
        # does for a normal single-item delete — no separate sync call
        # needed here for categories that still have surviving items.
        purchase_items_deleted = PurchaseItem.objects.filter(product=product).count()
        PurchaseItem.objects.filter(product=product).delete()

        # ── Stock movements ──
        # StockMovement is normally append-only (see its docstring), but
        # that convention exists to protect a *surviving* Product's audit
        # trail. Once the Product itself is gone the trail is meaningless,
        # so this is a deliberate, scoped exception to that rule.
        stock_movements_deleted = StockMovement.objects.filter(product=product).count()
        StockMovement.objects.filter(product=product).delete()

        # ── ProductVendor / price history ──
        # on_delete=CASCADE — removed automatically by product.delete()
        # below. Counted here only for the audit summary.
        product_vendor_count = ProductVendor.objects.filter(product=product).count()

        # ── Reconcile every affected Purchase now that its items are final ──
        purchases_cancelled = []
        purchases_recalculated = []
        for purchase in Purchase.objects.filter(pk__in=affected_purchase_ids):
            if not purchase.items.exists():
                # Emptied by the purge — cancel through the canonical
                # Purchase service rather than leaving a zero-item Purchase
                # with a stale total. all_items is empty by this point, so
                # cancel()'s stock-reversal loop is a correct no-op even
                # for a CONFIRMED purchase — there is nothing left to
                # reverse, and Section 7 explicitly does not require
                # restoring the purged Product's own stock.
                if purchase.status != PurchaseStatus.CANCELLED:
                    purchase.cancel()
                purchases_cancelled.append(purchase.pk)
            else:
                # Still has other items — the post_delete signal above
                # already recalculated surviving categories; only the
                # fully-vanished-category gap needs explicit handling.
                ProductPurgeService._reconcile_vanished_categories(purchase)
                purchases_recalculated.append(purchase.pk)

        product.delete()

        summary = {
            **product_repr,
            "surgery_used_items_deleted": surgery_used_items_deleted,
            "affected_surgery_history_ids": affected_surgery_history_ids,
            "surgery_consumption_items_deleted": consumption_items_deleted,
            "affected_legacy_surgery_ids": affected_legacy_surgery_ids,
            "stock_movements_deleted": stock_movements_deleted,
            "purchase_items_deleted": purchase_items_deleted,
            "product_vendors_deleted": product_vendor_count,
            "purchases_cancelled": purchases_cancelled,
            "purchases_recalculated": purchases_recalculated,
        }

        ProductPurgeService._log_purge(user, product_repr, summary)

        return summary
