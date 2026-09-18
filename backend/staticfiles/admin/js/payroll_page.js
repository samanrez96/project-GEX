/**
 * PayrollPageApp — API-driven payroll report page for Django Admin.
 *
 * Fetches from /api/v2/payroll/report/ with date and wage_type filters.
 * Shows summary cards and a paginated employee table.
 */
const PayrollPageApp = (function () {
    'use strict';

    var REPORT_URL = '/api/v2/payroll/report/';
    var COLS       = 6;

    var currentPage = 1;
    var pageSize    = 50;
    var filters     = {
        year:      '',
        month:     '',
        wage_type: 'both',
    };
    var allExpanded = false;

    // ── Utilities ────────────────────────────────────────────────

    // true for null/undefined/NaN/"0"/"0.00"/Decimal-like zero strings —
    // false for any other numeric value, including small non-zero ones.
    function isZeroish(n) {
        if (n === null || n === undefined || n === '') return true;
        var num = parseFloat(n);
        return isNaN(num) || num === 0;
    }

    function formatPrice(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return '۰';
            var digits = Math.round(num).toLocaleString('en-US', { maximumFractionDigits: 0 }).replace(/,/g, '٬');
            return window.PersianFormat ? window.PersianFormat.toPersianDigits(digits) : digits;
        } catch (_) { return '۰'; }
    }

    // Hours keep their fractional part (7.5, 12.25) — unlike money, they
    // must never be rounded to a whole number.
    function formatHours(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return '۰';
            var rounded = Math.round(num * 100) / 100;
            var parts = String(rounded).split('.');
            var intDigits = parseInt(parts[0], 10).toLocaleString('en-US').replace(/,/g, '٬');
            var result = parts.length > 1 ? intDigits + '.' + parts[1] : intDigits;
            return window.PersianFormat ? window.PersianFormat.toPersianDigits(result) : result;
        } catch (_) { return '۰'; }
    }

    // Display-only zero rendering: the dash is never sent back to the API,
    // it only replaces a zero/absent component amount in the table so the
    // eye isn't drawn to rows of "۰ تومان". total_payment must never use
    // this — it always shows the real (possibly zero) final result.
    function formatMoneyOrDash(n) {
        if (isZeroish(n)) return '—';
        return formatPrice(n) + ' تومان';
    }

    function formatHoursOrDash(n) {
        if (isZeroish(n)) return '—';
        return formatHours(n) + ' ساعت';
    }

    function escapeHtml(s) {
        if (s === null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ── Build API params ─────────────────────────────────────────

    function buildParams() {
        var p = new URLSearchParams();
        if (filters.year)      p.set('year', filters.year);
        if (filters.month)     p.set('month', filters.month);
        if (filters.wage_type && filters.wage_type !== 'both') p.set('wage_type', filters.wage_type);
        return p;
    }

    // ── Fetch report ─────────────────────────────────────────────

    function fetchReport() {
        showLoading();

        var url = REPORT_URL + '?' + buildParams().toString();
        fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401) {
                    window.location.href = '/admin/login/?next=' + encodeURIComponent(window.location.pathname);
                    return null;
                }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                renderSummary(data);
                renderPeriodSubtitle(data);
                renderRows(data.employees || []);
                hideLoading();
            })
            .catch(function (err) {
                showError(err.message);
                hideLoading();
            });
    }

    // ── Render summary cards ─────────────────────────────────────

    function renderSummary(data) {
        setText('py-total-fixed', formatPrice(data.total_fixed_salary) + ' تومان');
        setText('py-total-commission', formatPrice(data.total_commission) + ' تومان');
        setText('py-total-hourly', formatPrice(data.total_hourly_salary) + ' تومان');
        setText('py-total-hours', formatHours(data.total_hours_worked) + ' ساعت');
        setText('py-total-labor', formatPrice(data.total_labor_cost) + ' تومان');
        var countFmt = window.PersianFormat ? window.PersianFormat.toPersianDigits(String(data.employee_count || 0)) : String(data.employee_count || 0);
        setText('py-employee-count', countFmt);
    }

    function renderPeriodSubtitle(data) {
        var el = document.getElementById('py-period-subtitle');
        if (!el) return;
        if (data.start_date && data.end_date) {
            el.textContent = data.start_date + ' تا ' + data.end_date;
        } else {
            el.textContent = 'همه دوره‌ها';
        }
    }

    // ── Render table rows ────────────────────────────────────────

    // Six visible cells, every value read by its named backend field — never
    // by array/object position — so a backend field-order change can never
    // silently shift a value into the wrong column. Purchase/surgery
    // commission are not permanent columns: they live in a per-row detail
    // row that expands on demand, keyed by the same employee_id.
    function renderRows(employees) {
        var tbody   = document.getElementById('py-tbody');
        var emptyEl = document.getElementById('py-empty-state');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!employees || employees.length === 0) {
            if (emptyEl) {
                var hasFilters = !!(filters.year || filters.month || (filters.wage_type && filters.wage_type !== 'both'));
                var titleEl = document.getElementById('py-empty-title');
                var descEl  = document.getElementById('py-empty-desc');
                var clearBtn = document.getElementById('py-clear-filters-btn');
                if (hasFilters) {
                    if (titleEl) titleEl.textContent = 'داده‌ای یافت نشد';
                    if (descEl)  descEl.textContent  = 'فیلترها را تغییر دهید.';
                }
                if (clearBtn) clearBtn.style.display = hasFilters ? '' : 'none';
                emptyEl.style.display = '';
            }
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        employees.forEach(function (emp) {
            var rowId        = 'py-detail-' + emp.employee_id;
            var purchaseComm = parseFloat(emp.purchase_commission) || 0;
            var surgeryComm  = parseFloat(emp.surgery_commission)  || 0;
            var totalComm    = parseFloat(emp.total_commission)    || 0;
            var fixedSalary  = parseFloat(emp.fixed_salary)        || 0;
            var hourlySalary = parseFloat(emp.hourly_salary)       || 0;
            var totalHours   = parseFloat(emp.total_hours_worked)  || 0;
            var totalPayment = parseFloat(emp.total_payment)       || 0;
            var hourlyIsZero = isZeroish(hourlySalary) && isZeroish(totalHours);

            var mainRow = document.createElement('tr');
            mainRow.className = 'payroll-table__row';
            mainRow.innerHTML =
                '<td class="payroll-table__employee">'
                +   '<button type="button" class="payroll-table__toggle" aria-expanded="false" aria-controls="' + rowId + '">'
                +     '<span class="payroll-table__chevron" aria-hidden="true"></span>'
                +     '<a href="/admin/employees/employee/' + emp.employee_id + '/detail/" class="payroll-table__employee-link">' + escapeHtml(emp.employee_name) + '</a>'
                +   '</button>'
                + '</td>'
                + '<td class="payroll-table__position"><span class="payroll-table__badge">' + escapeHtml(emp.job_position) + '</span></td>'
                + '<td><span class="payroll-table__amount">' + formatMoneyOrDash(fixedSalary) + '</span></td>'
                + '<td><span class="payroll-table__amount payroll-table__amount--commission">' + formatMoneyOrDash(totalComm) + '</span></td>'
                + '<td>' + (
                      hourlyIsZero
                        ? '<span class="payroll-table__amount">—</span>'
                        : '<span class="payroll-table__hourly">'
                          + '<span class="payroll-table__amount">' + formatMoneyOrDash(hourlySalary) + '</span>'
                          + '<span class="payroll-table__hourly-secondary">' + formatHoursOrDash(totalHours) + '</span>'
                          + '</span>'
                  )
                + '</td>'
                + '<td><span class="payroll-table__amount payroll-table__amount--total">' + formatPrice(totalPayment) + ' تومان</span></td>';

            var detailRow = document.createElement('tr');
            detailRow.className = 'payroll-table__detail-row';
            detailRow.id = rowId;
            detailRow.hidden = true;
            detailRow.innerHTML =
                '<td colspan="' + COLS + '">'
                +   '<div class="payroll-table__detail-grid">'
                +     '<div class="payroll-table__detail-item"><span class="payroll-table__detail-label">کمیسیون خرید</span><span class="payroll-table__detail-value">' + formatMoneyOrDash(purchaseComm) + '</span></div>'
                +     '<div class="payroll-table__detail-item"><span class="payroll-table__detail-label">کمیسیون عمل</span><span class="payroll-table__detail-value">' + formatMoneyOrDash(surgeryComm) + '</span></div>'
                +     '<div class="payroll-table__detail-item"><span class="payroll-table__detail-label">ساعات کارکرد</span><span class="payroll-table__detail-value">' + formatHoursOrDash(totalHours) + '</span></div>'
                +   '</div>'
                + '</td>';

            tbody.appendChild(mainRow);
            tbody.appendChild(detailRow);
        });

        if (allExpanded) setAllExpanded(true);
    }

    function toggleRow(toggleBtn) {
        var detailId  = toggleBtn.getAttribute('aria-controls');
        var detailRow = document.getElementById(detailId);
        if (!detailRow) return;
        var expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
        toggleBtn.setAttribute('aria-expanded', String(!expanded));
        detailRow.hidden = expanded;
        var mainRow = toggleBtn.closest('tr');
        if (mainRow) mainRow.classList.toggle('payroll-table__row--expanded', !expanded);
    }

    function setAllExpanded(expand) {
        var tbody = document.getElementById('py-tbody');
        if (!tbody) return;
        var toggles = tbody.querySelectorAll('.payroll-table__toggle');
        for (var i = 0; i < toggles.length; i++) {
            var btn = toggles[i];
            var isExpanded = btn.getAttribute('aria-expanded') === 'true';
            if (isExpanded !== expand) toggleRow(btn);
        }
    }

    // ── Loading / Error states ───────────────────────────────────

    function showLoading() {
        var tbody = document.getElementById('py-tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="' + COLS + '" class="py-table-loading" style="text-align:center">در حال بارگذاری…</td></tr>';
        }
        var emptyEl = document.getElementById('py-empty-state');
        if (emptyEl) emptyEl.style.display = 'none';
    }

    function hideLoading() {
        // Loading is replaced by renderRows or showError
    }

    function showError(msg) {
        var tbody = document.getElementById('py-tbody');
        if (tbody) {
            tbody.innerHTML =
                '<tr><td colspan="' + COLS + '" style="text-align:center;color:var(--red);padding:24px">'
                + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</td></tr>';
        }
    }

    function setText(id, val) {
        var el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    // ── Sync UI controls ↔ state ─────────────────────────────────

    function syncControlsToState() {
        var yearEl  = document.getElementById('py-filter-year');
        var monthEl = document.getElementById('py-filter-month');
        var typeEl  = document.getElementById('py-filter-wage-type');

        if (yearEl)  yearEl.value  = filters.year;
        if (monthEl) monthEl.value = filters.month;
        if (typeEl)  typeEl.value  = filters.wage_type;
    }

    // ── Event wiring ─────────────────────────────────────────────

    function bindEvents() {
        var applyBtn    = document.getElementById('py-apply-btn');
        var resetBtn    = document.getElementById('py-reset-btn');
        var clearBtn    = document.getElementById('py-clear-filters-btn');
        var expandAllBtn = document.getElementById('py-expand-all-btn');
        var tbody       = document.getElementById('py-tbody');

        if (tbody) {
            tbody.addEventListener('click', function (ev) {
                var toggleBtn = ev.target.closest('.payroll-table__toggle');
                if (toggleBtn) toggleRow(toggleBtn);
            });
        }

        if (expandAllBtn) {
            expandAllBtn.addEventListener('click', function () {
                allExpanded = !allExpanded;
                setAllExpanded(allExpanded);
                expandAllBtn.setAttribute('aria-pressed', String(allExpanded));
                expandAllBtn.textContent = allExpanded ? 'بستن جزئیات همه' : 'نمایش جزئیات همه';
            });
        }

        if (applyBtn) {
            applyBtn.addEventListener('click', function () {
                var yearEl  = document.getElementById('py-filter-year');
                var monthEl = document.getElementById('py-filter-month');
                var typeEl  = document.getElementById('py-filter-wage-type');

                filters.year      = yearEl  ? yearEl.value  : '';
                filters.month     = monthEl ? monthEl.value : '';
                filters.wage_type = typeEl  ? typeEl.value  : 'both';

                fetchReport();
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', function () {
                filters = { year: '', month: '', wage_type: 'both' };
                syncControlsToState();
                fetchReport();
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                filters = { year: '', month: '', wage_type: 'both' };
                syncControlsToState();
                fetchReport();
            });
        }
    }

    // ── Init ─────────────────────────────────────────────────────

    function init() {
        bindEvents();
        fetchReport();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', PayrollPageApp.init);
