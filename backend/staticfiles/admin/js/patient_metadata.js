/**
 * PatientMetadataWidget — auto-displays the selected Patient's age/gender
 * on the SurgeryHistory add/edit form, right below the Patient selector.
 *
 * Read-only, informational only: age/gender are never submitted as part of
 * the Surgery form — the backend always reads them live from the canonical
 * Patient record (see SurgeryHistorySerializer.patient_age/patient_gender),
 * so nothing here is trusted as authoritative data.
 *
 * Reuses the existing Patient retrieve endpoint (already scoped by
 * Patient.objects.visible_to(user) in PatientViewSet.get_queryset), so a
 * hidden Patient's age/gender can never be fetched by an unauthorized user
 * — the request simply 404s and the widget shows "—", same as any other
 * failure.
 *
 * Django's own admin/js/admin/RelatedObjectLookups.js already triggers a
 * native `change` event on #id_patient after any related-object popup
 * action (add/edit/delete a Patient from the "+"/pencil/view icons beside
 * the selector) — the plain `change` listener below picks that up for
 * free, so a freshly added/edited Patient's age/gender refresh without an
 * extra event wiring.
 */
(function () {
    'use strict';

    var PATIENT_API_URL = '/api/v2/surgeries/patients/';

    var metaRow = null;
    var activeController = null;

    function toPersianDigits(n) {
        return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; });
    }

    function renderMetadata(data) {
        if (!metaRow) return;
        var ageEl    = metaRow.querySelector('.pm-age');
        var genderEl = metaRow.querySelector('.pm-gender');
        if (!data) {
            ageEl.textContent    = '—';
            genderEl.textContent = '—';
            return;
        }
        ageEl.textContent = (data.age === null || data.age === undefined)
            ? '—'
            : toPersianDigits(data.age) + ' سال';
        genderEl.textContent = data.gender_display || '—';
    }

    /**
     * Fetch Patient metadata and render age/gender. Aborts any still-in-
     * flight request for a previous selection first, so a user changing
     * the Patient selector rapidly can never have an older response
     * overwrite a newer one.
     */
    async function refreshSelectedPatientInfo(patientId) {
        if (activeController) {
            activeController.abort();
            activeController = null;
        }
        if (!patientId) {
            renderMetadata(null);
            return;
        }
        var controller = new AbortController();
        activeController = controller;
        if (metaRow) metaRow.classList.add('pm-loading');
        try {
            var res = await fetch(PATIENT_API_URL + encodeURIComponent(patientId) + '/', {
                credentials: 'same-origin',
                signal: controller.signal,
            });
            if (!res.ok) {
                renderMetadata(null);
                return;
            }
            var data = await res.json();
            renderMetadata(data);
        } catch (err) {
            if (err && err.name === 'AbortError') return;
            renderMetadata(null);
        } finally {
            if (activeController === controller) {
                activeController = null;
                if (metaRow) metaRow.classList.remove('pm-loading');
            }
        }
    }

    function buildMetadataRow() {
        var row = document.createElement('div');
        row.id = 'patient-metadata-row';
        row.className = 'form-row pm-row';

        var ageItem = document.createElement('div');
        ageItem.className = 'pm-item';
        var ageLabel = document.createElement('span');
        ageLabel.className = 'pm-label';
        ageLabel.textContent = 'سن بیمار:';
        var ageValue = document.createElement('span');
        ageValue.className = 'pm-value pm-age';
        ageValue.textContent = '—';
        ageItem.appendChild(ageLabel);
        ageItem.appendChild(ageValue);

        var genderItem = document.createElement('div');
        genderItem.className = 'pm-item';
        var genderLabel = document.createElement('span');
        genderLabel.className = 'pm-label';
        genderLabel.textContent = 'جنسیت:';
        var genderValue = document.createElement('span');
        genderValue.className = 'pm-value pm-gender';
        genderValue.textContent = '—';
        genderItem.appendChild(genderLabel);
        genderItem.appendChild(genderValue);

        row.appendChild(ageItem);
        row.appendChild(genderItem);
        return row;
    }

    function init() {
        var select = document.getElementById('id_patient');
        if (!select) return;
        var fieldRow = select.closest('.form-row');
        if (!fieldRow || !fieldRow.parentNode) return;

        metaRow = buildMetadataRow();
        fieldRow.parentNode.insertBefore(metaRow, fieldRow.nextSibling);

        select.addEventListener('change', function () {
            refreshSelectedPatientInfo(select.value);
        });

        // Patient may already be selected on load — the change page, or an
        // add page re-rendered after a validation error.
        if (select.value) {
            refreshSelectedPatientInfo(select.value);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
