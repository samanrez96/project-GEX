/**
 * ProductTypeTagWidget — inline نوع محصول (ProductTypeTag) management for
 * the Product add/edit form.
 *
 * Mirrors static/admin/js/anesthesia_type.js exactly (same modal pattern,
 * same "ds-" CSS classes from doctor_specialty.css) — the one structural
 * difference: an AnesthesiaType <option> value is the row's numeric pk,
 * but a ProductTypeTag <option> value must stay the actual string written
 * to Product.product_type (دارو/تجهیزات/...), so the row's pk travels
 * separately as a data-tag-id attribute and is only ever used to build the
 * management endpoint URLs below.
 *
 * Adds "+" (add) and "حذف" (delete) buttons beside the #id_product_type
 * select. Both actions POST a JSON body to the protected utility endpoints
 * and never reload the page, so unsaved Product form values are preserved.
 *
 * Delete semantics: an unused tag is hard-deleted on confirm. A tag still
 * assigned to one or more Products cannot be hard-deleted — the delete
 * endpoint reports how many products use it, and the widget offers to
 * deactivate it instead (is_active=False, never touches Product.product_type).
 */
(function () {
    'use strict';

    var CREATE_URL              = '/admin/inventory/product/product-type-tag/create/';
    var DELETE_URL_TEMPLATE     = '/admin/inventory/product/product-type-tag/0/delete/';
    var DEACTIVATE_URL_TEMPLATE = '/admin/inventory/product/product-type-tag/0/deactivate/';
    var ACTIVATE_URL_TEMPLATE   = '/admin/inventory/product/product-type-tag/0/activate/';

    function getCsrfToken() {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var pair = cookies[i].trim().split('=');
            if (pair[0] === 'csrftoken') return decodeURIComponent(pair[1]);
        }
        return '';
    }

    function showToast(message, type) {
        var existing = document.getElementById('ptt-toast');
        if (existing) existing.remove();
        var toast = document.createElement('div');
        toast.id = 'ptt-toast';
        toast.className = 'ds-toast ds-toast--' + (type || 'success');
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 3500);
    }

    function postJSON(url, payload) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify(payload || {}),
        }).then(function (res) {
            var contentType = res.headers.get('content-type') || '';
            if (contentType.indexOf('application/json') !== -1) {
                return res.json().then(function (data) { return { status: res.status, data: data }; });
            }
            if (res.status === 403 || res.status === 401 || res.redirected) {
                return {
                    status: res.status,
                    data: { success: false, code: 'session_expired', message: 'نشست شما منقضی شده است. صفحه را تازه‌سازی کنید.' },
                };
            }
            throw new Error('Unexpected non-JSON response: ' + res.status);
        });
    }

    function init() {
        var select = document.getElementById('id_product_type');
        if (!select) return;

        // ── Buttons beside the selector ─────────────────────────────
        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.id = 'ptt-add-btn';
        addBtn.className = 'ds-icon-btn';
        addBtn.title = 'افزودن نوع محصول جدید';
        addBtn.textContent = '+';

        var deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.id = 'ptt-delete-btn';
        deleteBtn.className = 'ds-icon-btn';
        deleteBtn.title = 'حذف نوع محصول انتخاب‌شده';
        deleteBtn.textContent = 'حذف';

        var activateBtn = document.createElement('button');
        activateBtn.type = 'button';
        activateBtn.id = 'ptt-activate-btn';
        activateBtn.className = 'ds-icon-btn';
        activateBtn.title = 'فعال‌سازی نوع محصول انتخاب‌شده';
        activateBtn.textContent = 'فعال کردن';
        activateBtn.style.display = 'none';

        select.insertAdjacentElement('afterend', activateBtn);
        select.insertAdjacentElement('afterend', deleteBtn);
        select.insertAdjacentElement('afterend', addBtn);

        function selectedOption() {
            return select.options[select.selectedIndex] || null;
        }

        function selectedTagId() {
            var opt = selectedOption();
            return opt ? opt.getAttribute('data-tag-id') : null;
        }

        function selectedOptionIsInactive() {
            var opt = selectedOption();
            return !!opt && opt.textContent.indexOf('(غیرفعال)') !== -1;
        }

        function refreshActivateButton() {
            activateBtn.style.display = selectedOptionIsInactive() ? '' : 'none';
        }

        select.addEventListener('change', refreshActivateButton);
        refreshActivateButton();

        // ── Add-type modal ───────────────────────────────────────────
        var addOverlay = document.createElement('div');
        addOverlay.id = 'ptt-add-overlay';
        addOverlay.className = 'ds-overlay';
        addOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<h2 class="ds-modal-title">افزودن نوع محصول جدید</h2>' +
            '<label class="ds-modal-label" for="ptt-add-input">نام نوع محصول</label>' +
            '<input type="text" id="ptt-add-input" class="ds-modal-input" dir="rtl">' +
            '<div id="ptt-add-error" class="ds-modal-error" style="display:none"></div>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="ptt-add-save" class="ds-btn ds-btn--primary">ذخیره</button>' +
            '<button type="button" id="ptt-add-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(addOverlay);

        var addInput = document.getElementById('ptt-add-input');
        var addError = document.getElementById('ptt-add-error');
        var addSaveBtn = document.getElementById('ptt-add-save');

        function openAddModal() {
            addInput.value = '';
            addError.style.display = 'none';
            addError.textContent = '';
            addOverlay.classList.add('ds-open');
            addInput.focus();
        }

        function closeAddModal() {
            addOverlay.classList.remove('ds-open');
        }

        addBtn.addEventListener('click', openAddModal);
        document.getElementById('ptt-add-cancel').addEventListener('click', closeAddModal);
        addOverlay.addEventListener('click', function (e) {
            if (e.target === addOverlay) closeAddModal();
        });

        addSaveBtn.addEventListener('click', function () {
            addError.style.display = 'none';
            addSaveBtn.disabled = true;
            addSaveBtn.textContent = 'در حال ذخیره...';

            postJSON(CREATE_URL, { name: addInput.value })
                .then(function (result) {
                    var data = result.data;
                    if (!data.success) {
                        addError.textContent = data.message || 'خطا در ثبت نوع محصول.';
                        addError.style.display = '';
                        return;
                    }
                    var opt = document.createElement('option');
                    opt.value = data.value;
                    opt.textContent = data.label;
                    opt.setAttribute('data-tag-id', data.id);
                    opt.selected = true;
                    select.appendChild(opt);
                    select.value = data.value;
                    refreshActivateButton();
                    closeAddModal();
                    showToast(data.message || 'نوع محصول با موفقیت اضافه شد.', 'success');
                })
                .catch(function () {
                    addError.textContent = 'خطا در ارتباط با سرور.';
                    addError.style.display = '';
                })
                .finally(function () {
                    addSaveBtn.disabled = false;
                    addSaveBtn.textContent = 'ذخیره';
                });
        });

        // ── Delete confirm dialog ─────────────────────────────────────
        var delOverlay = document.createElement('div');
        delOverlay.id = 'ptt-delete-overlay';
        delOverlay.className = 'ds-overlay';
        delOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<p id="ptt-delete-message" class="ds-modal-message"></p>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="ptt-delete-confirm" class="ds-btn ds-btn--danger">تأیید حذف</button>' +
            '<button type="button" id="ptt-delete-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(delOverlay);

        var delMessageEl = document.getElementById('ptt-delete-message');
        var delConfirmBtn = document.getElementById('ptt-delete-confirm');
        var pendingId = null;
        var pendingValue = null;

        function openDeleteConfirm(id, value, label) {
            pendingId = id;
            pendingValue = value;
            delMessageEl.textContent = 'آیا از حذف نوع محصول «' + label + '» مطمئن هستید؟';
            delOverlay.classList.add('ds-open');
        }

        function closeDeleteConfirm() {
            delOverlay.classList.remove('ds-open');
            pendingId = null;
            pendingValue = null;
        }

        // ── Deactivate confirm dialog (offered when delete is blocked) ─
        var deactivateOverlay = document.createElement('div');
        deactivateOverlay.id = 'ptt-deactivate-overlay';
        deactivateOverlay.className = 'ds-overlay';
        deactivateOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<p id="ptt-deactivate-message" class="ds-modal-message"></p>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="ptt-deactivate-confirm" class="ds-btn ds-btn--primary">غیرفعال کردن</button>' +
            '<button type="button" id="ptt-deactivate-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(deactivateOverlay);

        var deactivateMessageEl = document.getElementById('ptt-deactivate-message');
        var deactivateConfirmBtn = document.getElementById('ptt-deactivate-confirm');

        function openDeactivateConfirm(message) {
            deactivateMessageEl.textContent = message + ' آیا می‌خواهید آن را غیرفعال کنید؟';
            deactivateOverlay.classList.add('ds-open');
        }

        function closeDeactivateConfirm() {
            deactivateOverlay.classList.remove('ds-open');
            pendingId = null;
            pendingValue = null;
        }

        deleteBtn.addEventListener('click', function () {
            var id = selectedTagId();
            if (!id) return;
            var opt = selectedOption();
            openDeleteConfirm(id, select.value, opt ? opt.textContent : '');
        });

        document.getElementById('ptt-delete-cancel').addEventListener('click', closeDeleteConfirm);
        delOverlay.addEventListener('click', function (e) {
            if (e.target === delOverlay) closeDeleteConfirm();
        });

        document.getElementById('ptt-deactivate-cancel').addEventListener('click', closeDeactivateConfirm);
        deactivateOverlay.addEventListener('click', function (e) {
            if (e.target === deactivateOverlay) closeDeactivateConfirm();
        });

        delConfirmBtn.addEventListener('click', function () {
            if (!pendingId) return;
            var id = pendingId;
            var url = DELETE_URL_TEMPLATE.replace('/0/delete/', '/' + id + '/delete/');

            delConfirmBtn.disabled = true;
            postJSON(url)
                .then(function (result) {
                    var data = result.data;
                    if (data.success) {
                        var opt = select.querySelector('option[data-tag-id="' + id + '"]');
                        if (opt) opt.remove();
                        select.value = '';
                        refreshActivateButton();
                        closeDeleteConfirm();
                        showToast(data.message || 'نوع محصول با موفقیت حذف شد.', 'success');
                        return;
                    }
                    closeDeleteConfirm();
                    if (data.code === 'product_type_tag_in_use') {
                        pendingId = id;
                        openDeactivateConfirm(data.message);
                    } else {
                        showToast(data.message || 'حذف نوع محصول ناموفق بود.', 'error');
                    }
                })
                .catch(function () {
                    showToast('خطا در ارتباط با سرور.', 'error');
                    closeDeleteConfirm();
                })
                .finally(function () {
                    delConfirmBtn.disabled = false;
                });
        });

        deactivateConfirmBtn.addEventListener('click', function () {
            if (!pendingId) return;
            var id = pendingId;
            var url = DEACTIVATE_URL_TEMPLATE.replace('/0/deactivate/', '/' + id + '/deactivate/');

            deactivateConfirmBtn.disabled = true;
            postJSON(url)
                .then(function (result) {
                    var data = result.data;
                    if (!data.success) {
                        showToast(data.message || 'غیرفعال‌سازی نوع محصول ناموفق بود.', 'error');
                        closeDeactivateConfirm();
                        return;
                    }
                    var opt = select.querySelector('option[data-tag-id="' + id + '"]');
                    if (opt) {
                        var isCurrentValue = pendingValue !== null && select.value === pendingValue;
                        if (isCurrentValue) {
                            if (opt.textContent.indexOf('(غیرفعال)') === -1) {
                                opt.textContent = opt.textContent + ' (غیرفعال)';
                            }
                            refreshActivateButton();
                        } else {
                            var wasSelected = select.value === opt.value;
                            opt.remove();
                            if (wasSelected) { select.value = ''; refreshActivateButton(); }
                        }
                    }
                    closeDeactivateConfirm();
                    showToast(data.message || 'نوع محصول با موفقیت غیرفعال شد.', 'success');
                })
                .catch(function () {
                    showToast('خطا در ارتباط با سرور.', 'error');
                    closeDeactivateConfirm();
                })
                .finally(function () {
                    deactivateConfirmBtn.disabled = false;
                });
        });

        // ── Activate (offered when the selected option is inactive) ───
        activateBtn.addEventListener('click', function () {
            var id = selectedTagId();
            if (!id) return;
            var url = ACTIVATE_URL_TEMPLATE.replace('/0/activate/', '/' + id + '/activate/');

            activateBtn.disabled = true;
            postJSON(url)
                .then(function (result) {
                    var data = result.data;
                    if (!data.success) {
                        showToast(data.message || 'فعال‌سازی نوع محصول ناموفق بود.', 'error');
                        return;
                    }
                    var opt = select.querySelector('option[data-tag-id="' + id + '"]');
                    if (opt) opt.textContent = opt.textContent.replace(' (غیرفعال)', '');
                    refreshActivateButton();
                    showToast(data.message || 'نوع محصول با موفقیت فعال شد.', 'success');
                })
                .catch(function () {
                    showToast('خطا در ارتباط با سرور.', 'error');
                })
                .finally(function () {
                    activateBtn.disabled = false;
                });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
