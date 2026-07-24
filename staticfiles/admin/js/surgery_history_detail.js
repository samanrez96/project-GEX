/**
 * SurgeryHistoryDetailApp — API-driven surgery history detail for Django Admin.
 *
 * tabLoaded[tab] is set to true only on successful render so that
 * a failed tab remains retryable by clicking it again.
 *
 * Auth: same SessionAuthentication pattern as list page — the admin
 * session cookie authenticates same-origin fetch() calls automatically.
 * 401 → redirect to login.
 */
const SurgeryHistoryDetailApp = (function () {
    'use strict';

    var API_URL        = '/api/v1/surgeries/history/';
    var USED_ITEMS_URL = '/api/v1/surgeries/used-items/';
    var PRODUCTS_URL   = '/api/v1/inventory/products/';

    var surgeryId   = null;
    var surgeryData = null;
    var activeTab   = 'info';
    var tabLoaded   = {};

    // Items-tab state
    var itemsCache        = [];   // last fetched list, keyed by lookup below
    var editingItem       = null; // null → add mode; object → edit mode
    var selectedProduct   = null; // {id, name, internal_code, product_type, product_type_display, unit, current_stock, is_out_of_stock, is_active}
    var productSearchSeq  = 0;    // guards against out-of-order debounced/paginated responses
    var pendingDeleteItem = null;

    // Product selector (افزودن قلم مصرفی modal) state
    var productResults      = [];   // accumulated rows for the current search term (across "load more" pages)
    var productNextPageUrl  = null; // DRF's next-page URL, or null when there are no more pages
    var productCurrentTerm  = '';   // last term a search was run for (drives the empty-state message)
    var productFocusedIndex = -1;   // keyboard-navigation cursor into the selectable options

    // ── Utilities ────────────────────────────────────────────────

    function getCsrfToken() {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var pair = cookies[i].trim().split('=');
            if (pair[0] === 'csrftoken') return decodeURIComponent(pair[1]);
        }
        return '';
    }

    function showToast(message, type) {
        var existing = document.getElementById('shd-toast');
        if (existing) existing.remove();
        var toast = document.createElement('div');
        toast.id = 'shd-toast';
        toast.className = 'shd-toast shd-toast--' + (type || 'success');
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 3500);
    }

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

    // Quantities/stock are decimal_places=3 — trims trailing zeros (20.000 → 20)
    // so fractional units (7.5) still show cleanly.
    function formatQty(n) {
        if (n === null || n === undefined || n === '') return '۰';
        var num = parseFloat(n);
        if (isNaN(num)) return toPersian(String(n));
        var str = num.toFixed(3).replace(/\.?0+$/, '');
        return toPersian(str);
    }

    function toPersian(n) {
        return String(n).replace(/\d/g, function (d) {
            return '۰۱۲۳۴۵۶۷۸۹'[d];
        });
    }

    // Normalizes Persian/Arabic digits the user may type into the Product
    // search box back to ASCII, since internal_code/barcode are stored (and
    // matched via icontains) as plain ASCII digits.
    var _PERSIAN_ARABIC_DIGITS = { '۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9',
                                    '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9' };
    function toEnglishDigits(s) {
        return String(s).replace(/[۰-۹٠-٩]/g, function (d) { return _PERSIAN_ARABIC_DIGITS[d] || d; });
    }

    function formatMoney(n) {
        if (n === null || n === undefined || n === '') return '—';
        var num = parseFloat(n);
        if (isNaN(num)) return '—';
        var formatted = Math.round(num).toLocaleString('en-US', { maximumFractionDigits: 0 }).replace(/,/g, '٬');
        return toPersian(formatted) + ' تومان';
    }

    function formatTime(t) {
        if (!t) return '—';
        var parts = String(t).split(':');
        if (parts.length < 2) return toPersian(t);
        return toPersian(parts[0]) + ':' + toPersian(parts[1]);
    }

    function fieldOrMuted(value) {
        return value ? escapeHtml(value) : '<span class="shd-muted">—</span>';
    }

    function renderPreviousSurgeries(list) {
        if (!list || list.length === 0) return '<span class="shd-muted">—</span>';
        return '<ul class="shd-prev-surgeries">' + list.map(function (s) {
            var label = 'ردیف ' + toPersian(s.id) + ' — ' + formatDate(s.surgery_date)
                + (s.surgery_type_name ? ' — ' + escapeHtml(s.surgery_type_name) : '');
            return '<li><a class="shd-link" href="' + escapeHtml(s.detail_url) + '">' + label + '</a></li>';
        }).join('') + '</ul>';
    }

    function redirectToLogin() {
        window.location.href =
            '/admin/login/?next=' + encodeURIComponent(window.location.pathname);
    }

    // ── Status / payment badge HTML ───────────────────────────────

    function statusBadge(status, display) {
        var cls = {
            PLANNED:     'shd-badge--planned',
            IN_PROGRESS: 'shd-badge--in-progress',
            COMPLETED:   'shd-badge--completed',
            CANCELLED:   'shd-badge--cancelled',
        }[status] || 'shd-badge--planned';
        return '<span class="shd-badge ' + cls + '">' + escapeHtml(display || status) + '</span>';
    }

    function paymentBadge(status, display) {
        var cls = {
            PENDING: 'shd-badge--pending',
            PARTIAL: 'shd-badge--partial',
            PAID:    'shd-badge--paid',
        }[status] || 'shd-badge--pending';
        return '<span class="shd-badge ' + cls + '">' + escapeHtml(display || status) + '</span>';
    }

    // ── Fetch surgery detail ──────────────────────────────────────

    function fetchSurgery() {
        showHeaderSkeleton();
        showPanelSkeleton('info');

        fetch(API_URL + surgeryId + '/', { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401) { redirectToLogin(); return null; }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                surgeryData = data;
                renderHeader(data);
                renderInfoTab(data);
                renderTimeline(data);
                tabLoaded['info'] = true;
            })
            .catch(function (err) {
                showHeaderError(err.message);
                showPanelError('info', err.message);
            });
    }

    // ── Header card ───────────────────────────────────────────────

    function showHeaderSkeleton() {
        var el = document.getElementById('shd-header');
        if (!el) return;
        el.innerHTML =
            '<div class="shd-header-skeleton">'
            + '<div class="shd-skeleton shd-skeleton-title"></div>'
            + '<div class="shd-skeleton shd-skeleton-sub" style="margin-top:8px"></div>'
            + '</div>';
    }

    function showHeaderError(msg) {
        var el = document.getElementById('shd-header');
        if (el) el.innerHTML =
            '<div style="color:var(--red);padding:8px">خطا در بارگذاری: ' + escapeHtml(msg) + '</div>';
    }

    function renderHeader(data) {
        var el = document.getElementById('shd-header');
        if (!el) return;

        var bc = document.getElementById('shd-breadcrumb-name');
        if (bc) bc.textContent = data.patient_name || 'تاریخچه عمل';

        var changeUrl = '/admin/surgeries/surgeryhistory/' + surgeryId + '/change/';
        var listUrl   = '/admin/surgeries/surgeryhistory/';

        var typeBadge = data.surgery_type_name
            ? '<span class="shd-badge shd-badge--type">' + escapeHtml(data.surgery_type_name) + '</span>'
            : '';

        el.innerHTML =
            '<div class="shd-header-meta">'
            + '<h1 class="shd-patient-name">' + escapeHtml(data.patient_name || '—') + '</h1>'
            + '<div class="shd-header-badges">'
            + typeBadge
            + statusBadge(data.status, data.status_display)
            + paymentBadge(data.payment_status, data.payment_status_display)
            + '</div>'
            + '<div class="shd-header-meta-row">'
            + '<span>📅 ' + formatDate(data.surgery_date) + '</span>'
            + '<span style="margin-inline-start:12px">💰 <span class="shd-header-amount">' + formatMoney(data.amount) + '</span></span>'
            + '</div>'
            + (data.doctor_name
                ? '<div class="shd-header-meta-row">👨‍⚕️ ' + escapeHtml(data.doctor_name) + '</div>'
                : '')
            + '</div>'
            + '<div class="shd-header-actions">'
            + '<a class="shd-btn shd-btn--primary" href="' + changeUrl + '">✏️ ویرایش</a>'
            + '<a class="shd-btn" href="' + listUrl + '">← بازگشت به لیست</a>'
            + '</div>';
    }

    // ── Panel loading states ──────────────────────────────────────

    function showPanelSkeleton(tab) {
        var el = document.getElementById('shd-panel-' + tab);
        if (!el) return;
        el.innerHTML =
            '<div class="shd-panel-skeleton">'
            + '<div class="shd-skeleton shd-skeleton-field shd-skeleton-lg"></div>'
            + '<div class="shd-skeleton shd-skeleton-field shd-skeleton-med"></div>'
            + '<div class="shd-skeleton shd-skeleton-field shd-skeleton-sm"></div>'
            + '<div class="shd-skeleton shd-skeleton-field shd-skeleton-med"></div>'
            + '</div>';
    }

    function showPanelError(tab, msg) {
        var el = document.getElementById('shd-panel-' + tab);
        if (el) el.innerHTML =
            '<div style="text-align:center;padding:40px;color:var(--red)">'
            + 'خطا در بارگذاری: ' + escapeHtml(msg) + '</div>';
    }

    // ── Tab 1: Surgery info ───────────────────────────────────────

    function renderInfoTab(data) {
        var el = document.getElementById('shd-panel-info');
        if (!el) return;

        var patientHtml = data.patient_admin_url
            ? '<a class="shd-link" href="' + escapeHtml(data.patient_admin_url) + '">'
                + escapeHtml(data.patient_name || '—') + '</a>'
            : escapeHtml(data.patient_name || '—');

        // ── Required order (اطلاعات عمومی عمل) ──────────────────────
        var fields = [
            ['ردیف',                 '<span class="shd-ltr">' + toPersian(data.id) + '</span>'],
            ['بیمار',                 patientHtml],
            ['سن بیمار',              (data.patient_age === null || data.patient_age === undefined)
                ? '<span class="shd-muted">—</span>' : toPersian(data.patient_age)],
            ['جنسیت',                 fieldOrMuted(data.patient_gender_display)],
            ['نوع عمل',               data.surgery_type_name
                ? '<span class="shd-badge shd-badge--type">' + escapeHtml(data.surgery_type_name) + '</span>'
                : '<span class="shd-muted">—</span>'],
            ['تاریخ عمل',             formatDate(data.surgery_date)],
            ['نام جراح/درمانگر',      fieldOrMuted(data.doctor_name)],
            ['کمک اول جراح',          fieldOrMuted(data.assistant_surgeon_name)],
            ['کمک دوم جراح',          fieldOrMuted(data.second_assistant_surgeon_name)],
            ['اسکراب',                fieldOrMuted(data.scrub_employee_name)],
            ['سیرکولر',               fieldOrMuted(data.circulator_employee_name)],
            ['متخصص بیهوشی',          fieldOrMuted(data.anesthesiologist_name)],
            ['تکنسین بیهوشی',         fieldOrMuted(data.anesthesia_technician_name)],
            ['نوع بیهوشی',            fieldOrMuted(data.anesthesia_type_name)],
            ['ساعت شروع عمل',         formatTime(data.surgery_start_time)],
            ['ساعت اتمام عمل',        formatTime(data.surgery_end_time)],
            ['اعمال جراحی انجام‌شده', renderPreviousSurgeries(data.previous_surgeries)],
            ['مسئول اتاق عمل',        fieldOrMuted(data.operating_room_manager_name)],
            ['خدمات',                 fieldOrMuted(data.service_employee_name)],
            // Remaining pre-existing fields — not part of the required
            // order above, kept in this same tab (their existing section).
            ['کد پرونده',             '<span class="shd-ltr">' + escapeHtml(data.medical_record_code || '—') + '</span>'],
            ['شماره تلفن',            '<span class="shd-ltr">' + escapeHtml(data.phone_number || '—') + '</span>'],
            ['تشخیص بعد از عمل',      fieldOrMuted(data.postoperative_diagnosis)],
            ['شرح عمل و مشاهدات',      fieldOrMuted(data.operation_description)],
            ['مبلغ',                  formatMoney(data.amount)],
            ['وضعیت پرداخت',          paymentBadge(data.payment_status, data.payment_status_display)],
            ['وضعیت عمل',             statusBadge(data.status, data.status_display)],
        ];

        el.innerHTML =
            '<div class="shd-field-card">'
            + '<table class="shd-field-table">'
            + fields.map(function (r) {
                return '<tr><th>' + r[0] + '</th><td>' + r[1] + '</td></tr>';
            }).join('')
            + '</table>'
            + '</div>';

        tabLoaded['info'] = true;
    }

    // ── Tab 2: Used items (lazy fetch) ────────────────────────────

    function productTypeBadge(item) {
        if (!item.product_type) return '';
        var cls = item.product_type === 'medicine' ? 'shd-badge--medicine' : 'shd-badge--equipment';
        return '<span class="shd-badge ' + cls + '">' + escapeHtml(item.product_type_display || '') + '</span>';
    }

    function itemsToolbarHtml() {
        return '<div class="shd-items-toolbar">'
            + '<button type="button" id="shd-add-item-btn" class="shd-btn shd-btn--primary">➕ افزودن قلم مصرفی</button>'
            + '</div>';
    }

    function renderItemsTab() {
        var el = document.getElementById('shd-panel-items');
        if (!el) return;

        showPanelSkeleton('items');

        fetch(USED_ITEMS_URL + '?surgery=' + surgeryId + '&page_size=200', { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401) { redirectToLogin(); return null; }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                var items = data.results || [];
                itemsCache = items;

                if (items.length === 0) {
                    el.innerHTML =
                        itemsToolbarHtml()
                        + '<div class="shd-empty">'
                        + '<div class="shd-empty-icon">📦</div>'
                        + '<div class="shd-empty-title">اقلام مصرفی ثبت نشده</div>'
                        + '<div class="shd-empty-desc">برای این عمل هیچ قلم مصرفی ثبت نشده است.</div>'
                        + '</div>';
                } else {
                    var rows = items.map(function (item) {
                        return '<tr>'
                            + '<td>' + escapeHtml(item.product_name || '—') + '</td>'
                            + '<td class="shd-ltr" style="color:var(--muted);font-size:13px">'
                            + escapeHtml(item.product_code || '—') + '</td>'
                            + '<td>' + productTypeBadge(item) + '</td>'
                            + '<td style="text-align:left;direction:ltr">'
                            + formatQty(item.quantity) + '</td>'
                            + '<td>' + escapeHtml(item.unit || '—') + '</td>'
                            + '<td style="text-align:left;direction:ltr">'
                            + (item.current_stock === null || item.current_stock === undefined ? '—' : formatQty(item.current_stock)) + '</td>'
                            + '<td style="color:var(--muted);font-size:13px">'
                            + (item.description ? escapeHtml(item.description) : '<span class="shd-muted">—</span>')
                            + '</td>'
                            + '<td>'
                            + '<div class="shd-row-actions">'
                            + '<button type="button" class="shd-row-action-btn" data-action="edit" data-id="' + item.id + '">ویرایش</button>'
                            + '<button type="button" class="shd-row-action-btn shd-row-action-btn--danger" data-action="delete" data-id="' + item.id + '">حذف / برگشت</button>'
                            + '</div>'
                            + '</td>'
                            + '</tr>';
                    }).join('');

                    el.innerHTML =
                        itemsToolbarHtml()
                        + '<div class="shd-items-table-wrap">'
                        + '<table class="shd-items-table">'
                        + '<thead><tr>'
                        + '<th>محصول</th>'
                        + '<th>کد داخلی</th>'
                        + '<th>نوع</th>'
                        + '<th>مقدار مصرف</th>'
                        + '<th>واحد</th>'
                        + '<th>موجودی فعلی</th>'
                        + '<th>توضیحات</th>'
                        + '<th>عملیات</th>'
                        + '</tr></thead>'
                        + '<tbody>' + rows + '</tbody>'
                        + '</table>'
                        + '</div>';
                }

                bindItemsToolbarEvents(el);
                tabLoaded['items'] = true;
            })
            .catch(function (err) {
                showPanelError('items', err.message);
            });
    }

    function bindItemsToolbarEvents(panelEl) {
        var addBtn = document.getElementById('shd-add-item-btn');
        if (addBtn) addBtn.addEventListener('click', function () { openItemModal(null); });

        panelEl.querySelectorAll('[data-action="edit"]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = itemsCache.filter(function (i) { return String(i.id) === btn.dataset.id; })[0];
                if (item) openItemModal(item);
            });
        });
        panelEl.querySelectorAll('[data-action="delete"]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = itemsCache.filter(function (i) { return String(i.id) === btn.dataset.id; })[0];
                if (item) openDeleteConfirm(item);
            });
        });
    }

    // ── Item add/edit modal ────────────────────────────────────────
    //
    // Built once on demand and appended to <body> (mirrors the pattern in
    // static/admin/js/anesthesia_type.js). The product/quantity preview
    // shown here is a UI convenience only — the backend recomputes and
    // enforces everything independently (SurgeryUsedItemSerializer +
    // SurgeryInventoryService), so nothing computed client-side is ever
    // trusted as-is by the API.

    var itemModalEls = null;

    function ensureItemModal() {
        if (itemModalEls) return itemModalEls;

        var overlay = document.createElement('div');
        overlay.id = 'shd-item-modal-overlay';
        overlay.className = 'shd-modal-overlay';
        overlay.innerHTML =
            '<div class="shd-modal">'
            + '<h2 class="shd-modal-title" id="shd-item-modal-title">افزودن قلم مصرفی</h2>'

            + '<div class="shd-form-group">'
            + '<label class="shd-form-label">محصول</label>'
            + '<div class="shd-product-search">'
            + '<input type="text" id="shd-product-search-input" class="shd-form-input" '
            + 'placeholder="جستجو بر اساس نام، کد داخلی، بارکد یا دسته‌بندی…" dir="rtl" autocomplete="off">'
            + '<div class="shd-product-selected" id="shd-product-selected">'
            + '<span class="shd-product-selected-info" id="shd-product-selected-info"></span>'
            + '<button type="button" class="shd-product-selected-change" id="shd-product-change-btn">تغییر</button>'
            + '</div>'
            + '<div class="shd-product-dropdown" id="shd-product-dropdown"></div>'
            + '</div>'
            + '<div class="shd-form-error" id="shd-product-error" style="display:none"></div>'
            + '</div>'

            + '<div class="shd-form-group">'
            + '<label class="shd-form-label" for="shd-quantity-input">مقدار مصرف</label>'
            + '<input type="number" id="shd-quantity-input" class="shd-form-input" min="0.001" step="0.001" dir="ltr">'
            + '<div class="shd-form-error" id="shd-quantity-error" style="display:none"></div>'
            + '</div>'

            + '<div class="shd-stock-preview" id="shd-stock-preview" style="display:none"></div>'

            + '<div class="shd-form-group">'
            + '<label class="shd-form-label" for="shd-description-input">توضیحات (اختیاری)</label>'
            + '<textarea id="shd-description-input" class="shd-form-input" dir="rtl"></textarea>'
            + '</div>'

            + '<div class="shd-form-error" id="shd-item-form-error" style="display:none"></div>'

            + '<div class="shd-modal-actions">'
            + '<button type="button" id="shd-item-save-btn" class="shd-btn shd-btn--primary">ذخیره</button>'
            + '<button type="button" id="shd-item-cancel-btn" class="shd-btn">انصراف</button>'
            + '</div>'
            + '</div>';
        document.body.appendChild(overlay);

        itemModalEls = {
            overlay:         overlay,
            title:           document.getElementById('shd-item-modal-title'),
            searchInput:     document.getElementById('shd-product-search-input'),
            selectedBox:     document.getElementById('shd-product-selected'),
            selectedInfo:    document.getElementById('shd-product-selected-info'),
            changeBtn:       document.getElementById('shd-product-change-btn'),
            dropdown:        document.getElementById('shd-product-dropdown'),
            productError:    document.getElementById('shd-product-error'),
            quantityInput:   document.getElementById('shd-quantity-input'),
            quantityError:   document.getElementById('shd-quantity-error'),
            stockPreview:    document.getElementById('shd-stock-preview'),
            descriptionInput: document.getElementById('shd-description-input'),
            formError:       document.getElementById('shd-item-form-error'),
            saveBtn:         document.getElementById('shd-item-save-btn'),
            cancelBtn:       document.getElementById('shd-item-cancel-btn'),
        };

        itemModalEls.searchInput.addEventListener('input', function () {
            scheduleProductSearch(itemModalEls.searchInput.value);
        });
        itemModalEls.searchInput.addEventListener('keydown', handleProductSearchKeydown);
        itemModalEls.changeBtn.addEventListener('click', function () {
            selectedProduct = null;
            itemModalEls.selectedBox.classList.remove('shd-open');
            itemModalEls.searchInput.style.display = '';
            itemModalEls.searchInput.value = '';
            itemModalEls.searchInput.focus();
            updateStockPreview();
            runProductSearch(''); // show the full list immediately — don't wait for typing
        });
        itemModalEls.quantityInput.addEventListener('input', updateStockPreview);
        itemModalEls.cancelBtn.addEventListener('click', closeItemModal);
        itemModalEls.saveBtn.addEventListener('click', saveItem);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeItemModal();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && overlay.classList.contains('shd-open')) closeItemModal();
        });

        return itemModalEls;
    }

    function openItemModal(item) {
        var els = ensureItemModal();
        editingItem = item || null;

        els.title.textContent = item ? 'ویرایش قلم مصرفی' : 'افزودن قلم مصرفی';
        els.formError.style.display = 'none';
        els.productError.style.display = 'none';
        els.quantityError.style.display = 'none';
        els.dropdown.classList.remove('shd-open');
        els.searchInput.value = '';

        if (item) {
            selectedProduct = {
                id: item.product,
                name: item.product_name,
                internal_code: item.product_code,
                product_type: item.product_type,
                product_type_display: item.product_type_display,
                unit: item.unit,
                current_stock: item.current_stock,
                is_out_of_stock: false,
                is_active: item.product_is_active !== undefined ? item.product_is_active : true,
            };
            els.quantityInput.value = item.quantity;
            els.descriptionInput.value = item.description || '';
        } else {
            selectedProduct = null;
            els.quantityInput.value = '';
            els.descriptionInput.value = '';
        }
        renderSelectedProduct();
        updateStockPreview();

        els.overlay.classList.add('shd-open');

        if (!item) {
            // Add mode: show a selectable Product list immediately — the
            // user should never have to type before seeing any options.
            els.searchInput.focus();
            runProductSearch('');
        } else {
            // Edit mode: the existing Product is already shown via the
            // "selected" summary box: no need to hit the API until the
            // user clicks تغییر to pick a different one.
            els.searchInput.blur();
        }
    }

    function closeItemModal() {
        if (!itemModalEls) return;
        itemModalEls.overlay.classList.remove('shd-open');
        itemModalEls.dropdown.classList.remove('shd-open');
        editingItem = null;
        selectedProduct = null;
        productSearchSeq += 1; // invalidate any in-flight search/load-more response
        productResults = [];
        productNextPageUrl = null;
        productCurrentTerm = '';
        productFocusedIndex = -1;
    }

    function renderSelectedProduct() {
        var els = itemModalEls;
        if (selectedProduct) {
            var stockText = selectedProduct.is_out_of_stock
                ? 'ناموجود'
                : 'موجودی: ' + formatQty(selectedProduct.current_stock) + ' ' + escapeHtml(selectedProduct.unit || '');
            var inactiveBadge = selectedProduct.is_active === false
                ? '<span class="shd-badge shd-badge--inactive shd-product-inactive-badge">غیرفعال</span>'
                : '';
            els.selectedInfo.innerHTML =
                '<div class="shd-product-selected-label">محصول انتخاب‌شده:</div>'
                + '<strong>' + escapeHtml(selectedProduct.name) + '</strong>'
                + ' — کد داخلی ' + escapeHtml(selectedProduct.internal_code)
                + ' — ' + escapeHtml(selectedProduct.product_type_display || '')
                + ' — ' + stockText
                + inactiveBadge;
            els.selectedBox.classList.add('shd-open');
            els.searchInput.style.display = 'none';
        } else {
            els.selectedBox.classList.remove('shd-open');
            els.searchInput.style.display = '';
        }
    }

    // ── Product search (debounced, hits the existing products list API —
    // no separate/duplicate product table or hardcoded list) ─────────
    //
    // Pagination: DRF's own `next` link (ProductListPagination) drives a
    // "نمایش محصولات بیشتر" button — accumulated results are reset whenever
    // the search term changes (a fresh runProductSearch() call), and kept
    // when the user clicks "load more" (fetchProductPage(..., append=true)).

    var productSearchTimer = null;

    function scheduleProductSearch(term) {
        if (productSearchTimer) clearTimeout(productSearchTimer);
        productSearchTimer = setTimeout(function () { runProductSearch(term); }, 300);
    }

    // Typing "دارو"/"تجهیزات" reuses ProductFilter's exact product_type
    // filter instead of a free-text search — the raw stored value
    // ("medicine"/"equipment") would never match Persian search text.
    function detectProductTypeLabel(term) {
        var t = term.trim();
        if (t === 'دارو' || t === 'دارویی') return 'medicine';
        if (t === 'تجهیزات' || t === 'تجهیزاتی') return 'equipment';
        return null;
    }

    function buildProductSearchUrl(term) {
        var normalized = toEnglishDigits(term || '').trim();
        var url = PRODUCTS_URL + '?is_active=true&page_size=20&ordering=name';

        var typeFilter = detectProductTypeLabel(normalized);
        if (typeFilter) {
            url += '&product_type=' + typeFilter;
        } else if (normalized) {
            url += '&search=' + encodeURIComponent(normalized);
        }
        return url;
    }

    function runProductSearch(term) {
        productCurrentTerm  = term || '';
        productResults      = [];
        productNextPageUrl  = null;
        productFocusedIndex = -1;

        var thisSeq = ++productSearchSeq;
        showProductDropdownLoading();
        fetchProductPage(buildProductSearchUrl(term), thisSeq, false);
    }

    function loadMoreProducts() {
        if (!productNextPageUrl) return;
        fetchProductPage(productNextPageUrl, productSearchSeq, true);
    }

    function fetchProductPage(url, seq, append) {
        fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401) { redirectToLogin(); return null; }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                if (!data || seq !== productSearchSeq) return; // stale/superseded response
                var newRows = data.results || [];
                if (append) {
                    // Defensive de-dup: the API itself never returns a product
                    // on two different pages, this just guards the render layer.
                    var existingIds = productResults.map(function (p) { return p.id; });
                    productResults = productResults.concat(
                        newRows.filter(function (p) { return existingIds.indexOf(p.id) === -1; })
                    );
                } else {
                    productResults = newRows;
                }
                productNextPageUrl = data.next || null;
                renderProductDropdown();
            })
            .catch(function () {
                if (seq !== productSearchSeq) return;
                itemModalEls.dropdown.innerHTML =
                    '<div class="shd-product-option-empty">دریافت فهرست محصولات با خطا مواجه شد.</div>';
                itemModalEls.dropdown.classList.add('shd-open');
            });
    }

    function showProductDropdownLoading() {
        var els = itemModalEls;
        els.dropdown.innerHTML = '<div class="shd-product-option-loading">در حال بارگذاری...</div>';
        els.dropdown.classList.add('shd-open');
    }

    function productStockStatusLabel(p) {
        if (p.stock_status) return p.stock_status; // موجود / کم‌موجودی / ناموجود — same logic as the Product list page
        return (parseFloat(p.current_stock) || 0) <= 0 ? 'ناموجود' : 'موجود';
    }

    function isProductSelectable(p) {
        return productStockStatusLabel(p) !== 'ناموجود';
    }

    function productOptionHtml(p, idx) {
        var status      = productStockStatusLabel(p);
        var outOfStock   = status === 'ناموجود';
        var stockCls     = outOfStock ? 'shd-product-option-stock--out'
                          : status === 'کم‌موجودی' ? 'shd-product-option-stock--low'
                          : 'shd-product-option-stock--ok';
        var typeCls      = p.product_type === 'medicine' ? 'shd-badge--medicine' : 'shd-badge--equipment';

        var extraBits = [];
        if (p.category_name) extraBits.push('دسته: ' + escapeHtml(p.category_name));
        if (p.barcode) extraBits.push('بارکد: ' + escapeHtml(p.barcode));
        var extraHtml = extraBits.length
            ? '<div class="shd-product-option-extra">' + extraBits.join(' · ') + '</div>'
            : '';

        var cls = 'shd-product-option' + (outOfStock ? ' shd-product-option--disabled' : '');

        return '<div class="' + cls + '" data-idx="' + idx + '"' + (outOfStock ? ' data-disabled="1"' : '')
            + ' role="option" tabindex="-1">'
            + '<div class="shd-product-option-name">' + escapeHtml(p.name) + '</div>'
            + '<div class="shd-product-option-code">کد داخلی: <span dir="ltr">' + escapeHtml(p.internal_code) + '</span></div>'
            + '<div class="shd-product-option-meta">'
            + '<span class="shd-badge ' + typeCls + '">' + escapeHtml(p.product_type_display || '') + '</span>'
            + '<span class="shd-product-option-stock ' + stockCls + '">'
            + status + ' — موجودی: ' + formatQty(p.current_stock) + ' ' + escapeHtml(p.unit || '')
            + '</span>'
            + '</div>'
            + extraHtml
            + '</div>';
    }

    function selectProductOption(p) {
        selectedProduct = {
            id: p.id,
            name: p.name,
            internal_code: p.internal_code,
            product_type: p.product_type,
            product_type_display: p.product_type_display,
            unit: p.unit,
            current_stock: p.current_stock,
            is_out_of_stock: !isProductSelectable(p),
            is_active: p.is_active !== undefined ? p.is_active : true,
        };
        renderSelectedProduct();
        updateStockPreview();
        itemModalEls.dropdown.classList.remove('shd-open');
    }

    function renderProductDropdown() {
        var els  = itemModalEls;
        var term = productCurrentTerm;

        if (productResults.length === 0) {
            var emptyMsg = (term && term.trim())
                ? 'محصولی مطابق جستجو یافت نشد.'
                : 'محصولی برای انتخاب یافت نشد.';
            els.dropdown.innerHTML = '<div class="shd-product-option-empty">' + emptyMsg + '</div>';
            els.dropdown.classList.add('shd-open');
            return;
        }

        var rowsHtml = productResults.map(productOptionHtml).join('');
        var loadMoreHtml = productNextPageUrl
            ? '<button type="button" class="shd-product-loadmore" id="shd-product-loadmore-btn">نمایش محصولات بیشتر</button>'
            : '';

        els.dropdown.innerHTML = rowsHtml + loadMoreHtml;
        els.dropdown.classList.add('shd-open');

        productResults.forEach(function (p, idx) {
            if (!isProductSelectable(p)) return;
            var optEl = els.dropdown.querySelector('[data-idx="' + idx + '"]');
            if (optEl) optEl.addEventListener('click', function () { selectProductOption(p); });
        });

        var loadMoreBtn = document.getElementById('shd-product-loadmore-btn');
        if (loadMoreBtn) loadMoreBtn.addEventListener('click', loadMoreProducts);
    }

    // ── Keyboard navigation inside the results dropdown ─────────────
    // Arrow keys move focus, Enter selects, Escape closes just the
    // dropdown (a second Escape then closes the modal via the existing
    // document-level handler, since this handler stops the first one from
    // bubbling only while the dropdown is open).

    function getSelectableOptionEls() {
        return Array.prototype.slice.call(
            itemModalEls.dropdown.querySelectorAll('.shd-product-option:not(.shd-product-option--disabled)')
        );
    }

    function moveProductFocus(delta) {
        var options = getSelectableOptionEls();
        if (!options.length) return;
        if (productFocusedIndex >= 0 && options[productFocusedIndex]) {
            options[productFocusedIndex].classList.remove('shd-product-option--focused');
        }
        productFocusedIndex += delta;
        if (productFocusedIndex < 0) productFocusedIndex = options.length - 1;
        if (productFocusedIndex >= options.length) productFocusedIndex = 0;
        var el = options[productFocusedIndex];
        el.classList.add('shd-product-option--focused');
        if (el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
    }

    function handleProductSearchKeydown(e) {
        var dropdownOpen = itemModalEls.dropdown.classList.contains('shd-open');
        if (e.key === 'ArrowDown' && dropdownOpen) {
            e.preventDefault();
            moveProductFocus(1);
        } else if (e.key === 'ArrowUp' && dropdownOpen) {
            e.preventDefault();
            moveProductFocus(-1);
        } else if (e.key === 'Enter' && dropdownOpen) {
            var options = getSelectableOptionEls();
            if (productFocusedIndex >= 0 && options[productFocusedIndex]) {
                e.preventDefault();
                options[productFocusedIndex].click();
            }
        } else if (e.key === 'Escape' && dropdownOpen) {
            e.stopPropagation();
            itemModalEls.dropdown.classList.remove('shd-open');
        }
    }

    // ── Stock preview (display-only; never sent to the API) ───────

    function updateStockPreview() {
        var els = itemModalEls;
        var box = els.stockPreview;
        var qtyRaw = els.quantityInput.value;
        var qty = parseFloat(qtyRaw);

        if (!selectedProduct || qtyRaw === '' || isNaN(qty) || qty <= 0) {
            box.style.display = 'none';
            return;
        }

        var current = parseFloat(selectedProduct.current_stock) || 0;
        // Editing the same product this row already consumes from: its own
        // reserved quantity is effectively still available for comparison
        // (mirrors SurgeryUsedItemSerializer.validate on the backend).
        if (editingItem && String(editingItem.product) === String(selectedProduct.id)) {
            current += parseFloat(editingItem.quantity) || 0;
        }
        var remaining = current - qty;
        var unit = escapeHtml(selectedProduct.unit || '');

        box.innerHTML =
            '<div class="shd-stock-preview-row"><span>موجودی فعلی:</span><span>' + formatQty(current) + ' ' + unit + '</span></div>'
            + '<div class="shd-stock-preview-row"><span>مقدار مصرف:</span><span>' + formatQty(qty) + ' ' + unit + '</span></div>'
            + '<div class="shd-stock-preview-row shd-stock-preview-row--result' + (remaining < 0 ? ' shd-stock-preview-row--negative' : '') + '">'
            + '<span>موجودی پس از ثبت:</span><span>' + formatQty(remaining) + ' ' + unit + '</span></div>';
        box.style.display = '';
    }

    // ── Save (create or update) ───────────────────────────────────

    function saveItem() {
        var els = itemModalEls;
        els.formError.style.display = 'none';
        els.productError.style.display = 'none';
        els.quantityError.style.display = 'none';

        if (!selectedProduct) {
            els.productError.textContent = 'انتخاب محصول الزامی است.';
            els.productError.style.display = '';
            return;
        }
        var quantity = els.quantityInput.value;
        if (!quantity || parseFloat(quantity) <= 0) {
            els.quantityError.textContent = 'مقدار مصرف باید بزرگ‌تر از صفر باشد.';
            els.quantityError.style.display = '';
            return;
        }

        var payload = {
            surgery:     surgeryId,
            product:     selectedProduct.id,
            quantity:    quantity,
            description: els.descriptionInput.value || '',
        };

        var isEdit = !!editingItem;
        var url    = isEdit ? USED_ITEMS_URL + editingItem.id + '/' : USED_ITEMS_URL;
        var method = isEdit ? 'PATCH' : 'POST';

        els.saveBtn.disabled = true;
        els.saveBtn.textContent = 'در حال ذخیره...';

        fetch(url, {
            method: method,
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify(payload),
        })
            .then(function (res) {
                if (res.status === 401) { redirectToLogin(); return null; }
                return FormErrors.parseResponse(res).then(function (data) {
                    return { ok: res.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result) return;
                if (!result.ok) {
                    els.formError.textContent = FormErrors.format(result.data);
                    els.formError.style.display = '';
                    return;
                }
                closeItemModal();
                showToast(isEdit ? 'قلم مصرفی با موفقیت ویرایش شد.' : 'قلم مصرفی با موفقیت ثبت شد.', 'success');
                renderItemsTab();
            })
            .catch(function () {
                els.formError.textContent = 'خطا در ارتباط با سرور.';
                els.formError.style.display = '';
            })
            .finally(function () {
                els.saveBtn.disabled = false;
                els.saveBtn.textContent = 'ذخیره';
            });
    }

    // ── Delete / reverse confirm ───────────────────────────────────

    var deleteModalEls = null;

    function ensureDeleteModal() {
        if (deleteModalEls) return deleteModalEls;

        var overlay = document.createElement('div');
        overlay.id = 'shd-delete-modal-overlay';
        overlay.className = 'shd-modal-overlay';
        overlay.innerHTML =
            '<div class="shd-modal shd-modal--confirm">'
            + '<h2 class="shd-modal-title">حذف / برگشت قلم مصرفی</h2>'
            + '<p class="shd-modal-msg" id="shd-delete-modal-msg"></p>'
            + '<div class="shd-modal-actions">'
            + '<button type="button" id="shd-delete-confirm-btn" class="shd-btn shd-btn--primary">تأیید</button>'
            + '<button type="button" id="shd-delete-cancel-btn" class="shd-btn">انصراف</button>'
            + '</div>'
            + '</div>';
        document.body.appendChild(overlay);

        deleteModalEls = {
            overlay:    overlay,
            msg:        document.getElementById('shd-delete-modal-msg'),
            confirmBtn: document.getElementById('shd-delete-confirm-btn'),
            cancelBtn:  document.getElementById('shd-delete-cancel-btn'),
        };
        deleteModalEls.cancelBtn.addEventListener('click', closeDeleteConfirm);
        deleteModalEls.confirmBtn.addEventListener('click', performDelete);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeDeleteConfirm();
        });

        return deleteModalEls;
    }

    function openDeleteConfirm(item) {
        var els = ensureDeleteModal();
        pendingDeleteItem = item;
        els.msg.textContent =
            'آیا از حذف «' + (item.product_name || '') + '» (' + item.quantity + ' ' + (item.unit || '') + ') مطمئن هستید؟ '
            + 'موجودی محصول به همان مقدار برگشت داده می‌شود.';
        els.overlay.classList.add('shd-open');
    }

    function closeDeleteConfirm() {
        if (!deleteModalEls) return;
        deleteModalEls.overlay.classList.remove('shd-open');
        pendingDeleteItem = null;
    }

    function performDelete() {
        if (!pendingDeleteItem) return;
        var item = pendingDeleteItem;
        var els  = deleteModalEls;

        els.confirmBtn.disabled = true;
        fetch(USED_ITEMS_URL + item.id + '/', {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': getCsrfToken() },
        })
            .then(function (res) {
                if (res.status === 401) { redirectToLogin(); return; }
                if (res.status === 404) {
                    // Already removed (e.g. a retried/duplicate request) —
                    // treat as success, nothing left to reverse.
                    closeDeleteConfirm();
                    renderItemsTab();
                    return;
                }
                if (!res.ok) {
                    return FormErrors.parseResponse(res).then(function (data) {
                        showToast(FormErrors.format(data), 'error');
                    });
                }
                closeDeleteConfirm();
                showToast('مصرف محصول با موفقیت برگشت داده شد.', 'success');
                renderItemsTab();
            })
            .catch(function () {
                showToast('خطا در ارتباط با سرور.', 'error');
            })
            .finally(function () {
                els.confirmBtn.disabled = false;
            });
    }

    // ── Tab 3: Center commission ──────────────────────────────────

    function renderCommissionTab(data) {
        var el = document.getElementById('shd-panel-commission');
        if (!el) return;

        var hasPercent = data.center_commission_percent !== null &&
                         data.center_commission_percent !== undefined;
        var hasAmount  = data.center_commission_amount  !== null &&
                         data.center_commission_amount  !== undefined;
        var hasIncome  = data.center_commission_income_amount !== null &&
                         data.center_commission_income_amount !== undefined;

        if (!hasPercent && !hasAmount && !hasIncome) {
            el.innerHTML =
                '<div class="shd-empty">'
                + '<div class="shd-empty-icon">💳</div>'
                + '<div class="shd-empty-title">کمیسیون مرکز تعریف نشده</div>'
                + '<div class="shd-empty-desc">برای این عمل کمیسیون مرکز تنظیم نشده است.</div>'
                + '</div>';
            tabLoaded['commission'] = true;
            return;
        }

        var fields = [];

        if (hasPercent) {
            fields.push(['درصد کمیسیون مرکز',
                toPersian(data.center_commission_percent) + ' ٪']);
        }
        if (hasAmount) {
            fields.push(['مبلغ ثابت کمیسیون',
                formatMoney(data.center_commission_amount)
                + ' <small style="color:var(--muted)">(اولویت بر درصد)</small>']);
        }

        var tableHtml =
            '<div class="shd-field-card">'
            + '<table class="shd-field-table">'
            + fields.map(function (r) {
                return '<tr><th>' + r[0] + '</th><td>' + r[1] + '</td></tr>';
            }).join('')
            + '</table>'
            + '</div>';

        var highlightHtml = '';
        if (hasIncome) {
            highlightHtml =
                '<div class="shd-finance-card">'
                + '<div class="shd-section-title">درآمد محاسبه شده</div>'
                + '<div class="shd-finance-highlight">'
                + '<span class="shd-finance-highlight-label">مبلغ درآمد کمیسیون مرکز:</span>'
                + '<span class="shd-finance-highlight-value">'
                + formatMoney(data.center_commission_income_amount) + '</span>'
                + '</div>'
                + '</div>';
        }

        el.innerHTML = tableHtml + highlightHtml;
        tabLoaded['commission'] = true;
    }

    // ── Tab: شرح عمل (procedure description) ───────────────────────
    // Reuses the exact fields already added in Task 1/2 — no new model
    // or serializer fields. Multi-line values (تشخیص بعد از عمل / شرح
    // عمل و مشاهدات) are HTML-escaped and rendered with a pre-wrap span
    // so line breaks are preserved and long Persian text wraps safely,
    // never via innerHTML with raw user text.
    function multilineOrMuted(value) {
        if (!value) return '<span class="shd-muted">—</span>';
        return '<span class="shd-pre-wrap">' + escapeHtml(value) + '</span>';
    }

    function renderProcedureTab(data) {
        var el = document.getElementById('shd-panel-procedure');
        if (!el) return;

        var fields = [
            ['نام بیمار',            fieldOrMuted(data.patient_name)],
            ['نام جراح/درمانگر',      fieldOrMuted(data.doctor_name)],
            ['کمک اول جراح',          fieldOrMuted(data.assistant_surgeon_name)],
            ['کمک دوم جراح',          fieldOrMuted(data.second_assistant_surgeon_name)],
            ['بیهوشی‌دهنده',          fieldOrMuted(data.anesthesiologist_name)],
            ['نوع بیهوشی',            fieldOrMuted(data.anesthesia_type_name)],
            ['تشخیص بعد از عمل',      multilineOrMuted(data.postoperative_diagnosis)],
            ['شرح عمل و مشاهدات',      multilineOrMuted(data.operation_description)],
        ];

        el.innerHTML =
            '<div class="shd-field-card">'
            + '<table class="shd-field-table">'
            + fields.map(function (r) {
                return '<tr><th>' + r[0] + '</th><td>' + r[1] + '</td></tr>';
            }).join('')
            + '</table>'
            + '</div>';

        tabLoaded['procedure'] = true;
    }

    // ── Timeline / Activity ───────────────────────────────────────

    function renderTimeline(data) {
        var el = document.getElementById('shd-timeline');
        if (!el) return;

        el.innerHTML =
            '<div class="shd-timeline-card">'
            + '<div class="shd-timeline-title">فعالیت</div>'
            + '<div class="shd-timeline-log">'
            + '<div class="shd-timeline-entry">'
            + '<span class="shd-timeline-dot"></span>'
            + '<div><span class="shd-timeline-action">ثبت شده در </span>'
            + '<span class="shd-timeline-time">' + formatDateTime(data.created_at) + '</span></div>'
            + '</div>'
            + '<div class="shd-timeline-entry">'
            + '<span class="shd-timeline-dot"></span>'
            + '<div><span class="shd-timeline-action">آخرین ویرایش </span>'
            + '<span class="shd-timeline-time">' + formatDateTime(data.updated_at) + '</span></div>'
            + '</div>'
            + '</div>'
            + '</div>';
    }

    // ── Tab switching ─────────────────────────────────────────────

    function switchTab(tabName) {
        document.querySelectorAll('.shd-tab').forEach(function (t) {
            t.classList.toggle('shd-tab--active', t.dataset.tab === tabName);
        });
        document.querySelectorAll('.shd-tab-panel').forEach(function (p) {
            p.classList.toggle('shd-tab-panel--active', p.dataset.tab === tabName);
        });
        activeTab = tabName;

        if (tabLoaded[tabName]) return;

        switch (tabName) {
            case 'procedure':
                if (surgeryData) renderProcedureTab(surgeryData);
                break;
            case 'items':
                renderItemsTab();
                break;
            case 'commission':
                if (surgeryData) renderCommissionTab(surgeryData);
                break;
        }
    }

    // ── Init ──────────────────────────────────────────────────────

    function init() {
        var root = document.getElementById('surgery-history-detail-root');
        if (!root) return;
        surgeryId = root.dataset.surgeryId;
        if (!surgeryId) return;

        document.querySelectorAll('.shd-tab').forEach(function (tab) {
            tab.addEventListener('click', function () { switchTab(tab.dataset.tab); });
        });

        fetchSurgery();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', SurgeryHistoryDetailApp.init);
