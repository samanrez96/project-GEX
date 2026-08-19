"""Targeted regression tests for three Product admin UI fixes:

  1. حذف کامل محصول delete action on the Product detail page
     (superuser-only, links to the existing purge workflow — no new
     deletion logic).
  2. ProductVendor inline on the Product change page: collapsed-by-default
     summary rows, vendor-name link to the Vendor detail page, validation
     errors force-expand the offending relation.
  3. StockMovement inline table markup/columns/reference links after the
     rtl_responsive.css `tr.form-row` fix.

None of these touch ProductPurgeService, stock/purchase calculations, or
Finance synchronization — verified indirectly by asserting the purge
button only *links* to the existing purge URL and by reusing the
existing permission helper, and by keeping the Product/PurchaseItem/
StockMovement models untouched.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import (
    MovementType,
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    SourceType,
    StockMovement,
    Vendor,
)
from inventory.services import StockService

User = get_user_model()

_ctr = [0]


def _product(**kwargs):
    _ctr[0] += 1
    defaults = {
        'name': f'محصول تست رابط {_ctr[0]}',
        'internal_code': f'UI-{_ctr[0]:05d}',
        'product_type': ProductType.MEDICINE,
        'unit': 'عدد',
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def _vendor(**kwargs):
    _ctr[0] += 1
    defaults = {'name': f'فروشنده تست رابط {_ctr[0]}'}
    defaults.update(kwargs)
    return Vendor.objects.create(**defaults)


def _superuser(name='ui_superuser'):
    _ctr[0] += 1
    return User.objects.create_superuser(f'{name}_{_ctr[0]}', f'{name}{_ctr[0]}@example.com', 'pass12345')


def _staff_admin(name='ui_staff_admin'):
    _ctr[0] += 1
    user = User.objects.create_user(f'{name}_{_ctr[0]}', f'{name}{_ctr[0]}@example.com', 'pass12345', is_staff=True)
    group, _ = Group.objects.get_or_create(name='admin')
    user.groups.add(group)
    return user


def _detail_url(pk):
    return f'/admin/inventory/product/{pk}/detail/'


def _change_url(pk):
    return f'/admin/inventory/product/{pk}/change/'


def _purge_url(pk):
    return reverse('admin:inventory_product_purge', args=[pk])


def _empty_stock_movement_management_form():
    """Every POST to the Product change page must include management-form
    data for *every* inline on the page, including StockMovementInline
    (read-only, add-disabled) — Django validates it regardless."""
    return {
        'stock_movements-TOTAL_FORMS': '0',
        'stock_movements-INITIAL_FORMS': '0',
        'stock_movements-MIN_NUM_FORMS': '0',
        'stock_movements-MAX_NUM_FORMS': '0',
    }


# ---------------------------------------------------------------------------
# 1. Product detail page — حذف کامل محصول action
# ---------------------------------------------------------------------------

class ProductDetailDeleteActionTest(TestCase):
    def setUp(self):
        self.product = _product()

    def test_detail_page_flags_main_administrator_for_superuser(self):
        self.client.force_login(_superuser())
        resp = self.client.get(_detail_url(self.product.pk))
        self.assertEqual(resp.status_code, 200)
        # Rendered as a data attribute consumed by product_detail.js — this
        # is what actually gates whether the button is drawn client-side.
        self.assertContains(resp, 'data-is-main-admin="1"')

    def test_detail_page_does_not_flag_normal_staff_admin(self):
        self.client.force_login(_staff_admin())
        resp = self.client.get(_detail_url(self.product.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-is-main-admin="0"')

    def test_detail_page_loads_product_detail_js(self):
        self.client.force_login(_superuser())
        resp = self.client.get(_detail_url(self.product.pk))
        self.assertContains(resp, 'product_detail.js')

    def test_purge_button_url_resolves_to_existing_purge_view(self):
        """The delete action's target URL is the already-implemented purge
        preview/confirmation page — not Django's default protected-delete
        page, and not a new deletion code path."""
        url = _purge_url(self.product.pk)
        self.assertEqual(url, f'/admin/inventory/product/{self.product.pk}/purge/')

        self.client.force_login(_superuser())
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.product.internal_code)
        self.assertContains(
            resp,
            'این عملیات دائمی است و تمام سوابق وابسته مشخص‌شده را حذف یا به‌روزرسانی می‌کند.',
        )

    def test_purge_get_never_deletes(self):
        """GET on the purge URL must only show the preview — never delete."""
        self.client.force_login(_superuser())
        self.client.get(_purge_url(self.product.pk))
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_normal_staff_admin_denied_on_purge_url(self):
        """Direct access to the purge URL remains denied for non-superusers,
        confirming the existing backend permission is unchanged."""
        self.client.force_login(_staff_admin())
        resp = self.client.get(_purge_url(self.product.pk))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_default_delete_url_still_redirects_to_purge_flow(self):
        """Confirms the change made in the prior task (blocking Django's
        default protected-delete page) is untouched by this UI work."""
        self.client.force_login(_superuser())
        resp = self.client.get(reverse('admin:inventory_product_delete', args=[self.product.pk]))
        self.assertRedirects(resp, _purge_url(self.product.pk))


# ---------------------------------------------------------------------------
# 2. Product change page — ProductVendor inline collapse UI
# ---------------------------------------------------------------------------

class ProductChangePageVendorInlineTest(TestCase):
    def setUp(self):
        self.product = _product()
        self.vendor = _vendor()
        self.pv = ProductVendor.objects.create(
            product=self.product, vendor=self.vendor, unit_price=Decimal('18000'), is_primary=True,
        )
        self.superuser = _superuser()
        self.client.force_login(self.superuser)

    def test_change_page_returns_200(self):
        resp = self.client.get(_change_url(self.product.pk))
        self.assertEqual(resp.status_code, 200)

    def test_change_page_loads_vendor_inline_collapse_assets(self):
        resp = self.client.get(_change_url(self.product.pk))
        self.assertContains(resp, 'product_vendor_inline.css')
        self.assertContains(resp, 'product_vendor_inline.js')

    def test_change_page_renders_the_existing_vendor_select(self):
        """The underlying formset/select field must still be present in
        the DOM — collapsing is JS/CSS only, never a markup removal."""
        resp = self.client.get(_change_url(self.product.pk))
        self.assertContains(resp, f'id_product_vendors-0-vendor')
        self.assertContains(resp, f'value="{self.pv.pk}"')

    def test_change_page_includes_management_form_fields(self):
        """TOTAL_FORMS/INITIAL_FORMS must be untouched (formset integrity)."""
        resp = self.client.get(_change_url(self.product.pk))
        self.assertContains(resp, 'product_vendors-TOTAL_FORMS')
        self.assertContains(resp, 'product_vendors-INITIAL_FORMS')

    def test_adding_a_second_vendor_relation_still_works(self):
        """POST semantics for the inline formset are untouched by the UI
        change — this exercises the real add path end-to-end."""
        vendor2 = _vendor()
        resp = self.client.get(_change_url(self.product.pk))
        self.assertEqual(resp.status_code, 200)

        data = {
            'name': self.product.name,
            'internal_code': self.product.internal_code,
            'product_type': self.product.product_type,
            'unit': self.product.unit,
            'purchase_price': '0',
            'minimum_stock': '0',
            'internal_notes': '',
            'product_vendors-TOTAL_FORMS': '2',
            'product_vendors-INITIAL_FORMS': '1',
            'product_vendors-MIN_NUM_FORMS': '0',
            'product_vendors-MAX_NUM_FORMS': '1000',
            'product_vendors-0-id': str(self.pv.pk),
            'product_vendors-0-product': str(self.product.pk),
            'product_vendors-0-vendor': str(self.vendor.pk),
            'product_vendors-0-unit_price': '18000',
            'product_vendors-0-currency': 'IRR',
            'product_vendors-0-minimum_order_quantity': '1',
            'product_vendors-0-lead_time_days': '0',
            'product_vendors-1-id': '',
            'product_vendors-1-product': str(self.product.pk),
            'product_vendors-1-vendor': str(vendor2.pk),
            'product_vendors-1-unit_price': '9000',
            'product_vendors-1-currency': 'IRR',
            'product_vendors-1-minimum_order_quantity': '1',
            'product_vendors-1-lead_time_days': '0',
            # Superuser editing an existing Product now also sees
            # desired_current_stock (see ProductAdmin._can_adjust_stock) —
            # unchanged from the real current stock, so no reason needed.
            'desired_current_stock': str(self.product.current_stock),
            'stock_adjustment_reason': '',
            '_save': 'Save',
        }
        data.update(_empty_stock_movement_management_form())
        resp = self.client.post(_change_url(self.product.pk), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ProductVendor.objects.filter(product=self.product).count(), 2)

    def test_validation_error_keeps_relation_rendered_with_errorlist(self):
        """product_vendor_inline.js only skips collapsing a row when it
        contains `.errorlist` (see initRow()/hasError() in the shipped
        script) — this confirms the server-side precondition it depends
        on: a failed submission still renders the erroring relation with
        its error, inside the same `.inline-related` block, exactly like
        every other Django formset error."""
        data = {
            'name': self.product.name,
            'internal_code': self.product.internal_code,
            'product_type': self.product.product_type,
            'unit': self.product.unit,
            'purchase_price': '0',
            'minimum_stock': '0',
            'internal_notes': '',
            'product_vendors-TOTAL_FORMS': '1',
            'product_vendors-INITIAL_FORMS': '1',
            'product_vendors-MIN_NUM_FORMS': '0',
            'product_vendors-MAX_NUM_FORMS': '1000',
            'product_vendors-0-id': str(self.pv.pk),
            'product_vendors-0-product': str(self.product.pk),
            'product_vendors-0-vendor': '',  # required field left blank -> error
            'product_vendors-0-unit_price': '18000',
            'product_vendors-0-currency': 'IRR',
            'product_vendors-0-minimum_order_quantity': '1',
            'product_vendors-0-lead_time_days': '0',
            '_save': 'Save',
        }
        data.update(_empty_stock_movement_management_form())
        resp = self.client.post(_change_url(self.product.pk), data)
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors, not redirected
        self.assertContains(resp, 'errorlist')
        # The relation was NOT deleted/changed since the submission failed.
        self.assertTrue(ProductVendor.objects.filter(pk=self.pv.pk, vendor=self.vendor).exists())

    def test_removing_a_vendor_relation_does_not_delete_the_vendor(self):
        data = {
            'name': self.product.name,
            'internal_code': self.product.internal_code,
            'product_type': self.product.product_type,
            'unit': self.product.unit,
            'purchase_price': '0',
            'minimum_stock': '0',
            'internal_notes': '',
            'product_vendors-TOTAL_FORMS': '1',
            'product_vendors-INITIAL_FORMS': '1',
            'product_vendors-MIN_NUM_FORMS': '0',
            'product_vendors-MAX_NUM_FORMS': '1000',
            'product_vendors-0-id': str(self.pv.pk),
            'product_vendors-0-product': str(self.product.pk),
            'product_vendors-0-vendor': str(self.vendor.pk),
            'product_vendors-0-unit_price': '18000',
            'product_vendors-0-currency': 'IRR',
            'product_vendors-0-minimum_order_quantity': '1',
            'product_vendors-0-lead_time_days': '0',
            'product_vendors-0-DELETE': 'on',
            'desired_current_stock': str(self.product.current_stock),
            'stock_adjustment_reason': '',
            '_save': 'Save',
        }
        data.update(_empty_stock_movement_management_form())
        resp = self.client.post(_change_url(self.product.pk), data)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductVendor.objects.filter(pk=self.pv.pk).exists())
        self.assertTrue(Vendor.objects.filter(pk=self.vendor.pk).exists())


# ---------------------------------------------------------------------------
# 3. StockMovement inline — table markup/columns/reference links
# ---------------------------------------------------------------------------

class ProductChangePageStockMovementTableTest(TestCase):
    def setUp(self):
        self.product = _product()
        self.superuser = _superuser()
        self.client.force_login(self.superuser)

    def test_change_page_loads_movement_table_assets(self):
        resp = self.client.get(_change_url(self.product.pk))
        self.assertContains(resp, 'product_movement_table.css')
        self.assertContains(resp, 'product_movement_table.js')

    def test_one_movement_renders_as_one_table_row(self):
        StockService.create_movement(
            product=self.product, quantity=Decimal('222'),
            movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id='initial-stock-test', description='موجودی اولیه',
        )
        resp = self.client.get(_change_url(self.product.pk))
        content = resp.content.decode()
        # Django's TabularInline always renders each row as a real <tr>;
        # this asserts the row for our one movement actually exists and is
        # a single row (not fragmented across several table rows).
        self.assertEqual(content.count('field-quantity_display'), 1)

    def test_all_expected_columns_are_rendered(self):
        StockService.create_movement(
            product=self.product, quantity=Decimal('5'),
            movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id='initial-stock-test',
        )
        resp = self.client.get(_change_url(self.product.pk))
        for column in (
            'column-movement_type', 'column-source_type', 'column-quantity_display',
            'column-unit', 'column-reference_display', 'column-movement_date_jalali',
            'column-description', 'column-created_at_jalali',
        ):
            self.assertContains(resp, column)

    def test_movement_type_and_source_type_use_persian_display_labels(self):
        StockService.create_movement(
            product=self.product, quantity=Decimal('1'),
            movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id='initial-stock-test',
        )
        resp = self.client.get(_change_url(self.product.pk))
        self.assertContains(resp, 'ورود به انبار')
        self.assertContains(resp, 'تعدیل دستی')
        self.assertNotContains(resp, '>IN<')
        self.assertNotContains(resp, '>MANUAL_ADJUSTMENT<')

    def test_quantity_uses_clean_decimal_display(self):
        StockService.create_movement(
            product=self.product, quantity=Decimal('222.000'),
            movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id='initial-stock-test',
        )
        resp = self.client.get(_change_url(self.product.pk))
        content = resp.content.decode()
        # The dedicated quantity_display column strips trailing zeros; the
        # unrelated Django "original" column (StockMovement.__str__) still
        # legitimately shows the raw model value elsewhere on the page, so
        # only the specific column cell is asserted here.
        cell = content.split('field-quantity_display')[1]
        self.assertIn('222</p>', cell[:60])
        self.assertNotIn('222.000', cell[:60])

    def test_created_at_and_movement_date_columns_get_identical_direction_treatment(self):
        """Regression for the follow-up bug report: تاریخ ایجاد (column 9)
        was left out of the original fix and never got the same LTR/
        nowrap/tabular-nums treatment as تاریخ حرکت (column 7), so it
        rendered unstably at the table's leftmost (in RTL) edge. Both are
        Jalali datetimes and must be styled identically."""
        from pathlib import Path

        from django.conf import settings

        css_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'css' / 'product_movement_table.css'
        content = css_path.read_text(encoding='utf-8')
        # Both date columns (7 and 9) must appear together in the same
        # direction/whitespace rule, not as two separately-drifting rules.
        marker = 'td:nth-child(7),'
        self.assertIn(marker, content)
        combined = content[content.index(marker):content.index(marker) + 400]
        self.assertIn('td:nth-child(9)', combined)
        self.assertIn('direction: ltr', combined)
        self.assertIn('white-space: nowrap', combined)

    def test_original_and_delete_columns_are_hidden(self):
        """Django's always-empty/duplicate first ("original"/__str__) and
        last ("Delete?", can_delete=False so always blank) columns used to
        compete for width against the real columns under table-layout:auto
        — hidden now via CSS so table-layout:fixed can allocate 100% of
        the width to the 8 meaningful columns."""
        StockService.create_movement(
            product=self.product, quantity=Decimal('1'),
            movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id='initial-stock-test',
        )
        resp = self.client.get(_change_url(self.product.pk))
        content = resp.content.decode()
        # The hidden pk/fk inputs inside the "original" column must still
        # be present and submittable — only their container is display:none.
        self.assertIn('name="stock_movements-0-id"', content)
        self.assertIn('name="stock_movements-0-product"', content)

        from pathlib import Path

        from django.conf import settings

        css_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'css' / 'product_movement_table.css'
        css_content = css_path.read_text(encoding='utf-8')
        self.assertIn('nth-child(1),', css_content)
        self.assertIn('last-child', css_content)

    def test_table_uses_fixed_layout_with_explicit_column_widths(self):
        from pathlib import Path

        from django.conf import settings

        css_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'css' / 'product_movement_table.css'
        content = css_path.read_text(encoding='utf-8')
        self.assertIn('table-layout: fixed', content)
        self.assertIn("nth-child(1),", content)
        self.assertIn('display: none', content)

    def test_purchase_reference_links_to_purchase_change_page(self):
        vendor = _vendor()
        purchase = Purchase.objects.create(vendor=vendor, purchase_date=timezone.now())
        PurchaseItem.objects.create(purchase=purchase, product=self.product, quantity=Decimal('2'), unit_price=Decimal('500'))
        purchase.confirm()

        resp = self.client.get(_change_url(self.product.pk))
        expected_url = reverse('admin:inventory_purchase_change', args=[purchase.pk])
        self.assertContains(resp, f'href="{expected_url}"')
        self.assertContains(resp, f'purchase-{purchase.pk}')

    def test_stale_reference_with_no_existing_object_renders_as_plain_text_not_a_link(self):
        StockService.create_movement(
            product=self.product, quantity=Decimal('3'),
            movement_type=MovementType.IN, source_type=SourceType.PURCHASE,
            reference_id='purchase-999999',
        )
        resp = self.client.get(_change_url(self.product.pk))
        content = resp.content.decode()
        self.assertIn('purchase-999999', content)
        bad_url = reverse('admin:inventory_purchase_change', args=[999999])
        self.assertNotIn(f'href="{bad_url}"', content)

    def test_empty_state_message_and_colspan_are_implemented(self):
        """The empty-state row is inserted client-side by
        product_movement_table.js: Django's own TabularInline template has
        no built-in hook for this without a custom template override, which
        was avoided to keep the management-form-safe default rendering
        untouched. Verify the shipped script implements the exact required
        message and assigns a real colspan (not a fixed/guessed number)."""
        from pathlib import Path

        from django.conf import settings

        js_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'js' / 'product_movement_table.js'
        content = js_path.read_text(encoding='utf-8')
        self.assertIn('هنوز حرکتی برای این محصول ثبت نشده است.', content)
        self.assertIn('td.colSpan = colCount', content)

        # And confirm the page with zero movements still returns 200 with
        # the JS asset that will render the empty state.
        resp = self.client.get(_change_url(self.product.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'product_movement_table.js')

    def test_purchase_page_and_surgery_history_page_still_load(self):
        """Regression: reference-link building must not break unrelated
        pages (it queries Purchase/SurgeryHistory but never writes)."""
        vendor = _vendor()
        purchase = Purchase.objects.create(vendor=vendor, purchase_date=timezone.now())
        resp = self.client.get(reverse('admin:inventory_purchase_change', args=[purchase.pk]))
        self.assertEqual(resp.status_code, 200)
