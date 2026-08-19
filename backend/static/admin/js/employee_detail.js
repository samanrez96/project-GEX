/**
 * EmployeeDetailApp — API-driven employee detail page for Django Admin.
 *
 * tabLoaded[tab] is set to true ONLY on successful render so that
 * a failed tab remains retryable by clicking it again.
 *
 * Auth: same SessionAuthentication pattern as EmployeeListApp — the admin
 * session cookie authenticates same-origin fetch() calls automatically.
 * 401 → redirect to login.
 */
const EmployeeDetailApp = (function () {
    'use strict';

    var API_URL                  = '/api/v2/employees/';
    var COMMISSIONS_URL          = '/api/v2/employees/purchase-commissions/';
    var SURGERY_COMMISSIONS_URL  = '/api/v2/payroll/commission-transactions/';

    var employeeId   = null;
    var employeeData = null;
    var activeTab    = 'work';
    var tabLoaded    = {};

    // ── Utilities ────────────────────────────────────────────────

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatDate(iso) {
        return window.PersianFormat
            ? window.PersianFormat.formatJalaliDate(iso)
            : (iso ? String(iso).slice(0, 10) : '—');
    }

    function formatDateTime(iso) {
        return window.PersianFormat
            ? window.PersianFormat.formatJalaliDateTime(iso)
            : (iso ? String(iso).slice(0, 16) : '—');
    }

    function getCsrfToken() {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var pair = cookies[i].trim().split('=');
            if (pair[0] === 'csrftoken') return decodeURIComponent(pair[1]);
        }
        return '';
    }

    function redirectToLogin() {
        window.location.href =
            '/admin/login/?next=' + encodeURIComponent(window.location.pathname);
    }

    // ── Fetch employee ────────────────────────────────────────────

    function fetchEmployee() {
        showHeaderSkeleton();
        showPanelSkeleton('work');

        fetch(API_URL + employeeId + '/', { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401) { redirectToLogin(); return null; }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                employeeData = data;
                renderHeader(data);
                renderWorkTab(data);
                renderChatter(data);
                tabLoaded['work'] = true;
            })
            .catch(function (err) {
                showHeaderError(err.message);
                showPanelError('work', err.message);
            });
    }

    // ── Header card ───────────────────────────────────────────────

    function showHeaderSkeleton() {
        var el = document.getElementById('ed-header');
        if (!el) return;
        el.innerHTML =
            '<div class="ed-header-skeleton">'
            + '<div class="ed-skeleton ed-skeleton-title"></div>'
            + '<div class="ed-skeleton ed-skeleton-sub" style="margin-top:8px"></div>'
            + '</div>';
    }

    function showHeaderError(msg) {
        var el = document.getElementById('ed-header');
        if (el) el.innerHTML =
            '<div style="color:var(--red);padding:8px">خطا در بارگذاری: ' + escapeHtml(msg) + '</div>';
    }

    function renderHeader(data) {
        var el = document.getElementById('ed-header');
        if (!el) return;

        var bc = document.getElementById('ed-breadcrumb-name');
        if (bc) bc.textContent = data.full_name;

        var activeBadge = data.is_active
            ? '<span class="ed-badge ed-badge--active">فعال</span>'
            : '<span class="ed-badge ed-badge--inactive">غیرفعال</span>';

        var posBadge = data.job_position_name
            ? '<span class="ed-badge ed-badge--position">' + escapeHtml(data.job_position_name) + '</span>'
            : '';

        var changeUrl = '/admin/employees/employee/' + employeeId + '/change/';
        var addUrl    = '/admin/employees/employee/add/';

        var toggleBtn = data.is_active
            ? '<button class="ed-btn ed-btn--danger" id="ed-toggle-btn" type="button">⏸ غیرفعال کردن</button>'
            : '<button class="ed-btn ed-btn--success" id="ed-toggle-btn" type="button">✅ فعال کردن</button>';

        el.innerHTML =
            '<div class="ed-header-meta">'
            + '<h1 class="ed-name">' + escapeHtml(data.full_name) + '</h1>'
            + '<div class="ed-header-badges">'
            + posBadge + activeBadge
            + '</div>'
            + '<div class="ed-header-start-date">تاریخ شروع همکاری: ' + formatDate(data.start_date) + '</div>'
            + '</div>'
            + '<div class="ed-header-actions">'
            + '<a class="ed-btn ed-btn--primary" href="' + changeUrl + '">✏️ ویرایش</a>'
            + '<a class="ed-btn" href="' + addUrl + '">➕ کارمند جدید</a>'
            + toggleBtn
            + '</div>';

        var btn = document.getElementById('ed-toggle-btn');
        if (btn) {
            btn.addEventListener('click', function () {
                toggleActiveStatus(!data.is_active);
            });
        }
    }

    // ── Panel loading states ──────────────────────────────────────

    function showPanelSkeleton(tab) {
        var el = document.getElementById('ed-panel-' + tab);
        if (!el) return;
        el.innerHTML =
            '<div class="ed-panel-skeleton">'
            + '<div class="ed-skeleton ed-skeleton-field ed-skeleton-lg"></div>'
            + '<div class="ed-skeleton ed-skeleton-field ed-skeleton-med"></div>'
            + '<div class="ed-skeleton ed-skeleton-field ed-skeleton-sm"></div>'
            + '<div class="ed-skeleton ed-skeleton-field ed-skeleton-med"></div>'
            + '</div>';
    }

    function showPanelError(tab, msg) {
        var el = document.getElementById('ed-panel-' + tab);
        if (el) el.innerHTML =
            '<div style="text-align:center;padding:40px;color:var(--red)">'
            + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</div>';
    }

    // ── Work tab (Tab 1) — from initial fetch ─────────────────────

    function renderWorkTab(data) {
        var el = document.getElementById('ed-panel-work');
        if (!el) return;

        var activeLbl = data.is_active ? 'فعال' : 'غیرفعال';
        var activeCls = data.is_active ? 'ed-badge--active' : 'ed-badge--inactive';

        var fields = [
            ['پوزیشن شغلی', data.job_position_name
                ? '<span class="ed-badge ed-badge--position">' + escapeHtml(data.job_position_name) + '</span>'
                : '<span class="ed-muted">—</span>'],
            ['ایمیل',       data.email
                ? '<span class="ed-ltr">' + escapeHtml(data.email) + '</span>'
                : '<span class="ed-muted">—</span>'],
            ['تلفن',        data.personal_phone
                ? '<span class="ed-ltr">' + escapeHtml(data.personal_phone) + '</span>'
                : '<span class="ed-muted">—</span>'],
            ['تاریخ شروع همکاری', formatDate(data.start_date)],
            ['وضعیت',      '<span class="ed-badge ' + activeCls + '">' + activeLbl + '</span>'],
        ];

        var tableHtml =
            '<div class="ed-field-card">'
            + '<table class="ed-field-table">'
            + fields.map(function (r) {
                return '<tr><th>' + r[0] + '</th><td>' + r[1] + '</td></tr>';
            }).join('')
            + '</table>'
            + '</div>';

        var emailLink = data.email
            ? '<a class="ed-contact-card" href="mailto:' + escapeHtml(data.email) + '">'
                + '<span class="ed-contact-icon">📧</span>'
                + '<div><div class="ed-contact-label">ایمیل</div>'
                + '<div class="ed-contact-value ed-ltr">' + escapeHtml(data.email) + '</div></div>'
                + '</a>'
            : '';

        var phoneLink = data.personal_phone
            ? '<a class="ed-contact-card" href="tel:' + escapeHtml(data.personal_phone) + '">'
                + '<span class="ed-contact-icon">📞</span>'
                + '<div><div class="ed-contact-label">تلفن</div>'
                + '<div class="ed-contact-value ed-ltr">' + escapeHtml(data.personal_phone) + '</div></div>'
                + '</a>'
            : '';

        var emergencyCard = data.emergency_contact_phone
            ? '<div class="ed-contact-card">'
                + '<span class="ed-contact-icon">📞</span>'
                + '<div><div class="ed-contact-label">تماس اضطراری</div>'
                + '<div class="ed-contact-value ed-ltr">' + escapeHtml(data.emergency_contact_phone) + '</div></div>'
                + '</div>'
            : '';

        el.innerHTML =
            '<div class="ed-work-layout">'
            + tableHtml
            + '<div class="ed-quick-contact">' + emailLink + phoneLink + emergencyCard + '</div>'
            + '</div>';
    }

    // ── Personal tab (Tab 2) — from cached employeeData ───────────

    function renderPersonalTab(data) {
        var el = document.getElementById('ed-panel-personal');
        if (!el) return;

        var fields = [
            ['جنسیت',     escapeHtml(data.gender_display || '—')],
            ['شماره ملی', '<span class="ed-ltr ed-national-id">' + escapeHtml(data.national_id || '—') + '</span>'],
            ['آدرس',      data.address
                ? escapeHtml(data.address)
                : '<span class="ed-muted">ثبت نشده</span>'],
        ];

        el.innerHTML =
            '<div class="ed-sensitive-label">🔒 اطلاعات محرمانه</div>'
            + '<div class="ed-field-card">'
            + '<table class="ed-field-table">'
            + fields.map(function (r) {
                return '<tr><th>' + r[0] + '</th><td>' + r[1] + '</td></tr>';
            }).join('')
            + '</table>'
            + '</div>';

        tabLoaded['personal'] = true;
    }

    // ── Payroll tab (Tab 3) ───────────────────────────────────────

    // The canonical hourly rate source is payroll.HourlyRate — never the
    // archived Employee.hourly_rate column (see EmployeeSerializer). A rate
    // exists in one of three states here, and each must read distinctly so
    // "no rate configured" is never confused with "rate not active yet":
    //   - current_hourly_rate set        → active as of today
    //   - no current, future_hourly_rate → scheduled, not active yet
    //   - neither set                    → nothing configured at all
    function renderPayrollTab() {
        var el = document.getElementById('ed-panel-payroll');
        if (!el) return;
        if (!employeeData) {
            renderStub('payroll', '💰', 'حقوق و دستمزد', 'ابتدا اطلاعات کارمند بارگذاری شود.');
            return;
        }
        var changeUrl      = '/admin/employees/employee/' + employeeId + '/change/';
        var workEntryUrl   = '/admin/payroll/hourlyworkentry/?employee__id__exact=' + employeeId;
        var rateHistoryUrl = '/admin/payroll/hourlyrate/?employee__id__exact=' + employeeId;

        var currentRate = employeeData.current_hourly_rate;
        var futureRate  = employeeData.future_hourly_rate;

        var rows;
        if (currentRate) {
            rows =
                '<tr><th>نرخ هر ساعت</th><td><span style="direction:ltr;unicode-bidi:isolate">' + formatMoney(currentRate) + '</span></td></tr>'
                + '<tr><th>از تاریخ</th><td>' + formatDate(employeeData.current_hourly_rate_start_date) + '</td></tr>'
                + (employeeData.current_hourly_rate_end_date
                    ? '<tr><th>تا تاریخ</th><td>' + formatDate(employeeData.current_hourly_rate_end_date) + '</td></tr>'
                    : '')
                + '<tr><th>وضعیت</th><td><span class="ed-badge ed-badge--active">فعال</span></td></tr>';
        } else if (futureRate) {
            rows =
                '<tr><th>نرخ فعلی</th><td><span class="ed-muted">تنظیم نشده</span></td></tr>'
                + '<tr><th>نرخ آینده</th><td><span style="direction:ltr;unicode-bidi:isolate">' + formatMoney(futureRate) + '</span>'
                + ' از تاریخ ' + formatDate(employeeData.future_hourly_rate_start_date) + '</td></tr>';
        } else {
            rows = '<tr><th>نرخ هر ساعت</th><td><span class="ed-muted">تنظیم نشده</span></td></tr>';
        }

        el.innerHTML =
            '<div class="ed-field-card">'
            + '<table class="ed-field-table">'
            + rows
            + '</table>'
            + '</div>'
            + '<div style="margin-top:12px">'
            + '<a class="ed-btn ed-btn--primary" href="' + changeUrl + '">✏️ ویرایش نرخ ساعتی</a>'
            + '<a class="ed-btn" href="' + workEntryUrl + '" style="margin-right:8px">📋 سابقه ساعت کاری</a>'
            + '<a class="ed-btn" href="' + rateHistoryUrl + '" style="margin-right:8px">🕘 تاریخچه نرخ‌های ساعتی</a>'
            + '</div>';

        tabLoaded['payroll'] = true;
    }

    // ── Commissions tab (Tab 4) — purchase-based commissions ─────

    function formatMoney(n) {
        if (n === null || n === undefined || n === '') return '—';
        var num = parseFloat(n);
        if (isNaN(num)) return '—';
        var formatted = Math.round(num).toLocaleString('en-US', { maximumFractionDigits: 0 }).replace(/,/g, '٬');
        return toPersian(formatted) + ' تومان';
    }

    function toPersian(s) {
        return String(s).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; });
    }

    function renderCommissionsTab() {
        var el = document.getElementById('ed-panel-commissions');
        if (!el) return;

        showPanelSkeleton('commissions');

        var purchaseUrl = COMMISSIONS_URL + '?employee=' + employeeId + '&ordering=-commission_date';
        var surgeryUrl  = SURGERY_COMMISSIONS_URL + '?employee=' + employeeId + '&ordering=-created_at';

        function safeFetch(url) {
            return fetch(url, { credentials: 'same-origin' }).then(function (res) {
                if (res.status === 401) { redirectToLogin(); return null; }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            });
        }

        Promise.all([safeFetch(purchaseUrl), safeFetch(surgeryUrl)])
            .then(function (results) {
                if (!results[0] || !results[1]) return;

                var purchaseItems = results[0].results || results[0];
                var surgeryItems  = results[1].results || results[1];
                if (!Array.isArray(purchaseItems)) purchaseItems = [];
                if (!Array.isArray(surgeryItems))  surgeryItems  = [];

                var purchaseTotal = purchaseItems.reduce(function (s, c) { return s + parseFloat(c.amount || 0); }, 0);
                var surgeryTotal  = surgeryItems.reduce(function (s, c)  { return s + parseFloat(c.amount || 0); }, 0);
                var grandTotal    = purchaseTotal + surgeryTotal;

                // ── Summary bar ──────────────────────────────────────────
                var summaryHtml =
                    '<div class="ed-commissions-summary">'
                    + '<span class="ed-commissions-total-label">کمیسیون خرید: </span>'
                    + '<span class="ed-commissions-total-value">' + formatMoney(purchaseTotal) + '</span>'
                    + '<span class="ed-commissions-sep"></span>'
                    + '<span class="ed-commissions-total-label">کمیسیون عمل: </span>'
                    + '<span class="ed-commissions-total-value">' + formatMoney(surgeryTotal) + '</span>'
                    + '<span class="ed-commissions-sep"></span>'
                    + '<span class="ed-commissions-total-label">مجموع کل: </span>'
                    + '<span class="ed-commissions-total-value ed-commissions-grand">' + formatMoney(grandTotal) + '</span>'
                    + '</div>';

                // ── Purchase commission table ─────────────────────────────
                var purchaseSection;
                if (purchaseItems.length === 0) {
                    purchaseSection =
                        '<div class="ed-commission-section">'
                        + '<div class="ed-commission-section-title">کمیسیون خرید کالا</div>'
                        + '<div class="ed-empty ed-empty--inline">'
                        + '<span class="ed-muted">هیچ کمیسیون خریدی ثبت نشده است.</span>'
                        + '</div></div>';
                } else {
                    var purchaseRows = purchaseItems.map(function (c) {
                        var purchaseCell = c.purchase_pk
                            ? ('<a href="/admin/inventory/purchase/' + escapeHtml(String(c.purchase_pk)) + '/change/" class="ed-link">'
                                + escapeHtml(c.purchase_ref || ('#' + c.purchase_pk)) + '</a>')
                            : '<span class="ed-muted">—</span>';
                        var purchaseDateCell = c.purchase_date ? formatDate(c.purchase_date) : '<span class="ed-muted">—</span>';
                        var itemsCell = c.items_summary ? escapeHtml(c.items_summary) : '<span class="ed-muted">—</span>';
                        var purchaseAmountCell = c.purchase_amount
                            ? formatMoney(c.purchase_amount)
                            : '<span class="ed-muted">—</span>';
                        return '<tr>'
                            + '<td>' + formatDate(c.commission_date) + '</td>'
                            + '<td>' + purchaseCell + '</td>'
                            + '<td>' + purchaseDateCell + '</td>'
                            + '<td>' + escapeHtml(c.vendor_name || '—') + '</td>'
                            + '<td class="ed-items-cell">' + itemsCell + '</td>'
                            + '<td><span class="ed-ltr">' + purchaseAmountCell + '</span></td>'
                            + '<td><span class="ed-ltr">' + formatMoney(c.amount) + '</span></td>'
                            + '<td>' + (c.description ? escapeHtml(c.description) : '<span class="ed-muted">—</span>') + '</td>'
                            + '</tr>';
                    }).join('');
                    purchaseSection =
                        '<div class="ed-commission-section">'
                        + '<div class="ed-commission-section-title">کمیسیون خرید کالا</div>'
                        + '<div class="ed-items-table-wrap">'
                        + '<table class="ed-items-table">'
                        + '<thead><tr>'
                        + '<th>تاریخ کمیسیون</th><th>شماره فاکتور</th><th>تاریخ خرید</th>'
                        + '<th>تامین‌کننده</th><th>محصولات</th><th>مبلغ خرید</th>'
                        + '<th>مبلغ کمیسیون</th><th>توضیحات</th>'
                        + '</tr></thead>'
                        + '<tbody>' + purchaseRows + '</tbody>'
                        + '</table></div></div>';
                }

                // ── Surgery commission table ──────────────────────────────
                var surgerySection;
                if (surgeryItems.length === 0) {
                    surgerySection =
                        '<div class="ed-commission-section">'
                        + '<div class="ed-commission-section-title">کمیسیون عمل جراحی</div>'
                        + '<div class="ed-empty ed-empty--inline">'
                        + '<span class="ed-muted">هیچ کمیسیون عملی ثبت نشده است.</span>'
                        + '</div></div>';
                } else {
                    var surgeryRows = surgeryItems.map(function (c) {
                        var surgeryLink = '<a href="/admin/surgeries/surgeryhistory/' + escapeHtml(String(c.surgery)) + '/change/" class="ed-link">#' + escapeHtml(String(c.surgery)) + '</a>';
                        var surgeryDateCell = c.surgery_date ? formatDate(c.surgery_date) : '<span class="ed-muted">—</span>';
                        var surgeryAmountCell = c.surgery_amount ? formatMoney(c.surgery_amount) : '<span class="ed-muted">—</span>';
                        var percentCell = c.commission_percent
                            ? '<span class="ed-ltr">' + escapeHtml(String(c.commission_percent)) + '%</span>'
                            : '<span class="ed-muted">—</span>';
                        return '<tr>'
                            + '<td>' + formatDate(c.created_at) + '</td>'
                            + '<td>' + surgeryLink + '</td>'
                            + '<td>' + escapeHtml(c.patient_name || '—') + '</td>'
                            + '<td>' + escapeHtml(c.surgery_type_name || '—') + '</td>'
                            + '<td>' + surgeryDateCell + '</td>'
                            + '<td><span class="ed-ltr">' + surgeryAmountCell + '</span></td>'
                            + '<td>' + percentCell + '</td>'
                            + '<td><span class="ed-ltr">' + formatMoney(c.amount) + '</span></td>'
                            + '<td>' + (c.notes ? escapeHtml(c.notes) : '<span class="ed-muted">—</span>') + '</td>'
                            + '</tr>';
                    }).join('');
                    surgerySection =
                        '<div class="ed-commission-section">'
                        + '<div class="ed-commission-section-title">کمیسیون عمل جراحی</div>'
                        + '<div class="ed-items-table-wrap">'
                        + '<table class="ed-items-table">'
                        + '<thead><tr>'
                        + '<th>تاریخ ثبت</th><th>شناسه عمل</th><th>نام بیمار</th>'
                        + '<th>نوع عمل</th><th>تاریخ عمل</th><th>مبلغ عمل</th>'
                        + '<th>درصد کمیسیون</th><th>مبلغ کمیسیون</th><th>توضیحات</th>'
                        + '</tr></thead>'
                        + '<tbody>' + surgeryRows + '</tbody>'
                        + '</table></div></div>';
                }

                if (purchaseItems.length === 0 && surgeryItems.length === 0) {
                    el.innerHTML =
                        '<div class="ed-empty">'
                        + '<div class="ed-empty-icon">💼</div>'
                        + '<div class="ed-empty-title">کمیسیونی ثبت نشده</div>'
                        + '<div class="ed-empty-desc">برای این کارمند هیچ کمیسیونی ثبت نشده است.</div>'
                        + '</div>';
                } else {
                    el.innerHTML = summaryHtml + purchaseSection + surgerySection;
                }

                tabLoaded['commissions'] = true;
            })
            .catch(function (err) {
                showPanelError('commissions', err.message);
            });
    }

    // ── Notes tab (Tab 5) — from cached employeeData ──────────────

    function renderNotesTab(data) {
        var el = document.getElementById('ed-panel-notes');
        if (!el) return;

        var notes = data.description || '';

        el.innerHTML =
            '<div class="ed-notes-card">'
            + '<div id="ed-notes-view">'
            + (notes
                ? '<p class="ed-notes-text">' + escapeHtml(notes) + '</p>'
                : '<p class="ed-notes-text ed-notes-empty">بدون یادداشت</p>')
            + '<div class="ed-notes-actions">'
            + '<button class="ed-btn" id="ed-notes-edit-btn" type="button">✏️ ویرایش</button>'
            + '</div>'
            + '</div>'
            + '<div id="ed-notes-edit" style="display:none">'
            + '<textarea class="ed-notes-textarea" id="ed-notes-textarea" dir="rtl">'
            + escapeHtml(notes)
            + '</textarea>'
            + '<div class="ed-notes-actions">'
            + '<button class="ed-btn ed-btn--primary" id="ed-notes-save-btn" type="button">ذخیره</button>'
            + '<button class="ed-btn" id="ed-notes-cancel-btn" type="button">انصراف</button>'
            + '</div>'
            + '</div>'
            + '</div>';

        document.getElementById('ed-notes-edit-btn').addEventListener('click', function () {
            document.getElementById('ed-notes-view').style.display = 'none';
            document.getElementById('ed-notes-edit').style.display = '';
            var ta = document.getElementById('ed-notes-textarea');
            if (ta) ta.focus();
        });

        document.getElementById('ed-notes-cancel-btn').addEventListener('click', function () {
            document.getElementById('ed-notes-view').style.display = '';
            document.getElementById('ed-notes-edit').style.display = 'none';
        });

        document.getElementById('ed-notes-save-btn').addEventListener('click', function () {
            var ta = document.getElementById('ed-notes-textarea');
            if (ta) saveNotes(ta.value);
        });

        tabLoaded['notes'] = true;
    }

    // ── Stub panels ───────────────────────────────────────────────

    function renderStub(tab, icon, title, desc) {
        var el = document.getElementById('ed-panel-' + tab);
        if (!el) return;
        el.innerHTML =
            '<div class="ed-stub">'
            + '<div class="ed-stub-icon">' + icon + '</div>'
            + '<div class="ed-stub-title">' + title + '</div>'
            + '<div class="ed-stub-desc">' + escapeHtml(desc) + '</div>'
            + '</div>';
        tabLoaded[tab] = true;
    }

    // ── Chatter / Activity section ────────────────────────────────

    function renderChatter(data) {
        var el = document.getElementById('ed-chatter');
        if (!el) return;

        el.innerHTML =
            '<div class="ed-chatter-card">'
            + '<h3 class="ed-chatter-title">📝 یادداشت جدید</h3>'
            + '<textarea class="ed-chatter-input" id="ed-chatter-note" dir="rtl" placeholder="یادداشت جدید..."></textarea>'
            + '<div class="ed-chatter-footer">'
            + '<button class="ed-btn ed-btn--primary" id="ed-chatter-submit" type="button">ثبت</button>'
            + '</div>'
            + '<div class="ed-chatter-log">'
            + '<div class="ed-chatter-entry">'
            + '<span class="ed-chatter-dot"></span>'
            + '<div><span class="ed-chatter-action">ایجاد شده در</span> '
            + '<span class="ed-chatter-time">' + formatDateTime(data.created_at) + '</span></div>'
            + '</div>'
            + '<div class="ed-chatter-entry">'
            + '<span class="ed-chatter-dot"></span>'
            + '<div><span class="ed-chatter-action">آخرین ویرایش</span> '
            + '<span class="ed-chatter-time">' + formatDateTime(data.updated_at) + '</span></div>'
            + '</div>'
            + '</div>'
            + '</div>';

        var submitBtn = document.getElementById('ed-chatter-submit');
        if (submitBtn) {
            submitBtn.addEventListener('click', function () {
                var noteEl = document.getElementById('ed-chatter-note');
                if (!noteEl || !noteEl.value.trim()) return;
                var now      = new Date().toLocaleString('fa-IR');
                var newNote  = '[' + now + ']\n' + noteEl.value.trim();
                var existing = employeeData ? (employeeData.description || '') : '';
                var combined = existing ? existing + '\n\n' + newNote : newNote;
                saveNotes(combined, function () { noteEl.value = ''; });
            });
        }
    }

    // ── Tab switching ─────────────────────────────────────────────

    function switchTab(tabName) {
        document.querySelectorAll('.ed-tab').forEach(function (t) {
            t.classList.toggle('ed-tab--active', t.dataset.tab === tabName);
        });
        document.querySelectorAll('.ed-tab-panel').forEach(function (p) {
            p.classList.toggle('ed-tab-panel--active', p.dataset.tab === tabName);
        });
        activeTab = tabName;

        if (tabLoaded[tabName]) return;

        switch (tabName) {
            case 'personal':
                if (employeeData) renderPersonalTab(employeeData);
                break;
            case 'payroll':
                renderPayrollTab();
                break;
            case 'commissions':
                renderCommissionsTab();
                break;
            case 'notes':
                if (employeeData) renderNotesTab(employeeData);
                break;
        }
    }

    // ── Toggle active status (activate=true → activate, false → deactivate)

    function toggleActiveStatus(activate) {
        var name = employeeData ? employeeData.full_name : '';
        var message, confirmLabel;
        if (activate) {
            message      = 'کارمند "' + name + '" فعال خواهد شد.';
            confirmLabel = 'فعال کردن';
        } else {
            message      = 'کارمند "' + name + '" غیرفعال خواهد شد.\nدسترسی این کارمند به سیستم قطع خواهد شد.';
            confirmLabel = 'غیرفعال کردن';
        }

        showModal(message, confirmLabel, function () {
            fetch(API_URL + employeeId + '/', {
                method:      'PATCH',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken':  getCsrfToken(),
                },
                body: JSON.stringify({ is_active: activate }),
            })
                .then(function (res) {
                    if (res.status === 401) { redirectToLogin(); return null; }
                    if (!res.ok) {
                        return FormErrors.parseResponse(res).then(function (errData) {
                            showToast('خطا: ' + FormErrors.format(errData), 'error');
                        });
                    }
                    return res.json().then(function (data) {
                        if (!data) return;
                        employeeData = data;
                        if (!activate) {
                            window.location.href = '/admin/employees/employee/';
                        } else {
                            renderHeader(data);
                            showToast('کارمند فعال شد', 'success');
                        }
                    });
                })
                .catch(function (err) {
                    showToast('خطا: ' + err.message, 'error');
                });
        });
    }

    // ── Save notes (description field) ───────────────────────────

    function saveNotes(notes, onSuccess) {
        var saveBtn = document.getElementById('ed-notes-save-btn');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'در حال ذخیره...'; }

        fetch(API_URL + employeeId + '/', {
            method:      'PATCH',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken':  getCsrfToken(),
            },
            body: JSON.stringify({ description: notes }),
        })
            .then(function (res) {
                if (!res.ok) {
                    return FormErrors.parseResponse(res).then(function (errData) {
                        showToast('خطا: ' + FormErrors.format(errData), 'error');
                        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'ذخیره'; }
                    });
                }
                return res.json().then(function (data) {
                    if (employeeData) employeeData.description = data.description;
                    if (tabLoaded['notes']) {
                        tabLoaded['notes'] = false;
                        renderNotesTab(employeeData);
                    }
                    showToast('یادداشت ذخیره شد', 'success');
                    if (onSuccess) onSuccess();
                });
            })
            .catch(function () {
                showToast('خطا در ذخیره‌سازی', 'error');
                if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'ذخیره'; }
            });
    }

    // ── Modal ─────────────────────────────────────────────────────

    var _modalCb = null;

    function showModal(message, confirmLabel, onConfirm) {
        var overlay    = document.getElementById('ed-modal-overlay');
        var msgEl      = document.getElementById('ed-modal-msg');
        var confirmBtn = document.getElementById('ed-modal-confirm');
        if (!overlay || !msgEl) return;
        msgEl.textContent = message;
        if (confirmBtn) confirmBtn.textContent = confirmLabel || 'تأیید';
        _modalCb = onConfirm;
        overlay.classList.add('ed-open');
    }

    function hideModal() {
        var overlay = document.getElementById('ed-modal-overlay');
        if (overlay) overlay.classList.remove('ed-open');
        _modalCb = null;
    }

    // ── Toast ─────────────────────────────────────────────────────

    function showToast(message, type) {
        var existing = document.getElementById('ed-toast');
        if (existing) existing.remove();

        var toast = document.createElement('div');
        toast.id          = 'ed-toast';
        toast.className   = 'ed-toast ed-toast--' + (type || 'success');
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 3000);
    }

    // ── Init ──────────────────────────────────────────────────────

    function init() {
        var root = document.getElementById('employee-detail-root');
        if (!root) return;
        employeeId = root.dataset.employeeId;
        if (!employeeId) return;

        // Tab clicks
        document.querySelectorAll('.ed-tab').forEach(function (tab) {
            tab.addEventListener('click', function () { switchTab(tab.dataset.tab); });
        });

        // Modal buttons
        var cancelBtn  = document.getElementById('ed-modal-cancel');
        var confirmBtn = document.getElementById('ed-modal-confirm');
        var overlay    = document.getElementById('ed-modal-overlay');
        if (cancelBtn)  cancelBtn.addEventListener('click', hideModal);
        if (confirmBtn) confirmBtn.addEventListener('click', function () {
            hideModal();
            if (_modalCb) _modalCb();
        });
        if (overlay) overlay.addEventListener('click', function (e) {
            if (e.target === overlay) hideModal();
        });

        // Keyboard dismiss
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') hideModal();
        });

        fetchEmployee();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', EmployeeDetailApp.init);
