/**
 * FormErrors — reusable helper for displaying DRF validation errors in the
 * API-driven admin pages.
 *
 * DRF returns validation errors as:
 *
 *   Field errors:
 *     { "field_name": ["پیام اول", "پیام دوم"] }
 *
 *   Non-field (object-level) errors:
 *     { "non_field_errors": ["پیام"] }
 *
 *   Single detail message (permission / not-found / etc.):
 *     { "detail": "پیام" }
 *
 * Usage:
 *
 *   // Show errors in a container element
 *   FormErrors.show('my-error-container', errorData);
 *
 *   // Build a readable string from any error shape
 *   var msg = FormErrors.format(errorData);
 *   showToast(msg, 'error');
 *
 *   // Clear a previously shown error container
 *   FormErrors.clear('my-error-container');
 *
 * The container element must have an id matching the first argument.
 * If the container is not found, errors are silently ignored (safe to call
 * even when no container exists on the page).
 */
window.FormErrors = (function () {
    'use strict';

    /**
     * Flatten a DRF error object into a human-readable Persian string.
     *
     * @param  {object|string|Array} data  — parsed JSON body from a 4xx response
     * @returns {string}
     */
    function format(data) {
        if (!data) return 'خطای نامشخص.';

        // Plain string
        if (typeof data === 'string') return data;

        // Array of messages (e.g. non_field_errors value)
        if (Array.isArray(data)) {
            return data.map(String).join('، ');
        }

        // { detail: "..." }
        if (data.detail) return String(data.detail);

        // { field: [messages] } object
        var lines = [];
        Object.keys(data).forEach(function (key) {
            var msgs = data[key];
            var text = Array.isArray(msgs) ? msgs.map(String).join('، ') : String(msgs);
            if (key === 'non_field_errors') {
                lines.push(text);
            } else {
                lines.push(key + ': ' + text);
            }
        });
        return lines.length ? lines.join('\n') : 'خطای نامشخص.';
    }

    /**
     * Render validation errors inside a DOM container.
     *
     * Creates a `.fv-error-summary` block with a list of error messages.
     * The container is shown automatically; call clear() to hide it.
     *
     * @param {string} containerId  — ID of the wrapping element
     * @param {object} data          — parsed DRF error response body
     */
    function show(containerId, data) {
        var container = document.getElementById(containerId);
        if (!container) return;

        var lines = [];

        if (typeof data === 'string') {
            lines.push(data);
        } else if (Array.isArray(data)) {
            lines = data.map(String);
        } else if (data && typeof data === 'object') {
            if (data.detail) {
                lines.push(String(data.detail));
            } else {
                Object.keys(data).forEach(function (key) {
                    var msgs = data[key];
                    var text = Array.isArray(msgs) ? msgs.map(String).join('، ') : String(msgs);
                    lines.push(text);
                });
            }
        }

        if (!lines.length) lines.push('خطایی رخ داد.');

        var html = '<div class="fv-error-summary" role="alert" dir="rtl">'
            + '<span class="fv-error-icon" aria-hidden="true">⚠️</span>'
            + '<ul class="fv-error-list">'
            + lines.map(function (l) {
                return '<li>' + _escape(l) + '</li>';
            }).join('')
            + '</ul>'
            + '</div>';

        container.innerHTML = html;
        container.style.display = '';
    }

    /**
     * Clear and hide a previously shown error container.
     *
     * @param {string} containerId
     */
    function clear(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';
        container.style.display = 'none';
    }

    /**
     * Parse a fetch() Response object that returned a 4xx status and return
     * the error body.  Resolves to a plain string if the body is not JSON.
     *
     * @param  {Response} response  — fetch() Response object
     * @returns {Promise<object|string>}
     */
    function parseResponse(response) {
        return response.text().then(function (text) {
            try {
                return JSON.parse(text);
            } catch (_) {
                return text || ('HTTP ' + response.status);
            }
        });
    }

    // ── Internal helpers ─────────────────────────────────────────────

    function _escape(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    return {
        format:        format,
        show:          show,
        clear:         clear,
        parseResponse: parseResponse,
    };
}());
