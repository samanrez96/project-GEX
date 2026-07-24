/**
 * GlobalSearch — shared debounced search component for API-driven admin pages.
 *
 * Attaches to every input with [data-global-search] and fires a
 * `global-search:changed` CustomEvent (bubbles) on the element itself after
 * the configured debounce delay.  Page JS files listen for this event on
 * their own search element and call their respective fetch functions.
 *
 * HTML usage:
 *   <input data-global-search
 *          data-search-param="search"   (default: "search")
 *          data-search-delay="300"      (default: 300 ms)
 *          data-search-min-length="0"   (default: 0 chars)
 *   >
 *
 * Page JS usage:
 *   searchEl.addEventListener('global-search:changed', function (e) {
 *       state.search = e.detail.value;
 *       state.page   = 1;
 *       fetchData();
 *   });
 *
 * CustomEvent detail:
 *   {
 *     value:   string,           — trimmed search value
 *     param:   string,           — search query-parameter name
 *     params:  URLSearchParams,  — current window.location.search snapshot
 *     element: HTMLInputElement, — the input element that triggered the event
 *   }
 *
 * Keyboard shortcuts (when focus is on the search input):
 *   Enter  — dispatch immediately, bypassing the remaining debounce delay
 *   Escape — clear the input and dispatch an empty search
 */
window.GlobalSearch = (function () {
    'use strict';

    var SELECTOR = '[data-global-search]';
    var EVENT    = 'global-search:changed';
    var INIT_KEY = '_gsInit';

    /**
     * Attach global-search behaviour to a single input element.
     * Safe to call multiple times on the same element (idempotent).
     */
    function attachTo(el) {
        if (el[INIT_KEY]) return;
        el[INIT_KEY] = true;

        var delay  = parseInt(el.getAttribute('data-search-delay'),      10) || 300;
        var param  = el.getAttribute('data-search-param') || 'search';
        var minLen = parseInt(el.getAttribute('data-search-min-length'), 10) || 0;
        var timer  = null;

        function dispatch(value) {
            clearTimeout(timer);
            timer = null;
            el.dispatchEvent(new CustomEvent(EVENT, {
                bubbles:    true,
                cancelable: false,
                detail: {
                    value:   value,
                    param:   param,
                    params:  new URLSearchParams(window.location.search),
                    element: el,
                },
            }));
        }

        function scheduleDispatch() {
            clearTimeout(timer);
            var val = el.value.trim();
            if (val.length >= minLen || val.length === 0) {
                timer = setTimeout(function () { dispatch(val); }, delay);
            }
        }

        el.addEventListener('input', scheduleDispatch);

        el.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                dispatch(el.value.trim());
            } else if (e.key === 'Escape') {
                el.value = '';
                dispatch('');
            }
        });
    }

    /**
     * Scan the document for [data-global-search] inputs and attach behaviour.
     * Called automatically on DOMContentLoaded; can also be called manually
     * after dynamic DOM mutations.
     */
    function init() {
        var els = document.querySelectorAll(SELECTOR);
        for (var i = 0; i < els.length; i++) {
            attachTo(els[i]);
        }
    }

    // Auto-init — respects pages that already have a loaded DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    return {
        init:     init,
        attachTo: attachTo,
        EVENT:    EVENT,
    };
}());
