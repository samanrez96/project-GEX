from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.permissions import is_main_administrator
from inventory.models import Product
from inventory.services import ProductPurgeService

_PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _fa_digits(n):
    return str(n).translate(_PERSIAN_DIGITS)


def product_purge_view(request, product_id):
    """Superuser-only impact preview + confirmed permanent deletion of a Product.

    Replaces Django's default protected-delete page (which is unusable here —
    Product has four PROTECT relations, see ProductPurgeService's docstring)
    with a page that shows exactly what will be removed/recalculated and
    requires the internal_code to be typed back before anything happens.

    GET  — render the dependency preview (no writes).
    POST — verify the typed confirmation code, then call
           ProductPurgeService.purge() inside its own atomic transaction.
    """
    if not is_main_administrator(request.user):
        raise PermissionDenied('فقط مدیر اصلی سامانه می‌تواند محصول را به‌طور کامل حذف کند.')

    product = get_object_or_404(Product, pk=product_id)

    if request.method == 'POST':
        confirmation = (request.POST.get('confirmation_code') or '').strip()
        if confirmation != product.internal_code:
            messages.error(
                request,
                'کد داخلی وارد شده مطابقت ندارد. برای حذف کامل، کد داخلی محصول را دقیقاً وارد کنید.',
            )
            return redirect('admin:inventory_product_purge', product_id=product.pk)

        try:
            summary = ProductPurgeService.purge(product, request.user)
        except (ValidationError, PermissionDenied) as exc:
            message = '؛ '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            messages.error(request, f'حذف محصول ممکن نشد: {message}')
            return redirect('admin:inventory_product_purge', product_id=product.pk)

        messages.success(
            request,
            (
                f"محصول با موفقیت حذف شد. "
                f"{_fa_digits(summary['surgery_used_items_deleted'] + summary['surgery_consumption_items_deleted'])} قلم مصرفی، "
                f"{_fa_digits(summary['stock_movements_deleted'])} حرکت موجودی و "
                f"{_fa_digits(summary['purchase_items_deleted'])} ردیف خرید پاک شد "
                f"و مبالغ مالی مرتبط به‌روزرسانی شدند."
            ),
        )
        return redirect('admin:inventory_product_changelist')

    from django.contrib import admin

    preview = ProductPurgeService.preview(product)
    context = {
        **admin.site.each_context(request),
        'original': product,
        'opts': Product._meta,
        'app_label': Product._meta.app_label,
        'preview': preview,
        'changelist_url': reverse('admin:inventory_product_changelist'),
        'purge_url': reverse('admin:inventory_product_purge', args=[product.pk]),
    }
    return render(request, 'admin/inventory/product/purge_confirmation.html', context)
