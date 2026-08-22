/**
 * TablePagination — shared pagination rendering for API-driven admin tables.
 *
 * Extracts the duplicated buildPageRange / renderPagination logic that was
 * previously copy-pasted into product_list.js, purchase_list.js,
 * employee_list.js, and surgery_history_list.js.
 *
 * Usage (page JS):
 *
 *   function renderPagination(data) {
 *       TablePagination.renderControls({
 *           pagesId:      'pl-pagination-pages',
 *           infoId:       'pl-pagination-info',
 *           data:         data,          // API response envelope
 *           currentPage:  state.page,
 *           btnClass:     'pl-page-btn', // CSS class prefix for buttons
 *           recordLabel:  'محصول',       // Persian label for one record
 *           onPageChange: goToPage,      // function(pageNumber)
 *       });
 *   }
 *
 * Expected API response fields (all provided by StandardPagination /
 * ProductPagination):
 *   count       {number}  — total number of matching records
 *   total_pages {number}  — total number of pages
 *   page_size   {number}  — records per page for the current request
 *   results     {array}   — records on the current page
 *
 * RTL note: in the RTL layout used by this project '>' is the "previous"
 * button (moves toward a lower page number, displayed on the right) and
 * '<' is the "next" button (displayed on the left).
 */
window.TablePagination = (function () {
    'use strict';

    /**
     * Convert ASCII digits in a value to their Persian/Arabic-Indic equivalents.
     * Mirrors the toPersian() helper that each page JS file declares locally.
     */
    function toPersian(n) {
        return String(n).replace(/\d/g, function (d) {
            return '۰۱۲۳۴۵۶۷۸۹'[d];
        });
    }

    /**
     * Return the array of page labels (numbers + '…' ellipsis markers) for a
     * pagination control that shows at most 7 entries.
     *
     * @param {number} current  1-based current page
     * @param {number} total    total number of pages
     * @returns {Array<number|string>}
     */
    function buildPageRange(current, total) {
        if (total <= 7) {
            return Array.from({ length: total }, function (_, i) { return i + 1; });
        }
        if (current <= 4) {
            return [1, 2, 3, 4, 5, '…', total];
        }
        if (current >= total - 3) {
            return [1, '…', total - 4, total - 3, total - 2, total - 1, total];
        }
        return [1, '…', current - 1, current, current + 1, '…', total];
    }

    /**
     * Populate the pagination controls in the DOM from an API response.
     *
     * @param {object} cfg
     * @param {string}   cfg.pagesId      ID of the <div> that holds page buttons
     * @param {string}   cfg.infoId       ID of the <span> for the "Showing X–Y of Z" text
     * @param {object}   cfg.data         API response envelope (count, total_pages, page_size)
     * @param {number}   cfg.currentPage  Current 1-based page number
     * @param {string}   cfg.btnClass     Base CSS class for page buttons (e.g. 'pl-page-btn')
     * @param {string}   cfg.recordLabel  Persian unit label  (e.g. 'محصول')
     * @param {function} cfg.onPageChange Callback invoked with the target page number
     */
    function renderControls(cfg) {
        var pagesEl = document.getElementById(cfg.pagesId);
        var infoEl  = document.getElementById(cfg.infoId);
        if (!pagesEl || !infoEl) return;

        var data       = cfg.data        || {};
        var total      = data.count      || 0;
        var pageSize   = data.page_size  || 25;
        var totalPages = data.total_pages
            || (total > 0 ? Math.ceil(total / pageSize) : 1);
        var current    = cfg.currentPage || 1;
        var start      = total === 0 ? 0 : (current - 1) * pageSize + 1;
        var end        = Math.min(current * pageSize, total);

        infoEl.textContent =
            'نمایش ' + toPersian(start) +
            ' تا '   + toPersian(end)   +
            ' از '   + toPersian(total) +
            ' '      + (cfg.recordLabel || 'مورد');

        pagesEl.innerHTML = '';

        var cls          = cfg.btnClass || 'tp-page-btn';
        var activeClass  = cls + '--active';
        var ellipsisClass = cls + '--ellipsis';

        function makeBtn(label, targetPage, disabled, active, ellipsis) {
            var btn = document.createElement('button');
            btn.type      = 'button';
            btn.className = cls
                + (active   ? ' ' + activeClass   : '')
                + (ellipsis ? ' ' + ellipsisClass : '');
            btn.textContent = toPersian(label);
            btn.disabled    = disabled || ellipsis;
            if (!disabled && !ellipsis && cfg.onPageChange) {
                /* IIFE captures targetPage correctly in older JS environments */
                (function (p) {
                    btn.addEventListener('click', function () { cfg.onPageChange(p); });
                }(targetPage));
            }
            return btn;
        }

        /* RTL: '>' = previous page (towards start, shown on the right side) */
        pagesEl.appendChild(makeBtn('>', current - 1, current <= 1, false, false));

        buildPageRange(current, totalPages).forEach(function (p) {
            if (p === '…') {
                pagesEl.appendChild(makeBtn('…', null, false, false, true));
            } else {
                pagesEl.appendChild(makeBtn(p, p, false, p === current, false));
            }
        });

        /* RTL: '<' = next page (towards end, shown on the left side) */
        pagesEl.appendChild(makeBtn('<', current + 1, current >= totalPages, false, false));
    }

    return {
        toPersian:      toPersian,
        buildPageRange: buildPageRange,
        renderControls: renderControls,
    };
}());
