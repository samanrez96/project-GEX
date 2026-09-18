/**
 * TableFilters — shared sort-control helper for API-driven admin tables.
 *
 * The project uses DRF's OrderingFilter convention:
 *   ordering=field      → ascending
 *   ordering=-field     → descending
 *
 * This module provides helpers for:
 *   - parsing the current ordering string into a {field, dir} pair
 *   - building an ordering string from a field + direction selection
 *   - syncing sort dropdowns to the current state.ordering value
 *   - binding sort dropdown change events so selecting a field/direction
 *     immediately updates state.ordering and triggers a fetch
 *
 * Usage in page JS:
 *
 *   // in syncControlsToState():
 *   TableFilters.syncSortControls('pl-sort-by', 'pl-sort-dir', state);
 *
 *   // in bindEvents():
 *   TableFilters.bindSortControls('pl-sort-by', 'pl-sort-dir', state, fetchProducts);
 *
 * Both helpers are safe to call when the elements are absent (e.g. on pages
 * that don't yet have sort controls).
 */
window.TableFilters = (function () {
    'use strict';

    /**
     * Decompose a DRF ordering string into its field name and direction.
     *
     * @param  {string} ordering  e.g. '-surgery_date' or 'full_name'
     * @returns {{ field: string, dir: 'asc'|'desc' }}
     */
    function parseOrdering(ordering) {
        if (!ordering) return { field: '', dir: 'asc' };
        if (ordering.charAt(0) === '-') {
            return { field: ordering.slice(1), dir: 'desc' };
        }
        return { field: ordering, dir: 'asc' };
    }

    /**
     * Build a DRF ordering string from a field name and direction.
     *
     * @param  {string} field  e.g. 'surgery_date'
     * @param  {string} dir    'asc' | 'desc'
     * @returns {string}  e.g. '-surgery_date'
     */
    function makeOrdering(field, dir) {
        if (!field) return '';
        return (dir === 'desc' ? '-' : '') + field;
    }

    /**
     * Push the current state.ordering into the sort-field and sort-direction
     * dropdown elements so the UI reflects the current sort state.
     *
     * @param {string} fieldSelectId  ID of the sort-field <select>
     * @param {string} dirSelectId    ID of the sort-direction <select>
     * @param {object} state          Page state object (must have .ordering)
     */
    function syncSortControls(fieldSelectId, dirSelectId, state) {
        var parsed   = parseOrdering(state.ordering || '');
        var fieldSel = document.getElementById(fieldSelectId);
        var dirSel   = document.getElementById(dirSelectId);

        if (fieldSel && parsed.field) {
            fieldSel.value = parsed.field;
        }
        if (dirSel) {
            dirSel.value = parsed.dir || 'asc';
        }
    }

    /**
     * Attach change listeners to the sort-field and sort-direction dropdowns.
     * When either changes, state.ordering is updated and fetchFn is called
     * with page reset to 1.
     *
     * @param {string}   fieldSelectId
     * @param {string}   dirSelectId
     * @param {object}   state    Page state object (mutated in place)
     * @param {function} fetchFn  Page-specific data-fetch function
     */
    function bindSortControls(fieldSelectId, dirSelectId, state, fetchFn) {
        var fieldSel = document.getElementById(fieldSelectId);
        var dirSel   = document.getElementById(dirSelectId);

        function onChange() {
            var fEl = document.getElementById(fieldSelectId);
            var dEl = document.getElementById(dirSelectId);
            if (!fEl || !dEl) return;
            var field = fEl.value;
            var dir   = dEl.value || 'asc';
            if (field) {
                state.ordering = makeOrdering(field, dir);
                state.page     = 1;
                fetchFn();
            }
        }

        if (fieldSel) fieldSel.addEventListener('change', onChange);
        if (dirSel)   dirSel.addEventListener('change', onChange);
    }

    return {
        parseOrdering:    parseOrdering,
        makeOrdering:     makeOrdering,
        syncSortControls: syncSortControls,
        bindSortControls: bindSortControls,
    };
}());
