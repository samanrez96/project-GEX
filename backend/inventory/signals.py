"""Inventory signal handlers.

Purchase → finance expense sync:
  Any time a Purchase is saved (status change to CONFIRMED/CANCELLED) or a
  PurchaseItem belonging to a confirmed purchase changes, the related expense
  Transactions in the finance module are created/updated/cancelled.

Purchase → product price sync:
  Any time a PurchaseItem is saved or deleted, Product.purchase_price is
  recalculated from the latest non-cancelled PurchaseItem for that product.
  This covers API creates, API updates, API deletes, and direct DB saves.
  Admin formset saves are additionally handled in PurchaseAdmin.save_related()
  to ensure the correct final state after the entire formset is persisted.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from inventory.models import Purchase, PurchaseItem


@receiver(post_save, sender=Purchase)
def on_purchase_saved(sender, instance, **kwargs):
    """Sync expense Transactions whenever a Purchase is saved."""
    from finance.services import PurchaseFinanceService
    PurchaseFinanceService.sync_purchase_expenses(instance)


@receiver(post_save, sender=PurchaseItem)
def on_purchase_item_saved(sender, instance, **kwargs):
    """Re-sync purchase expenses and recalculate product price when a line item
    is added or updated."""
    from finance.services import PurchaseFinanceService
    from inventory.services import PriceService
    try:
        purchase = instance.purchase
    except Exception:
        return
    PurchaseFinanceService.sync_purchase_expenses(purchase)
    PriceService.recalculate_product_price(instance.product_id)


@receiver(post_delete, sender=PurchaseItem)
def on_purchase_item_deleted(sender, instance, **kwargs):
    """Re-sync purchase expenses and recalculate product price when a line item
    is removed."""
    from finance.services import PurchaseFinanceService
    from inventory.services import PriceService
    try:
        # purchase may already be deleted (cascade); guard against that
        purchase = Purchase.objects.get(pk=instance.purchase_id)
    except Purchase.DoesNotExist:
        return
    PurchaseFinanceService.sync_purchase_expenses(purchase)
    PriceService.recalculate_product_price(instance.product_id)
