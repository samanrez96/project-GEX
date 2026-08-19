/**
 * ProductDetailApp — API-driven product detail page for Django Admin.
 *
 * Tabs: اطلاعات عمومی، تامین‌کننده‌ها، خریدها، موجودی، نمودار قیمت، توضیحات
 *
 * General tab: shows کد داخلی، نام، نوع، قیمت خرید، موجودی فعلی،
 *              حداقل موجودی، وضعیت موجودی — no barcode/unit/sale_price/active shown.
 *
 * Vendor tab: fully functional — list, add, edit price, remove links.
 *
 * Auth: SessionAuthentication via Django admin session cookie.
 * 401 → redirect to login.
 */
const ProductDetailApp = (function () {
    'use strict';

    var API_URL          = '/api/v2/inventory/products/';
    var PRODUCT_VENDOR_API = '/api/v2/inventory/product-vendors/';
    var VENDORS_API      = '/api/v2/inventory/vendors/';

    var productId   = null;
    var productData = null;
    var activeTab   = 'general';
    var tabLoaded   = {};
    var isMainAdmin = false;

    // Vendor tab state
    var _pvList    = [];   // current ProductVendor links
    var _allVendors = [];  // all active vendors (for dropdown)
    var _editPvId  = null; // null = add mode, number = edit mode

    // ── Utilities ────────────────────────────────────────────────

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatPrice(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return '—';
            return Math.round(num).toLocaleString('fa-IR');
        } catch (_) { return String(n); }
    }

    function formatStock(n) {
        try {
            var num = parseFloat(n);
            if (isNaN(num)) return '—';
            // num.toString() strips trailing zeros naturally (12.50 → "12.5", 12.00 → "12")
            var s = num.toString();
            return window.PersianFormat ? window.PersianFormat.toPersianDigits(s) : s;
        } catch (_) { return String(n); }
    }

    // Gregorian ISO → Jalali display string (falls back to raw date part).
    function faDate(iso) {
        if (!iso) return '—';
        return window.PersianFormat
            ? window.PersianFormat.formatJalaliDate(iso)
            : String(iso).substring(0, 10);
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

    function apiHeaders() {
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        };
    }

    // ── Stock status ──────────────────────────────────────────────

    function getStockStatus(data) {
        if (data.stock_status) return data.stock_status;
        var stock = parseFloat(data.current_stock);
        var min   = parseFloat(data.minimum_stock || 0);
        if (stock <= 0)              return 'ناموجود';
        if (min > 0 && stock <= min) return 'کم‌موجودی';
        return 'موجود';
    }

    function stockStatusHtml(status) {
        var cls = status === 'ناموجود' ? 'pd-badge--empty'
                : status === 'کم‌موجودی' ? 'pd-badge--low'
                : 'pd-badge--ok';
        return '<span class="pd-badge ' + cls + '">' + escapeHtml(status) + '</span>';
    }

    // ── Fetch product ─────────────────────────────────────────────

    function fetchProduct() {
        showHeaderSkeleton();
        showPanelSkeleton('general');

        fetch(API_URL + productId + '/', { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401) { redirectToLogin(); return null; }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                productData = data;
                renderHeader(data);
                renderGeneralTab(data);
                tabLoaded['general'] = true;
            })
            .catch(function (err) {
                showHeaderError(err.message);
                showPanelError('general', err.message);
            });
    }

    // ── Header card ───────────────────────────────────────────────

    function showHeaderSkeleton() {
        var el = document.getElementById('pd-header');
        if (!el) return;
        el.innerHTML =
            '<div class="pd-header-skeleton">'
            + '<div class="pd-skeleton pd-skeleton-title"></div>'
            + '<div class="pd-skeleton pd-skeleton-sub" style="margin-top:8px"></div>'
            + '</div>';
    }

    function showHeaderError(msg) {
        var el = document.getElementById('pd-header');
        if (el) el.innerHTML =
            '<div style="color:var(--red);padding:8px">خطا در بارگذاری: ' + escapeHtml(msg) + '</div>';
    }

    function renderHeader(data) {
        var el = document.getElementById('pd-header');
        if (!el) return;

        var bc = document.getElementById('pd-breadcrumb-name');
        if (bc) bc.textContent = data.name;

        var typeLabel = data.product_type === 'medicine' ? 'دارو' : 'تجهیزات';
        var typeCls   = data.product_type === 'medicine' ? 'pd-badge--medicine' : 'pd-badge--equipment';

        var stock    = parseFloat(data.current_stock);
        var stockStatus = getStockStatus(data);
        var stockCls = stockStatus === 'ناموجود' ? 'pd-header-stock--empty'
                     : stockStatus === 'کم‌موجودی' ? 'pd-header-stock--low'
                     : '';

        var changeUrl = '/admin/inventory/product/' + productId + '/change/';
        var addUrl    = '/admin/inventory/product/add/';
        var purgeUrl  = '/admin/inventory/product/' + productId + '/purge/';

        // Purge is superuser-only: the button is never rendered for anyone
        // else. Even if it were, GET on the purge URL only shows the
        // existing impact-preview/confirmation page (never deletes), and
        // the backend (ProductPurgeService / is_main_administrator) still
        // rejects a non-superuser outright — this is a UI convenience, not
        // the security boundary.
        var deleteBtn = isMainAdmin
            ? '<a class="pd-btn pd-btn--danger" href="' + purgeUrl + '" '
              + 'title="حذف دائمی محصول و تمام سوابق وابسته">🗑️ حذف کامل محصول</a>'
            : '';

        el.innerHTML =
            '<div class="pd-header-meta">'
            + '<span class="pd-header-code">' + escapeHtml(data.internal_code) + '</span>'
            + '<h1 class="pd-header-name">' + escapeHtml(data.name) + '</h1>'
            + '<div class="pd-header-badges">'
            + '<span class="pd-badge ' + typeCls + '">' + typeLabel + '</span>'
            + stockStatusHtml(stockStatus)
            + '</div>'
            + '<span class="pd-header-stock ' + stockCls + '">'
            + 'موجودی: ' + formatStock(data.current_stock)
            + '</span>'
            + '</div>'
            + '<div class="pd-header-actions">'
            + '<a class="pd-btn pd-btn--primary" href="' + changeUrl + '">✏️ ویرایش</a>'
            + '<a class="pd-btn" href="' + addUrl + '">➕ محصول جدید</a>'
            + deleteBtn
            + '</div>';
    }

    // ── Panel loading states ──────────────────────────────────────

    function showPanelSkeleton(tab) {
        var el = document.getElementById('pd-panel-' + tab);
        if (!el) return;
        el.innerHTML =
            '<div class="pd-panel-skeleton">'
            + '<div class="pd-skeleton pd-skeleton-field pd-skeleton-lg"></div>'
            + '<div class="pd-skeleton pd-skeleton-field pd-skeleton-med"></div>'
            + '<div class="pd-skeleton pd-skeleton-field pd-skeleton-sm"></div>'
            + '<div class="pd-skeleton pd-skeleton-field pd-skeleton-med"></div>'
            + '</div>';
    }

    function showPanelError(tab, msg) {
        var el = document.getElementById('pd-panel-' + tab);
        if (el) el.innerHTML =
            '<div style="text-align:center;padding:40px;color:var(--red)">'
            + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</div>';
    }

    // ── General tab ───────────────────────────────────────────────
    // STRICT WHITELIST: only the 6 fields below are ever rendered.
    // Fields NOT rendered (intentional): unit, barcode, sale_price,
    //   category, is_active — kept in DB but hidden from this UI.

    function renderGeneralTab(data) {
        var el = document.getElementById('pd-panel-general');
        if (!el) return;

        // Whitelist: only these three identity fields
        var typeBadgeCls = data.product_type === 'medicine' ? 'pd-badge--medicine' : 'pd-badge--equipment';
        var typeLabel    = data.product_type === 'medicine' ? 'دارو' : 'تجهیزات';

        var tableHtml =
            '<table class="pd-field-table">'
            + '<tr><th>نام محصول</th><td><strong>' + escapeHtml(data.name || '—') + '</strong></td></tr>'
            + '<tr><th>کد داخلی</th><td><span class="pd-field-value--code">' + escapeHtml(data.internal_code || '—') + '</span></td></tr>'
            + '<tr><th>نوع محصول</th><td><span class="pd-badge ' + typeBadgeCls + '">' + typeLabel + '</span></td></tr>'
            + '</table>';

        // Whitelist: only these four metric cards (stock status = inventory level, NOT active/inactive)
        var stockStatus = getStockStatus(data);
        var stockCls    = stockStatus === 'ناموجود'   ? 'pd-metric-card--empty'
                        : stockStatus === 'کم‌موجودی' ? 'pd-metric-card--low'
                        : '';

        var metricsHtml =
            '<div class="pd-metric-card">'
            + '<div class="pd-metric-label">قیمت خرید</div>'
            + '<div class="pd-metric-value">' + formatPrice(data.purchase_price) + ' تومان</div>'
            + '</div>'
            + '<div class="pd-metric-card ' + stockCls + '">'
            + '<div class="pd-metric-label">موجودی فعلی</div>'
            + '<div class="pd-metric-value">' + formatStock(data.current_stock) + '</div>'
            + '</div>'
            + '<div class="pd-metric-card">'
            + '<div class="pd-metric-label">حداقل موجودی</div>'
            + '<div class="pd-metric-value">' + formatStock(data.minimum_stock) + '</div>'
            + '</div>'
            + '<div class="pd-metric-card">'
            + '<div class="pd-metric-label">وضعیت موجودی</div>'
            + '<div class="pd-metric-value">' + stockStatusHtml(stockStatus) + '</div>'
            + '</div>';

        // Replace panel content entirely with only the whitelisted fields
        el.innerHTML =
            '<div class="pd-general-layout">'
            + '<div class="pd-field-card">' + tableHtml + '</div>'
            + '<div class="pd-metrics">' + metricsHtml + '</div>'
            + '</div>';
    }

    // ── Notes tab ─────────────────────────────────────────────────

    function renderNotesTab(data) {
        var el = document.getElementById('pd-panel-notes');
        if (!el) return;

        var notes = data.internal_notes || '';

        el.innerHTML =
            '<div class="pd-notes-card">'
            + '<div id="pd-notes-view">'
            + (notes
                ? '<p class="pd-notes-text">' + escapeHtml(notes) + '</p>'
                : '<p class="pd-notes-text pd-notes-empty">بدون یادداشت</p>')
            + '<div class="pd-notes-actions">'
            + '<button class="pd-btn" id="pd-notes-edit-btn" type="button">✏️ ویرایش</button>'
            + '</div>'
            + '</div>'
            + '<div id="pd-notes-edit" style="display:none">'
            + '<textarea class="pd-notes-textarea" id="pd-notes-textarea" dir="rtl">'
            + escapeHtml(notes)
            + '</textarea>'
            + '<div class="pd-notes-actions">'
            + '<button class="pd-btn pd-btn--primary" id="pd-notes-save-btn" type="button">ذخیره</button>'
            + '<button class="pd-btn" id="pd-notes-cancel-btn" type="button">انصراف</button>'
            + '</div>'
            + '</div>'
            + '</div>';

        document.getElementById('pd-notes-edit-btn').addEventListener('click', function () {
            document.getElementById('pd-notes-view').style.display = 'none';
            document.getElementById('pd-notes-edit').style.display = '';
            var ta = document.getElementById('pd-notes-textarea');
            if (ta) ta.focus();
        });

        document.getElementById('pd-notes-cancel-btn').addEventListener('click', function () {
            document.getElementById('pd-notes-view').style.display = '';
            document.getElementById('pd-notes-edit').style.display = 'none';
        });

        document.getElementById('pd-notes-save-btn').addEventListener('click', function () {
            var ta = document.getElementById('pd-notes-textarea');
            if (ta) saveNotes(ta.value);
        });
    }

    // ── Vendor tab ────────────────────────────────────────────────

    function renderVendorsTab() {
        showPanelSkeleton('vendors');

        // Load product-vendor links and all active vendors in parallel
        var pvUrl  = PRODUCT_VENDOR_API + '?product=' + productId + '&page_size=100';
        var allUrl = VENDORS_API + '?is_active=true&page_size=200&ordering=name';

        var pvPromise  = fetch(pvUrl,  { credentials: 'same-origin' }).then(function (r) {
            if (r.status === 401) { redirectToLogin(); return null; }
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
        var allPromise = fetch(allUrl, { credentials: 'same-origin' }).then(function (r) {
            if (!r.ok) return { results: [] };
            return r.json();
        });

        Promise.all([pvPromise, allPromise])
            .then(function (results) {
                if (!results[0]) return;
                _pvList     = results[0].results || [];
                _allVendors = results[1].results || [];
                _editPvId   = null;
                _renderVendorsPanel();
                tabLoaded['vendors'] = true;
            })
            .catch(function (err) {
                showPanelError('vendors', err.message);
            });
    }

    function _renderVendorsPanel() {
        var el = document.getElementById('pd-panel-vendors');
        if (!el) return;

        var html =
            '<div class="pd-vendors-wrap">'
            // Header + add button
            + '<div class="pd-vendors-header">'
            + '<h3 class="pd-vendors-title">تامین‌کنندگان این محصول</h3>'
            + '<button class="pd-btn pd-btn--primary" id="pd-vendor-add-btn" type="button">+ افزودن تامین‌کننده</button>'
            + '</div>'
            // Inline add/edit form (hidden by default)
            + '<div id="pd-vendor-form" class="pd-vendor-form" style="display:none">'
            + '<div id="pd-vendor-form-error" class="pd-vendor-form-error" style="display:none"></div>'
            + '<div class="pd-vendor-form-grid">'
            + '<div class="pd-vendor-field">'
            + '<label class="pd-vendor-label" for="pd-vendor-select">تامین‌کننده <span style="color:var(--red)">*</span></label>'
            + '<select id="pd-vendor-select" class="pd-vendor-input">'
            + '<option value="">انتخاب تامین‌کننده</option>'
            + _allVendors.map(function (v) {
                // Filter out already-linked vendors (except the one being edited)
                var linked = _pvList.some(function (pv) { return pv.vendor === v.id && pv.id !== _editPvId; });
                return linked ? '' :
                    '<option value="' + v.id + '">' + escapeHtml(v.name) + '</option>';
            }).join('')
            + '</select>'
            + '</div>'
            + '<div class="pd-vendor-field">'
            + '<label class="pd-vendor-label" for="pd-vendor-price">قیمت واحد (تومان)</label>'
            + '<input id="pd-vendor-price" class="pd-vendor-input" type="number" min="0" step="1" placeholder="۰">'
            + '</div>'
            + '<div class="pd-vendor-field">'
            + '<label class="pd-vendor-label pd-vendor-checkbox-label">'
            + '<input id="pd-vendor-primary" type="checkbox"> تامین‌کننده اصلی'
            + '</label>'
            + '</div>'
            + '</div>'
            + '<div class="pd-vendor-form-actions">'
            + '<button class="pd-btn pd-btn--primary" id="pd-vendor-save-btn" type="button">ذخیره</button>'
            + '<button class="pd-btn" id="pd-vendor-cancel-btn" type="button">انصراف</button>'
            + '</div>'
            + '</div>'
            // Vendor list
            + '<div id="pd-vendor-list">';

        var unit = productData && productData.unit ? productData.unit : '';

        if (_pvList.length === 0) {
            html += '<div class="pd-vendors-empty">هیچ تامین‌کننده‌ای برای این محصول تعریف نشده است.</div>';
        } else {
            html += '<div class="pd-vendors-table-wrap">'
                + '<table class="pd-vendors-table">'
                + '<colgroup>'
                + '<col style="width:24%">'   // تامین‌کننده
                + '<col style="width:15%">'   // قیمت واحد
                + '<col style="width:14%">'   // تعداد خریداری‌شده
                + '<col style="width:15%">'   // تاریخ آخرین خرید
                + '<col style="width:9%">'    // اصلی
                + '<col style="width:13%">'   // کد نزد تامین‌کننده
                + '<col style="width:10%">'   // عملیات
                + '</colgroup>'
                + '<thead><tr>'
                + '<th>تامین‌کننده</th>'
                + '<th>قیمت واحد (تومان)</th>'
                + '<th>تعداد خریداری‌شده</th>'
                + '<th>تاریخ آخرین خرید</th>'
                + '<th>اصلی</th>'
                + '<th>کد نزد تامین‌کننده</th>'
                + '<th></th>'
                + '</tr></thead>'
                + '<tbody>';
            _pvList.forEach(function (pv) {
                var vendorDetailUrl = pv.vendor_detail_url || ('/admin/inventory/vendor/' + pv.vendor + '/detail/');
                var vendorLink = '<a class="pd-vendor-link" href="' + escapeHtml(vendorDetailUrl) + '" title="' + escapeHtml(pv.vendor_name || '') + '">'
                    + escapeHtml(pv.vendor_name || '—')
                    + '</a>';

                var qtyRaw  = pv.total_purchased_quantity;
                var qtyDisp = (qtyRaw !== undefined && qtyRaw !== null)
                    ? formatStock(qtyRaw) + (unit ? ' ' + escapeHtml(unit) : '')
                    : '۰';

                var dateDisp = pv.latest_purchase_date ? faDate(pv.latest_purchase_date) : '—';

                html += '<tr id="pd-pv-row-' + pv.id + '">'
                    + '<td class="pd-vendor-name-cell">' + vendorLink + '</td>'
                    + '<td class="pd-vendor-price-cell">' + (pv.unit_price ? formatPrice(pv.unit_price) + ' تومان' : '—') + '</td>'
                    + '<td class="pd-vendor-qty-cell">' + qtyDisp + '</td>'
                    + '<td class="pd-vendor-date-cell">' + escapeHtml(dateDisp) + '</td>'
                    + '<td style="text-align:center">' + (pv.is_primary ? '<span class="pd-badge pd-badge--ok">اصلی</span>' : '—') + '</td>'
                    + '<td><span class="pd-field-value--code">' + escapeHtml(pv.supplier_product_code || '—') + '</span></td>'
                    + '<td class="pd-vendor-actions-cell">'
                    + '<button class="pl-action-btn" data-action="edit-pv" data-pv-id="' + pv.id + '">ویرایش</button>'
                    + ' <button class="pl-action-btn pl-action-btn--danger" data-action="remove-pv" data-pv-id="' + pv.id + '">حذف</button>'
                    + '</td>'
                    + '</tr>';
            });
            html += '</tbody></table></div>';
        }

        html += '</div></div>'; // close pd-vendor-list + pd-vendors-wrap

        el.innerHTML = html;

        // Wire up events via delegation
        el.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-action]');
            if (!btn) return;
            var action = btn.dataset.action;
            var pvId   = parseInt(btn.dataset.pvId, 10);

            if (action === 'edit-pv')   { _openEditVendorForm(pvId); }
            if (action === 'remove-pv') { _removeVendorLink(pvId); }
        });

        // Add button
        document.getElementById('pd-vendor-add-btn').addEventListener('click', function () {
            _openAddVendorForm();
        });

        // Form save / cancel
        document.getElementById('pd-vendor-save-btn').addEventListener('click', function () {
            _saveVendorForm();
        });
        document.getElementById('pd-vendor-cancel-btn').addEventListener('click', function () {
            _closeVendorForm();
        });
    }

    function _openAddVendorForm() {
        _editPvId = null;
        _setVendorFormTitle('افزودن تامین‌کننده');
        _clearVendorForm();
        // Re-render select with all unlinked vendors
        _refreshVendorSelect(null);
        document.getElementById('pd-vendor-form').style.display = '';
        document.getElementById('pd-vendor-add-btn').style.display = 'none';
        _clearVendorFormError();
    }

    function _openEditVendorForm(pvId) {
        var pv = _pvList.filter(function (p) { return p.id === pvId; })[0];
        if (!pv) return;
        _editPvId = pvId;
        _setVendorFormTitle('ویرایش تامین‌کننده: ' + (pv.vendor_name || ''));
        // Pre-fill form
        _refreshVendorSelect(pv.vendor);
        var priceEl   = document.getElementById('pd-vendor-price');
        var primaryEl = document.getElementById('pd-vendor-primary');
        if (priceEl)   priceEl.value   = pv.unit_price || '';
        if (primaryEl) primaryEl.checked = !!pv.is_primary;
        // Lock vendor dropdown on edit (can't change vendor of an existing link)
        var selEl = document.getElementById('pd-vendor-select');
        if (selEl) selEl.disabled = true;
        document.getElementById('pd-vendor-form').style.display = '';
        document.getElementById('pd-vendor-add-btn').style.display = 'none';
        _clearVendorFormError();
    }

    function _setVendorFormTitle(title) {
        var el = document.getElementById('pd-vendor-form-title');
        if (el) el.textContent = title;
    }

    function _clearVendorForm() {
        var priceEl   = document.getElementById('pd-vendor-price');
        var primaryEl = document.getElementById('pd-vendor-primary');
        var selEl     = document.getElementById('pd-vendor-select');
        if (priceEl)   priceEl.value    = '';
        if (primaryEl) primaryEl.checked = false;
        if (selEl)     selEl.disabled   = false;
    }

    function _refreshVendorSelect(selectedVendorId) {
        var selEl = document.getElementById('pd-vendor-select');
        if (!selEl) return;
        // Rebuild options: only show vendors not already linked (except the one being edited)
        selEl.innerHTML = '<option value="">انتخاب تامین‌کننده</option>';
        _allVendors.forEach(function (v) {
            var linked = _pvList.some(function (pv) {
                return pv.vendor === v.id && pv.id !== _editPvId;
            });
            if (!linked || v.id === selectedVendorId) {
                var opt = document.createElement('option');
                opt.value       = v.id;
                opt.textContent = v.name;
                if (v.id === selectedVendorId) opt.selected = true;
                selEl.appendChild(opt);
            }
        });
    }

    function _closeVendorForm() {
        document.getElementById('pd-vendor-form').style.display = 'none';
        document.getElementById('pd-vendor-add-btn').style.display = '';
        _editPvId = null;
        _clearVendorFormError();
    }

    function _clearVendorFormError() {
        var errEl = document.getElementById('pd-vendor-form-error');
        if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }
    }

    function _showVendorFormError(msg) {
        var errEl = document.getElementById('pd-vendor-form-error');
        if (errEl) { errEl.textContent = msg; errEl.style.display = ''; }
    }

    function _saveVendorForm() {
        var selEl     = document.getElementById('pd-vendor-select');
        var priceEl   = document.getElementById('pd-vendor-price');
        var primaryEl = document.getElementById('pd-vendor-primary');

        var vendorId  = selEl   ? parseInt(selEl.value, 10)   : 0;
        var price     = priceEl ? parseFloat(priceEl.value) || 0 : 0;
        var isPrimary = primaryEl ? primaryEl.checked : false;

        _clearVendorFormError();

        if (_editPvId === null && (!vendorId || isNaN(vendorId))) {
            _showVendorFormError('لطفاً یک تامین‌کننده انتخاب کنید.');
            return;
        }

        var saveBtn = document.getElementById('pd-vendor-save-btn');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'در حال ذخیره...'; }

        var url, method, body;
        if (_editPvId === null) {
            // Create new
            url    = PRODUCT_VENDOR_API;
            method = 'POST';
            body   = { product: parseInt(productId, 10), vendor: vendorId, unit_price: price, is_primary: isPrimary, is_active: true };
        } else {
            // Update existing
            url    = PRODUCT_VENDOR_API + _editPvId + '/';
            method = 'PATCH';
            body   = { unit_price: price, is_primary: isPrimary };
        }

        fetch(url, {
            method:      method,
            credentials: 'same-origin',
            headers:     apiHeaders(),
            body:        JSON.stringify(body),
        })
        .then(function (res) {
            if (res.status === 401) { redirectToLogin(); return null; }
            if (!res.ok) return res.json().then(function (e) { throw e; });
            return res.json();
        })
        .then(function (data) {
            if (!data) return;
            // Refresh vendor tab
            tabLoaded['vendors'] = false;
            renderVendorsTab();
        })
        .catch(function (err) {
            var msg = typeof err === 'object'
                ? (err.detail || err.non_field_errors || JSON.stringify(err))
                : String(err);
            if (Array.isArray(msg)) msg = msg.join('، ');
            _showVendorFormError('خطا: ' + msg);
        })
        .finally(function () {
            if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'ذخیره'; }
        });
    }

    function _removeVendorLink(pvId) {
        var pv   = _pvList.filter(function (p) { return p.id === pvId; })[0];
        var name = pv ? (pv.vendor_name || '') : '';
        if (!confirm('حذف تامین‌کننده "' + name + '" از این محصول؟')) return;

        fetch(PRODUCT_VENDOR_API + pvId + '/', {
            method:      'DELETE',
            credentials: 'same-origin',
            headers:     apiHeaders(),
        })
        .then(function (res) {
            if (res.status === 401) { redirectToLogin(); return; }
            if (res.status === 204 || res.ok) {
                tabLoaded['vendors'] = false;
                renderVendorsTab();
            } else {
                showToast('خطا در حذف تامین‌کننده', 'error');
            }
        })
        .catch(function () {
            showToast('خطا در حذف تامین‌کننده', 'error');
        });
    }

    // ── Stub tabs ─────────────────────────────────────────────────

    function renderStub(tab, icon, title, desc) {
        var el = document.getElementById('pd-panel-' + tab);
        if (!el) return;
        el.innerHTML =
            '<div class="pd-stub">'
            + '<div class="pd-stub-icon">' + icon + '</div>'
            + '<div class="pd-stub-title">' + title + '</div>'
            + '<div class="pd-stub-desc">' + desc + '</div>'
            + '</div>';
        tabLoaded[tab] = true;
    }

    function renderPurchasesTab() {
        renderStub('purchases', '🛒', 'خریدها', 'تاریخچه خریدهای این محصول اینجا نمایش داده می‌شود.');
    }

    function renderStockTab() {
        renderStub('stock', '📦', 'تاریخچه موجودی', 'تمام حرکات موجودی این محصول اینجا نمایش داده می‌شود.');
    }

    // ── Chart tab ─────────────────────────────────────────────────

    var PRICE_HISTORY_API = '/api/v2/inventory/products/';
    var _chartInstance    = null;

    function renderChartTab() {
        var el = document.getElementById('pd-panel-chart');
        if (!el) return;

        el.innerHTML =
            '<div class="pd-chart-card">'
            + '<div class="pd-chart-filters">'
            + '<div class="pd-chart-filter-group">'
            + '<label class="pd-chart-filter-label" for="pd-chart-vendor">فروشنده</label>'
            + '<select class="pd-chart-select" id="pd-chart-vendor">'
            + '<option value="">همه فروشندگان</option>'
            + '</select>'
            + '</div>'
            + '<div class="pd-chart-filter-group">'
            + '<label class="pd-chart-filter-label" for="pd-chart-date-from">از تاریخ</label>'
            + '<input class="pd-chart-input" type="date" id="pd-chart-date-from">'
            + '</div>'
            + '<div class="pd-chart-filter-group">'
            + '<label class="pd-chart-filter-label" for="pd-chart-date-to">تا تاریخ</label>'
            + '<input class="pd-chart-input" type="date" id="pd-chart-date-to">'
            + '</div>'
            + '<button class="pd-btn pd-btn--primary pd-chart-apply-btn" id="pd-chart-apply" type="button">اعمال فیلتر</button>'
            + '<button class="pd-btn pd-chart-reset-btn" id="pd-chart-reset" type="button">پاک کردن</button>'
            + '</div>'
            + '<div id="pd-chart-status"></div>'
            + '<div class="pd-chart-canvas-wrap" id="pd-chart-canvas-wrap">'
            + '<canvas id="pd-price-chart"></canvas>'
            + '</div>'
            + '<div id="pd-chart-table-wrap"></div>'
            + '</div>';

        var applyBtn = document.getElementById('pd-chart-apply');
        var resetBtn = document.getElementById('pd-chart-reset');
        if (applyBtn) applyBtn.addEventListener('click', loadChartData);
        if (resetBtn) resetBtn.addEventListener('click', function () {
            var vSel  = document.getElementById('pd-chart-vendor');
            var dFrom = document.getElementById('pd-chart-date-from');
            var dTo   = document.getElementById('pd-chart-date-to');
            if (vSel)  vSel.value  = '';
            if (dFrom) dFrom.value = '';
            if (dTo)   dTo.value   = '';
            loadChartData();
        });

        loadChartVendors();
        loadChartData();
    }

    function loadChartVendors() {
        var sel = document.getElementById('pd-chart-vendor');
        if (!sel) return;
        fetch(VENDORS_API + '?is_active=true&page_size=200', { credentials: 'same-origin' })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
            if (!data) return;
            (data.results || []).forEach(function (v) {
                var opt = document.createElement('option');
                opt.value       = v.id;
                opt.textContent = v.name;
                sel.appendChild(opt);
            });
        })
        .catch(function () {});
    }

    function loadChartData() {
        var statusEl = document.getElementById('pd-chart-status');
        var wrapEl   = document.getElementById('pd-chart-canvas-wrap');
        var tableEl  = document.getElementById('pd-chart-table-wrap');

        if (statusEl) statusEl.innerHTML =
            '<div class="pd-chart-loading">'
            + '<div class="pd-skeleton pd-skeleton-field pd-skeleton-lg" style="height:200px;margin:0"></div>'
            + '</div>';
        if (wrapEl)  wrapEl.style.display = 'none';
        if (tableEl) tableEl.innerHTML    = '';

        var params = [];
        var vendorEl = document.getElementById('pd-chart-vendor');
        var dateFrom = document.getElementById('pd-chart-date-from');
        var dateTo   = document.getElementById('pd-chart-date-to');
        if (vendorEl && vendorEl.value) params.push('vendor_id=' + encodeURIComponent(vendorEl.value));
        if (dateFrom && dateFrom.value) params.push('date_from=' + encodeURIComponent(dateFrom.value));
        if (dateTo   && dateTo.value)   params.push('date_to='   + encodeURIComponent(dateTo.value));

        var url = PRICE_HISTORY_API + productId + '/vendor-price-history/';
        if (params.length) url += '?' + params.join('&');

        fetch(url, { credentials: 'same-origin' })
        .then(function (res) {
            if (res.status === 401) { redirectToLogin(); return null; }
            if (!res.ok) return res.json().then(function (e) { throw e; });
            return res.json();
        })
        .then(function (data) {
            if (!data) return;
            if (statusEl) statusEl.innerHTML = '';
            if (!Array.isArray(data) || data.length === 0) {
                if (statusEl) statusEl.innerHTML =
                    '<div class="pd-chart-empty">'
                    + '<div class="pd-stub-icon">📈</div>'
                    + '<div class="pd-stub-title">داده‌ای موجود نیست</div>'
                    + '<div class="pd-stub-desc">پس از ثبت و تأیید اولین خرید، نمودار قیمت نمایش داده می‌شود.</div>'
                    + '</div>';
                return;
            }
            renderChart(data);
            renderChartTable(data);
        })
        .catch(function (err) {
            var msg = (err && (err.error || err.detail)) || 'خطا در بارگذاری';
            if (statusEl) statusEl.innerHTML =
                '<div class="pd-chart-error">' + escapeHtml(String(msg)) + '</div>';
            if (wrapEl) wrapEl.style.display = 'none';
        });
    }

    function renderChart(rows) {
        if (typeof Chart === 'undefined') {
            var script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
            script.onload = function () { _buildChart(rows); };
            script.onerror = function () {
                var s = document.getElementById('pd-chart-status');
                if (s) s.innerHTML = '<div class="pd-chart-error">بارگذاری کتابخانه نمودار ناموفق بود.</div>';
            };
            document.head.appendChild(script);
        } else {
            _buildChart(rows);
        }
    }

    function _buildChart(rows) {
        var wrapEl = document.getElementById('pd-chart-canvas-wrap');
        if (wrapEl) wrapEl.style.display = '';
        if (_chartInstance) { _chartInstance.destroy(); _chartInstance = null; }
        var canvas = document.getElementById('pd-price-chart');
        if (!canvas) return;

        var vendorMap = {};
        rows.forEach(function (row) {
            var vid = row.vendor_id;
            if (!vendorMap[vid]) vendorMap[vid] = { name: row.vendor_name || ('فروشنده #' + vid), points: [] };
            vendorMap[vid].points.push({ x: faDate(row.purchase_date), y: parseFloat(row.unit_price), quantity: row.quantity, total_amount: row.total_amount, currency: row.currency || 'IRR' });
        });

        var palette = ['#6f5aa7', '#2563eb', '#16a34a', '#f97316', '#dc2626', '#0891b2', '#7c3aed', '#ca8a04'];
        var datasets = Object.keys(vendorMap).map(function (vid, idx) {
            var entry  = vendorMap[vid];
            var colour = palette[idx % palette.length];
            return { label: entry.name, data: entry.points, borderColor: colour, backgroundColor: colour + '26', pointBackgroundColor: colour, borderWidth: 2, tension: 0.3, fill: false, parsing: { xAxisKey: 'x', yAxisKey: 'y' } };
        });

        _chartInstance = new Chart(canvas, {
            type: 'line',
            data: { datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'bottom', labels: { font: { family: 'Vazirmatn, system-ui, sans-serif' } } },
                    tooltip: {
                        rtl: true,
                        textDirection: 'rtl',
                        callbacks: {
                            title: function (items) { return items.length ? items[0].raw.x : ''; },
                            label: function (item) {
                                var r = item.raw;
                                var currencyLabel = (r.currency === 'IRR' || !r.currency) ? 'تومان' : r.currency;
                                return item.dataset.label + ' — قیمت: ' + parseFloat(r.y).toLocaleString('fa-IR') + ' ' + currencyLabel;
                            },
                        },
                    },
                },
                scales: {
                    x: { type: 'category', title: { display: true, text: 'تاریخ خرید' }, ticks: { font: { family: 'Vazirmatn, system-ui, sans-serif' } } },
                    y: { title: { display: true, text: 'قیمت واحد' }, ticks: { font: { family: 'Vazirmatn, system-ui, sans-serif' }, callback: function (v) { return Number(v).toLocaleString('fa-IR'); } } },
                },
            },
        });
    }

    function renderChartTable(rows) {
        var tableEl = document.getElementById('pd-chart-table-wrap');
        if (!tableEl) return;
        var html = '<div class="pd-chart-table-container">'
            + '<table class="pd-chart-table"><thead><tr>'
            + '<th>تاریخ خرید</th><th>فروشنده</th><th>قیمت واحد</th><th>تعداد</th><th>مبلغ کل</th>'
            + '</tr></thead><tbody>'
            + rows.map(function (row) {
                return '<tr>'
                    + '<td>' + escapeHtml(faDate(row.purchase_date)) + '</td>'
                    + '<td>' + escapeHtml(row.vendor_name || '') + '</td>'
                    + '<td class="pd-chart-num">' + parseFloat(row.unit_price).toLocaleString('fa-IR') + '</td>'
                    + '<td class="pd-chart-num">' + parseFloat(row.quantity).toLocaleString('fa-IR') + '</td>'
                    + '<td class="pd-chart-num">' + parseFloat(row.total_amount).toLocaleString('fa-IR') + '</td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';
        tableEl.innerHTML = html;
    }

    // ── Tab switching ─────────────────────────────────────────────

    function switchTab(tabName) {
        document.querySelectorAll('.pd-tab').forEach(function (t) {
            t.classList.toggle('pd-tab--active', t.dataset.tab === tabName);
        });
        document.querySelectorAll('.pd-tab-panel').forEach(function (p) {
            p.classList.toggle('pd-tab-panel--active', p.dataset.tab === tabName);
        });
        activeTab = tabName;

        if (tabLoaded[tabName]) return;

        switch (tabName) {
            case 'vendors':   renderVendorsTab();   break;
            case 'purchases': renderPurchasesTab(); break;
            case 'stock':     renderStockTab();     break;
            case 'chart':     renderChartTab(); tabLoaded['chart'] = true; break;
            case 'notes':
                if (productData) { renderNotesTab(productData); tabLoaded['notes'] = true; }
                break;
        }
    }

    // ── Save notes ────────────────────────────────────────────────

    function saveNotes(notes) {
        var saveBtn = document.getElementById('pd-notes-save-btn');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'در حال ذخیره...'; }

        fetch(API_URL + productId + '/', {
            method:      'PATCH',
            credentials: 'same-origin',
            headers:     apiHeaders(),
            body:        JSON.stringify({ internal_notes: notes }),
        })
        .then(function (res) { if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); })
        .then(function (data) {
            productData.internal_notes = data.internal_notes;
            renderNotesTab(productData);
            showToast('یادداشت ذخیره شد', 'success');
        })
        .catch(function () {
            showToast('خطا در ذخیره‌سازی', 'error');
            if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'ذخیره'; }
        });
    }

    // ── Modal ─────────────────────────────────────────────────────

    var _modalCb = null;

    function showModal(message, onConfirm) {
        var overlay = document.getElementById('pd-modal-overlay');
        var msgEl   = document.getElementById('pd-modal-msg');
        if (!overlay || !msgEl) return;
        msgEl.textContent = message;
        _modalCb = onConfirm;
        overlay.classList.add('pd-open');
    }

    function hideModal() {
        var overlay = document.getElementById('pd-modal-overlay');
        if (overlay) overlay.classList.remove('pd-open');
        _modalCb = null;
    }

    // ── Toast ─────────────────────────────────────────────────────

    function showToast(message, type) {
        var existing = document.getElementById('pd-toast');
        if (existing) existing.remove();
        var toast = document.createElement('div');
        toast.id        = 'pd-toast';
        toast.className = 'pd-toast pd-toast--' + (type || 'success');
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 3000);
    }

    // ── Init ──────────────────────────────────────────────────────

    function init() {
        var root = document.getElementById('product-detail-root');
        if (!root) return;
        productId = root.dataset.productId;
        if (!productId) return;
        isMainAdmin = root.dataset.isMainAdmin === '1';

        document.querySelectorAll('.pd-tab').forEach(function (tab) {
            tab.addEventListener('click', function () { switchTab(tab.dataset.tab); });
        });

        var cancelBtn  = document.getElementById('pd-modal-cancel');
        var confirmBtn = document.getElementById('pd-modal-confirm');
        var overlay    = document.getElementById('pd-modal-overlay');
        if (cancelBtn)  cancelBtn.addEventListener('click', hideModal);
        if (confirmBtn) confirmBtn.addEventListener('click', function () {
            hideModal();
            if (_modalCb) _modalCb();
        });
        if (overlay) overlay.addEventListener('click', function (e) {
            if (e.target === overlay) hideModal();
        });

        fetchProduct();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', ProductDetailApp.init);
