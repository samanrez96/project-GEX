/**
 * ProductVendorInline (Product change page) — collapse-by-default UI.
 *
 * Django renders a normal StackedInline formset here (management form,
 * real <input>/<select> fields, delete checkbox) — none of that markup is
 * touched. This script only:
 *   1. Builds a compact summary line per existing relation (vendor name
 *      linking to its detail page, primary/active badges, unit price,
 *      supplier code) by reading the *already-rendered* field values.
 *   2. Hides the underlying fieldset behind a CSS class toggled by an
 *      explicit "ویرایش ارتباط" button, so add/edit/delete/validation all
 *      keep using Django's existing DOM/inputs exactly as before.
 *   3. Leaves a row fully expanded — no summary, no collapsing — when it
 *      has no saved vendor yet (a brand-new row: the initial blank state
 *      or one just added via "Add another") or when it carries a
 *      validation error, so the offending fields stay visible and
 *      editable after a failed submit.
 */
(function () {
    'use strict';

    var GROUP_ID = 'product_vendors-group';

    function fieldByName(row, name) {
        return row.querySelector('[id$="-' + name + '"]');
    }

    function fieldVal(row, name) {
        var el = fieldByName(row, name);
        return el ? el.value : '';
    }

    function fieldChecked(row, name) {
        var el = fieldByName(row, name);
        return !!(el && el.checked);
    }

    function vendorInfo(row) {
        var select = fieldByName(row, 'vendor');
        if (!select || !select.value) return null;
        var opt = select.options[select.selectedIndex];
        return { id: select.value, name: opt ? opt.textContent : '' };
    }

    function formatPrice(v) {
        var n = parseFloat(v);
        if (!v || isNaN(n)) return '—';
        try { return Math.round(n).toLocaleString('fa-IR') + ' تومان'; }
        catch (_) { return String(v) + ' تومان'; }
    }

    function hasError(row) {
        return !!row.querySelector('.errorlist');
    }

    function buildSummary(row, vendor) {
        var isPrimary = fieldChecked(row, 'is_primary');
        var isActive  = fieldChecked(row, 'is_active');
        var price     = fieldVal(row, 'unit_price');
        var code      = fieldVal(row, 'supplier_product_code');

        var wrap = document.createElement('div');
        wrap.className = 'pv-summary';

        var main = document.createElement('div');
        main.className = 'pv-summary-main';

        var link = document.createElement('a');
        link.className = 'pv-summary-vendor-link';
        link.href = '/admin/inventory/vendor/' + vendor.id + '/detail/';
        link.textContent = vendor.name || '—';
        main.appendChild(link);

        var badges = document.createElement('span');
        badges.className = 'pv-summary-badges';
        badges.innerHTML =
            (isPrimary ? '<span class="pv-badge pv-badge--primary">فروشنده اصلی</span>' : '')
            + (isActive
                ? '<span class="pv-badge pv-badge--active">فعال</span>'
                : '<span class="pv-badge pv-badge--inactive">غیرفعال</span>');
        main.appendChild(badges);

        var meta = document.createElement('span');
        meta.className = 'pv-summary-meta';
        meta.textContent =
            'قیمت واحد: ' + formatPrice(price)
            + '   |   کد محصول نزد فروشنده: ' + (code || '—');
        main.appendChild(meta);

        wrap.appendChild(main);

        var actions = document.createElement('div');
        actions.className = 'pv-summary-actions';

        var editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'pv-summary-btn pv-summary-btn--edit';
        editBtn.textContent = '✏️ ویرایش ارتباط';
        editBtn.addEventListener('click', function (e) {
            e.preventDefault();
            row.classList.toggle('pv-collapsed');
        });
        actions.appendChild(editBtn);

        var deleteCheckbox = row.querySelector('.delete input[type="checkbox"]');
        if (deleteCheckbox) {
            var delBtn = document.createElement('button');
            delBtn.type = 'button';
            delBtn.className = 'pv-summary-btn pv-summary-btn--delete';
            delBtn.textContent = deleteCheckbox.checked ? 'لغو حذف' : '🗑 حذف ارتباط';
            delBtn.addEventListener('click', function (e) {
                e.preventDefault();
                deleteCheckbox.checked = !deleteCheckbox.checked;
                row.classList.toggle('pv-marked-deleted', deleteCheckbox.checked);
                delBtn.textContent = deleteCheckbox.checked ? 'لغو حذف' : '🗑 حذف ارتباط';
            });
            actions.appendChild(delBtn);
        }

        wrap.appendChild(actions);
        return wrap;
    }

    function initRow(row) {
        if (!row || row.classList.contains('empty-form')) return; // Django's clone template
        if (row.dataset.pvInit) return;
        row.dataset.pvInit = '1';

        var vendor = vendorInfo(row);
        if (!vendor || hasError(row)) {
            // New/unsaved row, or one that failed validation: leave fully
            // expanded so every field (and its error) stays visible.
            return;
        }

        var h3 = row.querySelector('h3');
        if (h3) h3.style.display = 'none';

        row.insertBefore(buildSummary(row, vendor), row.firstChild);
        row.classList.add('pv-collapsible', 'pv-collapsed');
    }

    function initAll() {
        var group = document.getElementById(GROUP_ID);
        if (!group) return;
        Array.prototype.forEach.call(group.querySelectorAll('.inline-related'), initRow);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }

    // Django triggers this jQuery event after cloning a new inline row from
    // the "Add another" link. A freshly-added row has no vendor selected
    // yet, so initRow() leaves it expanded automatically (see above).
    if (window.django && window.django.jQuery) {
        window.django.jQuery(document).on('formset:added', function (event, row) {
            var el = row && row.jquery ? row[0] : row;
            initRow(el);
        });
    }
}());
