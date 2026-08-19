/**
 * VendorFormApp — manages the API-driven products section on the vendor
 * add/edit page (/admin/inventory/vendor/{id}/change/).
 *
 * Products section: list, add, edit unit_price + is_primary, remove.
 * Uses the same /api/v2/inventory/product-vendors/ endpoint as product_detail.js.
 *
 * Auth: SessionAuthentication via Django admin session cookie.
 * 401 → redirect to login.
 */
const VendorFormApp = (function () {
    'use strict';

    var PRODUCT_VENDOR_API = '/api/v2/inventory/product-vendors/';
    var PRODUCTS_API       = '/api/v2/inventory/products/';

    var vendorId  = window.VF_VENDOR_ID || null;
    var _pvList   = [];    // current ProductVendor links for this vendor
    var _allProds = [];    // all active products (for dropdown)
    var _editPvId = null;  // null = add mode, number = edit mode

    // ── Utilities ────────────────────────────────────────────────

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function toPersian(n) {
        return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; });
    }

    function formatPrice(n) {
        var num = parseFloat(n);
        if (isNaN(num)) return '—';
        return Math.round(num).toLocaleString('fa-IR');
    }

    function getCsrfToken() {
        // Primary source: the hidden csrfmiddlewaretoken input rendered by
        // {% csrf_token %} inside the Django admin form on this page.
        // This works regardless of cookie HttpOnly / SameSite settings and
        // never truncates the token.
        var el = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (el && el.value) return el.value;

        // Fallback: CSRF cookie, using a regex that correctly captures values
        // containing '=' characters (safe; no truncation).
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }

    function apiHeaders() {
        var token = getCsrfToken();
        if (!token) {
            // Surface a clear Persian message instead of sending an empty/invalid header
            showFormError('توکن امنیتی صفحه نامعتبر است. لطفاً صفحه را دوباره بارگذاری کنید.');
        }
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': token,
        };
    }

    function redirectToLogin() {
        window.location.href =
            '/admin/login/?next=' + encodeURIComponent(window.location.pathname);
    }

    // ── Toast notifications ───────────────────────────────────────

    function showToast(message, type) {
        var existing = document.getElementById('vf-toast');
        if (existing) existing.remove();
        var toast = document.createElement('div');
        toast.id        = 'vf-toast';
        toast.className = 'vf-toast vf-toast--' + (type || 'success');
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 3000);
    }

    // ── Modal ─────────────────────────────────────────────────────

    var _modalCb = null;

    function showModal(message, onConfirm) {
        var overlay = document.getElementById('vf-modal-overlay');
        var msgEl   = document.getElementById('vf-modal-msg');
        if (!overlay || !msgEl) return;
        msgEl.textContent = message;
        _modalCb = onConfirm;
        overlay.style.display = 'flex';
    }

    function hideModal() {
        var overlay = document.getElementById('vf-modal-overlay');
        if (overlay) overlay.style.display = 'none';
        _modalCb = null;
    }

    // ── Load products for this vendor ─────────────────────────────

    function loadProducts() {
        if (!vendorId) return;
        showProductsSkeleton();

        var pvUrl   = PRODUCT_VENDOR_API + '?vendor=' + vendorId + '&page_size=200';
        var prodUrl = PRODUCTS_API + '?page_size=500&ordering=name&is_active=true';

        var pvPromise   = fetch(pvUrl,   { credentials: 'same-origin' })
            .then(function (r) {
                if (r.status === 401) { redirectToLogin(); return null; }
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            });
        var prodPromise = fetch(prodUrl, { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) return { results: [] };
                return r.json();
            });

        Promise.all([pvPromise, prodPromise])
            .then(function (results) {
                if (!results[0]) return;
                _pvList   = results[0].results || [];
                _allProds = results[1].results || [];
                _editPvId = null;
                renderProductsTable();
            })
            .catch(function (err) {
                showProductsError(err.message);
            });
    }

    // ── Skeleton / error states ───────────────────────────────────

    function showProductsSkeleton() {
        var body = document.getElementById('vf-products-body');
        if (!body) return;
        body.innerHTML =
            '<div class="vf-products-skeleton">'
            + '<div class="vf-skeleton vf-skeleton-lg"></div>'
            + '<div class="vf-skeleton vf-skeleton-med" style="margin-top:8px"></div>'
            + '<div class="vf-skeleton vf-skeleton-sm" style="margin-top:8px"></div>'
            + '</div>';
    }

    function showProductsError(msg) {
        var body = document.getElementById('vf-products-body');
        if (body) body.innerHTML =
            '<div class="vf-products-empty" style="color:var(--red)">'
            + 'خطا در بارگذاری محصولات: ' + escapeHtml(msg) + '</div>';
    }

    // ── Render the products table ─────────────────────────────────

    function renderProductsTable() {
        var body    = document.getElementById('vf-products-body');
        var countEl = document.getElementById('vf-products-count');
        if (!body) return;

        if (countEl) countEl.textContent = toPersian(_pvList.length);

        if (_pvList.length === 0) {
            body.innerHTML =
                '<div class="vf-products-empty">'
                + 'هیچ محصولی برای این تامین‌کننده ثبت نشده است.'
                + '</div>';
            return;
        }

        var rows = _pvList.map(function (pv) {
            var price  = pv.unit_price ? formatPrice(pv.unit_price) + ' تومان' : '—';
            var badge  = pv.is_primary
                ? '<span class="vf-primary-badge">اصلی</span>'
                : '—';
            var code   = pv.product_code
                ? '<span class="vf-product-code">' + escapeHtml(pv.product_code) + '</span>'
                : '—';
            return '<tr>'
                + '<td class="vf-product-name-cell"><strong>'
                + escapeHtml(pv.product_name || '—')
                + '</strong><br>' + code + '</td>'
                + '<td class="vf-price-cell">' + price + '</td>'
                + '<td>' + badge + '</td>'
                + '<td><div class="vf-actions-cell">'
                + '<button class="vf-action-btn" type="button" data-action="edit-pv" data-pv-id="' + pv.id + '">ویرایش</button>'
                + '<button class="vf-action-btn vf-action-btn--danger" type="button" data-action="remove-pv" data-pv-id="' + pv.id + '">حذف</button>'
                + '</div></td>'
                + '</tr>';
        }).join('');

        body.innerHTML =
            '<div class="vf-products-table-wrap">'
            + '<table class="vf-products-table">'
            + '<thead><tr>'
            + '<th>محصول</th>'
            + '<th>قیمت واحد</th>'
            + '<th>فروشنده اصلی</th>'
            + '<th></th>'
            + '</tr></thead>'
            + '<tbody>' + rows + '</tbody>'
            + '</table></div>';

        body.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-action]');
            if (!btn) return;
            var action = btn.dataset.action;
            var pvId   = parseInt(btn.dataset.pvId, 10);
            if (action === 'edit-pv')   openEditForm(pvId);
            if (action === 'remove-pv') removeProduct(pvId);
        });
    }

    // ── Product autocomplete ──────────────────────────────────────
    // Architecture: one visible text input (search + display) +
    //               one hidden input storing the selected product id +
    //               one custom dropdown div for results.
    //
    // mousedown on dropdown items fires BEFORE the blur event on the text
    // input, so e.preventDefault() inside mousedown keeps focus on the input
    // long enough to record the selection before the dropdown closes.

    function _productLabel(p) {
        return p.internal_code ? p.name + ' (' + p.internal_code + ')' : p.name;
    }

    function renderProductDropdown(searchText) {
        var dropEl = document.getElementById('vf-product-dropdown');
        if (!dropEl) return;

        var query   = (searchText || '').trim().toLowerCase();
        var matches = query
            ? _allProds.filter(function (p) {
                return (p.name && p.name.toLowerCase().indexOf(query) !== -1)
                    || (p.internal_code && p.internal_code.toLowerCase().indexOf(query) !== -1);
              })
            : _allProds.slice(0, 100);   // show first 100 when query is empty

        if (matches.length === 0) {
            dropEl.innerHTML = '<div style="padding:10px 14px;color:var(--muted,#888);font-size:13px">محصولی یافت نشد</div>';
        } else {
            dropEl.innerHTML = matches.map(function (p) {
                var label = escapeHtml(_productLabel(p));
                return '<div class="vf-ac-item" data-pid="' + p.id + '" data-label="' + label + '"'
                    + ' style="padding:9px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border,#eee)">'
                    + label + '</div>';
            }).join('');
        }
        dropEl.style.display = '';
    }

    function hideProductDropdown() {
        var dropEl = document.getElementById('vf-product-dropdown');
        if (dropEl) dropEl.style.display = 'none';
    }

    function setSelectedProduct(productId, label) {
        var hiddenEl = document.getElementById('vf-product-id');
        var searchEl = document.getElementById('vf-product-search');
        if (hiddenEl) hiddenEl.value = productId ? String(productId) : '';
        if (searchEl) searchEl.value = label || '';
        hideProductDropdown();
    }

    // Wire up search input and dropdown interactions.
    // Called once from init() after the DOM is ready.
    function bindProductSearch() {
        var searchEl = document.getElementById('vf-product-search');
        var dropEl   = document.getElementById('vf-product-dropdown');
        if (!searchEl || !dropEl) return;

        // Filter and show dropdown while typing
        searchEl.addEventListener('input', function () {
            var hiddenEl = document.getElementById('vf-product-id');
            if (hiddenEl) hiddenEl.value = '';   // clear stale selection when typing starts
            renderProductDropdown(searchEl.value);
        });

        // Show dropdown when input gains focus (so user can see options immediately)
        searchEl.addEventListener('focus', function () {
            if (_allProds.length > 0) {
                renderProductDropdown(searchEl.value);
            }
        });

        // Hide dropdown when input loses focus.
        // Delay 200 ms so mousedown on a dropdown item fires first.
        searchEl.addEventListener('blur', function () {
            setTimeout(hideProductDropdown, 200);
        });

        // Use mousedown (fires before blur) to capture the clicked item.
        // e.preventDefault() keeps focus on the text input, which is harmless.
        dropEl.addEventListener('mousedown', function (e) {
            var item = e.target.closest('.vf-ac-item');
            if (!item) return;
            e.preventDefault();  // prevents blur → keeps dropdown alive during click
            var pid   = parseInt(item.dataset.pid, 10);
            var label = item.dataset.label || item.textContent.trim();
            setSelectedProduct(pid, label);
        });
    }

    // ── Form open/close ───────────────────────────────────────────

    function openAddForm() {
        _editPvId = null;
        clearFormError();
        hideProductDropdown();
        var hiddenEl  = document.getElementById('vf-product-id');
        var searchEl  = document.getElementById('vf-product-search');
        var priceEl   = document.getElementById('vf-product-price');
        var primaryEl = document.getElementById('vf-product-primary');
        if (hiddenEl)  hiddenEl.value    = '';
        if (searchEl)  { searchEl.value = ''; searchEl.readOnly = false; }
        if (priceEl)   priceEl.value     = '';
        if (primaryEl) primaryEl.checked = false;
        document.getElementById('vf-product-form').style.display = '';
        document.getElementById('vf-add-product-btn').style.display = 'none';
        if (searchEl) searchEl.focus();
    }

    function openEditForm(pvId) {
        var pv = _pvList.filter(function (p) { return p.id === pvId; })[0];
        if (!pv) return;
        _editPvId = pvId;
        clearFormError();
        hideProductDropdown();
        // Resolve the display label for the currently linked product
        var prod  = _allProds.filter(function (p) { return p.id === pv.product; })[0];
        var label = prod ? _productLabel(prod) : (pv.product_name || String(pv.product));
        var hiddenEl  = document.getElementById('vf-product-id');
        var searchEl  = document.getElementById('vf-product-search');
        var priceEl   = document.getElementById('vf-product-price');
        var primaryEl = document.getElementById('vf-product-primary');
        if (hiddenEl)  hiddenEl.value    = pv.product || '';
        if (searchEl)  { searchEl.value = label; searchEl.readOnly = true; }  // lock on edit
        if (priceEl)   priceEl.value     = pv.unit_price || '';
        if (primaryEl) primaryEl.checked = !!pv.is_primary;
        document.getElementById('vf-product-form').style.display = '';
        document.getElementById('vf-add-product-btn').style.display = 'none';
    }

    function closeForm() {
        var searchEl = document.getElementById('vf-product-search');
        if (searchEl) searchEl.readOnly = false;
        hideProductDropdown();
        document.getElementById('vf-product-form').style.display = 'none';
        document.getElementById('vf-add-product-btn').style.display = '';
        _editPvId = null;
        clearFormError();
    }

    function clearFormError() {
        var errEl = document.getElementById('vf-product-form-error');
        if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
    }

    function showFormError(msg) {
        var errEl = document.getElementById('vf-product-form-error');
        if (errEl) { errEl.textContent = msg; errEl.style.display = ''; }
    }

    // ── Save (add or edit) ────────────────────────────────────────

    function saveForm() {
        var hiddenEl  = document.getElementById('vf-product-id');
        var priceEl   = document.getElementById('vf-product-price');
        var primaryEl = document.getElementById('vf-product-primary');
        var saveBtn   = document.getElementById('vf-product-save-btn');

        var productId = hiddenEl ? parseInt(hiddenEl.value, 10) : 0;
        var price     = priceEl ? (parseFloat(priceEl.value) || 0) : 0;
        var isPrimary = primaryEl ? primaryEl.checked : false;

        clearFormError();

        if (_editPvId === null && (!productId || isNaN(productId))) {
            showFormError('لطفاً یک محصول انتخاب کنید.');
            return;
        }

        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'در حال ذخیره...'; }

        var url, method, body;
        if (_editPvId === null) {
            url    = PRODUCT_VENDOR_API;
            method = 'POST';
            body   = {
                vendor:     vendorId,
                product:    productId,
                unit_price: price,
                is_primary: isPrimary,
                is_active:  true,
            };
        } else {
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
            closeForm();
            showToast(
                _editPvId !== null ? 'محصول به‌روز شد' : 'محصول افزوده شد',
                'success'
            );
            loadProducts();
        })
        .catch(function (err) {
            var msg = typeof err === 'object'
                ? (err.detail || err.non_field_errors || JSON.stringify(err))
                : String(err);
            if (Array.isArray(msg)) msg = msg.join('، ');
            showFormError('خطا: ' + msg);
        })
        .finally(function () {
            if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'ذخیره'; }
        });
    }

    // ── Remove product link ───────────────────────────────────────

    function removeProduct(pvId) {
        var pv   = _pvList.filter(function (p) { return p.id === pvId; })[0];
        var name = pv ? (pv.product_name || '') : '';
        showModal(
            'آیا می‌خواهید محصول "' + name + '" را از این تامین‌کننده حذف کنید؟',
            function () {
                fetch(PRODUCT_VENDOR_API + pvId + '/', {
                    method:      'DELETE',
                    credentials: 'same-origin',
                    headers:     apiHeaders(),
                })
                .then(function (res) {
                    if (res.status === 401) { redirectToLogin(); return; }
                    if (res.status === 204 || res.ok) {
                        showToast('محصول حذف شد', 'success');
                        loadProducts();
                    } else {
                        showToast('خطا در حذف محصول', 'error');
                    }
                })
                .catch(function () {
                    showToast('خطا در حذف محصول', 'error');
                });
            }
        );
    }

    // ── Init ──────────────────────────────────────────────────────

    function init() {
        if (!vendorId) return;

        loadProducts();
        bindProductSearch();

        var addBtn    = document.getElementById('vf-add-product-btn');
        var saveBtn   = document.getElementById('vf-product-save-btn');
        var cancelBtn = document.getElementById('vf-product-cancel-btn');

        if (addBtn)    addBtn.addEventListener('click', openAddForm);
        if (saveBtn)   saveBtn.addEventListener('click', saveForm);
        if (cancelBtn) cancelBtn.addEventListener('click', closeForm);

        var modalCancel  = document.getElementById('vf-modal-cancel');
        var modalConfirm = document.getElementById('vf-modal-confirm');
        var overlay      = document.getElementById('vf-modal-overlay');
        if (modalCancel)  modalCancel.addEventListener('click', hideModal);
        if (modalConfirm) modalConfirm.addEventListener('click', function () {
            var cb = _modalCb;   // capture before hideModal() nulls _modalCb
            hideModal();
            if (cb) cb();
        });
        if (overlay) overlay.addEventListener('click', function (e) {
            if (e.target === overlay) hideModal();
        });
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', VendorFormApp.init);

// ── VendorPhonesModule ────────────────────────────────────────────────────
// Manages the add/remove phone rows for the VendorPhone inline formset.
// Uses window.VF_PHONES_PREFIX (set by the template) as the Django formset prefix.

const VendorPhonesModule = (function () {
    'use strict';

    var prefix = '';  // set from window.VF_PHONES_PREFIX on init

    function getTotalFormsInput() {
        return document.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]');
    }

    function getTotalForms() {
        var inp = getTotalFormsInput();
        return inp ? parseInt(inp.value, 10) : 0;
    }

    function setTotalForms(n) {
        var inp = getTotalFormsInput();
        if (inp) inp.value = String(n);
    }

    function getContainer() {
        return document.getElementById('vf-additional-phones');
    }

    function getExtraSection() {
        return document.getElementById('vf-phones-extra-section');
    }

    function showExtraSection() {
        var sec = getExtraSection();
        if (sec) sec.classList.add('has-phones');
    }

    function hideExtraSectionIfEmpty() {
        var container = getContainer();
        if (!container) return;
        // Count visible (non-deleted) rows
        var visible = container.querySelectorAll('.vf-phone-extra-row:not(.vf-phone-deleted)');
        var sec = getExtraSection();
        if (sec) {
            if (visible.length > 0 || sec.querySelector('.vf-phone-formset-errors')) {
                sec.classList.add('has-phones');
            } else {
                sec.classList.remove('has-phones');
            }
        }
    }

    function addPhoneRow() {
        var template = document.getElementById('vf-phone-empty-form');
        if (!template) return;

        var total = getTotalForms();
        var html  = template.innerHTML.replace(/__prefix__/g, String(total));

        var container = getContainer();
        if (!container) return;

        var wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        var newRow = wrapper.firstElementChild;
        container.appendChild(newRow);

        setTotalForms(total + 1);
        showExtraSection();

        // Focus the new input
        var inp = newRow.querySelector('input[type="text"]');
        if (inp) inp.focus();

        bindRemoveBtn(newRow);
    }

    function removePhoneRow(row) {
        var deleteField = row.querySelector('.vf-phone-delete-field');
        var idInput     = row.querySelector('input[name$="-id"]');

        if (idInput && idInput.value) {
            // Existing persisted row: mark DELETE and hide
            if (deleteField) {
                var chk = deleteField.querySelector('input[type="checkbox"]');
                if (chk) chk.checked = true;
            }
            row.classList.add('vf-phone-deleted');
            row.style.display = 'none';
        } else {
            // New (unsaved) row: remove from DOM entirely, decrement TOTAL_FORMS
            var total = getTotalForms();
            row.parentNode.removeChild(row);
            setTotalForms(Math.max(0, total - 1));
            // Re-index remaining new rows so formset indices stay contiguous
            reIndexRows();
        }

        hideExtraSectionIfEmpty();
    }

    function reIndexRows() {
        // After removing a new row, re-index only NEW rows (no id).
        // Existing rows keep their original index — Django identifies them by id.
        var container = getContainer();
        if (!container) return;
        var rows = container.querySelectorAll('.vf-phone-extra-row');
        var newIndex = 0;
        // Collect initial form count (persisted rows) — they keep their indices 0..N-1
        var initialForms = parseInt(
            (document.querySelector('input[name="' + prefix + '-INITIAL_FORMS"]') || {}).value || '0',
            10
        );
        newIndex = initialForms;
        rows.forEach(function (row) {
            var idInp = row.querySelector('input[name$="-id"]');
            if (idInp && idInp.value) {
                // Persisted row — don't touch its indices
                return;
            }
            // New row — re-index
            row.querySelectorAll('input, select, textarea').forEach(function (el) {
                ['name', 'id'].forEach(function (attr) {
                    var val = el.getAttribute(attr);
                    if (val) {
                        el.setAttribute(attr, val.replace(new RegExp('^' + prefix + '-\\d+-'), prefix + '-' + newIndex + '-'));
                    }
                });
            });
            row.id = 'vf-phone-row-' + newIndex;
            newIndex += 1;
        });
        setTotalForms(newIndex);
    }

    function bindRemoveBtn(row) {
        var btn = row.querySelector('.vf-phone-remove-btn');
        if (btn) {
            btn.addEventListener('click', function () {
                removePhoneRow(row);
            });
        }
    }

    function init() {
        prefix = window.VF_PHONES_PREFIX || 'vendorphone';

        // Bind add button
        var addBtn = document.getElementById('vf-phone-add-btn');
        if (addBtn) {
            addBtn.addEventListener('click', addPhoneRow);
        }

        // Bind remove buttons for existing rows rendered by the template
        var container = getContainer();
        if (container) {
            container.querySelectorAll('.vf-phone-extra-row').forEach(function (row) {
                bindRemoveBtn(row);
            });
        }

        // Show section if there are already phones rendered (server-side)
        hideExtraSectionIfEmpty();
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', VendorPhonesModule.init);
