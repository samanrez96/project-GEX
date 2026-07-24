/* Main Dashboard — fetch API data, render metric cards + cost breakdown + recent surgeries */
(function () {
    'use strict';

    var API_BALANCE = window.MD_API_BALANCE;
    var API_HISTORY = window.MD_API_HISTORY;

    /* ── Persian number helpers ───────────────────────────────────── */

    /* toPersian is provided by table_pagination.js (loaded before this script).
       Inline fallback for safety. */
    function toPersian(n) {
        if (window.TablePagination && window.TablePagination.toPersian) {
            return window.TablePagination.toPersian(n);
        }
        return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; });
    }

    /* Format a monetary value.
       Problem: fa-IR locale emits U+066C (Arabic Thousands Separator ٬) which
       renders as a floating isolated mark in RTL context.
       Fix: format with en-US (ASCII commas), then convert digits to Persian.
       Negative values use a trailing proper minus (U+2212) for RTL readability. */
    function fmt(num) {
        if (num === null || num === undefined || num === '') return '—';
        var n = parseFloat(num);
        if (isNaN(n)) return '—';
        var isNeg = n < 0;
        var abs   = Math.abs(n);
        var formatted = abs.toLocaleString('en-US', { maximumFractionDigits: 0 });
        var persian   = toPersian(formatted);   // converts digits; ASCII commas stay
        return isNeg ? persian + '−' : persian;
    }

    function setText(id, val) {
        var el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function setClass(id, add, remove) {
        var el = document.getElementById(id);
        if (!el) return;
        if (add)    el.classList.add(add);
        if (remove) el.classList.remove(remove);
    }

    function fmtDate(dateStr) {
        if (!dateStr) return '—';
        return window.PersianFormat
            ? window.PersianFormat.formatJalaliDate(dateStr)
            : toPersian(String(dateStr).slice(0, 10));
    }

    /* ── Cost breakdown bars ──────────────────────────────────────── */

    function renderCostBreakdown(data) {
        var equipment  = parseFloat(data.total_equipment_cost) || 0;
        var medicine   = parseFloat(data.total_medicine_cost)  || 0;
        var employee   = parseFloat(data.total_employee_cost)  || 0;
        var totalExp   = parseFloat(data.total_expense)        || 0;
        var other      = Math.max(0, totalExp - equipment - medicine - employee);
        var grandTotal = equipment + medicine + employee + other;

        function applyBar(barId, valId, value) {
            var pct   = grandTotal > 0 ? (value / grandTotal * 100) : 0;
            var barEl = document.getElementById(barId);
            var valEl = document.getElementById(valId);
            if (barEl) barEl.style.width = pct.toFixed(1) + '%';
            if (valEl) valEl.textContent = fmt(value);
        }

        applyBar('md-cb-bar-equipment', 'md-cb-val-equipment', equipment);
        applyBar('md-cb-bar-medicine',  'md-cb-val-medicine',  medicine);
        applyBar('md-cb-bar-employee',  'md-cb-val-employee',  employee);
        applyBar('md-cb-bar-other',     'md-cb-val-other',     other);

    }

    /* ── Balance API ──────────────────────────────────────────────── */

    function loadBalance() {
        fetch(API_BALANCE, { credentials: 'same-origin' })
            .then(function (resp) { if (!resp.ok) return null; return resp.json(); })
            .then(function (data) {
                if (!data) return;
                setText('md-total-income',   fmt(data.total_income));
                setText('md-total-expense',  fmt(data.total_expense));
                setText('md-final-balance',  fmt(data.final_balance));
                setText('md-employee-cost',  fmt(data.total_employee_cost));
                setText('md-equipment-cost', fmt(data.total_equipment_cost));
                setText('md-medicine-cost',  fmt(data.total_medicine_cost));
                setText('md-commission',     fmt(data.center_commission_income));

                var balance = parseFloat(data.final_balance || 0);
                if (!isNaN(balance)) {
                    if (balance >= 0) {
                        setClass('md-balance-card', 'md-positive', 'md-negative');
                    } else {
                        setClass('md-balance-card', 'md-negative', 'md-positive');
                    }
                }

                renderCostBreakdown(data);
            }).catch(function () {});
    }

    /* ── Surgery count for current Gregorian month ───────────────── */

    function loadSurgeryCount() {
        var now      = new Date();
        var year     = now.getFullYear();
        var month    = now.getMonth() + 1;
        var pad      = function (n) { return n < 10 ? '0' + n : String(n); };
        var firstDay = year + '-' + pad(month) + '-01';
        var lastDate = new Date(year, month, 0).getDate();
        var lastDay  = year + '-' + pad(month) + '-' + pad(lastDate);
        var url      = API_HISTORY
            + '?surgery_date_from=' + firstDay
            + '&surgery_date_to='   + lastDay
            + '&page_size=1';

        fetch(url, { credentials: 'same-origin' })
            .then(function (resp) { if (!resp.ok) return null; return resp.json(); })
            .then(function (data) {
                if (!data) return;
                var count = data.count !== undefined ? toPersian(data.count) : '—';
                setText('md-surgery-count', count);
            }).catch(function () {});
    }

    /* ── Recent surgeries table ───────────────────────────────────── */

    var STATUS_MAP = {
        'planned':     { cls: 'planned',     label: 'برنامه‌ریزی شده' },
        'in_progress': { cls: 'in-progress', label: 'در حال انجام' },
        'completed':   { cls: 'completed',   label: 'انجام شده' },
        'cancelled':   { cls: 'cancelled',   label: 'لغو شده' },
    };

    function statusBadge(status, statusDisplay) {
        var info = STATUS_MAP[status];
        if (!info) { info = { cls: status || '', label: statusDisplay || status || '—' }; }
        return '<span class="sh-badge sh-badge--' + info.cls + '">' + info.label + '</span>';
    }

    function renderSurgeries(items) {
        var tbody = document.getElementById('md-surgeries-tbody');
        if (!tbody) return;
        if (!items || !items.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="md-table-loading">هیچ عملی ثبت نشده</td></tr>';
            return;
        }
        tbody.innerHTML = items.map(function (s) {
            var detailUrl = '/admin/surgeries/surgeryhistory/' + s.id + '/change/';
            return (
                '<tr>' +
                '<td><a class="sh-name-link" href="' + detailUrl + '">' + (s.patient_name || '—') + '</a></td>' +
                '<td>' + (s.surgery_type_name || '—') + '</td>' +
                '<td>' + fmtDate(s.surgery_date) + '</td>' +
                '<td>' + fmt(s.amount) + '</td>' +
                '<td>' + statusBadge(s.status, s.status_display) + '</td>' +
                '</tr>'
            );
        }).join('');
    }

    function loadRecentSurgeries() {
        var tbody = document.getElementById('md-surgeries-tbody');
        var url   = API_HISTORY + '?page_size=8&ordering=-surgery_date';
        fetch(url, { credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="md-table-loading">خطا در بارگذاری</td></tr>';
                    return null;
                }
                return resp.json();
            })
            .then(function (data) { if (!data) return; renderSurgeries(data.results || []); })
            .catch(function () {
                if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="md-table-loading">خطا در بارگذاری</td></tr>';
            });
    }

    /* ── Init ─────────────────────────────────────────────────────── */

    function init() {
        loadBalance();
        loadSurgeryCount();
        loadRecentSurgeries();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
