/**
 * AnesthesiaTypeWidget — inline AnesthesiaType management for the
 * SurgeryHistory add/edit form.
 *
 * Mirrors static/admin/js/doctor_specialty.js exactly (same modal pattern,
 * same CSS classes from doctor_specialty.css — only the element id prefix
 * ("at-" instead of "ds-") and the target select/config differ, so both
 * widgets can coexist safely if ever loaded on the same page.
 *
 * Adds "+" (add) and "حذف" (delete) buttons beside the #id_anesthesia_type
 * select. Both actions POST a JSON body to the protected utility endpoints
 * and never reload the page, so unsaved Surgery form values are preserved.
 *
 * Delete semantics: an unused type is hard-deleted on confirm. A type still
 * assigned to one or more SurgeryHistory records cannot be hard-deleted —
 * the delete endpoint reports how many records use it, and the widget
 * offers to deactivate it instead (is_active=False, never touches
 * SurgeryHistory.anesthesia_type).
 */
(function () {
    'use strict';

    function getCsrfToken() {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var pair = cookies[i].trim().split('=');
            if (pair[0] === 'csrftoken') return decodeURIComponent(pair[1]);
        }
        return '';
    }

    function showToast(message, type) {
        var existing = document.getElementById('at-toast');
        if (existing) existing.remove();
        var toast = document.createElement('div');
        toast.id = 'at-toast';
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
            // A non-JSON response here (HTML CSRF-failure page, or a
            // redirect to the login page) means the session/CSRF cookie is
            // no longer valid — not a generic connection failure.
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
        var config = window.ANESTHESIA_TYPE_CONFIG;
        var select = document.getElementById('id_anesthesia_type');
        if (!config || !select) return;

        // ── Buttons beside the selector ─────────────────────────────
        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.id = 'at-add-btn';
        addBtn.className = 'ds-icon-btn';
        addBtn.title = 'افزودن نوع بیهوشی جدید';
        addBtn.textContent = '+';
        if (!config.canAdd) addBtn.style.display = 'none';

        var deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.id = 'at-delete-btn';
        deleteBtn.className = 'ds-icon-btn';
        deleteBtn.title = 'حذف نوع بیهوشی انتخاب‌شده';
        deleteBtn.textContent = 'حذف';
        if (!config.canDelete) deleteBtn.style.display = 'none';

        var activateBtn = document.createElement('button');
        activateBtn.type = 'button';
        activateBtn.id = 'at-activate-btn';
        activateBtn.className = 'ds-icon-btn';
        activateBtn.title = 'فعال‌سازی نوع بیهوشی انتخاب‌شده';
        activateBtn.textContent = 'فعال کردن';
        activateBtn.style.display = 'none';

        select.insertAdjacentElement('afterend', activateBtn);
        select.insertAdjacentElement('afterend', deleteBtn);
        select.insertAdjacentElement('afterend', addBtn);

        function selectedOptionIsInactive() {
            var opt = select.options[select.selectedIndex];
            return !!opt && opt.textContent.indexOf('(غیرفعال)') !== -1;
        }

        function refreshActivateButton() {
            activateBtn.style.display = (config.canChange && selectedOptionIsInactive()) ? '' : 'none';
        }

        select.addEventListener('change', refreshActivateButton);
        refreshActivateButton();

        // ── Add-type modal ───────────────────────────────────────────
        var addOverlay = document.createElement('div');
        addOverlay.id = 'at-add-overlay';
        addOverlay.className = 'ds-overlay';
        addOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<h2 class="ds-modal-title">افزودن نوع بیهوشی جدید</h2>' +
            '<label class="ds-modal-label" for="at-add-input">نام نوع بیهوشی</label>' +
            '<input type="text" id="at-add-input" class="ds-modal-input" dir="rtl">' +
            '<div id="at-add-error" class="ds-modal-error" style="display:none"></div>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="at-add-save" class="ds-btn ds-btn--primary">ذخیره</button>' +
            '<button type="button" id="at-add-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(addOverlay);

        var addInput = document.getElementById('at-add-input');
        var addError = document.getElementById('at-add-error');
        var addSaveBtn = document.getElementById('at-add-save');

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
        document.getElementById('at-add-cancel').addEventListener('click', closeAddModal);
        addOverlay.addEventListener('click', function (e) {
            if (e.target === addOverlay) closeAddModal();
        });

        addSaveBtn.addEventListener('click', function () {
            addError.style.display = 'none';
            addSaveBtn.disabled = true;
            addSaveBtn.textContent = 'در حال ذخیره...';

            postJSON(config.createUrl, { name: addInput.value })
                .then(function (result) {
                    var data = result.data;
                    if (!data.success) {
                        addError.textContent = data.message || 'خطا در ثبت نوع بیهوشی.';
                        addError.style.display = '';
                        return;
                    }
                    var opt = document.createElement('option');
                    opt.value = data.id;
                    opt.textContent = data.name;
                    opt.selected = true;
                    select.appendChild(opt);
                    select.value = String(data.id);
                    refreshActivateButton();
                    closeAddModal();
                    showToast(data.message || 'نوع بیهوشی با موفقیت اضافه شد.', 'success');
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
        delOverlay.id = 'at-delete-overlay';
        delOverlay.className = 'ds-overlay';
        delOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<p id="at-delete-message" class="ds-modal-message"></p>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="at-delete-confirm" class="ds-btn ds-btn--danger">تأیید حذف</button>' +
            '<button type="button" id="at-delete-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(delOverlay);

        var delMessageEl = document.getElementById('at-delete-message');
        var delConfirmBtn = document.getElementById('at-delete-confirm');
        var pendingId = null;

        function openDeleteConfirm(id, name) {
            pendingId = id;
            delMessageEl.textContent = 'آیا از حذف نوع بیهوشی «' + name + '» مطمئن هستید؟';
            delOverlay.classList.add('ds-open');
        }

        function closeDeleteConfirm() {
            delOverlay.classList.remove('ds-open');
            pendingId = null;
        }

        // ── Deactivate confirm dialog (offered when delete is blocked) ─
        var deactivateOverlay = document.createElement('div');
        deactivateOverlay.id = 'at-deactivate-overlay';
        deactivateOverlay.className = 'ds-overlay';
        deactivateOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<p id="at-deactivate-message" class="ds-modal-message"></p>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="at-deactivate-confirm" class="ds-btn ds-btn--primary">غیرفعال کردن</button>' +
            '<button type="button" id="at-deactivate-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(deactivateOverlay);

        var deactivateMessageEl = document.getElementById('at-deactivate-message');
        var deactivateConfirmBtn = document.getElementById('at-deactivate-confirm');

        function openDeactivateConfirm(id, message) {
            pendingId = id;
            deactivateMessageEl.textContent = message + ' آیا می‌خواهید آن را غیرفعال کنید؟';
            deactivateOverlay.classList.add('ds-open');
        }

        function closeDeactivateConfirm() {
            deactivateOverlay.classList.remove('ds-open');
            pendingId = null;
        }

        deleteBtn.addEventListener('click', function () {
            if (!select.value) return;
            var opt = select.options[select.selectedIndex];
            openDeleteConfirm(select.value, opt ? opt.textContent : '');
        });

        document.getElementById('at-delete-cancel').addEventListener('click', closeDeleteConfirm);
        delOverlay.addEventListener('click', function (e) {
            if (e.target === delOverlay) closeDeleteConfirm();
        });

        document.getElementById('at-deactivate-cancel').addEventListener('click', closeDeactivateConfirm);
        deactivateOverlay.addEventListener('click', function (e) {
            if (e.target === deactivateOverlay) closeDeactivateConfirm();
        });

        delConfirmBtn.addEventListener('click', function () {
            if (!pendingId) return;
            var id = pendingId;
            var url = config.deleteUrlTemplate.replace('/0/delete/', '/' + id + '/delete/');

            delConfirmBtn.disabled = true;
            postJSON(url)
                .then(function (result) {
                    var data = result.data;
                    if (data.success) {
                        var opt = select.querySelector('option[value="' + id + '"]');
                        if (opt) opt.remove();
                        select.value = '';
                        refreshActivateButton();
                        closeDeleteConfirm();
                        showToast(data.message || 'نوع بیهوشی با موفقیت حذف شد.', 'success');
                        return;
                    }
                    closeDeleteConfirm();
                    if (data.code === 'anesthesia_type_in_use') {
                        openDeactivateConfirm(id, data.message);
                    } else {
                        showToast(data.message || 'حذف نوع بیهوشی ناموفق بود.', 'error');
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
            var url = config.deactivateUrlTemplate.replace('/0/deactivate/', '/' + id + '/deactivate/');

            deactivateConfirmBtn.disabled = true;
            postJSON(url)
                .then(function (result) {
                    var data = result.data;
                    if (!data.success) {
                        showToast(data.message || 'غیرفعال‌سازی نوع بیهوشی ناموفق بود.', 'error');
                        closeDeactivateConfirm();
                        return;
                    }
                    var opt = select.querySelector('option[value="' + id + '"]');
                    if (opt) {
                        var isCurrentAnesthesiaType = config.currentAnesthesiaTypeId !== null
                            && String(config.currentAnesthesiaTypeId) === String(id);
                        if (isCurrentAnesthesiaType) {
                            if (opt.textContent.indexOf('(غیرفعال)') === -1) {
                                opt.textContent = opt.textContent + ' (غیرفعال)';
                            }
                            refreshActivateButton();
                        } else {
                            var wasSelected = select.value === String(id);
                            opt.remove();
                            if (wasSelected) { select.value = ''; refreshActivateButton(); }
                        }
                    }
                    closeDeactivateConfirm();
                    showToast(data.message || 'نوع بیهوشی با موفقیت غیرفعال شد.', 'success');
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
            if (!select.value) return;
            var id = select.value;
            var url = config.activateUrlTemplate.replace('/0/activate/', '/' + id + '/activate/');

            activateBtn.disabled = true;
            postJSON(url)
                .then(function (result) {
                    var data = result.data;
                    if (!data.success) {
                        showToast(data.message || 'فعال‌سازی نوع بیهوشی ناموفق بود.', 'error');
                        return;
                    }
                    var opt = select.querySelector('option[value="' + id + '"]');
                    if (opt) opt.textContent = opt.textContent.replace(' (غیرفعال)', '');
                    refreshActivateButton();
                    showToast(data.message || 'نوع بیهوشی با موفقیت فعال شد.', 'success');
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
