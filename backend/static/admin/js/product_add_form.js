/**
 * ProductAddFormApp — existing-product detection for the Product add form only.
 *
 * When the user types a product name, queries the products API for an exact
 * case-insensitive match and:
 *   1. Shows a Persian warning below the name field with price/stock info.
 *   2. Provides links to the existing product (edit + detail pages).
 *   3. Auto-fills price, initial stock, type, and minimum stock from the match.
 *   4. Does NOT overwrite fields the user has already manually changed.
 *   5. Hides the warning when the typed name no longer has an exact match.
 *
 * This script is loaded on every ProductAdmin change-form page, but the URL
 * guard at the top ensures it runs only on /admin/inventory/product/add/.
 */
const ProductAddFormApp = (function () {
    'use strict';

    // Guard: only run on the product add form, nowhere else.
    if (!window.location.pathname.match(/\/inventory\/product\/add\/?$/)) {
        return {};
    }

    var API_URL     = '/api/v2/inventory/products/';
    var DEBOUNCE_MS = 400;
    var MIN_CHARS   = 2;

    var _timer    = null;
    var _edited   = {};   // { 'id_purchase_price': true, ... } — user has edited this field

    // ── Formatting ───────────────────────────────────────────────

    function formatPrice(val) {
        var n = parseFloat(val) || 0;
        if (n === 0) return '۰';
        return Math.round(n).toLocaleString('fa-IR');
    }

    function formatStock(val) {
        var n = parseFloat(val);
        if (isNaN(n) || n === 0) return '۰';
        // Strip trailing decimal zeros: 10.000 → 10, 10.500 → 10.5
        var rounded = parseFloat(n.toFixed(3));
        var s = rounded % 1 === 0 ? String(Math.round(rounded)) : String(rounded);
        return s.replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[+d]; });
    }

    // ── Warning / info box ────────────────────────────────────────

    function getOrCreateBox() {
        var box = document.getElementById('pa-dup-box');
        if (box) return box;

        box = document.createElement('div');
        box.id = 'pa-dup-box';
        box.style.cssText = (
            'display:none;margin:6px 0 4px;padding:10px 14px;' +
            'background:#fff8e1;border:1px solid #f9a825;border-radius:6px;' +
            'color:#5f4200;font-size:0.85em;line-height:1.7;direction:rtl;text-align:right;'
        );

        var nameEl = document.getElementById('id_name');
        if (!nameEl) return box;
        var row = nameEl.closest('.form-row') || nameEl.closest('div') || nameEl.parentElement;
        if (row) row.insertAdjacentElement('afterend', box);
        return box;
    }

    function showBox(product) {
        var box   = getOrCreateBox();
        var chUrl = '/admin/inventory/product/' + product.id + '/change/';
        var dtUrl = '/admin/inventory/product/' + product.id + '/detail/';

        box.innerHTML = (
            '<strong>&#9888; محصولی با این نام قبلاً ثبت شده است</strong>' +
            '<br>' +
            '<span style="font-size:0.93em;">' +
                'کد داخلی: <b>' + (product.internal_code || '—') + '</b>' +
                ' &nbsp;|&nbsp; قیمت خرید: <b>' + formatPrice(product.purchase_price) + ' تومان</b>' +
                ' &nbsp;|&nbsp; موجودی فعلی: <b>' + formatStock(product.current_stock) + '</b>' +
            '</span>' +
            '<br>' +
            '<a href="' + chUrl + '" style="color:#1558c0;text-decoration:none;margin-left:14px;">&#9998; ویرایش محصول موجود</a>' +
            '<a href="' + dtUrl + '" style="color:#1558c0;text-decoration:none;">&#128269; مشاهده جزئیات</a>'
        );
        box.style.display = '';
    }

    function hideBox() {
        var box = document.getElementById('pa-dup-box');
        if (box) box.style.display = 'none';
    }

    // ── Auto-fill ────────────────────────────────────────────────

    function setField(id, value) {
        if (_edited[id]) return;          // user manually changed this field — leave it
        var el = document.getElementById(id);
        if (!el) return;
        el.value = (value !== null && value !== undefined) ? value : '';
    }

    function autoFill(product) {
        var price = parseFloat(product.purchase_price) || 0;
        setField('id_purchase_price', price > 0 ? price : '0');

        var stock = parseFloat(product.current_stock) || 0;
        setField('id_initial_stock', stock > 0 ? stock : '');

        var minSt = parseFloat(product.minimum_stock) || 0;
        setField('id_minimum_stock', minSt > 0 ? minSt : '');

        setField('id_product_type', product.product_type || '');
    }

    // ── API lookup ───────────────────────────────────────────────

    function lookup(name) {
        var term = name.trim();
        if (term.length < MIN_CHARS) { hideBox(); return; }

        fetch(
            API_URL + '?search=' + encodeURIComponent(term) + '&page_size=10',
            { credentials: 'same-origin' }
        )
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
            if (!data || !data.results) { hideBox(); return; }

            var lower = term.toLowerCase();
            var match = null;
            for (var i = 0; i < data.results.length; i++) {
                if (data.results[i].name.toLowerCase().trim() === lower) {
                    match = data.results[i];
                    break;
                }
            }

            if (match) {
                showBox(match);
                autoFill(match);
            } else {
                hideBox();
            }
        })
        .catch(function () { hideBox(); });
    }

    // ── Init ─────────────────────────────────────────────────────

    function init() {
        var nameEl = document.getElementById('id_name');
        if (!nameEl) return;

        // Debounced lookup on every keystroke in the name field.
        nameEl.addEventListener('input', function () {
            clearTimeout(_timer);
            _timer = setTimeout(function () { lookup(nameEl.value); }, DEBOUNCE_MS);
        });

        // Mark a field as user-edited so auto-fill will not overwrite it later.
        ['id_purchase_price', 'id_initial_stock', 'id_minimum_stock', 'id_product_type']
            .forEach(function (id) {
                var el = document.getElementById(id);
                if (!el) return;
                el.addEventListener('input',  function () { _edited[id] = true; });
                el.addEventListener('change', function () { _edited[id] = true; });
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    return { init: init };
}());
