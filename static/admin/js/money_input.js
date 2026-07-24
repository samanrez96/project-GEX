/**
 * MoneyInput — live thousands-separator formatting for [data-money-input] inputs.
 *
 * Responsibilities:
 *   - Format existing values on page load with comma thousands separators
 *   - Format while the user types, preserving cursor position
 *   - Accept English, Persian (۰–۹), and Arabic-Indic (٠–٩) digits
 *   - Handle paste, select-and-replace, delete, backspace
 *   - Auto-initialise inputs added dynamically (inline formset rows)
 *
 * The submitted value is NOT touched here — the server-side
 * MoneyInput.value_from_datadict() strips commas and normalises digits.
 */
(function () {
    'use strict';

    function fromPersian(s) {
        return String(s)
            .replace(/[۰-۹]/g, function (c) { return c.charCodeAt(0) - 0x06F0; })
            .replace(/[٠-٩]/g, function (c) { return c.charCodeAt(0) - 0x0660; });
    }

    function toRaw(s) {
        return fromPersian(String(s)).replace(/,/g, '');
    }

    function addCommas(s) {
        var parts = s.split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return parts.join('.');
    }

    function formatRaw(raw) {
        if (raw === '' || raw === '-') return raw;
        if (!/^-?\d*\.?\d*$/.test(raw)) return null;
        return addCommas(raw);
    }

    function onInput(e) {
        var el = e.target;
        var raw = toRaw(el.value);
        var formatted = formatRaw(raw);
        if (formatted === null || formatted === el.value) return;

        var start = el.selectionStart;
        var oldLen = el.value.length;
        el.value = formatted;
        var pos = Math.max(0, start + (formatted.length - oldLen));
        el.setSelectionRange(pos, pos);
    }

    function initEl(el) {
        if (el._moneyInit) return;
        el._moneyInit = true;
        el.addEventListener('input', onInput);
        if (el.value) {
            var raw = toRaw(el.value);
            var formatted = formatRaw(raw);
            if (formatted !== null) el.value = formatted;
        }
    }

    function initAll(root) {
        var els = (root || document).querySelectorAll('[data-money-input]');
        for (var i = 0; i < els.length; i++) initEl(els[i]);
    }

    document.addEventListener('DOMContentLoaded', function () {
        initAll();

        // Auto-initialise inputs inserted dynamically (e.g. "افزودن قلم" in purchase form)
        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var added = mutations[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var node = added[j];
                    if (node.nodeType !== 1) continue;
                    if (node.matches && node.matches('[data-money-input]')) initEl(node);
                    initAll(node);
                }
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    });

    window.MoneyInput = { init: initAll };
}());
