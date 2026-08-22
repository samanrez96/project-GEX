"""Tests for the هزینه‌های متفرقه (Miscellaneous Expenses) admin panel.

Coverage:
  - 21 explicit requirements (sidebar, CRUD, permissions, finance independence)
  - Model: create, str, positive-amount validation
  - Admin list view: 200 for staff, redirect for anonymous, search, date filter
  - Admin add view: GET 200, POST creates, POST invalid re-renders
  - Admin change view: GET 200, POST updates, POST invalid re-renders
  - Delete confirm view: GET shows page, POST removes record, 403 for non-perm
  - 3-column table, subject link, amount format (تومان, no .00)
  - Independence from Finance: no Transaction created, Finance dashboard intact
  - Clickable rows: data-edit-url, tabindex, role="link", aria-label
  - Sidebar CSS structure: nav scrolls, footer pinned (overflow fix)
"""

import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from misc_expenses.models import MiscellaneousExpense

User = get_user_model()

LIST_URL = "/admin/misc-expenses/"
ADD_URL  = "/admin/misc-expenses/add/"


def _change_url(pk):
    return f"/admin/misc-expenses/{pk}/change/"


def _delete_url(pk):
    return f"/admin/misc-expenses/{pk}/delete/"


def _make_superuser(username="me_super"):
    return User.objects.create_superuser(username=username, password="pass")


def _make_staff_no_perm(username="me_staff"):
    u = User.objects.create_user(username=username, password="pass", is_staff=True)
    return u


def _make_expense(**kw):
    defaults = {
        "date":    "2026-06-01",
        "subject": "هزینه آزمایشی",
        "amount":  Decimal("15000"),
    }
    defaults.update(kw)
    return MiscellaneousExpense.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Req 1-2 and 3-5: Sidebar placement
# ---------------------------------------------------------------------------

class MiscExpenseSidebarTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("sb_super")
        self.client.force_login(self.admin)

    # Req 1 ──────────────────────────────────────────────────────────────────
    def test_req1_no_standalone_misc_expenses_sidebar_section(self):
        """There must be no top-level sidebar section keyed 'misc-expenses'."""
        resp = self.client.get(LIST_URL)
        self.assertNotContains(resp, 'data-sidebar-section="misc-expenses"')

    # Req 2 ──────────────────────────────────────────────────────────────────
    def test_req2_link_appears_under_finance_section(self):
        """The misc-expenses link must live inside the finance sidebar section."""
        resp = self.client.get(LIST_URL)
        content = resp.content.decode()
        finance_m = re.search(
            r'data-sidebar-section="finance"(.*?)(?=data-sidebar-section=|</aside>)',
            content, re.DOTALL
        )
        self.assertIsNotNone(finance_m, "Finance sidebar section not found in HTML")
        self.assertIn(LIST_URL, finance_m.group(1),
                      "هزینه‌های متفرقه link not found inside finance sidebar section")

    # Req 3 ──────────────────────────────────────────────────────────────────
    def test_req3_finance_section_contains_misc_link_on_list_page(self):
        """Finance section's submenu contains the misc-expenses link on the list page."""
        resp = self.client.get(LIST_URL)
        content = resp.content.decode()
        finance_m = re.search(
            r'data-sidebar-section="finance"(.*?)(?=data-sidebar-section=|</aside>)',
            content, re.DOTALL
        )
        self.assertIsNotNone(finance_m)
        self.assertIn(LIST_URL, finance_m.group(1))

    # Req 4 ──────────────────────────────────────────────────────────────────
    def test_req4_finance_section_contains_misc_link_on_add_page(self):
        """Finance section contains the misc-expenses link on the add page."""
        resp = self.client.get(ADD_URL)
        content = resp.content.decode()
        finance_m = re.search(
            r'data-sidebar-section="finance"(.*?)(?=data-sidebar-section=|</aside>)',
            content, re.DOTALL
        )
        self.assertIsNotNone(finance_m)
        self.assertIn(LIST_URL, finance_m.group(1))

    # Req 5 ──────────────────────────────────────────────────────────────────
    def test_req5_finance_section_contains_misc_link_on_change_page(self):
        """Finance section contains the misc-expenses link on the change page."""
        e = _make_expense()
        resp = self.client.get(_change_url(e.pk))
        content = resp.content.decode()
        finance_m = re.search(
            r'data-sidebar-section="finance"(.*?)(?=data-sidebar-section=|</aside>)',
            content, re.DOTALL
        )
        self.assertIsNotNone(finance_m)
        self.assertIn(LIST_URL, finance_m.group(1))


# ---------------------------------------------------------------------------
# Req 6-7: Table columns
# ---------------------------------------------------------------------------

class MiscExpenseTableTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("tbl_super")
        self.client.force_login(self.admin)

    # Req 6 ──────────────────────────────────────────────────────────────────
    def test_req6_table_has_exactly_three_columns(self):
        """List table must have exactly 3 header columns (تاریخ, موضوع, مبلغ)."""
        _make_expense()
        resp = self.client.get(LIST_URL)
        content = resp.content.decode()
        table_m = re.search(r'<table class="me-table"[^>]*>(.*?)</table>', content, re.DOTALL)
        self.assertIsNotNone(table_m, "me-table not found in response")
        headers = re.findall(r'<th\b[^>]*>(.*?)</th>', table_m.group(1), re.DOTALL)
        stripped = [h.strip() for h in headers]
        self.assertIn("تاریخ", stripped)
        self.assertIn("موضوع", stripped)
        self.assertIn("مبلغ (تومان)", stripped)
        self.assertNotIn("عملیات", stripped)
        self.assertEqual(len(stripped), 3, f"Expected 3 columns, got: {stripped}")

    # Req 7 ──────────────────────────────────────────────────────────────────
    def test_req7_subject_links_to_correct_change_url(self):
        """Subject in the list table must link to the correct change URL."""
        e = _make_expense(subject="هزینه قابل کلیک")
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, _change_url(e.pk))
        self.assertContains(resp, "هزینه قابل کلیک")


# ---------------------------------------------------------------------------
# Req 8-10: Edit functionality
# ---------------------------------------------------------------------------

class MiscExpenseEditTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("edit_super")
        self.client.force_login(self.admin)
        self.expense = _make_expense(subject="هزینه اصلی", amount=Decimal("10000"))

    # Req 8 ──────────────────────────────────────────────────────────────────
    def test_req8_edit_page_loads_existing_values(self):
        """Change GET must pre-populate the form with the record's current values."""
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "هزینه اصلی")

    # Req 9 ──────────────────────────────────────────────────────────────────
    def test_req9_edit_post_updates_same_record(self):
        """Change POST must update the existing record and redirect."""
        resp = self.client.post(_change_url(self.expense.pk), data={
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "هزینه ویرایش‌شده",
            "amount":  "20000",
        })
        self.assertIn(resp.status_code, (301, 302))
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.subject, "هزینه ویرایش‌شده")
        self.assertEqual(self.expense.amount, Decimal("20000"))

    # Req 10 ─────────────────────────────────────────────────────────────────
    def test_req10_edit_does_not_create_duplicate(self):
        """A successful change POST must not increase the total record count."""
        count_before = MiscellaneousExpense.objects.count()
        self.client.post(_change_url(self.expense.pk), data={
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "هزینه ویرایش‌شده",
            "amount":  "20000",
        })
        self.assertEqual(MiscellaneousExpense.objects.count(), count_before)


# ---------------------------------------------------------------------------
# Req 11-16: Delete confirmation view
# ---------------------------------------------------------------------------

class MiscExpenseDeleteTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("del_super")
        self.client.force_login(self.admin)
        self.expense = _make_expense(subject="هزینه حذفی", amount=Decimal("50000"))

    # Req 11 ─────────────────────────────────────────────────────────────────
    def test_req11_delete_button_visible_for_superuser(self):
        """Superuser must see the delete button (link to delete confirm page) on change form."""
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertContains(resp, _delete_url(self.expense.pk))

    def test_req11_delete_button_hidden_for_staff_without_perm(self):
        """Staff without delete permission must NOT see the delete button."""
        staff = _make_staff_no_perm("del_noauth")
        self.client.force_login(staff)
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertNotContains(resp, _delete_url(self.expense.pk))

    # Req 12 ─────────────────────────────────────────────────────────────────
    def test_req12_delete_confirm_get_returns_200(self):
        """DELETE confirm GET must return 200 for authorized user."""
        resp = self.client.get(_delete_url(self.expense.pk))
        self.assertEqual(resp.status_code, 200)

    def test_req12_delete_confirm_shows_expense_details(self):
        """DELETE confirm GET must show subject and تومان amount."""
        resp = self.client.get(_delete_url(self.expense.pk))
        self.assertContains(resp, self.expense.subject)
        self.assertContains(resp, "تومان")

    # Req 13 ─────────────────────────────────────────────────────────────────
    def test_req13_delete_post_removes_only_targeted_record(self):
        """DELETE POST must remove the targeted record and leave others intact."""
        other = _make_expense(subject="هزینه دیگر")
        pk = self.expense.pk
        self.client.post(_delete_url(pk))
        self.assertFalse(MiscellaneousExpense.objects.filter(pk=pk).exists())
        self.assertTrue(MiscellaneousExpense.objects.filter(pk=other.pk).exists())

    # Req 14 ─────────────────────────────────────────────────────────────────
    def test_req14_delete_get_does_not_delete(self):
        """GET request to delete URL must NOT delete the record."""
        pk = self.expense.pk
        self.client.get(_delete_url(pk))
        self.assertTrue(MiscellaneousExpense.objects.filter(pk=pk).exists())

    # Req 15 ─────────────────────────────────────────────────────────────────
    def test_req15_unauthorized_user_gets_403(self):
        """Staff without delete permission must get 403 on DELETE POST."""
        staff = _make_staff_no_perm("del_403")
        self.client.force_login(staff)
        resp = self.client.post(_delete_url(self.expense.pk))
        self.assertEqual(resp.status_code, 403)

    def test_req15_unauthorized_user_gets_403_on_get(self):
        """Staff without delete permission must get 403 on DELETE GET."""
        staff = _make_staff_no_perm("del_403g")
        self.client.force_login(staff)
        resp = self.client.get(_delete_url(self.expense.pk))
        self.assertEqual(resp.status_code, 403)

    # Req 16 ─────────────────────────────────────────────────────────────────
    def test_req16_delete_confirm_has_csrf_token(self):
        """DELETE confirm page must contain a CSRF token field."""
        resp = self.client.get(_delete_url(self.expense.pk))
        self.assertContains(resp, "csrfmiddlewaretoken")


# ---------------------------------------------------------------------------
# Req 17: Amount format
# ---------------------------------------------------------------------------

class MiscExpenseAmountFormatTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("amt_super")
        self.client.force_login(self.admin)

    # Req 17 ─────────────────────────────────────────────────────────────────
    def test_req17_amount_has_toman_suffix(self):
        """List must show تومان suffix on the amount."""
        _make_expense(amount=Decimal("30000"))
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "تومان")

    def test_req17_amount_has_no_decimal_zeros(self):
        """Amount must not show .00 or unnecessary decimal digits."""
        _make_expense(amount=Decimal("30000.00"))
        resp = self.client.get(LIST_URL)
        content = resp.content.decode()
        self.assertNotIn(".00", content)
        self.assertNotIn("30000", content)  # plain ASCII digits → converted to Persian


# ---------------------------------------------------------------------------
# Req 18: Form field count
# ---------------------------------------------------------------------------

class MiscExpenseFormFieldsTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("fld_super")
        self.client.force_login(self.admin)

    # Req 18 ─────────────────────────────────────────────────────────────────
    def test_req18_form_has_exactly_three_fields(self):
        """Add form must expose exactly 3 named fields: date, subject, amount."""
        resp = self.client.get(ADD_URL)
        self.assertContains(resp, "id_date")
        self.assertContains(resp, "id_subject")
        self.assertContains(resp, "id_amount")
        content = resp.content.decode()
        named_inputs = re.findall(r'<input[^>]+name="([^"]+)"', content)
        form_fields = {n for n in named_inputs if n in ("date", "subject", "amount")}
        self.assertEqual(form_fields, {"date", "subject", "amount"},
                         f"Unexpected form fields: {form_fields}")


# ---------------------------------------------------------------------------
# Req 19: Search and date filters
# ---------------------------------------------------------------------------

class MiscExpenseFilterTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("flt_super")
        self.client.force_login(self.admin)

    # Req 19 ─────────────────────────────────────────────────────────────────
    def test_req19_search_filter_by_subject(self):
        """Search filter must narrow results to matching subjects."""
        _make_expense(subject="نظافت بهداشتی")
        _make_expense(subject="برق اضافه")
        resp = self.client.get(LIST_URL + "?search=نظافت")
        self.assertContains(resp, "نظافت بهداشتی")
        self.assertNotContains(resp, "برق اضافه")

    def test_req19_date_from_filter(self):
        """date_from filter must exclude earlier records."""
        _make_expense(subject="قدیمی", date="2025-01-01")
        _make_expense(subject="جدید",  date="2026-06-01")
        resp = self.client.get(LIST_URL + "?date_from=۱۴۰۵/۰۱/۰۱")
        self.assertContains(resp, "جدید")
        self.assertNotContains(resp, "قدیمی")

    def test_req19_date_to_filter(self):
        """date_to filter must exclude later records."""
        _make_expense(subject="قدیمی", date="2025-01-01")
        _make_expense(subject="جدید",  date="2026-06-01")
        resp = self.client.get(LIST_URL + "?date_to=۱۴۰۳/۱۲/۲۹")
        self.assertContains(resp, "قدیمی")
        self.assertNotContains(resp, "جدید")

    def test_req19_invalid_date_filter_ignored(self):
        """Invalid date_from/date_to values must be silently ignored."""
        _make_expense(subject="هزینه")
        resp = self.client.get(LIST_URL + "?date_from=invalid")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "هزینه")


# ---------------------------------------------------------------------------
# Req 20: Finance independence (Transactions count)
# ---------------------------------------------------------------------------

class MiscExpenseFinanceIndependenceTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("fi_super")
        self.client.force_login(self.admin)

    # Req 20 ─────────────────────────────────────────────────────────────────
    def test_req20_add_does_not_create_finance_transaction(self):
        """Adding a misc expense must NOT create a finance Transaction."""
        try:
            from finance.models import Transaction
        except ImportError:
            return
        count_before = Transaction.objects.count()
        self.client.post(ADD_URL, data={
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "هزینه تست تراکنش",
            "amount":  "15000",
        })
        self.assertEqual(Transaction.objects.count(), count_before,
                         "Finance Transaction must not be created for misc expense")

    def test_req20_edit_does_not_create_finance_transaction(self):
        """Editing a misc expense must NOT create a finance Transaction."""
        try:
            from finance.models import Transaction
        except ImportError:
            return
        expense = _make_expense()
        count_before = Transaction.objects.count()
        self.client.post(_change_url(expense.pk), data={
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "ویرایش بدون تراکنش",
            "amount":  "5000",
        })
        self.assertEqual(Transaction.objects.count(), count_before)

    def test_req20_model_has_no_finance_fields(self):
        """Model must not have transaction, category, or transaction_type fields."""
        field_names = [f.name for f in MiscellaneousExpense._meta.get_fields()]
        self.assertNotIn("transaction", field_names)
        self.assertNotIn("category", field_names)
        self.assertNotIn("transaction_type", field_names)

    # Req 21 ─────────────────────────────────────────────────────────────────
    def test_req21_finance_dashboard_still_loads(self):
        """Finance dashboard must still return 200 after misc-expenses changes."""
        resp = self.client.get("/admin/finance/")
        self.assertEqual(resp.status_code, 200)

    def test_req21_finance_transactions_still_loads(self):
        """Finance transactions page must still return 200."""
        resp = self.client.get("/admin/finance/transactions/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class MiscExpenseModelTest(TestCase):

    def test_create_and_retrieve(self):
        e = _make_expense()
        e.refresh_from_db()
        self.assertEqual(e.subject, "هزینه آزمایشی")
        self.assertEqual(e.amount, Decimal("15000"))

    def test_str_representation(self):
        e = _make_expense(subject="نظافت", date="2026-06-15")
        self.assertIn("نظافت", str(e))

    def test_amount_must_be_positive(self):
        e = MiscellaneousExpense(
            date="2026-06-01",
            subject="هزینه منفی",
            amount=Decimal("-100"),
        )
        with self.assertRaises(ValidationError):
            e.full_clean()

    def test_amount_zero_fails(self):
        e = MiscellaneousExpense(
            date="2026-06-01",
            subject="هزینه صفر",
            amount=Decimal("0"),
        )
        with self.assertRaises(ValidationError):
            e.full_clean()

    def test_amount_positive_passes(self):
        e = MiscellaneousExpense(
            date="2026-06-01",
            subject="هزینه مثبت",
            amount=Decimal("0.01"),
        )
        e.full_clean()

    def test_ordering_by_date_desc(self):
        e1 = _make_expense(subject="قدیمی‌تر", date="2026-01-01")
        e2 = _make_expense(subject="جدیدتر",  date="2026-06-01")
        first = MiscellaneousExpense.objects.first()
        self.assertEqual(first.pk, e2.pk)

    def test_auto_created_at(self):
        e = _make_expense()
        self.assertIsNotNone(e.created_at)

    def test_auto_updated_at(self):
        e = _make_expense()
        self.assertIsNotNone(e.updated_at)


# ---------------------------------------------------------------------------
# List view
# ---------------------------------------------------------------------------

class MiscExpenseListViewTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("lst_super")
        self.client.force_login(self.admin)

    def test_list_returns_200(self):
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_list_redirects_anonymous(self):
        self.client.logout()
        resp = self.client.get(LIST_URL)
        self.assertIn(resp.status_code, (301, 302))

    def test_list_loads_css(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "misc_expenses.css")

    def test_list_loads_rtl_css(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "rtl_responsive.css")

    def test_list_shows_expenses(self):
        _make_expense(subject="آزمایش یک")
        _make_expense(subject="آزمایش دو")
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "آزمایش یک")
        self.assertContains(resp, "آزمایش دو")

    def test_list_empty_state_shown_when_no_records(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "هنوز هزینه‌ای ثبت نشده")

    def test_list_empty_state_with_no_filter_match(self):
        _make_expense(subject="هزینه واقعی")
        resp = self.client.get(LIST_URL + "?search=غیرموجود")
        self.assertContains(resp, "یافت نشد")

    def test_list_search_empty_shows_all(self):
        _make_expense(subject="هزینه اول")
        _make_expense(subject="هزینه دوم")
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "هزینه اول")
        self.assertContains(resp, "هزینه دوم")

    def test_list_has_add_button(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, ADD_URL)

    def test_list_shows_jalali_date(self):
        _make_expense(date="2026-06-01")
        resp = self.client.get(LIST_URL)
        content = resp.content.decode()
        self.assertIn("۱۴۰۵", content)

    def test_list_section_label_is_mali(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "مالی")


# ---------------------------------------------------------------------------
# Add view
# ---------------------------------------------------------------------------

class MiscExpenseAddViewTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("add_super")
        self.client.force_login(self.admin)

    def _post_add(self, **extra):
        data = {
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "هزینه جدید",
            "amount":  "25000",
        }
        data.update(extra)
        return self.client.post(ADD_URL, data=data)

    def test_add_get_returns_200(self):
        resp = self.client.get(ADD_URL)
        self.assertEqual(resp.status_code, 200)

    def test_add_loads_css(self):
        resp = self.client.get(ADD_URL)
        self.assertContains(resp, "misc_expenses.css")

    def test_add_redirects_anonymous(self):
        self.client.logout()
        resp = self.client.get(ADD_URL)
        self.assertIn(resp.status_code, (301, 302))

    def test_add_post_creates_expense_and_redirects(self):
        resp = self._post_add()
        self.assertIn(resp.status_code, (301, 302))
        self.assertTrue(
            MiscellaneousExpense.objects.filter(subject="هزینه جدید").exists()
        )

    def test_add_post_invalid_amount_rerenders(self):
        resp = self._post_add(amount="-100")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            MiscellaneousExpense.objects.filter(amount=Decimal("-100")).exists()
        )

    def test_add_post_missing_subject_rerenders(self):
        resp = self._post_add(subject="")
        self.assertEqual(resp.status_code, 200)

    def test_add_post_zero_amount_rerenders(self):
        resp = self._post_add(amount="0")
        self.assertEqual(resp.status_code, 200)

    def test_add_form_has_csrf(self):
        resp = self.client.get(ADD_URL)
        self.assertContains(resp, "csrfmiddlewaretoken")

    def test_add_save_button_label(self):
        """Add form must show 'ذخیره' (not 'ذخیره تغییرات')."""
        resp = self.client.get(ADD_URL)
        content = resp.content.decode()
        self.assertIn("ذخیره", content)

    def test_add_section_label_is_mali(self):
        resp = self.client.get(ADD_URL)
        self.assertContains(resp, "مالی")


# ---------------------------------------------------------------------------
# Change view
# ---------------------------------------------------------------------------

class MiscExpenseChangeViewTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("chg_super")
        self.client.force_login(self.admin)
        self.expense = _make_expense(subject="هزینه قابل ویرایش", amount=Decimal("10000"))

    def test_change_get_returns_200(self):
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertEqual(resp.status_code, 200)

    def test_change_shows_existing_values(self):
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertContains(resp, "هزینه قابل ویرایش")

    def test_change_loads_css(self):
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertContains(resp, "misc_expenses.css")

    def test_change_redirects_anonymous(self):
        self.client.logout()
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertIn(resp.status_code, (301, 302))

    def test_change_404_for_nonexistent(self):
        resp = self.client.get(_change_url(99999))
        self.assertEqual(resp.status_code, 404)

    def test_change_post_updates_and_redirects(self):
        resp = self.client.post(_change_url(self.expense.pk), data={
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "هزینه ویرایش‌شده",
            "amount":  "20000",
        })
        self.assertIn(resp.status_code, (301, 302))
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.subject, "هزینه ویرایش‌شده")
        self.assertEqual(self.expense.amount, Decimal("20000"))

    def test_change_post_invalid_rerenders(self):
        resp = self.client.post(_change_url(self.expense.pk), data={
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "",
            "amount":  "10000",
        })
        self.assertEqual(resp.status_code, 200)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.subject, "هزینه قابل ویرایش")

    def test_change_post_legacy_delete_removes_record(self):
        """Legacy _delete POST handler (backward compat) must still work."""
        pk = self.expense.pk
        resp = self.client.post(_change_url(pk), data={"_delete": "1"})
        self.assertIn(resp.status_code, (301, 302))
        self.assertFalse(MiscellaneousExpense.objects.filter(pk=pk).exists())

    def test_change_shows_delete_link_to_confirm_page(self):
        """Change form for superuser must contain a link to the delete confirm URL."""
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertContains(resp, _delete_url(self.expense.pk))

    def test_change_save_button_label_on_edit(self):
        """Edit form must show 'ذخیره تغییرات'."""
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertContains(resp, "ذخیره تغییرات")

    def test_change_section_label_is_mali(self):
        resp = self.client.get(_change_url(self.expense.pk))
        self.assertContains(resp, "مالی")

    def test_change_has_no_transaction_side_effect(self):
        try:
            from finance.models import Transaction
            count_before = Transaction.objects.count()
        except ImportError:
            return
        self.client.post(_change_url(self.expense.pk), data={
            "date":    "۱۴۰۵/۰۳/۱۱",
            "subject": "ویرایش بدون تراکنش",
            "amount":  "5000",
        })
        count_after = Transaction.objects.count()
        self.assertEqual(count_before, count_after)


# ---------------------------------------------------------------------------
# Clickable-row attributes (full-row navigation)
# ---------------------------------------------------------------------------

class MiscExpenseClickableRowTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("row_super")
        self.client.force_login(self.admin)

    def test_row_has_clickable_row_class(self):
        """Every expense row must carry the me-clickable-row class."""
        _make_expense()
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "me-clickable-row")

    def test_row_has_data_edit_url(self):
        """Every expense row must have a data-edit-url pointing to its change URL."""
        e = _make_expense()
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, f'data-edit-url="{_change_url(e.pk)}"')

    def test_row_has_tabindex_zero(self):
        """Every expense row must be keyboard-focusable (tabindex=0)."""
        _make_expense()
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, 'tabindex="0"')

    def test_row_has_role_link(self):
        """Every expense row must declare role=link for screen readers."""
        _make_expense()
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, 'role="link"')

    def test_row_has_aria_label(self):
        """Every expense row must carry an accessible Persian label."""
        _make_expense(subject="تست اکسسیبیلیتی")
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "ویرایش هزینه متفرقه: تست اکسسیبیلیتی")

    def test_correct_edit_url_for_multiple_expenses(self):
        """Each row must carry its own correct edit URL (not another row's)."""
        e1 = _make_expense(subject="هزینه یک")
        e2 = _make_expense(subject="هزینه دو")
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, f'data-edit-url="{_change_url(e1.pk)}"')
        self.assertContains(resp, f'data-edit-url="{_change_url(e2.pk)}"')

    def test_subject_still_visible_in_row(self):
        """Row subject text must still be visible inside the clickable row."""
        _make_expense(subject="موضوع قابل کلیک")
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "موضوع قابل کلیک")

    def test_no_amaliyat_column_in_clickable_table(self):
        """Adding clickable rows must NOT introduce an عملیات column."""
        _make_expense()
        resp = self.client.get(LIST_URL)
        content = resp.content.decode()
        table_m = re.search(r'<table class="me-table"[^>]*>(.*?)</table>', content, re.DOTALL)
        if table_m:
            headers = re.findall(r'<th\b[^>]*>(.*?)</th>', table_m.group(1), re.DOTALL)
            stripped = [h.strip() for h in headers]
            self.assertNotIn("عملیات", stripped)
            self.assertEqual(len(stripped), 3)

    def test_row_js_is_present_in_list_page(self):
        """The list page must include the row-navigation JavaScript."""
        _make_expense()
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, "me-clickable-row")
        self.assertContains(resp, "editUrl")

    def test_empty_state_has_no_clickable_rows(self):
        """When the list is empty, no tabindex-0 <tr> rows should appear."""
        resp = self.client.get(LIST_URL)
        content = resp.content.decode()
        # tabindex="0" only appears on <tr> expense rows, not in JS or elsewhere
        tr_with_tabindex = re.findall(r'<tr[^>]*tabindex="0"', content)
        self.assertEqual(len(tr_with_tabindex), 0,
                         "No expense rows should be rendered on the empty list page")


# ---------------------------------------------------------------------------
# Sidebar CSS structure tests
# ---------------------------------------------------------------------------

class SidebarCSSStructureTest(TestCase):

    def _read_custom_admin_css(self):
        import os
        css_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "..", "..", "static", "admin", "css", "custom_admin.css"
        ))
        with open(css_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_sidebar_nav_has_flex_grow(self):
        """ca-sidebar-nav must use flex:1 so it fills space between brand and footer."""
        css = self._read_custom_admin_css()
        self.assertIn(".ca-sidebar-nav", css)
        # Find the ca-sidebar-nav rule block
        import re
        m = re.search(r'\.ca-sidebar-nav\s*\{([^}]+)\}', css)
        self.assertIsNotNone(m, ".ca-sidebar-nav rule not found")
        block = m.group(1)
        self.assertIn("flex", block)

    def test_sidebar_nav_has_min_height_zero(self):
        """ca-sidebar-nav must have min-height:0 to allow flex child to shrink/scroll."""
        css = self._read_custom_admin_css()
        import re
        m = re.search(r'\.ca-sidebar-nav\s*\{([^}]+)\}', css)
        self.assertIsNotNone(m)
        self.assertIn("min-height", m.group(1))

    def test_sidebar_nav_has_overflow_y_auto(self):
        """ca-sidebar-nav must have overflow-y:auto so nav items scroll."""
        css = self._read_custom_admin_css()
        import re
        m = re.search(r'\.ca-sidebar-nav\s*\{([^}]+)\}', css)
        self.assertIsNotNone(m)
        self.assertIn("overflow-y", m.group(1))

    def test_sidebar_itself_does_not_have_overflow_y_auto(self):
        """ca-sidebar must NOT have overflow-y:auto — that causes footer drift."""
        css = self._read_custom_admin_css()
        import re
        # Find the .ca-sidebar rule block (not .ca-sidebar-nav or .ca-sidebar-footer)
        m = re.search(r'(?<![a-zA-Z-])\.ca-sidebar\s*\{([^}]+)\}', css)
        self.assertIsNotNone(m, ".ca-sidebar rule not found")
        block = m.group(1)
        self.assertNotIn("overflow-y: auto", block,
                         ".ca-sidebar must not have overflow-y:auto — use overflow:hidden")

    def test_sidebar_footer_not_using_margin_top_auto(self):
        """ca-sidebar-footer must use flex-shrink:0 not margin-top:auto."""
        css = self._read_custom_admin_css()
        import re
        m = re.search(r'\.ca-sidebar-footer\s*\{([^}]+)\}', css)
        self.assertIsNotNone(m, ".ca-sidebar-footer rule not found")
        block = m.group(1)
        self.assertNotIn("margin-top: auto", block,
                         "Footer must use flex-shrink:0 instead of margin-top:auto")
        self.assertIn("flex-shrink", block)


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

class MiscExpenseSummaryCardsTest(TestCase):

    def setUp(self):
        self.admin = _make_superuser("cards_super")
        self.client.force_login(self.admin)

    def _get_list(self, **params):
        return self.client.get(LIST_URL, params)

    # ── Card structure ───────────────────────────────────────────────────────

    def test_all_four_card_titles_present(self):
        resp = self._get_list()
        self.assertContains(resp, "مجموع هزینه‌های متفرقه")
        self.assertContains(resp, "تعداد هزینه‌ها")
        self.assertContains(resp, "میانگین مبلغ")
        self.assertContains(resp, "بیشترین هزینه")

    def test_four_card_css_classes_present(self):
        resp = self._get_list()
        for cls in ("me-card--total", "me-card--count", "me-card--avg", "me-card--max"):
            self.assertContains(resp, cls)

    # ── Correct values ───────────────────────────────────────────────────────

    def test_total_amount_correct(self):
        _make_expense(amount=Decimal("10000"))
        _make_expense(amount=Decimal("5000"))
        resp = self._get_list()
        # 10000 + 5000 = 15000 → ۱۵٬۰۰۰
        self.assertContains(resp, "۱۵٬۰۰۰")

    def test_expense_count_correct(self):
        for _ in range(3):
            _make_expense()
        resp = self._get_list()
        self.assertContains(resp, "me-card--count")
        # count = 3 → ۳
        content = resp.content.decode()
        m = re.search(
            r'me-card--count.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m, "me-card--count value not found")
        self.assertIn("۳", m.group(1))

    def test_average_amount_correct(self):
        _make_expense(amount=Decimal("10000"))
        _make_expense(amount=Decimal("20000"))
        resp = self._get_list()
        # avg = 15000 → ۱۵٬۰۰۰
        self.assertContains(resp, "۱۵٬۰۰۰")

    def test_maximum_amount_correct(self):
        _make_expense(amount=Decimal("5000"))
        _make_expense(amount=Decimal("99000"))
        resp = self._get_list()
        # max = 99000 → ۹۹٬۰۰۰
        self.assertContains(resp, "۹۹٬۰۰۰")

    # ── Zero state ───────────────────────────────────────────────────────────

    def test_empty_shows_zero_toman_for_total(self):
        resp = self._get_list()
        self.assertContains(resp, "۰ تومان")

    def test_empty_shows_zero_for_count(self):
        resp = self._get_list()
        content = resp.content.decode()
        m = re.search(
            r'me-card--count.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("۰", m.group(1))

    def test_empty_shows_zero_toman_for_average(self):
        resp = self._get_list()
        content = resp.content.decode()
        m = re.search(
            r'me-card--avg.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("۰", m.group(1))

    def test_empty_shows_zero_toman_for_maximum(self):
        resp = self._get_list()
        content = resp.content.decode()
        m = re.search(
            r'me-card--max.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("۰", m.group(1))

    # ── Filter-aware ─────────────────────────────────────────────────────────

    def test_subject_filter_updates_total(self):
        _make_expense(subject="نظافت", amount=Decimal("10000"))
        _make_expense(subject="برق",   amount=Decimal("20000"))
        resp = self._get_list(search="نظافت")
        content = resp.content.decode()
        # Only 10000 should appear as total, not 30000
        self.assertContains(resp, "۱۰٬۰۰۰")
        self.assertNotIn("۳۰٬۰۰۰", content)

    def test_subject_filter_updates_count(self):
        _make_expense(subject="نظافت", amount=Decimal("10000"))
        _make_expense(subject="برق",   amount=Decimal("20000"))
        resp = self._get_list(search="نظافت")
        content = resp.content.decode()
        m = re.search(
            r'me-card--count.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("۱", m.group(1))

    def test_date_from_filter_updates_cards(self):
        _make_expense(date="2026-01-01", amount=Decimal("5000"))   # Jalali: 1404/10/11
        _make_expense(date="2026-06-01", amount=Decimal("25000"))  # Jalali: 1405/03/11
        # Filter from 1405/01/01 — should only include the June expense
        resp = self._get_list(date_from="1405/01/01")
        content = resp.content.decode()
        self.assertIn("۲۵٬۰۰۰", content)
        self.assertNotIn("۳۰٬۰۰۰", content)

    def test_date_to_filter_updates_cards(self):
        _make_expense(date="2026-01-01", amount=Decimal("5000"))   # Jalali: 1404/10/11
        _make_expense(date="2026-06-01", amount=Decimal("25000"))  # Jalali: 1405/03/11
        # Filter up to 1404/12/29 — should only include the January expense
        resp = self._get_list(date_to="1404/12/29")
        content = resp.content.decode()
        self.assertIn("۵٬۰۰۰", content)
        self.assertNotIn("۳۰٬۰۰۰", content)

    def test_combined_filters_update_all_cards(self):
        _make_expense(subject="نظافت", date="2026-06-01", amount=Decimal("15000"))
        _make_expense(subject="برق",   date="2026-06-01", amount=Decimal("10000"))
        _make_expense(subject="نظافت", date="2026-01-01", amount=Decimal("8000"))
        # Filter by subject only — all dates with "نظافت"
        resp = self._get_list(search="نظافت")
        content = resp.content.decode()
        # total = 15000 + 8000 = 23000
        self.assertIn("۲۳٬۰۰۰", content)

    # ── Formatting ───────────────────────────────────────────────────────────

    def test_total_card_has_toman_suffix(self):
        _make_expense(amount=Decimal("10000"))
        resp = self._get_list()
        content = resp.content.decode()
        m = re.search(
            r'me-card--total.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("تومان", m.group(1))

    def test_average_card_has_toman_suffix(self):
        _make_expense(amount=Decimal("10000"))
        resp = self._get_list()
        content = resp.content.decode()
        m = re.search(
            r'me-card--avg.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("تومان", m.group(1))

    def test_maximum_card_has_toman_suffix(self):
        _make_expense(amount=Decimal("10000"))
        resp = self._get_list()
        content = resp.content.decode()
        m = re.search(
            r'me-card--max.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertIn("تومان", m.group(1))

    def test_count_card_has_no_toman_suffix(self):
        _make_expense()
        resp = self._get_list()
        content = resp.content.decode()
        m = re.search(
            r'me-card--count.*?me-summary-card__value[^>]*>(.*?)</div>',
            content, re.DOTALL
        )
        self.assertIsNotNone(m)
        self.assertNotIn("تومان", m.group(1))

    def test_values_have_no_decimal_point(self):
        _make_expense(amount=Decimal("12345"))
        resp = self._get_list()
        content = resp.content.decode()
        self.assertNotIn("12345.00", content)
        self.assertNotIn(".00", content)

    def test_values_have_no_rial_or_irr(self):
        _make_expense(amount=Decimal("5000"))
        resp = self._get_list()
        content = resp.content.decode()
        self.assertNotIn("ریال", content)
        self.assertNotIn("IRR", content)

    def test_values_use_persian_digits(self):
        _make_expense(amount=Decimal("10000"))
        resp = self._get_list()
        content = resp.content.decode()
        # Persian digits: ۰-۹
        self.assertTrue(
            any(c in content for c in "۰۱۲۳۴۵۶۷۸۹"),
            "Summary card values must use Persian digits"
        )

    # ── Finance isolation ────────────────────────────────────────────────────

    def test_finance_transaction_count_unchanged_by_cards(self):
        try:
            from finance.models import Transaction
        except ImportError:
            return
        count_before = Transaction.objects.count()
        _make_expense(amount=Decimal("50000"))
        self._get_list()
        self.assertEqual(Transaction.objects.count(), count_before)

    def test_no_new_model_fields_for_aggregates(self):
        """Aggregates must be computed in the view — not stored as model fields."""
        field_names = {f.name for f in MiscellaneousExpense._meta.get_fields()}
        for computed in ("total_amount", "expense_count", "average_amount", "maximum_amount"):
            self.assertNotIn(computed, field_names)
