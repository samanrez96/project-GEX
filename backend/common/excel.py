"""Reusable, professional Excel (.xlsx) export architecture.

One centralized place for building workbooks so every export in the project
(Surgery, Product, Employee, Purchase, Doctor, Patient, ...) shares the same
report structure, theme, RTL setup, and number/date formatting rules instead
of each app re-implementing workbook construction independently.

Usage in a DRF ViewSet (the common case — reuses the ViewSet's own filtered
queryset, so search/filters/ordering/permissions are never re-implemented):

    class ProductViewSet(ExcelExportMixin, viewsets.ModelViewSet):
        excel_filename_prefix = 'product-list'
        excel_sheet_title      = 'محصولات'
        excel_report_title     = 'گزارش فهرست محصولات'

        def get_excel_columns(self, request):
            return [
                ExcelColumn(key='name', label='نام محصول', data_type='text', width=24),
                ExcelColumn(key='price', label='قیمت خرید (تومان)', data_type='money', width=16),
            ]

        def queryset_to_excel_rows(self, queryset):
            for obj in queryset.iterator():
                yield {'name': obj.name, 'price': obj.purchase_price}

        def get_excel_meta_rows(self, request):
            return [('نوع محصول', 'دارو')]   # active filters, already in Persian

        def get_excel_summary(self, request, queryset):
            return [('تعداد کل محصولات', queryset.count())]

Usage directly (non-ViewSet views, e.g. a Django admin changelist reusing its
own ChangeList queryset):

    content = build_excel(columns=[...], rows=[...], report_title='...')
    return excel_file_response(content, filename=make_export_filename('patient-list'))

``build_excel`` is a single-sheet convenience wrapper around
``build_workbook``, which supports multiple sheets (e.g. a Purchase workbook
with a "خلاصه خریدها" summary sheet and an "اقلام خرید" line-item sheet).
"""

import io
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional

from django.contrib import messages
from django.contrib.admin.utils import label_for_field
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

# ── Constants ───────────────────────────────────────────────────────────────

CONTENT_TYPE   = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
EXCEL_MAX_ROWS = 10_000          # hard cap for safety; views may lower it

DEFAULT_EMPTY_MESSAGE = 'رکوردی مطابق فیلترهای انتخاب‌شده یافت نشد.'

# One shared palette for every export — pulled from the same CSS variables
# the web admin itself uses (custom_admin.css), so a printed/opened workbook
# reads as part of the same product rather than a generic spreadsheet dump.
COLOR_HEADER_FILL  = 'E8F1FA'   # --purple-light
COLOR_HEADER_TEXT  = '0F2B46'   # --sidebar-bg / --text-strong
COLOR_TITLE_TEXT   = '0F2B46'
COLOR_BORDER       = 'DCE3EC'   # --border
COLOR_STRIPE       = 'F5F7FA'   # --bg
COLOR_MUTED_TEXT   = '6B7888'   # --muted

_NUMBER_FORMATS = {
    'money':   '#,##0',
    'integer': '#,##0',
    'number':  '#,##0.##',      # quantities / fractional hours — up to 2 decimals
    'percent': '0.##%',
}

_ALIGNMENTS = {
    'text':     'right',
    'money':    'left',
    'integer':  'left',
    'number':   'left',
    'percent':  'left',
    'date':     'center',
    'datetime': 'center',
}


# ── Column / sheet configuration ─────────────────────────────────────────────

@dataclass
class ExcelColumn:
    """One exported column.

    data_type drives both the Excel number format and cell alignment:
      text      — Persian labels, names, free text (right-aligned)
      money     — Decimal/int Toman amounts, format #,##0 (left-aligned, numeric)
      integer   — whole-number counts, format #,##0
      number    — quantities / fractional work hours, format #,##0.## (keeps
                  7.5 as 7.5, never rounds/forces a false precision)
      date      — Python date/datetime → Jalali date string (١,٢,٣ digits)
      datetime  — Python datetime → Jalali date + time string

    getter, if given, is called as ``getter(row_object)``; otherwise the row
    is treated as a dict and looked up by ``key``. Both styles are supported
    so callers can pass either plain objects (with getters) or pre-built
    dicts (the original convention every existing export in this project
    already used).
    """

    key: str
    label: str
    data_type: str = 'text'
    width: Optional[int] = None
    wrap: bool = False
    number_format: Optional[str] = None
    getter: Optional[Callable[[Any], Any]] = None


@dataclass
class ExcelSheet:
    name: str
    columns: list
    rows: Iterable[Any]
    summary: Optional[list] = None            # list[(label, value)]
    empty_message: str = DEFAULT_EMPTY_MESSAGE


def _coerce_column(c) -> ExcelColumn:
    """Accept either an ExcelColumn or the legacy (header, key[, data_type]) tuple."""
    if isinstance(c, ExcelColumn):
        return c
    header, key = c[0], c[1]
    data_type = c[2] if len(c) > 2 else 'text'
    return ExcelColumn(key=key, label=header, data_type=data_type)


def _sanitize_sheet_name(name: str) -> str:
    """Excel worksheet names: <=31 chars, no : \\ / ? * [ ]."""
    name = re.sub(r'[:\\/?*\[\]]', ' ', name or 'گزارش').strip()
    return (name or 'گزارش')[:31]


# ── Value normalisation ───────────────────────────────────────────────────────

def _resolve_value(raw, data_type):
    """Convert a raw Python value to what belongs in the Excel cell.

    - date/datetime columns always render as a Jalali string (or '—' for
      None) — the underlying queryset filtering must already have happened
      against the real database date; this is presentation-only.
    - Decimal values are passed through unchanged. openpyxl writes Decimal
      cells precisely (verified: no float round-trip is needed), so money/
      quantity columns stay numeric and exact instead of going through
      unsafe float conversion.
    - None stays None for non-date columns — a genuinely blank cell,
      distinguishable from a real numeric zero.
    """
    if data_type in ('date', 'datetime'):
        if raw is None or raw == '':
            return '—'
        if hasattr(raw, 'strftime'):
            from common.dates import to_jalali_date, to_jalali_datetime
            return to_jalali_datetime(raw) if data_type == 'datetime' else to_jalali_date(raw)
        return raw  # already a formatted string
    if raw is None:
        return None
    if isinstance(raw, bool):
        return 'بله' if raw else 'خیر'
    if hasattr(raw, 'strftime'):
        from common.dates import to_jalali_date
        return to_jalali_date(raw)
    return raw


# ── Core workbook builder ─────────────────────────────────────────────────────

def build_workbook(sheets, *, report_title=None, meta_rows=None, generated_by=None) -> bytes:
    """Build a multi-sheet, professionally formatted workbook and return its bytes.

    Every sheet gets the same report structure:
        Row 1   merged report title (if report_title given)
        Row N   one merged row per meta_rows entry (active filters)
        Row N+1 merged "تاریخ تهیه: ... | تهیه‌کننده: ..." line
        Row N+2 blank separator
        Row N+3 column headers (bold, filled, frozen below, auto-filtered)
        Row N+4+ data rows (thin borders, alternating shading, wrapped text
                  where requested)
        (blank + summary rows, if any)

    Args:
        sheets      : list of ExcelSheet.
        report_title: optional title merged across the sheet's columns.
        meta_rows   : optional list of (label, value) filter-summary pairs,
                      shared by every sheet in the workbook.
        generated_by: optional display name of the exporting user.

    Returns:
        bytes — the .xlsx file content.
    """
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from common.dates import to_jalali_datetime

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    thin        = Side(style='thin', color=COLOR_BORDER)
    border_all  = Border(left=thin, right=thin, top=thin, bottom=thin)
    title_font  = Font(bold=True, color=COLOR_TITLE_TEXT, size=14)
    meta_font   = Font(color=COLOR_MUTED_TEXT, size=10)
    header_font = Font(bold=True, color=COLOR_HEADER_TEXT, size=11)
    header_fill = PatternFill('solid', fgColor=COLOR_HEADER_FILL)
    stripe_fill = PatternFill('solid', fgColor=COLOR_STRIPE)
    summary_font = Font(bold=True, size=11)
    empty_font  = Font(italic=True, color=COLOR_MUTED_TEXT)

    generated_line = f'تاریخ تهیه: {to_jalali_datetime(timezone.localtime(timezone.now()))}'
    if generated_by:
        generated_line += f' | تهیه‌کننده: {generated_by}'

    used_names = set()
    for sheet_spec in sheets:
        columns = [_coerce_column(c) for c in sheet_spec.columns]
        n_cols  = max(len(columns), 1)

        base_name = _sanitize_sheet_name(sheet_spec.name)
        sheet_name, suffix = base_name, 2
        while sheet_name in used_names:
            sheet_name = f'{base_name[:28]} {suffix}'
            suffix += 1
        used_names.add(sheet_name)

        ws = wb.create_sheet(sheet_name)
        ws.sheet_view.rightToLeft = True

        row = 1

        if report_title:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
            cell = ws.cell(row=row, column=1, value=report_title)
            cell.font = title_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            ws.row_dimensions[row].height = 26
            row += 1

        if meta_rows:
            for label, value in meta_rows:
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
                text = f'{label}: {value}' if value not in (None, '') else str(label)
                cell = ws.cell(row=row, column=1, value=text)
                cell.font = meta_font
                cell.alignment = Alignment(horizontal='right')
                row += 1

        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
        gcell = ws.cell(row=row, column=1, value=generated_line)
        gcell.font = meta_font
        gcell.alignment = Alignment(horizontal='right')
        row += 1

        row += 1  # blank separator row

        header_row = row
        for col_idx, col in enumerate(columns, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=col.label)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border_all
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.row_dimensions[header_row].height = 22
        row += 1

        data_start = row
        has_wrap   = any(c.wrap for c in columns)
        row_count  = 0
        for source in sheet_spec.rows:
            for col_idx, col in enumerate(columns, start=1):
                raw = col.getter(source) if col.getter else source.get(col.key)
                value = _resolve_value(raw, col.data_type)
                cell = ws.cell(row=row, column=col_idx, value=value)
                cell.border = border_all
                cell.alignment = Alignment(
                    horizontal=_ALIGNMENTS.get(col.data_type, 'right'),
                    vertical='center',
                    wrap_text=col.wrap,
                )
                fmt = col.number_format or _NUMBER_FORMATS.get(col.data_type)
                if fmt and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    cell.number_format = fmt
            if (row - data_start) % 2 == 1:
                for col_idx in range(1, n_cols + 1):
                    ws.cell(row=row, column=col_idx).fill = stripe_fill
            if has_wrap:
                ws.row_dimensions[row].height = 34
            row += 1
            row_count += 1

        if row_count == 0:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=n_cols)
            msg_cell = ws.cell(row=row, column=1, value=sheet_spec.empty_message)
            msg_cell.font = empty_font
            msg_cell.alignment = Alignment(horizontal='center')
            msg_cell.border = border_all
            row += 1

        last_data_row = row - 1

        # Freeze everything above and including the header row; auto-filter
        # spans the header + all data rows (or the empty-message row).
        ws.freeze_panes = f'A{header_row + 1}'
        if last_data_row >= header_row:
            ws.auto_filter.ref = f'A{header_row}:{get_column_letter(n_cols)}{last_data_row}'

        if sheet_spec.summary:
            row += 1
            for label, value in sheet_spec.summary:
                label_cell = ws.cell(row=row, column=1, value=label)
                label_cell.font = summary_font
                is_numeric = isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
                val_cell = ws.cell(row=row, column=2, value=value if is_numeric else _resolve_value(value, 'text'))
                val_cell.font = summary_font
                if is_numeric:
                    val_cell.number_format = '#,##0'
                    val_cell.alignment = Alignment(horizontal='left')
                row += 1

        for col_idx, col in enumerate(columns, start=1):
            letter = get_column_letter(col_idx)
            if col.width:
                ws.column_dimensions[letter].width = col.width
                continue
            max_len = len(col.label) * 2
            for r in range(header_row, last_data_row + 1):
                v = ws.cell(row=r, column=col_idx).value
                if v:
                    max_len = max(max_len, len(str(v)) + 4)
            ws.column_dimensions[letter].width = min(max_len, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def build_excel(columns, rows, *, sheet_title='گزارش', meta_rows=None,
                 report_title=None, summary=None, generated_by=None,
                 empty_message=None) -> bytes:
    """Single-sheet convenience wrapper around build_workbook.

    Kept for backward compatibility with the original (header, key) column
    tuples — existing callers do not need to change to use ExcelColumn.
    """
    sheet = ExcelSheet(
        name=sheet_title,
        columns=[_coerce_column(c) for c in columns],
        rows=rows,
        summary=summary,
        empty_message=empty_message or DEFAULT_EMPTY_MESSAGE,
    )
    return build_workbook([sheet], report_title=report_title, meta_rows=meta_rows,
                           generated_by=generated_by)


# ── Filename / HTTP response helpers ─────────────────────────────────────────

def make_export_filename(prefix: str) -> str:
    """e.g. make_export_filename('surgery-list') -> 'surgery-list-1405-04-25.xlsx'.

    Uses today's Jalali date (ASCII digits, dash-separated — safe for
    filenames and URLs, unlike the Persian-digit slash-separated display
    format used inside the workbook itself).
    """
    from common.dates import _gregorian_to_jalali

    now = timezone.localtime(timezone.now())
    jy, jm, jd = _gregorian_to_jalali(now.year, now.month, now.day)
    safe_prefix = re.sub(r'[^A-Za-z0-9_-]+', '-', prefix or 'export').strip('-') or 'export'
    return f'{safe_prefix}-{jy:04d}-{jm:02d}-{jd:02d}.xlsx'


def excel_file_response(content: bytes, *, filename: str = 'export.xlsx') -> HttpResponse:
    """Wrap Excel bytes in an HttpResponse with the correct content type."""
    response = HttpResponse(content, content_type=CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def get_display_name(user) -> str:
    """Best-effort human display name for the 'تهیه‌کننده' metadata line."""
    if user is None:
        return ''
    full_name = getattr(user, 'get_full_name', lambda: '')()
    return full_name or getattr(user, 'username', '') or ''


def describe_ordering(ordering_param, field_labels) -> Optional[str]:
    """Convert a DRF OrderingFilter ``?ordering=`` value into a Persian
    summary string for the export's filter-metadata area, e.g.
    ``describe_ordering('-internal_code', {'internal_code': 'کد داخلی'})``
    → ``'کد داخلی (نزولی)'``. Unknown field names fall back to the raw
    field name rather than being silently dropped.
    """
    if not ordering_param:
        return None
    parts = []
    for raw_field in ordering_param.split(','):
        raw_field = raw_field.strip()
        if not raw_field:
            continue
        descending = raw_field.startswith('-')
        name  = raw_field[1:] if descending else raw_field
        label = field_labels.get(name, name)
        parts.append(f"{label} ({'نزولی' if descending else 'صعودی'})")
    return '، '.join(parts) if parts else None


# ── ViewSet mixin ─────────────────────────────────────────────────────────────

class ExcelExportMixin:
    """Add ``?export=excel`` support to any DRF ViewSet ``list`` action.

    Reuses the ViewSet's own permission_classes, filter_backends, and
    filterset — the export always calls ``self.filter_queryset(...)``, the
    exact same method the normal paginated list uses, so search/filters/
    ordering never need a second implementation and can never be bypassed.

    Subclasses must implement:
        ``get_excel_columns(request)``   → list of ExcelColumn (or legacy tuples)
        ``queryset_to_excel_rows(qs)``   → iterable of row dicts (or objects,
                                            if columns use ``getter``)

    Optionally override:
        ``get_export_queryset()``               → base queryset for export
                                                    (default: get_queryset())
        ``get_excel_report_title(request)``      → merged title row text
        ``get_excel_meta_rows(request)``         → list[(label, value)] of
                                                    active filters, already
                                                    converted to Persian
        ``get_excel_summary(request, queryset)`` → list[(label, value)] totals
        ``excel_filename``        — static filename (legacy)
        ``excel_filename_prefix`` — preferred: dated filename via
                                    make_export_filename()
        ``excel_sheet_title``     — default 'داده‌ها'
    """

    excel_filename        = None
    excel_filename_prefix = None
    excel_sheet_title     = 'داده‌ها'
    excel_report_title    = None

    def get_excel_columns(self, request):       # pragma: no cover
        raise NotImplementedError(
            f'{type(self).__name__} must implement get_excel_columns(request)'
        )

    def queryset_to_excel_rows(self, queryset): # pragma: no cover
        raise NotImplementedError(
            f'{type(self).__name__} must implement queryset_to_excel_rows(queryset)'
        )

    def get_export_queryset(self):
        """Return the base queryset for export (before filtering)."""
        return self.get_queryset()

    def get_excel_report_title(self, request):
        return self.excel_report_title

    def get_excel_meta_rows(self, request):
        return []

    def get_excel_summary(self, request, queryset):
        return None

    def get_excel_filename(self):
        if self.excel_filename_prefix:
            return make_export_filename(self.excel_filename_prefix)
        return self.excel_filename or 'export.xlsx'

    def list(self, request, *args, **kwargs):
        if request.query_params.get('export') == 'excel':
            return self._handle_excel_export(request)
        return super().list(request, *args, **kwargs)

    def _handle_excel_export(self, request):
        qs    = self.filter_queryset(self.get_export_queryset())
        count = qs.count()
        if count > EXCEL_MAX_ROWS:
            return Response(
                {
                    'detail': (
                        f'تعداد نتایج ({count:,}) بیشتر از حد مجاز ({EXCEL_MAX_ROWS:,}) است. '
                        'لطفاً فیلترها را محدودتر کنید.'
                    ),
                    'count': count,
                    'max':   EXCEL_MAX_ROWS,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # One DB pass, reused for both the data rows and any summary totals
        # (get_excel_summary would otherwise re-run the same query).
        objects = list(qs)
        columns = self.get_excel_columns(request)
        rows    = list(self.queryset_to_excel_rows(objects))
        content = build_excel(
            columns=columns,
            rows=rows,
            sheet_title=self.excel_sheet_title,
            report_title=self.get_excel_report_title(request),
            meta_rows=self.get_excel_meta_rows(request),
            summary=self.get_excel_summary(request, objects),
            generated_by=get_display_name(request.user),
        )
        return excel_file_response(content, filename=self.get_excel_filename())


# ── ModelAdmin mixin ──────────────────────────────────────────────────────────

class AdminExcelExportMixin:
    """Add a server-rendered Excel export view to any ``ModelAdmin``.

    Unlike ``ExcelExportMixin`` (for DRF ViewSets), this reuses the admin's
    own ``ChangeList`` — the exact object Django already builds to apply
    ``?q=`` search, ``list_filter`` values, and ``?o=`` column ordering for
    the normal paginated change list page. The export therefore never
    re-implements filtering: whatever the changelist currently shows (minus
    pagination) is exactly what gets exported.

    Wiring, per ModelAdmin subclass::

        class ProductAdmin(AdminExcelExportMixin, admin.ModelAdmin):
            excel_filename_prefix = 'product-list'
            excel_report_title    = 'گزارش فهرست محصولات'

            def get_urls(self):
                return self.get_excel_urls() + super().get_urls()

            def get_excel_columns(self, request):
                return [ExcelColumn(key='name', label='نام', data_type='text')]

            def get_excel_rows(self, request, objects):
                return [{'name': obj.name} for obj in objects]

    Optionally override ``get_excel_export_queryset`` (add select_related/
    prefetch_related on top of ``cl.queryset``, which is still lazy at this
    point), ``get_excel_meta_rows`` (extra filter-summary lines beyond the
    search/ordering ones already included), ``get_excel_summary``, or
    ``build_excel_content`` entirely (e.g. for a multi-sheet workbook).
    """

    excel_filename_prefix = None
    excel_report_title    = None
    excel_sheet_title      = 'داده‌ها'

    def get_excel_urls(self):
        opts = self.model._meta
        return [
            path(
                'export-excel/',
                self.admin_site.admin_view(self.export_excel_view),
                name=f'{opts.app_label}_{opts.model_name}_export_excel',
            ),
        ]

    def get_excel_export_queryset(self, request, cl):
        return cl.queryset

    def get_excel_columns(self, request):       # pragma: no cover
        raise NotImplementedError(
            f'{type(self).__name__} must implement get_excel_columns(request)'
        )

    def get_excel_rows(self, request, objects): # pragma: no cover
        raise NotImplementedError(
            f'{type(self).__name__} must implement get_excel_rows(request, objects)'
        )

    def get_excel_ordering_summary(self, cl) -> Optional[str]:
        """Persian summary of the changelist's current ``?o=`` ordering.

        Django admin encodes ordering as column *indices* into ``list_display``
        rather than field names, so this can't reuse ``describe_ordering``
        (built for DRF's ``?ordering=field`` convention) — it resolves each
        index through ``label_for_field``, the same helper Django's own
        changelist header rendering uses.
        """
        order_cols = cl.get_ordering_field_columns()
        if not order_cols:
            return None
        parts = []
        for idx_str, order_type in order_cols.items():
            try:
                field_name = cl.list_display[int(idx_str)]
            except (IndexError, TypeError, ValueError):
                continue
            label = label_for_field(field_name, cl.model, model_admin=self)
            parts.append(f"{label} ({'نزولی' if order_type == 'desc' else 'صعودی'})")
        return '، '.join(parts) if parts else None

    def get_excel_meta_rows(self, request, cl):
        meta = []
        search_val = request.GET.get('q')
        if search_val:
            meta.append(('جستجو', search_val))
        ordering_desc = self.get_excel_ordering_summary(cl)
        if ordering_desc:
            meta.append(('مرتب‌سازی', ordering_desc))
        return meta

    def get_excel_summary(self, request, objects):
        return None

    def get_excel_filename(self):
        return make_export_filename(self.excel_filename_prefix or 'export')

    def build_excel_content(self, request, objects, meta_rows):
        return build_excel(
            columns=self.get_excel_columns(request),
            rows=self.get_excel_rows(request, objects),
            sheet_title=self.excel_sheet_title,
            report_title=self.excel_report_title,
            meta_rows=meta_rows,
            summary=self.get_excel_summary(request, objects),
            generated_by=get_display_name(request.user),
        )

    def export_excel_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied

        cl = self.get_changelist_instance(request)
        qs = self.get_excel_export_queryset(request, cl)
        count = qs.count()
        if count > EXCEL_MAX_ROWS:
            messages.error(
                request,
                f'تعداد نتایج ({count:,}) بیشتر از حد مجاز ({EXCEL_MAX_ROWS:,}) است. '
                'لطفاً جستجو/فیلترها را محدودتر کنید.',
            )
            opts = self.model._meta
            changelist_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
            return redirect(f'{changelist_url}?{request.GET.urlencode()}')

        objects   = list(qs)
        meta_rows = self.get_excel_meta_rows(request, cl)
        content   = self.build_excel_content(request, objects, meta_rows)
        return excel_file_response(content, filename=self.get_excel_filename())
