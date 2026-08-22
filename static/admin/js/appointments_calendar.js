/**
 * AppointmentsCalendarApp — week-grid view for نوبت‌دهی (patient visit
 * scheduling). Fetches appointments for the visible Gregorian week (Sat–Fri)
 * from the DRF API and renders them as positioned blocks in an hour grid.
 * Clicking an empty area opens the admin add-form prefilled with doctor/
 * date/time; clicking an existing appointment opens its change form.
 *
 * Auth: SessionAuthentication — admin session cookie used for same-origin
 * fetch(). A 401 redirects to login, same convention as every other
 * custom admin page's JS in this project.
 */
const AppointmentsCalendarApp = (function () {
    'use strict';

    var APPOINTMENTS_URL = '/api/v1/appointments/appointments/';
    var DOCTORS_URL       = '/api/v1/contacts/doctors/';

    var START_HOUR   = 8;
    var END_HOUR     = 20;               // grid covers [START_HOUR, END_HOUR)
    var TOTAL_MIN    = (END_HOUR - START_HOUR) * 60;
    var DAY_NAMES    = ['شنبه', 'یک‌شنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه'];

    var STATUS_LABEL = {
        SCHEDULED: 'برنامه‌ریزی‌شده',
        COMPLETED: 'انجام‌شده',
        CANCELLED: 'لغو شده',
        NO_SHOW:   'عدم مراجعه',
    };

    var state = {
        weekStart:   null,   // Date — Gregorian Saturday of the visible week
        doctorId:    '',
        loading:     false,
    };

    var els = {};

    // ── Date helpers (Gregorian arithmetic only — Jalali display goes
    // through window.PersianFormat, which uses Intl internally) ─────────

    function startOfWeek(d) {
        var day = d.getDay();               // Sun=0 ... Sat=6
        var sinceSaturday = (day + 1) % 7;   // Sat=0, Sun=1, ..., Fri=6
        var out = new Date(d);
        out.setHours(0, 0, 0, 0);
        out.setDate(out.getDate() - sinceSaturday);
        return out;
    }

    function addDays(d, n) {
        var out = new Date(d);
        out.setDate(out.getDate() + n);
        return out;
    }

    function isoDate(d) {
        var y = d.getFullYear();
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var day = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + day;
    }

    function toPersian(n) {
        return window.PersianFormat ? window.PersianFormat.toPersianDigits(n) : String(n);
    }

    function jalaliDate(d) {
        return window.PersianFormat ? window.PersianFormat.formatJalaliDate(isoDate(d)) : isoDate(d);
    }

    function isToday(d) {
        var now = new Date();
        return d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
    }

    function parseTimeToMinutes(t) {
        // t is 'HH:MM:SS' or 'HH:MM'
        var parts = String(t).split(':');
        return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    }

    function minutesToHHMM(mins) {
        var h = Math.floor(mins / 60);
        var m = mins % 60;
        return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ── Doctor filter dropdown ───────────────────────────────────────

    function loadDoctors() {
        var url = DOCTORS_URL + '?is_active=true&page_size=100&ordering=full_name';
        fetch(url, { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : { results: [] }; })
            .then(function (data) {
                var sel = els.doctorFilter;
                (data.results || []).forEach(function (doc) {
                    var opt = document.createElement('option');
                    opt.value = doc.id;
                    opt.textContent = doc.full_name;
                    sel.appendChild(opt);
                });
            })
            .catch(function () { /* silent — filter just stays "همه پزشکان" */ });
    }

    // ── Fetch + render week ───────────────────────────────────────────

    function fetchWeek() {
        state.loading = true;
        els.loading.style.display = '';
        els.grid.style.display = 'none';

        var weekEnd = addDays(state.weekStart, 6);
        var params = new URLSearchParams();
        params.set('visit_date__gte', isoDate(state.weekStart));
        params.set('visit_date__lte', isoDate(weekEnd));
        params.set('page_size', '100');
        params.set('ordering', 'start_time');
        if (state.doctorId) params.set('doctor', state.doctorId);

        fetch(APPOINTMENTS_URL + '?' + params.toString(), { credentials: 'same-origin' })
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
                state.loading = false;
                renderWeek(data.results || []);
                els.loading.style.display = 'none';
                els.grid.style.display = '';
            })
            .catch(function () {
                state.loading = false;
                els.loading.textContent = 'خطا در بارگذاری نوبت‌ها.';
            });
    }

    function renderWeekLabel() {
        var weekEnd = addDays(state.weekStart, 6);
        els.weekLabel.textContent = jalaliDate(state.weekStart) + '  تا  ' + jalaliDate(weekEnd);
    }

    function buildAddUrl(dateObj, minutesFromMidnight) {
        var p = new URLSearchParams();
        if (state.doctorId) p.set('doctor', state.doctorId);
        p.set('visit_date', isoDate(dateObj));
        p.set('start_time', minutesToHHMM(minutesFromMidnight));
        return '/admin/appointments/appointment/add/?' + p.toString();
    }

    function renderWeek(appointments) {
        renderWeekLabel();

        var byDay = {};
        for (var i = 0; i < 7; i++) byDay[i] = [];
        appointments.forEach(function (appt) {
            var d = new Date(appt.visit_date + 'T00:00:00');
            var diffDays = Math.round((d - state.weekStart) / 86400000);
            if (diffDays >= 0 && diffDays <= 6) byDay[diffDays].push(appt);
        });

        var hourRows = [];
        for (var h = START_HOUR; h < END_HOUR; h++) hourRows.push(h);

        // Header row
        var headerHtml = '<div class="apt-grid-time-col apt-grid-header-cell"></div>';
        var dayDates = [];
        for (var day = 0; day < 7; day++) {
            var dDate = addDays(state.weekStart, day);
            dayDates.push(dDate);
            headerHtml += '<div class="apt-grid-header-cell' + (isToday(dDate) ? ' apt-is-today' : '') + '">'
                + '<div class="apt-day-name">' + DAY_NAMES[day] + '</div>'
                + '<div class="apt-day-date">' + jalaliDate(dDate) + '</div>'
                + '</div>';
        }

        // Time gutter
        var gutterHtml = hourRows.map(function (h) {
            return '<div class="apt-hour-label" style="height:' + (100 / hourRows.length) + '%">' + toPersian(String(h).padStart(2, '0')) + ':۰۰</div>';
        }).join('');

        // Day columns
        var colsHtml = '';
        for (day = 0; day < 7; day++) {
            var dDate2 = dayDates[day];
            var linesHtml = hourRows.map(function (h, idx) {
                return '<div class="apt-hour-line" style="top:' + (idx / hourRows.length * 100) + '%"></div>';
            }).join('');

            var blocksHtml = byDay[day].map(function (appt) {
                var startMin = parseTimeToMinutes(appt.start_time);
                var clampedStart = Math.max(START_HOUR * 60, Math.min(startMin, END_HOUR * 60));
                var top = (clampedStart - START_HOUR * 60) / TOTAL_MIN * 100;
                var heightMin = Math.max(appt.duration_minutes || 30, 15);
                var height = Math.min(heightMin / TOTAL_MIN * 100, 100 - top);
                var statusCls = 'apt-block--' + (appt.status || 'SCHEDULED').toLowerCase();
                return '<div class="apt-block ' + statusCls + '" style="top:' + top + '%;height:' + height + '%" '
                    + 'data-id="' + appt.id + '" role="button" tabindex="0">'
                    + '<div class="apt-block-time">' + toPersian(appt.start_time.slice(0, 5)) + '</div>'
                    + '<div class="apt-block-name">' + escapeHtml(appt.patient_display_name) + '</div>'
                    + '<div class="apt-block-doctor">' + escapeHtml(appt.doctor_name) + '</div>'
                    + '</div>';
            }).join('');

            colsHtml += '<div class="apt-grid-day-col" data-day="' + day + '" data-date="' + isoDate(dDate2) + '">'
                + linesHtml + blocksHtml
                + '</div>';
        }

        els.grid.innerHTML =
            '<div class="apt-grid-header">' + headerHtml + '</div>'
            + '<div class="apt-grid-body">'
            + '<div class="apt-grid-time-col">' + gutterHtml + '</div>'
            + colsHtml
            + '</div>';

        bindGridClicks();
    }

    function bindGridClicks() {
        var canAdd = els.root.getAttribute('data-has-add-permission') === '1';

        els.grid.querySelectorAll('.apt-block').forEach(function (block) {
            block.addEventListener('click', function (e) {
                e.stopPropagation();
                window.location.href = '/admin/appointments/appointment/' + block.getAttribute('data-id') + '/change/';
            });
        });

        if (!canAdd) return;

        els.grid.querySelectorAll('.apt-grid-day-col').forEach(function (col) {
            col.addEventListener('click', function (e) {
                if (e.target.closest('.apt-block')) return;
                var rect = col.getBoundingClientRect();
                var ratio = (e.clientY - rect.top) / rect.height;
                ratio = Math.max(0, Math.min(ratio, 1));
                var minutesFromStart = ratio * TOTAL_MIN;
                var roundedMinutes = Math.round(minutesFromStart / 15) * 15;
                var absoluteMinutes = START_HOUR * 60 + roundedMinutes;
                var dateObj = new Date(col.getAttribute('data-date') + 'T00:00:00');
                window.location.href = buildAddUrl(dateObj, absoluteMinutes);
            });
        });
    }

    // ── Navigation ────────────────────────────────────────────────────

    function goToWeek(weekStart) {
        state.weekStart = weekStart;
        fetchWeek();
    }

    function bindEvents() {
        els.prevBtn.addEventListener('click', function () {
            goToWeek(addDays(state.weekStart, -7));
        });
        els.nextBtn.addEventListener('click', function () {
            goToWeek(addDays(state.weekStart, 7));
        });
        els.todayBtn.addEventListener('click', function () {
            goToWeek(startOfWeek(new Date()));
        });
        els.doctorFilter.addEventListener('change', function () {
            state.doctorId = els.doctorFilter.value;
            var addBtn = els.addBtn;
            if (addBtn) {
                var url = new URL(addBtn.href, window.location.origin);
                if (state.doctorId) url.searchParams.set('doctor', state.doctorId);
                else url.searchParams.delete('doctor');
                addBtn.href = url.pathname + '?' + url.searchParams.toString();
            }
            fetchWeek();
        });
    }

    function init() {
        els.root         = document.getElementById('apt-root');
        els.loading       = document.getElementById('apt-calendar-loading');
        els.grid          = document.getElementById('apt-calendar-grid');
        els.doctorFilter  = document.getElementById('apt-filter-doctor');
        els.prevBtn       = document.getElementById('apt-prev-week');
        els.nextBtn       = document.getElementById('apt-next-week');
        els.todayBtn      = document.getElementById('apt-today-btn');
        els.weekLabel      = document.getElementById('apt-week-label');
        els.addBtn         = document.getElementById('apt-add-btn');
        if (!els.root) return;

        loadDoctors();
        bindEvents();
        goToWeek(startOfWeek(new Date()));
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', AppointmentsCalendarApp.init);
