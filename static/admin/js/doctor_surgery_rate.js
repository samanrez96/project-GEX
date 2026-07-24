/**
 * DoctorSurgeryRate inline formset — dynamic add/remove-row behaviour.
 *
 * Fully self-contained: does not rely on Django's default admin/js/inlines.js
 * (which expects the stock tabular-inline DOM shape). The empty-row markup
 * lives inert inside <template id="doctor-rate-empty-form">, using Django's
 * formset "__prefix__" convention in every field name/id — cloning it and
 * replacing "__prefix__" with the current form count produces a fully wired
 * new row, then TOTAL_FORMS is bumped so Django accepts it on submit.
 */
(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        var wrapper = document.querySelector('.doctor-rates-wrapper');
        if (!wrapper) return;

        var tbody = wrapper.querySelector('#doctor-rates-body');
        var template = wrapper.querySelector('#doctor-rate-empty-form');
        var addBtn = wrapper.querySelector('#doctor-rate-add-row');
        var totalFormsInput = wrapper.querySelector('input[name$="-TOTAL_FORMS"]');
        if (!tbody || !template || !addBtn || !totalFormsInput) return;

        addBtn.addEventListener('click', function (evt) {
            evt.preventDefault();
            var index = parseInt(totalFormsInput.value, 10) || 0;
            var html = template.innerHTML.split('__prefix__').join(index);
            var holder = document.createElement('tbody');
            holder.innerHTML = html;
            var newRow = holder.firstElementChild;
            if (!newRow) return;
            tbody.appendChild(newRow);
            totalFormsInput.value = index + 1;
        });

        tbody.addEventListener('click', function (evt) {
            var removeBtn = evt.target.closest('.dsr-remove-row');
            if (!removeBtn) return;
            evt.preventDefault();
            var row = removeBtn.closest('tr');
            if (row) row.remove();
        });
    });
})();
