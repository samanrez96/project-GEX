/**
 * DoctorSpecialtyWidget — inline Specialty management for the Doctor add/edit form.
 *
 * Adds "+" (add), "حذف" (delete) and, when the selected specialty is
 * inactive, "فعال کردن" (activate) buttons beside the #id_specialty select.
 * All four actions POST a JSON body to the protected utility endpoints
 * (contacts_doctor_specialty_create / _delete / _deactivate / _activate)
 * and never reload the page, so unsaved Doctor form fields are preserved.
 *
 * Delete semantics: an unused specialty is hard-deleted on confirm. A
 * specialty still assigned to one or more Doctors cannot be hard-deleted —
 * the delete endpoint reports how many Doctors use it, and the widget
 * offers to deactivate it instead (is_active=False, never touches
 * Doctor.specialty).
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
        var existing = document.getElementById('ds-toast');
        if (existing) existing.remove();
        var toast = document.createElement('div');
        toast.id = 'ds-toast';
        toast.className = 'ds-toast ds-toast--' + (type || 'success');
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 3500);
    }

    // Single shared helper for every Specialty request: JSON body,
    // credentials same-origin, CSRF token from the csrftoken cookie.
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
        var config = window.DOCTOR_SPECIALTY_CONFIG;
        var select = document.getElementById('id_specialty');
        if (!config || !select) return;

        // ── Buttons beside the selector ─────────────────────────────
        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.id = 'ds-add-btn';
        addBtn.className = 'ds-icon-btn';
        addBtn.title = 'افزودن تخصص جدید';
        addBtn.textContent = '+';
        if (!config.canAdd) addBtn.style.display = 'none';

        var deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.id = 'ds-delete-btn';
        deleteBtn.className = 'ds-icon-btn';
        deleteBtn.title = 'حذف تخصص انتخاب‌شده';
        deleteBtn.textContent = 'حذف';
        if (!config.canDelete) deleteBtn.style.display = 'none';

        var activateBtn = document.createElement('button');
        activateBtn.type = 'button';
        activateBtn.id = 'ds-activate-btn';
        activateBtn.className = 'ds-icon-btn';
        activateBtn.title = 'فعال‌سازی تخصص انتخاب‌شده';
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

        // ── Add-specialty modal ──────────────────────────────────────
        var addOverlay = document.createElement('div');
        addOverlay.id = 'ds-add-overlay';
        addOverlay.className = 'ds-overlay';
        addOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<h2 class="ds-modal-title">افزودن تخصص جدید</h2>' +
            '<label class="ds-modal-label" for="ds-add-input">عنوان تخصص</label>' +
            '<input type="text" id="ds-add-input" class="ds-modal-input" dir="rtl">' +
            '<div id="ds-add-error" class="ds-modal-error" style="display:none"></div>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="ds-add-save" class="ds-btn ds-btn--primary">ذخیره</button>' +
            '<button type="button" id="ds-add-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(addOverlay);

        var addInput = document.getElementById('ds-add-input');
        var addError = document.getElementById('ds-add-error');
        var addSaveBtn = document.getElementById('ds-add-save');

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
        document.getElementById('ds-add-cancel').addEventListener('click', closeAddModal);
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
                        addError.textContent = data.message || 'خطا در ثبت تخصص.';
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
                    showToast(data.message || 'تخصص با موفقیت اضافه شد.', 'success');
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

        // ── Delete-specialty confirm dialog ──────────────────────────
        var delOverlay = document.createElement('div');
        delOverlay.id = 'ds-delete-overlay';
        delOverlay.className = 'ds-overlay';
        delOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<p id="ds-delete-message" class="ds-modal-message"></p>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="ds-delete-confirm" class="ds-btn ds-btn--danger">تأیید حذف</button>' +
            '<button type="button" id="ds-delete-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(delOverlay);

        var delMessageEl = document.getElementById('ds-delete-message');
        var delConfirmBtn = document.getElementById('ds-delete-confirm');
        var pendingId = null;

        function openDeleteConfirm(id, name) {
            pendingId = id;
            delMessageEl.textContent = 'آیا از حذف تخصص «' + name + '» مطمئن هستید؟';
            delOverlay.classList.add('ds-open');
        }

        function closeDeleteConfirm() {
            delOverlay.classList.remove('ds-open');
            pendingId = null;
        }

        // ── Deactivate confirm dialog (offered when delete is blocked) ─
        var deactivateOverlay = document.createElement('div');
        deactivateOverlay.id = 'ds-deactivate-overlay';
        deactivateOverlay.className = 'ds-overlay';
        deactivateOverlay.innerHTML =
            '<div class="ds-modal">' +
            '<p id="ds-deactivate-message" class="ds-modal-message"></p>' +
            '<div class="ds-modal-actions">' +
            '<button type="button" id="ds-deactivate-confirm" class="ds-btn ds-btn--primary">غیرفعال کردن</button>' +
            '<button type="button" id="ds-deactivate-cancel" class="ds-btn">انصراف</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(deactivateOverlay);

        var deactivateMessageEl = document.getElementById('ds-deactivate-message');
        var deactivateConfirmBtn = document.getElementById('ds-deactivate-confirm');

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

        document.getElementById('ds-delete-cancel').addEventListener('click', closeDeleteConfirm);
        delOverlay.addEventListener('click', function (e) {
            if (e.target === delOverlay) closeDeleteConfirm();
        });

        document.getElementById('ds-deactivate-cancel').addEventListener('click', closeDeactivateConfirm);
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
                        showToast(data.message || 'تخصص با موفقیت حذف شد.', 'success');
                        return;
                    }
                    closeDeleteConfirm();
                    if (data.code === 'specialty_in_use') {
                        openDeactivateConfirm(id, data.message);
                    } else {
                        showToast(data.message || 'حذف تخصص ناموفق بود.', 'error');
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
                        showToast(data.message || 'غیرفعال‌سازی تخصص ناموفق بود.', 'error');
                        closeDeactivateConfirm();
                        return;
                    }
                    var opt = select.querySelector('option[value="' + id + '"]');
                    if (opt) {
                        var isCurrentDoctorsSpecialty = config.currentSpecialtyId !== null
                            && String(config.currentSpecialtyId) === String(id);
                        if (isCurrentDoctorsSpecialty) {
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
                    showToast(data.message || 'تخصص با موفقیت غیرفعال شد.', 'success');
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
                        showToast(data.message || 'فعال‌سازی تخصص ناموفق بود.', 'error');
                        return;
                    }
                    var opt = select.querySelector('option[value="' + id + '"]');
                    if (opt) opt.textContent = opt.textContent.replace(' (غیرفعال)', '');
                    refreshActivateButton();
                    showToast(data.message || 'تخصص با موفقیت فعال شد.', 'success');
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
