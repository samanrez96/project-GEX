"""Surgery services: inventory consumption and center commission finance sync.

SurgeryInventoryService — the single canonical entry point for every stock
change triggered by a SurgeryUsedItem (create / update / delete). Called
exclusively from SurgeryUsedItemViewSet — the admin page for this model is
locked to view-only (see SurgeryUsedItemAdmin) precisely so no second,
independent stock-mutation path can ever exist.

SurgeryFinanceService   — CenterCommissionIncome create/update when a
                          SurgeryHistory is saved, and the Doctor-fee
                          snapshot/expense created at finalization.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from surgeries.models import SurgeryStatus


class SurgeryInventoryService:
    """Service for inventory operations triggered by surgery events.

    consume_product()    — CREATE: one OUT movement for the full quantity.
    adjust_consumption()  — UPDATE: a compensating movement for the
                            difference only, or a full reverse+re-consume
                            pair when the product itself changed.
    reverse_consumption() — DELETE: one compensating IN/RETURN movement that
                            restores whatever quantity is passed in (the
                            item's current quantity by default).

    Every StockMovement created here is a new row — the original OUT
    movement from consume_product() is never edited or deleted, preserving
    StockMovement's append-only audit trail.
    """

    @staticmethod
    @transaction.atomic
    def consume_product(used_item) -> None:
        """Create an OUT StockMovement for a newly-saved SurgeryUsedItem.

        Called from SurgeryUsedItemViewSet.perform_create() after the item
        is saved, inside the same transaction.  Raises Django ValidationError
        if the product has insufficient stock — the caller converts it to a
        DRF ValidationError and the transaction is rolled back.

        Args:
            used_item: A saved SurgeryUsedItem instance.
        """
        from inventory.models import MovementType, SourceType
        from inventory.services import StockService

        surgery = used_item.surgery
        StockService.create_movement(
            product=used_item.product,
            quantity=used_item.quantity,
            movement_type=MovementType.OUT,
            source_type=SourceType.SURGERY_CONSUMPTION,
            reference_id=f"surgery-history-{surgery.pk}",
            description=(
                f"مصرف در عمل جراحی — {surgery.patient.full_name} "
                f"({surgery.surgery_type.name})"
            ),
            movement_date=surgery.surgery_date,
        )

    @staticmethod
    @transaction.atomic
    def reverse_consumption(used_item, quantity=None, product=None) -> None:
        """Create a compensating IN/RETURN movement that restores stock
        previously deducted for `used_item`.

        Defaults to reversing the item's current (quantity, product) — the
        right call when deleting/reversing an item outright. Callers
        reconciling a product change pass the OLD product explicitly (as a
        Product instance or PK — StockService.create_movement accepts
        either), since by the time this runs `used_item` may already carry
        the new product.

        Args:
            used_item: A saved SurgeryUsedItem instance (for surgery context
                       in the movement's description/reference_id).
            quantity:  Amount to restore; defaults to used_item.quantity.
            product:   Product (or PK) to credit; defaults to used_item.product.
        """
        from inventory.models import MovementType, SourceType
        from inventory.services import StockService

        if quantity is None:
            quantity = used_item.quantity
        if product is None:
            product = used_item.product
        if quantity <= 0:
            return

        surgery = used_item.surgery
        StockService.create_movement(
            product=product,
            quantity=quantity,
            movement_type=MovementType.IN,
            source_type=SourceType.RETURN,
            reference_id=f"surgery-history-{surgery.pk}",
            description=(
                f"برگشت مصرف در عمل جراحی — {surgery.patient.full_name} "
                f"({surgery.surgery_type.name})"
            ),
            movement_date=surgery.surgery_date,
        )

    @staticmethod
    @transaction.atomic
    def adjust_consumption(used_item, old_product_id, old_quantity) -> None:
        """Reconcile stock after a SurgeryUsedItem was changed from
        (old_product_id, old_quantity) to its current, already-saved
        (product, quantity).

        - Same product, quantity increased → OUT movement for the increase only.
        - Same product, quantity decreased → IN/RETURN movement for the decrease only.
        - Same product, quantity unchanged → no movement at all (e.g. only
          `description` changed).
        - Product changed                  → the old product is fully restored
          (IN/RETURN) and the new product is fully deducted (OUT via
          consume_product), both inside this one atomic transaction.

        Called from SurgeryUsedItemViewSet.perform_update() with the
        pre-update values captured before serializer.save() ran. Raises
        Django ValidationError if the net deduction would leave insufficient
        stock — the caller converts it to a DRF ValidationError and the
        whole transaction (including the SurgeryUsedItem field update)
        rolls back, so the row keeps its previous values.

        Calling this twice with the same old_product_id/old_quantity against
        an unchanged instance is a no-op the second time — nothing about the
        current row differs from what was already reconciled.
        """
        new_product_id = used_item.product_id
        new_quantity    = used_item.quantity

        if new_product_id == old_product_id:
            diff = new_quantity - old_quantity
            if diff == 0:
                return
            if diff > 0:
                from inventory.models import MovementType, SourceType
                from inventory.services import StockService

                surgery = used_item.surgery
                StockService.create_movement(
                    product=used_item.product,
                    quantity=diff,
                    movement_type=MovementType.OUT,
                    source_type=SourceType.SURGERY_CONSUMPTION,
                    reference_id=f"surgery-history-{surgery.pk}",
                    description=(
                        f"افزایش مصرف در عمل جراحی — {surgery.patient.full_name} "
                        f"({surgery.surgery_type.name})"
                    ),
                    movement_date=surgery.surgery_date,
                )
            else:
                SurgeryInventoryService.reverse_consumption(
                    used_item, quantity=-diff, product=used_item.product,
                )
        else:
            if old_quantity and old_quantity > 0:
                SurgeryInventoryService.reverse_consumption(
                    used_item, quantity=old_quantity, product=old_product_id,
                )
            SurgeryInventoryService.consume_product(used_item)


class SurgeryFinanceService:
    """Service for finance operations triggered by SurgeryHistory events."""

    @staticmethod
    def calculate_center_commission(surgery) -> Decimal:
        """Return the center commission amount for a SurgeryHistory.

        Priority: center_commission_amount > center_commission_percent > 0.
        Returns Decimal('0') when no commission is configured.
        """
        if surgery.center_commission_amount is not None:
            return Decimal(str(surgery.center_commission_amount))
        if surgery.center_commission_percent is not None:
            return (
                Decimal(str(surgery.amount))
                * Decimal(str(surgery.center_commission_percent))
                / Decimal('100')
            )
        return Decimal('0')

    @staticmethod
    @transaction.atomic
    def sync_center_commission_income(surgery) -> None:
        """Create or update the CenterCommissionIncome for a SurgeryHistory.

        Idempotent — calling this multiple times for the same surgery always
        results in exactly one income record (status=CONFIRMED) or a cancelled
        record if the calculated income is zero.

        Called from SurgeryHistoryViewSet.perform_create/perform_update so
        that surgery save + income sync happen in the same atomic transaction.
        """
        from finance.models import CenterCommissionIncome, IncomeStatus

        center_income = SurgeryFinanceService.calculate_center_commission(surgery)

        try:
            income = CenterCommissionIncome.objects.get(surgery=surgery)
        except CenterCommissionIncome.DoesNotExist:
            income = None

        if center_income > 0:
            description = (
                f"درآمد کمیسیون مرکز برای عمل جراحی #{surgery.pk} "
                f"— {surgery.patient.full_name}"
            )
            if income is None:
                CenterCommissionIncome.objects.create(
                    surgery=surgery,
                    amount=center_income,
                    status=IncomeStatus.CONFIRMED,
                    description=description,
                    income_date=surgery.surgery_date,
                )
            else:
                income.amount      = center_income
                income.status      = IncomeStatus.CONFIRMED
                income.description = description
                income.income_date = surgery.surgery_date
                income.save(update_fields=['amount', 'status', 'description', 'income_date', 'updated_at'])
        else:
            # Calculated income is zero: cancel existing record if present.
            if income is not None and income.status != IncomeStatus.CANCELLED:
                income.status = IncomeStatus.CANCELLED
                income.save(update_fields=['status', 'updated_at'])

    @staticmethod
    @transaction.atomic
    def sync_doctor_fee_expense(surgery) -> None:
        """Create the permanent Doctor-fee snapshot/expense when a Surgery
        becomes finalized (status=COMPLETED), using the exact
        DoctorSurgeryRate for (clinical_doctor, surgery_type).

        - Idempotent: once a DoctorFeeExpense exists for this surgery, its
          amount/doctor/surgery_type are never recalculated or overwritten
          on subsequent saves — it is a permanent historical record.
        - Blocks finalization: raises django.core.exceptions.ValidationError
          if status is COMPLETED, a doctor is assigned, and no exact
          DoctorSurgeryRate exists for that (doctor, surgery_type) pair.
          Callers (the DRF ViewSet) convert this to a 400 response; the
          admin path is separately guarded by SurgeryHistory.clean().
        - Cancellation: if the surgery is CANCELLED after a snapshot already
          exists, the snapshot (and its mirrored finance Transaction) is
          marked CANCELLED rather than deleted, preserving audit history.
          Any other non-COMPLETED status is a no-op once a snapshot exists.
        """
        from contacts.services import DoctorRateService
        from finance.models import DoctorFeeExpense, IncomeStatus

        try:
            existing = DoctorFeeExpense.objects.get(surgery=surgery)
        except DoctorFeeExpense.DoesNotExist:
            existing = None

        if existing is not None:
            if surgery.status == SurgeryStatus.CANCELLED and existing.status != IncomeStatus.CANCELLED:
                existing.status = IncomeStatus.CANCELLED
                existing.save(update_fields=['status', 'updated_at'])
            return  # permanent snapshot — never recomputed once created

        if surgery.status != SurgeryStatus.COMPLETED:
            return  # not finalized yet — nothing to snapshot

        if not surgery.clinical_doctor_id:
            return  # no doctor assigned — nothing to finalize against

        rate = DoctorRateService.get_rate(surgery.clinical_doctor, surgery.surgery_type)
        if rate is None:
            raise ValidationError(
                'برای تکمیل این عمل، نرخ پزشک برای این نوع عمل ثبت نشده است.'
            )

        DoctorFeeExpense.objects.create(
            surgery=surgery,
            doctor=surgery.clinical_doctor,
            surgery_type=surgery.surgery_type,
            amount=rate,
            status=IncomeStatus.CONFIRMED,
            description=(
                f"حق‌الزحمه پزشک برای عمل جراحی #{surgery.pk} — {surgery.patient.full_name}"
            ),
            fee_date=surgery.surgery_date,
        )
