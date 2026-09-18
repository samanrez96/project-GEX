/**
 * StockMovementInline (Product change page) — presentation-only fix-up.
 *
 * Django already renders a correct <table>/<thead>/<tbody> for this
 * read-only TabularInline (see StockMovementInline's docstring in
 * inventory/admin.py). Column widths, direction handling for the two
 * Jalali-date columns, and hiding the empty "original"/"delete" columns
 * are all done in product_movement_table.css via nth-child, on purpose —
 * that works even before this script runs. This script only handles the
 * two things CSS genuinely cannot:
 *   1. Wraps the existing <table> in a `.product-movement-table-scroll`
 *      div and tags the table itself `.product-movement-table`.
 *   2. When there are zero movement rows, replaces Django's empty <tbody>
 *      with a single full-width "no movements yet" row.
 * Neither touches any form field, name=, or id= attribute.
 */
(function () {
    'use strict';

    function init() {
        var group = document.getElementById('stock_movements-group');
        if (!group) return;

        var table = group.querySelector('table');
        if (!table || table.classList.contains('product-movement-table')) return;

        table.classList.add('product-movement-table');

        var scroll = document.createElement('div');
        scroll.className = 'product-movement-table-scroll';
        table.parentNode.insertBefore(scroll, table);
        scroll.appendChild(table);

        var headerCells = table.querySelectorAll('thead th');
        var bodyRows = table.querySelectorAll('tbody tr');
        var dataRowCount = 0;
        bodyRows.forEach(function (row) {
            // Django renders one hidden "empty form" template row (class
            // contains "empty-form") that must stay invisible and doesn't
            // count as a real movement. StockMovementInline never has one
            // (has_add_permission is always False here), but this stays
            // as a defensive no-op guard.
            if (!row.classList.contains('empty-form')) dataRowCount += 1;
        });

        if (dataRowCount === 0) {
            var tbody = table.querySelector('tbody');
            if (tbody) {
                var colCount = headerCells.length || 10;
                var tr = document.createElement('tr');
                var td = document.createElement('td');
                td.className = 'pmt-empty-state';
                td.colSpan = colCount;
                td.textContent = 'هنوز حرکتی برای این محصول ثبت نشده است.';
                tr.appendChild(td);
                tbody.appendChild(tr);
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
