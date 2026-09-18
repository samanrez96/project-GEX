from decimal import Decimal

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Max, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.contrib.auth.decorators import user_passes_test

from common.dates import parse_jalali_date, to_jalali_date

from .forms import MiscellaneousExpenseForm
from .models import MiscellaneousExpense


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _user_is_admin_or_finance(user):
    """Return True if user is in admin or finance_user group (or superuser)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=['admin', 'finance_user']).exists()


# Decorator that combines staff_member_required and the group check.
def admin_or_finance_required(view_func):
    decorated = staff_member_required(view_func)
    return user_passes_test(_user_is_admin_or_finance, login_url='admin:login')(decorated)


# ---------------------------------------------------------------------------
# Persian money formatter (independent from finance app)
# ---------------------------------------------------------------------------

def _fmt_toman(value):
    """Return a Persian-digit string like ۱۵٬۰۰۰ (no currency suffix)."""
    _PERSIAN = '۰۱۲۳۴۵۶۷۸۹'
    try:
        n = int(Decimal(str(value)).quantize(Decimal('1')))
        is_neg = n < 0
        raw = f'{abs(n):,}'.replace(',', '٬')
        persian = ''.join(_PERSIAN[int(c)] if c.isdigit() else c for c in raw)
        return ('-' + persian) if is_neg else persian
    except Exception:
        return '—'


# ---------------------------------------------------------------------------
# Custom admin views (restricted to admin/finance)
# ---------------------------------------------------------------------------

@admin_or_finance_required
def misc_expenses_list_view(request):
    qs = MiscellaneousExpense.objects.all()

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(subject__icontains=search)

    date_from = request.GET.get("date_from", "").strip()
    date_to   = request.GET.get("date_to",   "").strip()

    if date_from:
        try:
            qs = qs.filter(date__gte=parse_jalali_date(date_from))
        except Exception:
            pass
    if date_to:
        try:
            qs = qs.filter(date__lte=parse_jalali_date(date_to))
        except Exception:
            pass

    agg = qs.aggregate(
        total_amount=Sum("amount"),
        expense_count=Count("id"),
        average_amount=Avg("amount"),
        maximum_amount=Max("amount"),
    )
    summary = {
        "total":   _fmt_toman(agg["total_amount"]   or 0),
        "count":   _fmt_toman(agg["expense_count"]  or 0),
        "average": _fmt_toman(agg["average_amount"] or 0),
        "maximum": _fmt_toman(agg["maximum_amount"] or 0),
    }

    expenses = [
        {
            "id":         e.id,
            "date":       to_jalali_date(e.date),
            "subject":    e.subject,
            "amount":     _fmt_toman(e.amount),
            "change_url": reverse("admin:misc_expenses_change", args=[e.id]),
        }
        for e in qs
    ]

    context = {
        **admin.site.each_context(request),
        "title":              "هزینه‌های متفرقه",
        "expenses":           expenses,
        "summary":            summary,
        "search":             search,
        "date_from":          date_from,
        "date_to":            date_to,
        "add_url":            reverse("admin:misc_expenses_add"),
        "has_add_permission": request.user.has_perm("misc_expenses.add_miscellaneousexpense"),
    }
    return render(request, "admin/misc_expenses/change_list.html", context)


@admin_or_finance_required
def misc_expenses_add_view(request):
    if request.method == "POST":
        form = MiscellaneousExpenseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "هزینه متفرقه با موفقیت ثبت شد.")
            return redirect(reverse("admin:misc_expenses_list"))
    else:
        form = MiscellaneousExpenseForm()

    context = {
        **admin.site.each_context(request),
        "title":    "افزودن هزینه متفرقه",
        "form":     form,
        "is_add":   True,
        "list_url": reverse("admin:misc_expenses_list"),
    }
    return render(request, "admin/misc_expenses/change_form.html", context)


@admin_or_finance_required
def misc_expenses_change_view(request, pk):
    expense = get_object_or_404(MiscellaneousExpense, pk=pk)

    if request.method == "POST":
        # Legacy inline delete — kept for test backward-compat; UI uses dedicated URL.
        if "_delete" in request.POST:
            if not request.user.has_perm("misc_expenses.delete_miscellaneousexpense"):
                raise PermissionDenied
            expense.delete()
            messages.success(request, "هزینه متفرقه با موفقیت حذف شد.")
            return redirect(reverse("admin:misc_expenses_list"))

        form = MiscellaneousExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, "هزینه متفرقه با موفقیت ویرایش شد.")
            return redirect(reverse("admin:misc_expenses_list"))
    else:
        form = MiscellaneousExpenseForm(instance=expense)

    can_delete = request.user.has_perm("misc_expenses.delete_miscellaneousexpense")

    context = {
        **admin.site.each_context(request),
        "title":      f"ویرایش: {expense.subject}",
        "form":       form,
        "expense":    expense,
        "is_add":     False,
        "list_url":   reverse("admin:misc_expenses_list"),
        "delete_url": reverse("admin:misc_expenses_delete", args=[pk]),
        "can_delete": can_delete,
    }
    return render(request, "admin/misc_expenses/change_form.html", context)


@admin_or_finance_required
def misc_expenses_delete_view(request, pk):
    expense = get_object_or_404(MiscellaneousExpense, pk=pk)

    if not request.user.has_perm("misc_expenses.delete_miscellaneousexpense"):
        raise PermissionDenied

    if request.method == "POST":
        expense.delete()
        messages.success(request, "هزینه متفرقه با موفقیت حذف شد.")
        return redirect(reverse("admin:misc_expenses_list"))

    context = {
        **admin.site.each_context(request),
        "title":      "تأیید حذف هزینه متفرقه",
        "expense":    expense,
        "date_fmt":   to_jalali_date(expense.date),
        "amount_fmt": _fmt_toman(expense.amount),
        "list_url":   reverse("admin:misc_expenses_list"),
        "change_url": reverse("admin:misc_expenses_change", args=[pk]),
    }
    return render(request, "admin/misc_expenses/delete_confirm.html", context)

