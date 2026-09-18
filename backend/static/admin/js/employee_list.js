/**
 * EmployeeListApp — API-driven employee list for Django Admin.
 *
 * Auth: SessionAuthentication — admin session cookie used for same-origin fetch().
 * If the session expires the API returns 401 → we redirect to login.
 */
const EmployeeListApp = (function () {
    'use strict';

    var API_URL       = '/api/v2/employees/';
    var POSITIONS_URL = '/api/v2/employees/positions/';

    // ── State ────────────────────────────────────────────────────
    var state = {
        search:          '',
        job_position:    null,
        is_active:       '',
        start_date_from: null,    // employee start_date range
        start_date_to:   null,
        page:            1,
        page_size:       25,
        ordering:        'full_name',
        loading:         false,
        data:            null,
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

    // ── Build URL params from state ───────────────────────────────
    function buildParams() {
        var p = new URLSearchParams();
        p.set('page',      String(state.page));
        p.set('page_size', String(state.page_size));
        p.set('ordering',  state.ordering);
        if (state.search)          p.set('search',          state.search);
        if (state.job_position)    p.set('job_position',    state.job_position);
        if (state.is_active)       p.set('is_active',       state.is_active);
        if (state.start_date_from) p.set('start_date_from', state.start_date_from);
        if (state.start_date_to)   p.set('start_date_to',   state.start_date_to);
        return p;
    }

    // Excel export button — always reflects the current filters/search/
    // ordering (minus pagination), which the export endpoint ignores anyway.
    function updateExportButton() {
        var btn = document.getElementById('em-export-btn');
        if (!btn) return;
        var p = buildParams();
        p.set('export', 'excel');
        btn.setAttribute('href', API_URL + '?' + p.toString());
    }

    // ── Fetch employees ───────────────────────────────────────────
    function fetchEmployees() {
        if (state.loading) return Promise.resolve();
        state.loading = true;
        showLoading();

        updateExportButton();
        var url = API_URL + '?' + buildParams().toString();
        return fetch(url, { credentials: 'same-origin' })
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
                renderSummaryCards(data.results, data.count);
                renderPagination(data);
                updateURL();
                updateFilterDots();
            })
            .catch(function (err) {
                state.loading = false;
                hideLoading();
                showError(err.message);
            });
    }

    // ── Summary cards (computed from current page) ────────────────
    function renderSummaryCards(results, totalCount) {
        var active    = 0;
        var inactive  = 0;
        var positions = {};

        if (results && results.length) {
            results.forEach(function (e) {
                if (e.is_active) {
                    active++;
                } else {
                    inactive++;
                }
                if (e.job_position) {
                    positions[e.job_position] = true;
                }
            });
        }

        var el;
        el = document.getElementById('em-count-total');
        if (el) el.textContent = toPersian(totalCount || 0);
        el = document.getElementById('em-count-active');
        if (el) el.textContent = toPersian(active);
        el = document.getElementById('em-count-inactive');
        if (el) el.textContent = toPersian(inactive);
        el = document.getElementById('em-count-positions');
        if (el) el.textContent = toPersian(Object.keys(positions).length);
    }

    // ── Status badge HTML ─────────────────────────────────────────
    function activeBadge(isActive) {
        if (isActive) {
            return '<span class="em-badge em-badge--active">فعال</span>';
        }
        return '<span class="em-badge em-badge--inactive">غیرفعال</span>';
    }

    // ── Render table rows ─────────────────────────────────────────
    function renderTable(results) {
        var tbody = document.getElementById('em-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!results || results.length === 0) {
            showEmpty();
            return;
        }
        hideEmpty();

        results.forEach(function (e) {
            var row = document.createElement('tr');
            var editUrl   = '/admin/employees/employee/' + e.id + '/change/';
            var detailUrl = '/admin/employees/employee/' + e.id + '/detail/';

            var posHtml = e.job_position_name
                ? '<span class="em-badge em-badge--position">' + escapeHtml(e.job_position_name) + '</span>'
                : '<span class="em-muted">—</span>';

            var emailHtml = e.email
                ? escapeHtml(e.email)
                : '<span class="em-muted">—</span>';

            var phoneHtml = e.personal_phone
                ? escapeHtml(e.personal_phone)
                : '<span class="em-muted">—</span>';

            var nationalIdHtml = e.national_id
                ? '<span class="em-national-id">' + escapeHtml(e.national_id) + '</span>'
                : '<span class="em-muted">—</span>';

            row.innerHTML =
                '<td><a class="em-name-link" href="' + editUrl + '" onclick="event.stopPropagation()">'
                + escapeHtml(e.full_name) + '</a></td>'
                + '<td>' + posHtml + '</td>'
                + '<td class="em-td--ltr">' + emailHtml + '</td>'
                + '<td class="em-td--ltr">' + phoneHtml + '</td>'
                + '<td class="em-td--ltr">' + nationalIdHtml + '</td>'
                + '<td>' + activeBadge(e.is_active) + '</td>';

            row.addEventListener('click', function (e) {
                if (e.target.closest('.em-action-btn')) return;
                window.location.href = editUrl;
            });

            tbody.appendChild(row);
        });
    }

    // ── Render pagination bar (shared via TablePagination module) ──
    function renderPagination(data) {
        TablePagination.renderControls({
            pagesId:      'em-pagination-pages',
            infoId:       'em-pagination-info',
            data:         data,
            currentPage:  state.page,
            btnClass:     'em-page-btn',
            recordLabel:  'کارمند',
            onPageChange: goToPage,
        });
    }

    function goToPage(page) {
        state.page = page;
        fetchEmployees();
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
        if (p.has('search'))          state.search          = p.get('search');
        if (p.has('job_position'))    state.job_position    = p.get('job_position') || null;
        if (p.has('is_active'))       state.is_active       = p.get('is_active');
        if (p.has('start_date_from')) state.start_date_from = p.get('start_date_from') || null;
        if (p.has('start_date_to'))   state.start_date_to   = p.get('start_date_to')   || null;
        if (p.has('page'))            state.page            = parseInt(p.get('page'),      10) || 1;
        if (p.has('page_size'))       state.page_size       = parseInt(p.get('page_size'), 10) || 25;
        if (p.has('ordering'))        state.ordering        = p.get('ordering');
    }

    // ── Active-filter dot indicators ──────────────────────────────
    function updateFilterDots() {
        setDot('em-dot-position',  !!state.job_position);
        setDot('em-dot-active',    !!state.is_active);
        setDot('em-dot-startdate', !!(state.start_date_from || state.start_date_to));

        var hasAny = state.job_position || state.is_active
            || state.start_date_from || state.start_date_to;
        var clearBtn = document.getElementById('em-clear-filters');
        if (clearBtn) clearBtn.classList.toggle('em-visible', !!hasAny);
    }

    function setDot(id, active) {
        var el = document.getElementById(id);
        if (el) el.classList.toggle('em-active', active);
    }

    // ── Loading / error / empty state ─────────────────────────────
    function showLoading() {
        var tbody = document.getElementById('em-tbody');
        if (!tbody) return;
        hideEmpty();
        tbody.innerHTML = [0, 1, 2].map(function () {
            return '<tr class="em-loading-row">'
                + '<td><div class="em-skeleton em-skeleton-lg"></div></td>'
                + '<td><div class="em-skeleton em-skeleton-med"></div></td>'
                + '<td><div class="em-skeleton em-skeleton-med"></div></td>'
                + '<td><div class="em-skeleton em-skeleton-sm"></div></td>'
                + '<td><div class="em-skeleton em-skeleton-sm"></div></td>'
                + '<td><div class="em-skeleton em-skeleton-sm"></div></td>'
                + '<td><div class="em-skeleton em-skeleton-sm"></div></td>'
                + '</tr>';
        }).join('');

        var spinner = document.getElementById('em-spinner');
        if (spinner) spinner.classList.add('em-visible');
    }

    function hideLoading() {
        var spinner = document.getElementById('em-spinner');
        if (spinner) spinner.classList.remove('em-visible');
    }

    function showEmpty() {
        var wrap     = document.getElementById('em-empty-state');
        var clearBtn = document.getElementById('em-clear-search-btn');
        var addBtn   = document.getElementById('em-add-first-btn');
        var titleEl  = document.getElementById('em-empty-title');
        var desc     = document.getElementById('em-empty-desc');
        if (!wrap) return;

        var hasFilters = !!(state.search || state.job_position || state.is_active
            || state.start_date_from || state.start_date_to);

        if (hasFilters) {
            if (titleEl) titleEl.textContent = 'کارمندی پیدا نشد';
            if (desc)    desc.textContent    = 'جستجو یا فیلترهای کارمندان را تغییر دهید.';
            if (clearBtn) clearBtn.style.display = '';
            if (addBtn)   addBtn.style.display   = 'none';
        } else {
            if (titleEl) titleEl.textContent = 'هنوز کارمندی ثبت نشده است';
            if (desc)    desc.textContent    = 'برای مدیریت منابع انسانی، اولین کارمند را اضافه کنید.';
            if (clearBtn) clearBtn.style.display = 'none';
            if (addBtn)   addBtn.style.display   = '';
        }

        wrap.style.display = '';
        var tbody = document.getElementById('em-tbody');
        if (tbody) tbody.innerHTML = '';
    }

    function hideEmpty() {
        var wrap = document.getElementById('em-empty-state');
        if (wrap) wrap.style.display = 'none';
    }

    function showError(msg) {
        var tbody = document.getElementById('em-tbody');
        if (tbody) {
            tbody.innerHTML =
                '<tr><td colspan="7" style="text-align:center;color:var(--red);padding:24px">'
                + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</td></tr>';
        }
    }

    // ── Load position dropdown ────────────────────────────────────
    function loadPositions() {
        var sel = document.getElementById('em-filter-position');
        if (!sel) return Promise.resolve();

        return fetch(POSITIONS_URL + '?is_active=true&page_size=200', { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                var items = data.results || data;
                items.forEach(function (pos) {
                    var opt = document.createElement('option');
                    opt.value       = String(pos.id);
                    opt.textContent = pos.name;
                    sel.appendChild(opt);
                });
                if (state.job_position) sel.value = state.job_position;
            })
            .catch(function (err) {
                console.warn('Positions dropdown failed to load:', err);
                // Graceful degradation: replace select with plain text input
                var input = document.createElement('input');
                input.type        = 'text';
                input.id          = 'em-filter-position';
                input.className   = 'em-filter-input';
                input.placeholder = 'شناسه پوزیشن...';
                input.value       = state.job_position || '';
                if (sel.parentNode) sel.parentNode.replaceChild(input, sel);
                var debouncedPos = debounce(function () {
                    state.job_position = input.value.trim() || null;
                    state.page         = 1;
                    fetchEmployees();
                }, 400);
                input.addEventListener('input', debouncedPos);
            });
    }

    // ── Toast ─────────────────────────────────────────────────────
    function showToast(message, type) {
        var toast = document.createElement('div');
        toast.className   = 'em-toast em-toast--' + (type || 'success');
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () { toast.remove(); }, 3000);
    }

    // ── Sync UI controls → state ───────────────────────────────────
    function syncControlsToState() {
        var el;
        el = document.getElementById('em-search');
        if (el) el.value = state.search;

        el = document.getElementById('em-filter-position');
        if (el) el.value = state.job_position || '';

        el = document.getElementById('em-filter-active');
        if (el) el.value = state.is_active;

        el = document.getElementById('em-filter-start-from');
        if (el) el.value = state.start_date_from || '';

        el = document.getElementById('em-filter-start-to');
        if (el) el.value = state.start_date_to || '';

        el = document.getElementById('em-page-size-select');
        if (el) el.value = String(state.page_size);

        TableFilters.syncSortControls('em-sort-by', 'em-sort-dir', state);
    }

    // ── Wire up all events ─────────────────────────────────────────
    function bindEvents() {
        // Search — debounced via GlobalSearch component (global_search.js)
        var searchEl = document.getElementById('em-search');
        if (searchEl) {
            searchEl.addEventListener('global-search:changed', function (e) {
                state.search = e.detail.value;
                state.page   = 1;
                fetchEmployees();
            });
        }

        // Position filter (select populated by loadPositions; may be replaced by input on failure)
        var posEl = document.getElementById('em-filter-position');
        if (posEl && posEl.tagName === 'SELECT') {
            posEl.addEventListener('change', function () {
                state.job_position = posEl.value || null;
                state.page         = 1;
                fetchEmployees();
            });
        }

        // Active/inactive/all
        var activeEl = document.getElementById('em-filter-active');
        if (activeEl) {
            activeEl.addEventListener('change', function () {
                state.is_active = activeEl.value;
                state.page      = 1;
                fetchEmployees();
            });
        }

        // Page size
        var sizeEl = document.getElementById('em-page-size-select');
        if (sizeEl) {
            sizeEl.addEventListener('change', function () {
                state.page_size = parseInt(sizeEl.value, 10);
                state.page      = 1;
                fetchEmployees();
            });
        }

        // Start date range — debounced
        var startFromEl = document.getElementById('em-filter-start-from');
        var startToEl   = document.getElementById('em-filter-start-to');
        var debouncedStart = debounce(function () {
            state.start_date_from = (startFromEl && startFromEl.value) ? startFromEl.value : null;
            state.start_date_to   = (startToEl   && startToEl.value)   ? startToEl.value   : null;
            state.page            = 1;
            fetchEmployees();
        }, 400);
        if (startFromEl) startFromEl.addEventListener('change', debouncedStart);
        if (startToEl)   startToEl.addEventListener('change', debouncedStart);

        // Sort controls
        TableFilters.bindSortControls('em-sort-by', 'em-sort-dir', state, fetchEmployees);

        // Clear filters
        var clearFiltersBtn = document.getElementById('em-clear-filters');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', function () {
                state.job_position    = null;
                state.is_active       = '';
                state.start_date_from = null;
                state.start_date_to   = null;
                state.page            = 1;
                syncControlsToState();
                fetchEmployees();
            });
        }

        // "Clear filters" button (shown in empty state — clears search AND all filters)
        var clearSearchBtn = document.getElementById('em-clear-search-btn');
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', function () {
                state.search          = '';
                state.job_position    = null;
                state.is_active       = '';
                state.start_date_from = null;
                state.start_date_to   = null;
                state.page            = 1;
                syncControlsToState();
                fetchEmployees();
            });
        }

        // Back / forward navigation
        window.addEventListener('popstate', function () {
            readURL();
            syncControlsToState();
            fetchEmployees();
        });

        // Keyboard shortcuts (ArrowLeft = next page, ArrowRight = prev page in RTL)
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
        bindEvents();
        Promise.all([loadPositions(), fetchEmployees()]);
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', EmployeeListApp.init);
