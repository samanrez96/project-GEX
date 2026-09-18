/**
 * ProductListApp — Unified API-driven product list for Django Admin.
 *
 * Shows ALL products in one single table (no separate medicine/equipment sections).
 * Columns: کد داخلی، نام محصول، نوع، تعداد، قیمت، وضعیت موجودی
 *
 * Auth: SessionAuthentication authenticates same-origin fetch() calls
 * automatically. 401 → redirect to login.
 */
const ProductListApp = (function () {
    'use strict';

    var API_URL = '/api/v2/inventory/products/';
    var COLS    = 6; // کد داخلی، نام، نوع، تعداد، قیمت، وضعیت موجودی

    // ── Shared filter / page state ────────────────────────────────
    var state = {
        search:       '',
        product_type: '',
        price_min:    null,
        price_max:    null,
        ordering:     'internal_code',   // CLI-68: default sort = internal code asc
        page:         1,
        page_size:    100,
        loading:      false,
        data:         null,
    };

    // ── Utilities ─────────────────────────────────────────────────

    function debounce(fn, ms) {
        var timer;
        return function () { clearTimeout(timer); timer = setTimeout(fn, ms); };
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function formatPrice(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return '—';
            var digits = Math.round(num).toLocaleString('en-US');
            return window.PersianFormat ? window.PersianFormat.toPersianDigits(digits) : digits;
        } catch (_) { return String(n); }
    }

    function formatStock(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return '—';
            // num.toString() strips trailing zeros naturally (12.50 → "12.5", 12.00 → "12")
            var formatted = num.toString();
            return window.PersianFormat ? window.PersianFormat.toPersianDigits(formatted) : formatted;
        } catch (_) { return String(n); }
    }

    function toFa(n) {
        try {
            var s = String(Math.round(n));
            return window.PersianFormat ? window.PersianFormat.toPersianDigits(s) : s;
        } catch (_) { return String(n); }
    }

    // ── Stock status ──────────────────────────────────────────────

    function getStockStatus(product) {
        // Use backend-calculated stock_status if available (comes from updated serializer)
        if (product.stock_status) return product.stock_status;
        // Fallback local calculation
        var stock = parseFloat(product.current_stock);
        var min   = parseFloat(product.minimum_stock || 0);
        if (stock <= 0)              return 'ناموجود';
        if (min > 0 && stock <= min) return 'کم‌موجودی';
        return 'موجود';
    }

    function stockStatusHtml(status) {
        var cls;
        if      (status === 'ناموجود')   cls = 'pl-status--empty';
        else if (status === 'کم‌موجودی') cls = 'pl-status--low';
        else                              cls = 'pl-status--ok';
        return '<span class="pl-status-badge ' + cls + '">' + escapeHtml(status) + '</span>';
    }

    function typeHtml(product) {
        var label = product.product_type === 'medicine' ? 'دارو' : 'تجهیزات';
        var cls   = product.product_type === 'medicine' ? 'pl-type--medicine' : 'pl-type--equipment';
        return '<span class="pl-type-badge ' + cls + '">' + label + '</span>';
    }

    // ── Build API params ──────────────────────────────────────────

    function buildParams() {
        var p = new URLSearchParams();
        p.set('page',      String(state.page));
        p.set('page_size', String(state.page_size));

        // Determine ordering string. Default field is internal_code (CLI-68).
        var ordering = state.ordering || 'internal_code';
        if (ordering === '-created_at') {
            // "جدیدترین" is a fixed descending sort with no direction toggle
            p.set('ordering', ordering);
        } else {
            // Strip any leading '-' (e.g. state loaded from a URL like
            // ?ordering=-internal_code) so the direction dropdown is the single
            // source of truth and we never double-prefix ('--internal_code').
            var field  = ordering.replace(/^-/, '');
            var dirSel = document.getElementById('pl-sort-dir');
            var dir    = dirSel ? dirSel.value : 'asc';
            p.set('ordering', dir === 'desc' ? '-' + field : field);
        }

        if (state.search)       p.set('search',       state.search);
        if (state.product_type) p.set('product_type', state.product_type);
        if (state.price_min)    p.set('price_min',    state.price_min);
        if (state.price_max)    p.set('price_max',    state.price_max);
        return p;
    }

    // Excel export button — always reflects the current filters/search/
    // ordering (minus pagination), which the export endpoint ignores anyway.
    function updateExportButton() {
        var btn = document.getElementById('pl-export-btn');
        if (!btn) return;
        var p = buildParams();
        p.set('export', 'excel');
        btn.setAttribute('href', API_URL + '?' + p.toString());
    }

    // ── Fetch products ────────────────────────────────────────────

    function fetchProducts() {
        if (state.loading) return;
        state.loading = true;
        showLoadingSkeleton();
        showSpinner();

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
                renderRows(data.results || []);
                renderPagination(data);
                updateStats(data);
                updateFilterDots();
                updateURL();
                hideSpinner();
            })
            .catch(function (err) {
                state.loading = false;
                showError(err.message);
                hideSpinner();
            });
    }

    function fetchAll() {
        state.page = 1;
        fetchProducts();
    }

    // ── Render rows ───────────────────────────────────────────────

    function renderRows(results) {
        var tbody   = document.getElementById('pl-tbody');
        var emptyEl = document.getElementById('pl-empty');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!results || results.length === 0) {
            if (emptyEl) {
                var hasFilters = !!(state.search || state.product_type || state.price_min || state.price_max);
                var titleEl  = emptyEl.querySelector('.pl-empty-title');
                var clearBtn = emptyEl.querySelector('.pl-clear-filters-all');
                if (hasFilters && titleEl) titleEl.textContent = 'محصولی با این فیلترها یافت نشد';
                if (clearBtn) clearBtn.style.display = hasFilters ? '' : 'none';
                emptyEl.style.display = '';
            }
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        results.forEach(function (p) {
            var row       = document.createElement('tr');
            var detailUrl = '/admin/inventory/product/' + p.id + '/detail/';
            var editUrl   = '/admin/inventory/product/' + p.id + '/change/';
            var status    = getStockStatus(p);

            row.addEventListener('click', function (e) {
                if (e.target.closest('.pl-action-btn')) return;
                window.location.href = detailUrl;
            });

            row.innerHTML =
                '<td><span class="pl-code">' + escapeHtml(p.internal_code || '—') + '</span></td>'
                + '<td><a class="pl-product-name" href="' + detailUrl + '" onclick="event.stopPropagation()">'
                + escapeHtml(p.name) + '</a></td>'
                + '<td>' + typeHtml(p) + '</td>'
                + '<td class="pl-stock-cell">' + formatStock(p.current_stock) + '</td>'
                + '<td class="pl-price">' + formatPrice(p.purchase_price) + '</td>'
                + '<td>' + stockStatusHtml(status) + '</td>';

            tbody.appendChild(row);
        });
    }

    // ── Update summary stats ──────────────────────────────────────

    function updateStats(data) {
        var results    = data.results || [];
        var total      = data.count   || 0;
        var emptyCount = 0;
        results.forEach(function (p) {
            if (getStockStatus(p) === 'ناموجود') emptyCount++;
        });

        var totalEl = document.getElementById('pl-stat-total');
        var emptyEl = document.getElementById('pl-stat-empty');

        if (totalEl) totalEl.textContent = toFa(total);
        if (emptyEl) emptyEl.textContent = toFa(emptyCount);
    }

    // ── Render pagination ─────────────────────────────────────────

    function renderPagination(data) {
        var paginationEl = document.getElementById('pl-pagination');
        var totalPages = data.total_pages;
        if (!totalPages) {
            // Calculate from count / page_size
            var count = data.count || 0;
            totalPages = Math.ceil(count / state.page_size);
        }
        var showPagination = totalPages > 1;
        if (paginationEl) paginationEl.style.display = showPagination ? '' : 'none';

        TablePagination.renderControls({
            pagesId:      'pl-pages',
            infoId:       'pl-info',
            data:         data,
            currentPage:  state.page,
            btnClass:     'pl-page-btn',
            recordLabel:  'محصول',
            onPageChange: function (page) {
                state.page = page;
                fetchProducts();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            },
        });
    }

    // ── URL sync ──────────────────────────────────────────────────

    function updateURL() {
        var p = new URLSearchParams();
        if (state.search)                   p.set('search',       state.search);
        if (state.product_type)             p.set('product_type', state.product_type);
        if (state.price_min)                p.set('price_min',    state.price_min);
        if (state.price_max)                p.set('price_max',    state.price_max);
        if (state.ordering !== 'internal_code') p.set('ordering',  state.ordering);
        history.replaceState(
            {},
            '',
            window.location.pathname + (p.toString() ? '?' + p.toString() : '')
        );
    }

    function readURL() {
        var p = new URLSearchParams(window.location.search);
        if (p.has('search'))       state.search       = p.get('search');
        if (p.has('product_type')) state.product_type = p.get('product_type');
        if (p.has('price_min'))    state.price_min    = p.get('price_min') || null;
        if (p.has('price_max'))    state.price_max    = p.get('price_max') || null;
        if (p.has('ordering'))     state.ordering     = p.get('ordering');
    }

    // ── Active-filter dot indicators ──────────────────────────────

    function updateFilterDots() {
        setDot('pl-dot-price', !!(state.price_min || state.price_max));
        var hasAny = !!(state.price_min || state.price_max || state.product_type);
        var clearBtn = document.getElementById('pl-clear-filters');
        if (clearBtn) clearBtn.classList.toggle('pl-visible', hasAny);
    }

    function setDot(id, active) {
        var el = document.getElementById(id);
        if (el) el.classList.toggle('pl-active', active);
    }

    // ── Loading / spinner / error helpers ─────────────────────────

    function showLoadingSkeleton() {
        var tbody = document.getElementById('pl-tbody');
        var emptyEl = document.getElementById('pl-empty');
        if (!tbody) return;
        if (emptyEl) emptyEl.style.display = 'none';
        tbody.innerHTML = [0, 1, 2, 3].map(function () {
            return '<tr class="pl-loading-row">'
                + '<td><div class="pl-skeleton pl-skeleton-sm"></div></td>'
                + '<td><div class="pl-skeleton pl-skeleton-lg"></div></td>'
                + '<td><div class="pl-skeleton pl-skeleton-sm"></div></td>'
                + '<td><div class="pl-skeleton pl-skeleton-sm"></div></td>'
                + '<td><div class="pl-skeleton pl-skeleton-med"></div></td>'
                + '<td><div class="pl-skeleton pl-skeleton-sm"></div></td>'
                + '</tr>';
        }).join('');
    }

    function showSpinner() {
        var spinner = document.getElementById('pl-spinner');
        if (spinner) spinner.classList.add('pl-visible');
    }

    function hideSpinner() {
        var spinner = document.getElementById('pl-spinner');
        if (spinner) spinner.classList.remove('pl-visible');
    }

    function showError(msg) {
        var tbody = document.getElementById('pl-tbody');
        if (tbody) {
            tbody.innerHTML =
                '<tr><td colspan="' + COLS + '" style="text-align:center;color:var(--red);padding:24px">'
                + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</td></tr>';
        }
    }

    // ── Sync UI controls ↔ state ──────────────────────────────────

    function syncControlsToState() {
        var searchEl = document.getElementById('pl-search');
        if (searchEl) searchEl.value = state.search;

        var typeEl = document.getElementById('pl-filter-type');
        if (typeEl) typeEl.value = state.product_type;

        var minEl = document.getElementById('pl-filter-price-min');
        if (minEl) minEl.value = state.price_min || '';

        var maxEl = document.getElementById('pl-filter-price-max');
        if (maxEl) maxEl.value = state.price_max || '';

        // Sync sort dropdowns (TableFilters handles ordering field, not direction)
        var sortBy  = document.getElementById('pl-sort-by');
        var sortDir = document.getElementById('pl-sort-dir');
        if (sortBy && state.ordering) {
            // Strip leading '-' for the select value
            var ord = state.ordering.replace(/^-/, '');
            sortBy.value = ord;
            if (sortDir) sortDir.value = state.ordering.startsWith('-') ? 'desc' : 'asc';
        }
        updateFilterDots();
    }

    // ── Wire up all events ────────────────────────────────────────

    function bindEvents() {
        // Search (debounced via GlobalSearch component)
        var searchEl = document.getElementById('pl-search');
        if (searchEl) {
            searchEl.addEventListener('global-search:changed', function (e) {
                state.search = e.detail.value;
                fetchAll();
            });
        }

        // Product type filter
        var typeEl = document.getElementById('pl-filter-type');
        if (typeEl) {
            typeEl.addEventListener('change', function () {
                state.product_type = typeEl.value;
                fetchAll();
            });
        }

        // Price range — own debounce
        var minEl = document.getElementById('pl-filter-price-min');
        var maxEl = document.getElementById('pl-filter-price-max');
        var debouncedPrice = debounce(function () {
            state.price_min = (minEl && minEl.value) ? minEl.value : null;
            state.price_max = (maxEl && maxEl.value) ? maxEl.value : null;
            fetchAll();
        }, 400);
        if (minEl) minEl.addEventListener('input', debouncedPrice);
        if (maxEl) maxEl.addEventListener('input', debouncedPrice);

        // Sort field
        var sortBy = document.getElementById('pl-sort-by');
        if (sortBy) {
            sortBy.addEventListener('change', function () {
                state.ordering = sortBy.value;
                fetchAll();
            });
        }

        // Sort direction
        var sortDir = document.getElementById('pl-sort-dir');
        if (sortDir) {
            sortDir.addEventListener('change', function () {
                fetchAll();
            });
        }

        // Clear-all filters button (filter bar)
        var clearFiltersBtn = document.getElementById('pl-clear-filters');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', function () {
                state.price_min    = null;
                state.price_max    = null;
                state.product_type = '';
                syncControlsToState();
                fetchAll();
            });
        }

        // Empty-state "clear search" button
        var clearAllBtn = document.querySelector('.pl-clear-filters-all');
        if (clearAllBtn) {
            clearAllBtn.addEventListener('click', function () {
                state.search       = '';
                state.price_min    = null;
                state.price_max    = null;
                state.product_type = '';
                syncControlsToState();
                fetchAll();
            });
        }

        // Back / forward navigation
        window.addEventListener('popstate', function () {
            readURL();
            syncControlsToState();
            fetchAll();
        });
    }

    // ── Init ──────────────────────────────────────────────────────

    function init() {
        readURL();
        syncControlsToState();
        bindEvents();
        fetchAll();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', ProductListApp.init);
