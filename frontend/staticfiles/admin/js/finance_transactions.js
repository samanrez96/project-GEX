/**
 * FinanceTransactionsApp — API-driven transactions list for Django Admin.
 *
 * Fetches from /api/v1/finance/transactions/ with filters for type, status,
 * category, and date range. Shows summary cards and a paginated table.
 */
const FinanceTransactionsApp = (function () {
    'use strict';

    var API_URL         = '/api/v1/finance/transactions/';
    var CATEGORIES_URL  = '/api/v1/finance/categories/';
    var BALANCE_URL     = '/api/v1/finance/reports/balance/';
    var COLS            = 6;

    var currentPage     = 1;
    var pageSize        = 25;
    var filters         = {
        type:       '',
        status:     '',
        category:   '',
        date_from:  '',
        date_to:    '',
    };

    var STATUS_MAP = {
        'pending':   { label: 'در انتظار پرداخت', cls: 'pending' },
        'partial':   { label: 'پرداخت ناقص',      cls: 'partial' },
        'paid':      { label: 'پرداخت شده',       cls: 'paid' },
        'cancelled': { label: 'لغو شده',          cls: 'cancelled' },
    };

    var TYPE_MAP = {
        'income':  { label: 'درآمد', cls: 'income' },
        'expense': { label: 'هزینه', cls: 'expense' },
    };

    // ── Utilities ────────────────────────────────────────────────

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function formatPrice(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return String(n);
            var digits = Math.round(num).toLocaleString('en-US', { maximumFractionDigits: 0 }).replace(/,/g, '٬');
            return window.PersianFormat ? window.PersianFormat.toPersianDigits(digits) : digits;
        } catch (_) { return String(n); }
    }

    function formatDate(dateStr) {
        if (!dateStr) return '—';
        return window.PersianFormat
            ? window.PersianFormat.formatJalaliDate(dateStr)
            : String(dateStr).slice(0, 10);
    }

    function getCsrfToken() {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var pair = cookies[i].trim().split('=');
            if (pair[0] === 'csrftoken') return decodeURIComponent(pair[1]);
        }
        return '';
    }

    // ── Build API params ─────────────────────────────────────────

    function buildParams() {
        var p = new URLSearchParams();
        p.set('page', String(currentPage));
        p.set('page_size', String(pageSize));
        if (filters.type)      p.set('transaction_type', filters.type);
        if (filters.status)    p.set('payment_status', filters.status);
        if (filters.category)  p.set('category', filters.category);
        if (filters.date_from) p.set('transaction_date__gte', filters.date_from);
        if (filters.date_to)   p.set('transaction_date__lte', filters.date_to);
        return p;
    }

    // ── Fetch transactions ───────────────────────────────────────

    function fetchTransactions() {
        showLoading();

        var url = API_URL + '?' + buildParams().toString();
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
                renderRows(data.results || []);
                renderPagination(data);
                hideLoading();
            })
            .catch(function (err) {
                showError(err.message);
                hideLoading();
            });
    }

    // ── Fetch summary ────────────────────────────────────────────

    function fetchSummary() {
        var p = new URLSearchParams();
        if (filters.date_from) p.set('start_date', filters.date_from);
        if (filters.date_to)   p.set('end_date', filters.date_to);

        var url = BALANCE_URL + (p.toString() ? '?' + p.toString() : '');
        fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) return null;
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                var bal = parseFloat(data.final_balance) || 0;
                setText('ft-total-income', formatPrice(data.total_income) + ' تومان');
                setText('ft-total-expense', formatPrice(data.total_expense) + ' تومان');
                setText('ft-final-balance', formatPrice(data.final_balance) + ' تومان');

                var card = document.getElementById('ft-balance-card');
                if (card) {
                    card.classList.toggle('ft-positive', bal >= 0);
                    card.classList.toggle('ft-negative', bal < 0);
                }
            })
            .catch(function () {});
    }

    function fetchTransactionCount() {
        var p = new URLSearchParams();
        p.set('page_size', '1');
        if (filters.type)      p.set('transaction_type', filters.type);
        if (filters.status)    p.set('payment_status', filters.status);
        if (filters.category)  p.set('category', filters.category);
        if (filters.date_from) p.set('transaction_date__gte', filters.date_from);
        if (filters.date_to)   p.set('transaction_date__lte', filters.date_to);

        var url = API_URL + '?' + p.toString();
        fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) return null;
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                setText('ft-transaction-count', formatPrice(data.count || 0));
            })
            .catch(function () {});
    }

    // ── Load categories ──────────────────────────────────────────

    function loadCategories() {
        var sel = document.getElementById('ft-filter-category');
        if (!sel) return;

        fetch(CATEGORIES_URL + '?page_size=200', { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) return null;
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                var cats = data.results || data;
                if (!Array.isArray(cats)) return;
                cats.forEach(function (c) {
                    var opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = c.name;
                    sel.appendChild(opt);
                });
            })
            .catch(function () {});
    }

    // ── Render table rows ────────────────────────────────────────

    function renderRows(results) {
        var tbody   = document.getElementById('ft-tbody');
        var emptyEl = document.getElementById('ft-empty-state');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!results || results.length === 0) {
            if (emptyEl) {
                var hasFilters = !!(filters.type || filters.status || filters.category || filters.date_from || filters.date_to);
                var titleEl = emptyEl.querySelector('#ft-empty-title');
                var descEl  = emptyEl.querySelector('#ft-empty-desc');
                var clearBtn = document.getElementById('ft-clear-search-btn');
                if (hasFilters) {
                    if (titleEl) titleEl.textContent = 'تراکنشی پیدا نشد';
                    if (descEl)  descEl.textContent  = 'فیلترها را تغییر دهید.';
                }
                if (clearBtn) clearBtn.style.display = hasFilters ? '' : 'none';
                emptyEl.style.display = '';
            }
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        results.forEach(function (t) {
            var row = document.createElement('tr');
            var detailUrl = '/admin/finance/transaction/' + t.id + '/change/';

            var typeInfo = TYPE_MAP[t.transaction_type] || { label: t.transaction_type || '—', cls: '' };
            var statusInfo = STATUS_MAP[t.payment_status] || { label: t.payment_status_display || t.payment_status || '—', cls: '' };

            var amountClass = t.transaction_type === 'income' ? 'ft-amount--income' : 'ft-amount--expense';

            row.style.cursor = 'pointer';
            row.innerHTML =
                '<td>' + formatDate(t.transaction_date) + '</td>'
                + '<td><span class="ft-badge ft-badge--' + typeInfo.cls + '">' + typeInfo.label + '</span></td>'
                + '<td>' + escapeHtml((t.category_detail && t.category_detail.name) || t.category_name || '—') + '</td>'
                + '<td><span class="ft-amount ' + amountClass + '">' + formatPrice(t.amount) + '</span></td>'
                + '<td><span class="ft-badge ft-badge--' + statusInfo.cls + '">' + statusInfo.label + '</span></td>'
                + '<td>' + escapeHtml(t.description || '—') + '</td>';

            row.addEventListener('click', function () {
                window.location.href = detailUrl;
            });

            tbody.appendChild(row);
        });
    }

    // ── Render pagination ────────────────────────────────────────

    function renderPagination(data) {
        var pagesEl = document.getElementById('ft-pagination-pages');
        var infoEl  = document.getElementById('ft-pagination-info');
        if (!pagesEl) return;

        var totalPages = data.total_pages || 1;
        var totalItems = data.count || 0;
        var start = (currentPage - 1) * pageSize + 1;
        var end   = Math.min(currentPage * pageSize, totalItems);

        if (infoEl) {
            infoEl.textContent = totalItems > 0
                ? 'نمایش ' + start + ' تا ' + end + ' از ' + formatPrice(totalItems) + ' تراکنش'
                : '';
        }

        pagesEl.innerHTML = '';
        if (totalPages <= 1) return;

        // Previous
        var prevBtn = document.createElement('button');
        prevBtn.className = 'ft-page-btn' + (currentPage === 1 ? ' ft-page-btn--disabled' : '');
        prevBtn.textContent = '«';
        prevBtn.addEventListener('click', function () {
            if (currentPage > 1) { currentPage--; fetchTransactions(); }
        });
        pagesEl.appendChild(prevBtn);

        // Page numbers
        var startPage = Math.max(1, currentPage - 2);
        var endPage   = Math.min(totalPages, currentPage + 2);

        if (startPage > 1) {
            var btn1 = document.createElement('button');
            btn1.className = 'ft-page-btn';
            btn1.textContent = '1';
            btn1.addEventListener('click', function () { currentPage = 1; fetchTransactions(); });
            pagesEl.appendChild(btn1);
            if (startPage > 2) {
                var dots = document.createElement('span');
                dots.textContent = '...';
                dots.style.padding = '0 4px';
                dots.style.color = 'var(--muted)';
                pagesEl.appendChild(dots);
            }
        }

        for (var i = startPage; i <= endPage; i++) {
            (function (page) {
                var btn = document.createElement('button');
                btn.className = 'ft-page-btn' + (page === currentPage ? ' ft-page-btn--active' : '');
                btn.textContent = page;
                btn.addEventListener('click', function () { currentPage = page; fetchTransactions(); });
                pagesEl.appendChild(btn);
            })(i);
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                var dots2 = document.createElement('span');
                dots2.textContent = '...';
                dots2.style.padding = '0 4px';
                dots2.style.color = 'var(--muted)';
                pagesEl.appendChild(dots2);
            }
            var btnLast = document.createElement('button');
            btnLast.className = 'ft-page-btn';
            btnLast.textContent = totalPages;
            btnLast.addEventListener('click', function () { currentPage = totalPages; fetchTransactions(); });
            pagesEl.appendChild(btnLast);
        }

        // Next
        var nextBtn = document.createElement('button');
        nextBtn.className = 'ft-page-btn' + (currentPage === totalPages ? ' ft-page-btn--disabled' : '');
        nextBtn.textContent = '»';
        nextBtn.addEventListener('click', function () {
            if (currentPage < totalPages) { currentPage++; fetchTransactions(); }
        });
        pagesEl.appendChild(nextBtn);
    }

    // ── Loading / Error states ───────────────────────────────────

    function showLoading() {
        var tbody = document.getElementById('ft-tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="' + COLS + '" class="ft-table-loading">در حال بارگذاری…</td></tr>';
        }
        var emptyEl = document.getElementById('ft-empty-state');
        if (emptyEl) emptyEl.style.display = 'none';
    }

    function hideLoading() {
        // Loading is replaced by renderRows or showError
    }

    function showError(msg) {
        var tbody = document.getElementById('ft-tbody');
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
        var typeEl = document.getElementById('ft-filter-type');
        var statusEl = document.getElementById('ft-filter-status');
        var catEl = document.getElementById('ft-filter-category');
        var dateFromEl = document.getElementById('ft-filter-date-from');
        var dateToEl = document.getElementById('ft-filter-date-to');

        if (typeEl)     typeEl.value     = filters.type;
        if (statusEl)   statusEl.value   = filters.status;
        if (catEl)      catEl.value      = filters.category;
        if (dateFromEl) dateFromEl.value = filters.date_from;
        if (dateToEl)   dateToEl.value   = filters.date_to;
    }

    function loadAll() {
        currentPage = 1;
        fetchTransactions();
        fetchSummary();
        fetchTransactionCount();
    }

    // ── Event wiring ─────────────────────────────────────────────

    function bindEvents() {
        var applyBtn = document.getElementById('ft-apply-btn');
        var resetBtn = document.getElementById('ft-reset-btn');
        var clearBtn = document.getElementById('ft-clear-search-btn');

        if (applyBtn) {
            applyBtn.addEventListener('click', function () {
                var typeEl     = document.getElementById('ft-filter-type');
                var statusEl   = document.getElementById('ft-filter-status');
                var catEl      = document.getElementById('ft-filter-category');
                var dateFromEl = document.getElementById('ft-filter-date-from');
                var dateToEl   = document.getElementById('ft-filter-date-to');

                filters.type      = typeEl     ? typeEl.value     : '';
                filters.status    = statusEl   ? statusEl.value   : '';
                filters.category  = catEl      ? catEl.value      : '';
                filters.date_from = dateFromEl ? dateFromEl.value : '';
                filters.date_to   = dateToEl   ? dateToEl.value   : '';

                loadAll();
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', function () {
                filters = { type: '', status: '', category: '', date_from: '', date_to: '' };
                syncControlsToState();
                loadAll();
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                filters = { type: '', status: '', category: '', date_from: '', date_to: '' };
                syncControlsToState();
                loadAll();
            });
        }
    }

    // ── Init ─────────────────────────────────────────────────────

    function init() {
        bindEvents();
        loadCategories();
        loadAll();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', FinanceTransactionsApp.init);
