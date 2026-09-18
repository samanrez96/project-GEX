/**
 * PersianFormat — shared Jalali date and Persian number formatting.
 *
 * Exposed as window.PersianFormat so all page-specific scripts can use it
 * without duplicating logic. Loaded in base.html before {% block extrascript %}.
 *
 * formatJalaliDate(iso)     → '۱۴۰۵/۰۲/۱۹'
 * formatJalaliDateTime(iso) → '۱۴۰۵/۰۲/۱۹ ۱۴:۳۰'
 * toPersianDigits(str)      → convert ASCII digits to Persian equivalents
 */
window.PersianFormat = (function () {
    'use strict';

    var _PERSIAN = '۰۱۲۳۴۵۶۷۸۹';
    var _dateFmt = null;

    function toPersianDigits(s) {
        return String(s).replace(/\d/g, function (d) { return _PERSIAN[d]; });
    }

    function _getDateFmt() {
        if (!_dateFmt) {
            try {
                _dateFmt = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
                    year: 'numeric', month: '2-digit', day: '2-digit'
                });
            } catch (_) {
                _dateFmt = null;
            }
        }
        return _dateFmt;
    }

    function formatJalaliDate(iso) {
        if (!iso) return '—';
        try {
            var d = new Date(iso);
            if (isNaN(d.getTime())) return '—';
            var fmt = _getDateFmt();
            if (!fmt) return toPersianDigits(String(iso).slice(0, 10));
            // Normalize any non-slash separators the locale may emit
            return fmt.format(d).replace(/[.،,\-]/g, '/');
        } catch (_) { return '—'; }
    }

    function formatJalaliDateTime(iso) {
        if (!iso) return '—';
        try {
            var d = new Date(iso);
            if (isNaN(d.getTime())) return '—';
            var datePart = formatJalaliDate(iso);
            var h = toPersianDigits(String(d.getHours()).padStart(2, '0'));
            var m = toPersianDigits(String(d.getMinutes()).padStart(2, '0'));
            return datePart + ' ' + h + ':' + m;
        } catch (_) { return '—'; }
    }

    return {
        toPersianDigits:    toPersianDigits,
        formatJalaliDate:   formatJalaliDate,
        formatJalaliDateTime: formatJalaliDateTime,
    };
}());
