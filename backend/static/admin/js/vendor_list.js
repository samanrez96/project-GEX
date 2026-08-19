/**
 * VendorListApp — API-driven vendor list for Django Admin.
 *
 * Fetches from /api/v1/inventory/vendors/ with search and is_active filter.
 * Columns: نام فروشنده، شماره تماس، ایمیل، آدرس، توضیحات
 *
 * Auth: SessionAuthentication via Django admin session cookie.
 * 401 → redirect to login.
 */
const VendorListApp = (function () {
    'use strict';

    var API_URL = '/api/v1/inventory/vendors/';
    var COLS    = 5;

    var state = {
        search:    '',
        page:      1,
        page_size: 50,
        loading:   false,
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

    // ── Build API params ──────────────────────────────────────────

    function buildParams() {
        var p = new URLSearchParams();
        p.set('page',      String(state.page));
        p.set('page_size', String(state.page_size));
        if (state.search) p.set('search', state.search);
        return p;
    }

    // ── Fetch vendors ─────────────────────────────────────────────

    function fetchVendors() {
        if (state.loading) return;
        state.loading = true;
        showLoadingSkeleton();
        showSpinner();

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
                state.loading = false;
                renderRows(data.results || []);
                renderPagination(data);
                hideSpinner();
            })
            .catch(function (err) {
                state.loading = false;
                showError(err.message);
                hideSpinner();
            });
    }

    function fetchAll() { state.page = 1; fetchVendors(); }

    // ── Render rows ───────────────────────────────────────────────

    function renderRows(results) {
        var tbody   = document.getElementById('vl-tbody');
        var emptyEl = document.getElementById('vl-empty');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!results || results.length === 0) {
            if (emptyEl) emptyEl.style.display = '';
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        results.forEach(function (v) {
            var row     = document.createElement('tr');
            var editUrl = '/admin/inventory/vendor/' + v.id + '/change/';
            row.style.cursor = 'pointer';

            row.innerHTML =
                '<td><a class="vl-vendor-name" href="' + editUrl + '" onclick="event.stopPropagation()">' + escapeHtml(v.name) + '</a></td>'
                + '<td>' + escapeHtml(v.phone_number || '—') + '</td>'
                + '<td>' + (v.email ? escapeHtml(v.email) : '—') + '</td>'
                + '<td>' + (v.address ? escapeHtml(v.address) : '<span class="vl-muted">—</span>') + '</td>'
                + '<td>' + (v.notes ? escapeHtml(v.notes) : '<span class="vl-muted">—</span>') + '</td>';

            row.addEventListener('click', function (e) {
                if (e.target.tagName === 'A') return;
                window.location.href = editUrl;
            });

            tbody.appendChild(row);
        });
    }

    // ── Render pagination ─────────────────────────────────────────

    function renderPagination(data) {
        var paginationEl = document.getElementById('vl-pagination');
        var count = data.count || 0;
        var totalPages = Math.ceil(count / state.page_size);
        if (paginationEl) paginationEl.style.display = totalPages > 1 ? '' : 'none';

        TablePagination.renderControls({
            pagesId:      'vl-pages',
            infoId:       'vl-info',
            data:         data,
            currentPage:  state.page,
            btnClass:     'vl-page-btn',
            recordLabel:  'تامین‌کننده',
            onPageChange: function (page) {
                state.page = page;
                fetchVendors();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            },
        });
    }

    // ── Loading / error helpers ───────────────────────────────────

    function showLoadingSkeleton() {
        var tbody   = document.getElementById('vl-tbody');
        var emptyEl = document.getElementById('vl-empty');
        if (!tbody) return;
        if (emptyEl) emptyEl.style.display = 'none';
        tbody.innerHTML = [0, 1, 2, 3].map(function () {
            return '<tr class="vl-loading-row">'
                + '<td><div class="vl-skeleton vl-skeleton-lg"></div></td>'
                + '<td><div class="vl-skeleton vl-skeleton-sm"></div></td>'
                + '<td><div class="vl-skeleton vl-skeleton-med"></div></td>'
                + '<td><div class="vl-skeleton vl-skeleton-lg"></div></td>'
                + '<td><div class="vl-skeleton vl-skeleton-med"></div></td>'
                + '</tr>';
        }).join('');
    }

    function showSpinner() {
        var sp = document.getElementById('vl-spinner');
        if (sp) sp.classList.add('vl-visible');
    }

    function hideSpinner() {
        var sp = document.getElementById('vl-spinner');
        if (sp) sp.classList.remove('vl-visible');
    }

    function showError(msg) {
        var tbody = document.getElementById('vl-tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="' + COLS + '" style="text-align:center;color:var(--red);padding:24px">'
                + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</td></tr>';
        }
    }

    // ── Sync controls ↔ state ─────────────────────────────────────

    function syncControlsToState() {
        var searchEl = document.getElementById('vl-search');
        if (searchEl) searchEl.value = state.search;
    }

    // ── Event wiring ──────────────────────────────────────────────

    function bindEvents() {
        var searchEl = document.getElementById('vl-search');
        if (searchEl) {
            searchEl.addEventListener('global-search:changed', function (e) {
                state.search = e.detail.value;
                fetchAll();
            });
        }
    }

    // ── Init ──────────────────────────────────────────────────────

    function init() {
        syncControlsToState();
        bindEvents();
        fetchAll();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', VendorListApp.init);
