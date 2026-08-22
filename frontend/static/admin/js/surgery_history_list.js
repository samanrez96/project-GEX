/**
 * SurgeryHistoryListApp — API-driven surgery history list for Django Admin.
 *
 * Auth: SessionAuthentication — admin session cookie used for same-origin fetch().
 * 401 → redirect to login.
 */
const SurgeryHistoryListApp = (function () {
    'use strict';

    var API_URL      = '/api/v1/surgeries/history/';
    var TYPES_URL    = '/api/v1/surgeries/types/';
    var DOCTORS_URL  = '/api/v1/contacts/doctors/';

    // ── State ────────────────────────────────────────────────────
    var state = {
        search:              '',
        surgery_type:        null,
        doctor_or_therapist: null,
        surgery_date_from:   null,    // surgery date range
        surgery_date_to:     null,
        min_amount:          null,    // amount range
        max_amount:          null,
        page:                1,
        page_size:           25,
        ordering:            '-surgery_date',
        loading:             false,
        data:                null,
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

    function formatDate(iso) {
        return window.PersianFormat
            ? window.PersianFormat.formatJalaliDate(iso)
            : (iso ? String(iso).slice(0, 10) : '—');
    }

    // Pull the first human-readable message out of a DRF error body, e.g.
    // {"surgery_date_from": ["فرمت تاریخ نامعتبر است..."]} or
    // {"__all__": ["تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد."]} or
    // {"detail": "..."}. Without this, invalid/reversed date input only
    // ever surfaced a generic "HTTP 400" — the actual Persian validation
    // message from the backend was silently discarded.
    function extractErrorMessage(body) {
        if (!body || typeof body !== 'object') return null;
        if (body.detail) return String(body.detail);
        for (var key in body) {
            if (!Object.prototype.hasOwnProperty.call(body, key)) continue;
            var val = body[key];
            if (Array.isArray(val) && val.length) return String(val[0]);
            if (typeof val === 'string' && val) return val;
        }
        return null;
    }

    function formatMoney(n) {
        if (n === null || n === undefined || n === '') return '—';
        var num = parseFloat(n);
        if (isNaN(num)) return '—';
        var formatted = Math.round(num).toLocaleString('en-US', { maximumFractionDigits: 0 }).replace(/,/g, '٬');
        return toPersian(formatted);
    }

    // ── Single ordered column mapping ──────────────────────────────
    // The ONLY source of truth for the table's column set/order. Header
    // cells, row cells, the loading-row skeleton, and the error-row
    // colspan are all derived from this one array so they can never
    // drift out of sync with each other again.
    var COLUMNS = [
        {
            header: 'ردیف', headerClass: 'sh-th--row-number', skeleton: 'sh-skeleton-sm',
            cell: function (r) {
                return '<td class="sh-td--ltr sh-td--row-number">' + toPersian(r.id) + '</td>';
            },
        },
        {
            header: 'نام بیمار', skeleton: 'sh-skeleton-lg',
            cell: function (r) {
                var detailUrl = '/admin/surgeries/surgeryhistory/' + r.id + '/detail/';
                return '<td><a class="sh-name-link" href="' + detailUrl + '" onclick="event.stopPropagation()">'
                    + escapeHtml(r.patient_name || '—') + '</a></td>';
            },
        },
        {
            header: 'کد ملی بیمار', skeleton: 'sh-skeleton-sm',
            cell: function (r) {
                return '<td class="sh-td--ltr">' + escapeHtml(r.patient_national_id || '—') + '</td>';
            },
        },
        {
            header: 'شماره موبایل بیمار', skeleton: 'sh-skeleton-sm',
            cell: function (r) {
                return '<td class="sh-td--ltr">' + escapeHtml(r.phone_number || '—') + '</td>';
            },
        },
        {
            header: 'نام جراح/درمانگر', skeleton: 'sh-skeleton-med',
            cell: function (r) {
                var doctorHtml = r.doctor_name
                    ? escapeHtml(r.doctor_name)
                    : '<span class="sh-muted">—</span>';
                return '<td>' + doctorHtml + '</td>';
            },
        },
        {
            header: 'نوع عمل', skeleton: 'sh-skeleton-med',
            cell: function (r) {
                var typeHtml = r.surgery_type_name
                    ? '<span class="sh-badge sh-badge--surgery-type">' + escapeHtml(r.surgery_type_name) + '</span>'
                    : '<span class="sh-muted">—</span>';
                return '<td>' + typeHtml + '</td>';
            },
        },
        {
            header: 'تاریخ عمل', skeleton: 'sh-skeleton-sm',
            cell: function (r) {
                return '<td class="sh-td--ltr">' + formatDate(r.surgery_date) + '</td>';
            },
        },
        {
            header: 'مبلغ عمل (تومان)', skeleton: 'sh-skeleton-med',
            cell: function (r) {
                return '<td style="text-align:left;direction:ltr">' + formatMoney(r.amount) + '</td>';
            },
        },
        {
            header: 'سهم دانشگاه (۴۵٪)', skeleton: 'sh-skeleton-med',
            cell: function (r) {
                return '<td style="text-align:left;direction:ltr">' + formatMoney(r.university_share) + '</td>';
            },
        },
        {
            header: 'کمیسیون مرکز جراحی (۵۵٪)', skeleton: 'sh-skeleton-med',
            cell: function (r) {
                return '<td style="text-align:left;direction:ltr">' + formatMoney(r.doctor_share) + '</td>';
            },
        },
    ];

    function renderTableHeader() {
        var theadRow = document.querySelector('#sh-table thead tr');
        if (!theadRow) return;
        theadRow.innerHTML = COLUMNS.map(function (col) {
            return '<th' + (col.headerClass ? ' class="' + col.headerClass + '"' : '') + '>' + col.header + '</th>';
        }).join('');
    }

    // ── Build URL params from state ──────────────────────────────
    function buildParams() {
        var p = new URLSearchParams();
        p.set('page',      String(state.page));
        p.set('page_size', String(state.page_size));
        p.set('ordering',  state.ordering);
        if (state.search)              p.set('search',              state.search);
        if (state.surgery_type)        p.set('surgery_type',        state.surgery_type);
        if (state.doctor_or_therapist) p.set('clinical_doctor', state.doctor_or_therapist);
        if (state.surgery_date_from)   p.set('surgery_date_from',   state.surgery_date_from);
        if (state.surgery_date_to)     p.set('surgery_date_to',     state.surgery_date_to);
        if (state.min_amount)          p.set('min_amount',          state.min_amount);
        if (state.max_amount)          p.set('max_amount',          state.max_amount);
        return p;
    }

    // ── Excel export button — always reflects the current filters/search/
    // ordering (minus pagination), which the export endpoint ignores anyway.
    function updateExportButton() {
        var btn = document.getElementById('sh-export-btn');
        if (!btn) return;
        var p = buildParams();
        p.set('export', 'excel');
        btn.setAttribute('href', API_URL + '?' + p.toString());
    }

    // ── Fetch surgery histories ──────────────────────────────────
    function fetchList() {
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
                if (!res.ok) {
                    return res.json()
                        .catch(function () { return null; })
                        .then(function (body) {
                            throw new Error(extractErrorMessage(body) || ('HTTP ' + res.status));
                        });
                }
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

    // ── Summary cards ────────────────────────────────────────────
    function renderSummaryCards(results, totalCount) { return; }

    // ── Status badge HTML ────────────────────────────────────────
    function paymentBadge(status, display) {
        var cls = {
            PENDING: 'sh-badge--pending',
            PARTIAL: 'sh-badge--partial',
            PAID:    'sh-badge--paid',
        }[status] || 'sh-badge--pending';
        return '<span class="sh-badge ' + cls + '">' + escapeHtml(display || status) + '</span>';
    }

    // ── Render table rows ────────────────────────────────────────
    function renderTable(results) {
        var tbody = document.getElementById('sh-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!results || results.length === 0) {
            showEmpty();
            return;
        }
        hideEmpty();

        results.forEach(function (r) {
            var row       = document.createElement('tr');
            var detailUrl = '/admin/surgeries/surgeryhistory/' + r.id + '/detail/';

            row.innerHTML = COLUMNS.map(function (col) { return col.cell(r); }).join('');

            row.style.cursor = 'pointer';
            row.addEventListener('click', function (e) {
                if (e.target.tagName === 'A') return;
                window.location.href = detailUrl;
            });

            tbody.appendChild(row);
        });
    }

    // ── Render pagination (shared via TablePagination module) ───────
    function renderPagination(data) {
        TablePagination.renderControls({
            pagesId:      'sh-pagination-pages',
            infoId:       'sh-pagination-info',
            data:         data,
            currentPage:  state.page,
            btnClass:     'sh-page-btn',
            recordLabel:  'عمل جراحی',
            onPageChange: goToPage,
        });
    }

    function goToPage(page) {
        state.page = page;
        fetchList();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── URL sync ─────────────────────────────────────────────────
    function updateURL() {
        history.pushState({}, '', window.location.pathname + '?' + buildParams().toString());
    }

    function readURL() {
        var p = new URLSearchParams(window.location.search);
        if (p.has('search'))              state.search              = p.get('search');
        if (p.has('surgery_type'))        state.surgery_type        = p.get('surgery_type') || null;
        if (p.has('doctor_or_therapist')) state.doctor_or_therapist = p.get('doctor_or_therapist') || null;
        if (p.has('surgery_date_from'))   state.surgery_date_from   = p.get('surgery_date_from') || null;
        if (p.has('surgery_date_to'))     state.surgery_date_to     = p.get('surgery_date_to')   || null;
        if (p.has('min_amount'))          state.min_amount          = p.get('min_amount') || null;
        if (p.has('max_amount'))          state.max_amount          = p.get('max_amount') || null;
        if (p.has('page'))     state.page      = parseInt(p.get('page'),      10) || 1;
        if (p.has('page_size')) state.page_size = parseInt(p.get('page_size'), 10) || 25;
        if (p.has('ordering'))  state.ordering  = p.get('ordering');
    }

    // ── Filter dot indicators ─────────────────────────────────────
    function updateFilterDots() {
        setDot('sh-dot-surgery-type', !!state.surgery_type);
        setDot('sh-dot-doctor',       !!state.doctor_or_therapist);
        setDot('sh-dot-date',         !!(state.surgery_date_from || state.surgery_date_to));
        setDot('sh-dot-amount',       !!(state.min_amount || state.max_amount));

        var hasAny = state.surgery_type
            || state.doctor_or_therapist
            || state.surgery_date_from || state.surgery_date_to
            || state.min_amount || state.max_amount;
        var btn = document.getElementById('sh-clear-filters');
        if (btn) btn.classList.toggle('sh-visible', !!hasAny);
    }

    function setDot(id, active) {
        var el = document.getElementById(id);
        if (el) el.classList.toggle('sh-active', active);
    }

    // ── Loading / error / empty states ───────────────────────────
    function showLoading() {
        var tbody = document.getElementById('sh-tbody');
        if (!tbody) return;
        hideEmpty();
        var skeletonRow = '<tr class="sh-loading-row">'
            + COLUMNS.map(function (col) {
                return '<td><div class="sh-skeleton ' + col.skeleton + '"></div></td>';
            }).join('')
            + '</tr>';
        tbody.innerHTML = [0, 1, 2].map(function () { return skeletonRow; }).join('');

        var spinner = document.getElementById('sh-spinner');
        if (spinner) spinner.classList.add('sh-visible');
    }

    function hideLoading() {
        var spinner = document.getElementById('sh-spinner');
        if (spinner) spinner.classList.remove('sh-visible');
    }

    function showEmpty() {
        var wrap     = document.getElementById('sh-empty-state');
        var clearBtn = document.getElementById('sh-clear-search-btn');
        var addBtn   = document.getElementById('sh-add-first-btn');
        var titleEl  = document.getElementById('sh-empty-title');
        var desc     = document.getElementById('sh-empty-desc');
        if (!wrap) return;

        var hasFilters = !!(state.search || state.surgery_type || state.doctor_or_therapist
            || state.surgery_date_from || state.surgery_date_to
            || state.min_amount || state.max_amount);

        if (hasFilters) {
            if (titleEl) titleEl.textContent = 'عملی پیدا نشد';
            if (desc)    desc.textContent    = 'جستجو، فیلترها یا بازه تاریخ پرداخت را تغییر دهید.';
            if (clearBtn) clearBtn.style.display = '';
            if (addBtn)   addBtn.style.display   = 'none';
        } else {
            if (titleEl) titleEl.textContent = 'هنوز عملی ثبت نشده است';
            if (desc)    desc.textContent    = 'برای شروع ثبت سوابق درمانی، اولین عمل را اضافه کنید.';
            if (clearBtn) clearBtn.style.display = 'none';
            if (addBtn)   addBtn.style.display   = '';
        }

        wrap.style.display = '';
        var tbody = document.getElementById('sh-tbody');
        if (tbody) tbody.innerHTML = '';
    }

    function hideEmpty() {
        var wrap = document.getElementById('sh-empty-state');
        if (wrap) wrap.style.display = 'none';
    }

    function showError(msg) {
        var tbody = document.getElementById('sh-tbody');
        if (tbody) {
            tbody.innerHTML =
                '<tr><td colspan="' + COLUMNS.length + '" style="text-align:center;color:var(--red);padding:24px">'
                + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</td></tr>';
        }
    }

    // ── Load surgery types dropdown ───────────────────────────────
    function loadSurgeryTypes() {
        var sel = document.getElementById('sh-filter-surgery-type');
        if (!sel) return Promise.resolve();

        return fetch(TYPES_URL + '?page_size=200', { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                var items = data.results || data;
                items.forEach(function (t) {
                    var opt = document.createElement('option');
                    opt.value       = String(t.id);
                    opt.textContent = t.name;
                    sel.appendChild(opt);
                });
                if (state.surgery_type) sel.value = state.surgery_type;
            })
            .catch(function (err) {
                console.warn('Surgery types failed to load:', err);
            });
    }

    // ── Load doctors dropdown (from Doctor, not employees) ─
    function loadDoctors() {
        var sel = document.getElementById('sh-filter-doctor');
        if (!sel) return Promise.resolve();

        return fetch(DOCTORS_URL + '?page_size=200&is_active=true&ordering=full_name', { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                var items = data.results || data;
                items.forEach(function (d) {
                    var opt = document.createElement('option');
                    opt.value       = String(d.id);
                    opt.textContent = d.full_name + (d.specialty_name ? ' — ' + d.specialty_name : '');
                    sel.appendChild(opt);
                });
                if (state.doctor_or_therapist) sel.value = state.doctor_or_therapist;
            })
            .catch(function (err) {
                console.warn('Doctors dropdown failed to load:', err);
            });
    }

    // ── Sync UI controls → state ──────────────────────────────────
    function syncControlsToState() {
        var el;
        el = document.getElementById('sh-search');
        if (el) el.value = state.search;

        el = document.getElementById('sh-filter-surgery-type');
        if (el) el.value = state.surgery_type || '';



        el = document.getElementById('sh-filter-doctor');
        if (el) el.value = state.doctor_or_therapist || '';

        el = document.getElementById('sh-filter-date-from');
        if (el) el.value = state.surgery_date_from || '';

        el = document.getElementById('sh-filter-date-to');
        if (el) el.value = state.surgery_date_to || '';

        el = document.getElementById('sh-filter-amount-min');
        if (el) el.value = state.min_amount || '';

        el = document.getElementById('sh-filter-amount-max');
        if (el) el.value = state.max_amount || '';

        el = document.getElementById('sh-page-size-select');
        if (el) el.value = String(state.page_size);

        TableFilters.syncSortControls('sh-sort-by', 'sh-sort-dir', state);
    }

    // ── Wire up events ────────────────────────────────────────────
    function bindEvents() {
        // Search — debounced via GlobalSearch component (global_search.js)
        var searchEl = document.getElementById('sh-search');
        if (searchEl) {
            searchEl.addEventListener('global-search:changed', function (e) {
                state.search = e.detail.value;
                state.page   = 1;
                fetchList();
            });
        }

        var typeEl = document.getElementById('sh-filter-surgery-type');
        if (typeEl) {
            typeEl.addEventListener('change', function () {
                state.surgery_type = typeEl.value || null;
                state.page         = 1;
                fetchList();
            });
        }

        var doctorEl = document.getElementById('sh-filter-doctor');
        if (doctorEl) {
            doctorEl.addEventListener('change', function () {
                state.doctor_or_therapist = doctorEl.value || null;
                state.page                = 1;
                fetchList();
            });
        }

        var sizeEl = document.getElementById('sh-page-size-select');
        if (sizeEl) {
            sizeEl.addEventListener('change', function () {
                state.page_size = parseInt(sizeEl.value, 10);
                state.page      = 1;
                fetchList();
            });
        }

        // Surgery date range — debounced
        var dateFromEl = document.getElementById('sh-filter-date-from');
        var dateToEl   = document.getElementById('sh-filter-date-to');
        var debouncedDate = debounce(function () {
            state.surgery_date_from = (dateFromEl && dateFromEl.value) ? dateFromEl.value : null;
            state.surgery_date_to   = (dateToEl   && dateToEl.value)   ? dateToEl.value   : null;
            state.page              = 1;
            fetchList();
        }, 400);
        if (dateFromEl) dateFromEl.addEventListener('change', debouncedDate);
        if (dateToEl)   dateToEl.addEventListener('change', debouncedDate);

        // Amount range — debounced
        var amtMinEl = document.getElementById('sh-filter-amount-min');
        var amtMaxEl = document.getElementById('sh-filter-amount-max');
        var debouncedAmount = debounce(function () {
            state.min_amount = (amtMinEl && amtMinEl.value) ? amtMinEl.value : null;
            state.max_amount = (amtMaxEl && amtMaxEl.value) ? amtMaxEl.value : null;
            state.page       = 1;
            fetchList();
        }, 400);
        if (amtMinEl) amtMinEl.addEventListener('input', debouncedAmount);
        if (amtMaxEl) amtMaxEl.addEventListener('input', debouncedAmount);

        // Sort controls
        TableFilters.bindSortControls('sh-sort-by', 'sh-sort-dir', state, fetchList);

        var clearFiltersBtn = document.getElementById('sh-clear-filters');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', function () {
                state.surgery_type        = null;
                state.doctor_or_therapist = null;
                state.surgery_date_from   = null;
                state.surgery_date_to     = null;
                state.min_amount          = null;
                state.max_amount          = null;
                state.page                = 1;
                syncControlsToState();
                fetchList();
            });
        }

        // "Clear filters" button (shown in empty state — clears search AND all filters)
        var clearSearchBtn = document.getElementById('sh-clear-search-btn');
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', function () {
                state.search              = '';
                state.surgery_type        = null;
                state.doctor_or_therapist = null;
                state.surgery_date_from   = null;
                state.surgery_date_to     = null;
                state.min_amount          = null;
                state.max_amount          = null;
                state.page                = 1;
                syncControlsToState();
                fetchList();
            });
        }

        window.addEventListener('popstate', function () {
            readURL();
            syncControlsToState();
            fetchList();
        });

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
        renderTableHeader();
        readURL();
        syncControlsToState();
        bindEvents();
        Promise.all([loadSurgeryTypes(), loadDoctors(), fetchList()]);
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', SurgeryHistoryListApp.init);
