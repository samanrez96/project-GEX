/**
 * ContactsDirectoryApp — Contacts page with Doctors/Employees tabs.
 * Auth: SessionAuthentication (same-origin cookie).
 */
var ContactsDirectoryApp = (function () {
    'use strict';

    var DOCTORS_URL   = '/api/v1/contacts/doctors/';
    var EMPLOYEES_URL = '/api/v1/contacts/employees/';

    var state = {
        activeTab: 'doctors',
        search: '',
        page: 1,
        pageSize: 20,
    };

    function debounce(fn, ms) {
        var t;
        return function () { clearTimeout(t); t = setTimeout(fn, ms); };
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    async function fetchJSON(url) {
        var resp = await fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } });
        if (resp.status === 401) { window.location = '/admin/login/?next=' + encodeURIComponent(window.location.pathname); return null; }
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.json();
    }

    function buildUrl(base) {
        var p = new URLSearchParams();
        p.set('page', String(state.page));
        p.set('page_size', String(state.pageSize));
        if (state.search) p.set('search', state.search);
        return base + '?' + p.toString();
    }

    // Only the Doctors tab has a working Excel export endpoint today — the
    // Employees tab here is a lightweight contact view, and the full
    // Employee export already lives on /admin/employees/employee/.
    function updateExportButton() {
        var btn = document.getElementById('ct-export-btn');
        if (!btn) return;
        if (state.activeTab !== 'doctors') {
            btn.style.display = 'none';
            return;
        }
        btn.style.display = '';
        var p = new URLSearchParams();
        p.set('export', 'excel');
        if (state.search) p.set('search', state.search);
        btn.setAttribute('href', DOCTORS_URL + '?' + p.toString());
    }

    function renderPagination(containerId, data) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var count = data.count || 0;
        var pages = Math.ceil(count / state.pageSize);
        if (pages <= 1) { el.innerHTML = ''; return; }
        var html = '<div class="ct-pages">';
        if (state.page > 1) html += '<button class="ct-page-btn" data-page="' + (state.page - 1) + '">« قبلی</button>';
        html += '<span class="ct-page-info">صفحه ' + state.page + ' از ' + pages + '</span>';
        if (state.page < pages) html += '<button class="ct-page-btn" data-page="' + (state.page + 1) + '">بعدی »</button>';
        html += '</div>';
        el.innerHTML = html;
        el.querySelectorAll('.ct-page-btn').forEach(function (btn) {
            btn.addEventListener('click', function () { state.page = parseInt(btn.dataset.page, 10); loadData(); });
        });
    }

    function renderDoctors(data) {
        var tbody = document.getElementById('doctors-tbody');
        var empty = document.getElementById('doctors-empty');
        var results = data.results || [];
        tbody.innerHTML = '';
        empty.style.display = results.length ? 'none' : '';
        results.forEach(function (d) {
            var badge = d.cooperation_status === 'active'
                ? '<span class="ct-badge ct-badge--active">فعال</span>'
                : d.cooperation_status === 'inactive'
                ? '<span class="ct-badge ct-badge--inactive">غیرفعال</span>'
                : '<span class="ct-badge ct-badge--pending">در انتظار</span>';
            var editUrl = '/admin/contacts/doctor/' + d.id + '/change/';
            var tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            tr.innerHTML =
                '<td><a class="ct-name-link" href="' + editUrl + '" onclick="event.stopPropagation()">' + esc(d.full_name) + '</a></td>' +
                '<td>' + esc(d.specialty_name) + '</td>' +
                '<td dir="ltr">' + esc(d.phone_number) + '</td>' +
                '<td dir="ltr">' + esc(d.clinic_phone || '—') + '</td>' +
                '<td dir="ltr">' + esc(d.medical_system_number || '—') + '</td>' +
                '<td>' + badge + '</td>';
            tr.addEventListener('click', function (e) {
                if (e.target.tagName === 'A') return;
                window.location.href = editUrl;
            });
            tbody.appendChild(tr);
        });
        renderPagination('doctors-pagination', data);
    }

    function renderEmployees(data) {
        var tbody = document.getElementById('employees-tbody');
        var empty = document.getElementById('employees-empty');
        var results = data.results || [];
        tbody.innerHTML = '';
        empty.style.display = results.length ? 'none' : '';
        results.forEach(function (e) {
            var badge = e.is_active
                ? '<span class="ct-badge ct-badge--active">فعال</span>'
                : '<span class="ct-badge ct-badge--inactive">غیرفعال</span>';
            var editUrl = '/admin/employees/employee/' + e.id + '/change/';
            var tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            tr.innerHTML =
                '<td><a class="ct-name-link" href="' + editUrl + '" onclick="event.stopPropagation()">' + esc(e.full_name) + '</a></td>' +
                '<td>' + esc(e.job_position_name || '—') + '</td>' +
                '<td dir="ltr">' + esc(e.personal_phone || '—') + '</td>' +
                '<td>' + esc(e.email || '—') + '</td>' +
                '<td dir="ltr">' + esc(e.emergency_contact_phone || '—') + '</td>' +
                '<td>' + badge + '</td>';
            tr.addEventListener('click', function (e) {
                if (e.target.tagName === 'A') return;
                window.location.href = editUrl;
            });
            tbody.appendChild(tr);
        });
        renderPagination('employees-pagination', data);
    }

    async function loadData() {
        var spinner = document.getElementById('ct-spinner');
        if (spinner) spinner.style.display = 'inline-block';
        try {
            if (state.activeTab === 'doctors') {
                var d = await fetchJSON(buildUrl(DOCTORS_URL));
                if (d) renderDoctors(d);
            } else {
                var d = await fetchJSON(buildUrl(EMPLOYEES_URL));
                if (d) renderEmployees(d);
            }
        } catch (e) {
            console.error('Contacts fetch error:', e);
        } finally {
            if (spinner) spinner.style.display = 'none';
        }
    }

    function switchTab(tab) {
        state.activeTab = tab;
        state.page = 1;
        state.search = '';
        var searchEl = document.getElementById('ct-search');
        if (searchEl) searchEl.value = '';
        document.querySelectorAll('.ct-tab').forEach(function (btn) {
            btn.classList.toggle('ct-tab--active', btn.dataset.tab === tab);
        });
        document.getElementById('panel-doctors').style.display   = tab === 'doctors'   ? '' : 'none';
        document.getElementById('panel-employees').style.display = tab === 'employees' ? '' : 'none';
        updateExportButton();
        loadData();
    }

    function init() {
        document.querySelectorAll('.ct-tab').forEach(function (btn) {
            btn.addEventListener('click', function () { switchTab(btn.dataset.tab); });
        });
        var searchEl = document.getElementById('ct-search');
        if (searchEl) {
            searchEl.addEventListener('input', debounce(function () {
                state.search = searchEl.value.trim();
                state.page = 1;
                updateExportButton();
                loadData();
            }, 300));
        }
        updateExportButton();
        loadData();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    return { reload: loadData };
}());
