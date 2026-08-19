/**
 * PurchaseListApp — API-driven purchase list for Django Admin.
 *
 * Auth: SessionAuthentication — admin session cookie used for same-origin fetch().
 * If the session expires the API returns 401 → we redirect to login.
 */
const PurchaseListApp = (function () {
    'use strict';

    var API_URL     = '/api/v2/inventory/purchases/';
    var VENDORS_URL = '/api/v2/inventory/vendors/';

    // ── State ────────────────────────────────────────────────────
    var state = {
        search:    '',
        vendor:    null,
        status:    null,
        date_from: null,
        date_to:   null,
        page:      1,
        page_size: 25,
        ordering:  '-purchase_date',
        loading:   false,
        data:      null,
    };

    // ── Utilities ────────────────────────────────────────────────

    function debounce(fn, ms) {
        var timer;
        return function () {
            clearTimeout(timer);
            timer = setTimeout(fn, ms);
        };
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function toPersian(n) {
        return String(n).replace(/\d/g, function (d) {
            return '۰۱۲۳۴۵۶۷۸۹'[d];
        });
    }

    function formatAmount(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return '—';
            return Math.round(num).toLocaleString('fa-IR');
        } catch (_) {
            return String(n);
        }
    }

    function formatDate(iso) {
        return window.PersianFormat
            ? window.PersianFormat.formatJalaliDate(iso)
            : (iso ? String(iso).slice(0, 10) : '—');
    }

    function getCsrfToken() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? match[1] : '';
    }

    // ── Build URL params from state ───────────────────────────────
    function buildParams() {
        var p = new URLSearchParams();
        p.set('page',      String(state.page));
        p.set('page_size', String(state.page_size));
        p.set('ordering',  state.ordering);
        if (state.search)    p.set('search',    state.search);
        if (state.vendor)    p.set('vendor',    state.vendor);
        if (state.status)    p.set('status',    state.status);
        if (state.date_from) p.set('date_from', state.date_from);
        if (state.date_to)   p.set('date_to',   state.date_to);
        return p;
    }

    // Excel export button — always reflects the current filters/search/
    // ordering (minus pagination), which the export endpoint ignores anyway.
    function updateExportButton() {
        var btn = document.getElementById('pu-export-btn');
        if (!btn) return;
        var p = buildParams();
        p.set('export', 'excel');
        btn.setAttribute('href', API_URL + '?' + p.toString());
    }

    // ── Fetch purchases ───────────────────────────────────────────
    function fetchPurchases() {
        if (state.loading) return;
        state.loading = true;
        showLoading();

        updateExportButton();
        var url = API_URL + '?' + buildParams().toString();
        fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401) {
                    window.location.href =
                        '/admin/login/?next=' + encodeURIComponent(window.location.pathname);
                    return null;
                }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                state.data    = data;
                state.loading = false;
                hideLoading();
                renderTable(data.results);
                renderPagination(data);
                renderSummaryCards(data.results);
                updateURL();
                updateFilterDots();
            })
            .catch(function (err) {
                state.loading = false;
                hideLoading();
                showError(err.message);
            });
    }

    // ── Summary card — total amount only ─────────────────────────
    function renderSummaryCards(results) {
        var total = 0;
        if (results && results.length) {
            results.forEach(function (p) {
                if (p.total_amount) total += Math.round(parseFloat(p.total_amount)) || 0;
            });
        }
        var el = document.getElementById('pu-total-amount');
        if (el) el.textContent = formatAmount(total);
    }

    // ── Status badge HTML ─────────────────────────────────────────
    // status     = raw enum value: "PENDING" | "CONFIRMED" | "CANCELLED"
    // statusDisplay = Persian label from API (status_display field)
    function statusBadge(status, statusDisplay) {
        var text = statusDisplay || status;
        if (status === 'PENDING') {
            return '<span class="pu-badge pu-badge--pending">⏳ ' + escapeHtml(text) + '</span>';
        }
        if (status === 'CONFIRMED') {
            return '<span class="pu-badge pu-badge--confirmed">✓ ' + escapeHtml(text) + '</span>';
        }
        if (status === 'CANCELLED') {
            return '<span class="pu-badge pu-badge--cancelled">✕ ' + escapeHtml(text) + '</span>';
        }
        return '<span class="pu-badge">' + escapeHtml(text) + '</span>';
    }

    // ── Render table rows ─────────────────────────────────────────
    function renderTable(results) {
        var tbody = document.getElementById('pu-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!results || results.length === 0) {
            showEmpty();
            return;
        }
        hideEmpty();

        var offset = (state.page - 1) * state.page_size;

        results.forEach(function (p, idx) {
            var row = document.createElement('tr');
            row.setAttribute('data-purchase-id', String(p.id));

            var editUrl = '/admin/inventory/purchase/' + p.id + '/change/';

            var productHtml = escapeHtml(p.product_names_display || '—');

            row.innerHTML =
                '<td class="pu-cell-num">'       + toPersian(offset + idx + 1) + '</td>'
                + '<td class="pu-cell-product">' + productHtml + '</td>'
                + '<td class="pu-cell-vendor">'  + escapeHtml(p.vendor_name || '—') + '</td>'
                + '<td class="pu-cell-date">'    + formatDate(p.purchase_date) + '</td>'
                + '<td class="pu-cell-items">'   + toPersian(p.item_count || 0) + '</td>'
                + '<td class="pu-cell-amount">'  + (p.average_unit_price ? formatAmount(p.average_unit_price) : '—') + '</td>'
                + '<td class="pu-cell-amount">'  + formatAmount(p.total_amount) + '</td>'
                + '<td class="pu-cell-status">'  + statusBadge(p.status, p.status_display) + '</td>';

            row.style.cursor = 'pointer';
            row.addEventListener('click', function () {
                window.location.href = editUrl;
            });

            tbody.appendChild(row);
        });
    }


    // ── Render pagination bar (shared via TablePagination module) ──
    function renderPagination(data) {
        TablePagination.renderControls({
            pagesId:      'pu-pagination-pages',
            infoId:       'pu-pagination-info',
            data:         data,
            currentPage:  state.page,
            btnClass:     'pu-page-btn',
            recordLabel:  'خرید',
            onPageChange: goToPage,
        });
    }

    function goToPage(page) {
        state.page = page;
        fetchPurchases();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── URL sync (pushState + back button) ────────────────────────
    function updateURL() {
        history.pushState(
            {},
            '',
            window.location.pathname + '?' + buildParams().toString()
        );
    }

    function readURL() {
        var p = new URLSearchParams(window.location.search);
        if (p.has('search'))    state.search    = p.get('search');
        if (p.has('vendor'))    state.vendor    = p.get('vendor')    || null;
        if (p.has('status'))    state.status    = p.get('status')    || null;
        if (p.has('date_from')) state.date_from = p.get('date_from') || null;
        if (p.has('date_to'))   state.date_to   = p.get('date_to')   || null;
        if (p.has('page'))      state.page      = parseInt(p.get('page'),      10) || 1;
        if (p.has('page_size')) state.page_size = parseInt(p.get('page_size'), 10) || 25;
        if (p.has('ordering'))  state.ordering  = p.get('ordering');
    }

    // ── Active-filter dot indicators ──────────────────────────────
    function updateFilterDots() {
        setDot('pu-dot-vendor', !!state.vendor);
        setDot('pu-dot-date',   !!(state.date_from || state.date_to));
        setDot('pu-dot-status', !!state.status);

        var hasAny = state.vendor || state.date_from || state.date_to || state.status;
        var clearBtn = document.getElementById('pu-clear-filters');
        if (clearBtn) clearBtn.classList.toggle('pu-visible', !!hasAny);
    }

    function setDot(id, active) {
        var el = document.getElementById(id);
        if (el) el.classList.toggle('pu-active', active);
    }

    // ── Loading / error / empty state ─────────────────────────────
    function showLoading() {
        var tbody = document.getElementById('pu-tbody');
        if (!tbody) return;
        hideEmpty();
        tbody.innerHTML = [0, 1, 2].map(function () {
            return '<tr class="pu-loading-row">'
                + '<td><div class="pu-skeleton pu-skeleton-sm"></div></td>'
                + '<td><div class="pu-skeleton pu-skeleton-lg"></div></td>'
                + '<td><div class="pu-skeleton pu-skeleton-med"></div></td>'
                + '<td><div class="pu-skeleton pu-skeleton-sm"></div></td>'
                + '<td><div class="pu-skeleton pu-skeleton-sm"></div></td>'
                + '<td><div class="pu-skeleton pu-skeleton-med"></div></td>'
                + '<td><div class="pu-skeleton pu-skeleton-med"></div></td>'
                + '<td><div class="pu-skeleton pu-skeleton-sm"></div></td>'
                + '</tr>';
        }).join('');

        var spinner = document.getElementById('pu-spinner');
        if (spinner) spinner.classList.add('pu-visible');
    }

    function hideLoading() {
        var spinner = document.getElementById('pu-spinner');
        if (spinner) spinner.classList.remove('pu-visible');
    }

    function showEmpty() {
        var wrap     = document.getElementById('pu-empty-state');
        var clearBtn = document.getElementById('pu-clear-search-btn');
        var addBtn   = document.getElementById('pu-add-first-btn');
        var titleEl  = document.getElementById('pu-empty-title');
        var desc     = document.getElementById('pu-empty-desc');
        if (!wrap) return;

        var hasFilters = !!(state.search || state.vendor || state.date_from || state.date_to || state.status);

        if (hasFilters) {
            if (titleEl) titleEl.textContent = 'خریدی پیدا نشد';
            if (desc)    desc.textContent    = 'فیلترها یا بازه تاریخ خرید را تغییر دهید.';
            if (clearBtn) clearBtn.style.display = '';
            if (addBtn)   addBtn.style.display   = 'none';
        } else {
            if (titleEl) titleEl.textContent = 'هنوز خریدی ثبت نشده است';
            if (desc)    desc.textContent    = 'برای شروع مدیریت موجودی، اولین خرید را ثبت کنید.';
            if (clearBtn) clearBtn.style.display = 'none';
            if (addBtn)   addBtn.style.display   = '';
        }

        wrap.style.display = '';
        var tbody = document.getElementById('pu-tbody');
        if (tbody) tbody.innerHTML = '';
    }

    function hideEmpty() {
        var wrap = document.getElementById('pu-empty-state');
        if (wrap) wrap.style.display = 'none';
    }

    function showError(msg) {
        var tbody = document.getElementById('pu-tbody');
        if (tbody) {
            tbody.innerHTML =
                '<tr><td colspan="8" style="text-align:center;color:var(--red);padding:24px">'
                + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</td></tr>';
        }
    }

    // ── Load vendor dropdown ──────────────────────────────────────
    function loadVendors() {
        var sel = document.getElementById('pu-filter-vendor');
        if (!sel) return;

        fetch(VENDORS_URL + '?is_active=true&page_size=200', { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                var items = data.results || data;
                items.forEach(function (v) {
                    var opt = document.createElement('option');
                    opt.value       = String(v.id);
                    opt.textContent = v.name;
                    sel.appendChild(opt);
                });
                if (state.vendor) sel.value = state.vendor;
            })
            .catch(function (err) {
                console.warn('Vendor dropdown failed to load:', err);
            });
    }

    // ── Sync UI controls → state ───────────────────────────────────
    function syncControlsToState() {
        var el;
        el = document.getElementById('pu-search');
        if (el) el.value = state.search;

        el = document.getElementById('pu-filter-vendor');
        if (el) el.value = state.vendor || '';

        el = document.getElementById('pu-filter-date-from');
        if (el) el.value = state.date_from || '';

        el = document.getElementById('pu-filter-date-to');
        if (el) el.value = state.date_to || '';

        el = document.getElementById('pu-filter-status');
        if (el) el.value = state.status || '';

        el = document.getElementById('pu-page-size-select');
        if (el) el.value = String(state.page_size);

        TableFilters.syncSortControls('pu-sort-by', 'pu-sort-dir', state);
    }

    // ── Wire up all events ─────────────────────────────────────────
    function bindEvents() {
        // Search — debounced via GlobalSearch component (global_search.js)
        var searchEl = document.getElementById('pu-search');
        if (searchEl) {
            searchEl.addEventListener('global-search:changed', function (e) {
                state.search = e.detail.value;
                state.page   = 1;
                fetchPurchases();
            });
        }

        // Vendor
        var vendorEl = document.getElementById('pu-filter-vendor');
        if (vendorEl) {
            vendorEl.addEventListener('change', function () {
                state.vendor = vendorEl.value || null;
                state.page   = 1;
                fetchPurchases();
            });
        }

        // Date range — debounced so fast typing doesn't hammer the API
        var dateFromEl = document.getElementById('pu-filter-date-from');
        var dateToEl   = document.getElementById('pu-filter-date-to');
        var debouncedDate = debounce(function () {
            state.date_from = (dateFromEl && dateFromEl.value) ? dateFromEl.value : null;
            state.date_to   = (dateToEl   && dateToEl.value)   ? dateToEl.value   : null;
            state.page      = 1;
            fetchPurchases();
        }, 400);
        if (dateFromEl) dateFromEl.addEventListener('change', debouncedDate);
        if (dateToEl)   dateToEl.addEventListener('change', debouncedDate);

        // Page size
        var sizeEl = document.getElementById('pu-page-size-select');
        if (sizeEl) {
            sizeEl.addEventListener('change', function () {
                state.page_size = parseInt(sizeEl.value, 10);
                state.page      = 1;
                fetchPurchases();
            });
        }

        // Status
        var statusEl = document.getElementById('pu-filter-status');
        if (statusEl) {
            statusEl.addEventListener('change', function () {
                state.status = statusEl.value || null;
                state.page   = 1;
                fetchPurchases();
            });
        }

        // Clear filters
        var clearFiltersBtn = document.getElementById('pu-clear-filters');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', function () {
                state.vendor    = null;
                state.date_from = null;
                state.date_to   = null;
                state.status    = null;
                state.page      = 1;
                syncControlsToState();
                fetchPurchases();
            });
        }

        // "Clear filters" button (shown in empty state — clears search AND all filters)
        var clearSearchBtn = document.getElementById('pu-clear-search-btn');
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', function () {
                state.search    = '';
                state.vendor    = null;
                state.date_from = null;
                state.date_to   = null;
                state.status    = null;
                state.page      = 1;
                syncControlsToState();
                fetchPurchases();
            });
        }

        // Back / forward navigation
        window.addEventListener('popstate', function () {
            readURL();
            syncControlsToState();
            fetchPurchases();
        });

        // Sort controls
        TableFilters.bindSortControls('pu-sort-by', 'pu-sort-dir', state, fetchPurchases);

        // Keyboard shortcuts
        document.addEventListener('keydown', function (e) {
            var tag = e.target.tagName;
            if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
            if (e.key === 'ArrowLeft' && state.data && state.page < state.data.total_pages) {
                goToPage(state.page + 1);
            }
            if (e.key === 'ArrowRight' && state.page > 1) {
                goToPage(state.page - 1);
            }
        });
    }

    // ── Init ──────────────────────────────────────────────────────
    function init() {
        readURL();
        syncControlsToState();
        loadVendors();
        bindEvents();
        fetchPurchases();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', PurchaseListApp.init);
