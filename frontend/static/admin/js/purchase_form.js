/**
 * PurchaseFormApp — handles the custom purchase add/edit form.
 *
 * Responsibilities:
 *   - Row totals: automatic (quantity × unit_price) or manual override
 *   - Grand total aggregation across all active rows using effective total
 *   - Item count badge update
 *   - "افزودن قلم" — clone empty Django formset form, update prefix indices
 *   - "حذف ردیف" — mark existing rows for Django DELETE, hide new rows
 *   - Unit display refresh via products API when product select changes
 *   - Searchable product selector: trigger + dropdown with visible search box
 *   - Disable item inputs for locked (CONFIRMED/CANCELLED) purchases
 *
 * Manual override:
 *   Each row has a manual_total number input.
 *   - Empty (blank): automatic mode — placeholder shows quantity × unit_price.
 *   - Has value: manual mode — quantity/price changes do NOT overwrite the value.
 *   - Reset button (↺): clears manual_total input, returns to automatic mode.
 *   Programmatic updates (auto-fill) only touch the placeholder — never the value —
 *   so they cannot accidentally activate manual mode.
 */
const PurchaseFormApp = (function () {
    'use strict';

    var PREFIX       = window.PF_FORMSET_PREFIX || 'items';
    var API_PRODUCTS = window.PF_PRODUCTS_API   || '/api/v1/inventory/products/';

    // ── Utilities ────────────────────────────────────────────────

    function toPersian(n) {
        return String(n).replace(/\d/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[d]; });
    }

    function formatAmount(val) {
        var n = parseFloat(String(val).replace(/,/g, ''));
        if (isNaN(n)) return '—';
        return Math.round(n).toLocaleString('fa-IR');
    }

    function totalFormCountEl() {
        // Use querySelector with the name attribute because Django renders the
        // management form input with id="id_<prefix>-TOTAL_FORMS" (note the "id_"
        // prefix) which does not match a plain getElementById(prefix+"-TOTAL_FORMS").
        // Selecting by name is correct and resilient to Django ID conventions.
        return document.querySelector('[name="' + PREFIX + '-TOTAL_FORMS"]');
    }

    function getTotalFormCount() {
        var el = totalFormCountEl();
        return el ? (parseInt(el.value, 10) || 0) : 0;
    }

    function setTotalFormCount(n) {
        var el = totalFormCountEl();
        if (el) el.value = String(n);
    }

    // ── Row field helpers ────────────────────────────────────────

    function getRowQty(row) {
        var inp = row.querySelector('input[name$="-quantity"]');
        if (!inp) return 0;
        var v = parseFloat(inp.value.replace(/,/g, ''));
        return isNaN(v) ? 0 : v;
    }

    function getRowPrice(row) {
        var inp = row.querySelector('input[name$="-unit_price"]');
        if (!inp) return 0;
        var v = parseFloat(inp.value.replace(/,/g, ''));
        return isNaN(v) ? 0 : v;
    }

    function getManualTotalInput(row) {
        return row.querySelector('input[name$="-manual_total"]');
    }

    // Returns the effective total for a row:
    //   if manual_total input is non-empty → that value
    //   otherwise → quantity × unit_price
    function getRowEffectiveTotal(row) {
        var inp = getManualTotalInput(row);
        if (inp) {
            var raw = inp.value.trim();
            if (raw !== '') {
                var n = parseFloat(raw.replace(/,/g, ''));
                if (!isNaN(n) && n >= 0) return n;
            }
        }
        return getRowQty(row) * getRowPrice(row);
    }

    // Returns true when the manual_total input has a non-empty value.
    function rowIsManual(row) {
        var inp = getManualTotalInput(row);
        return inp !== null && inp.value.trim() !== '';
    }

    // ── Row total display ─────────────────────────────────────────
    //
    // In automatic mode: sets the input placeholder to the calculated total and
    //                    hides the reset button.
    // In manual mode:    shows the reset button (value stays as user entered).
    //
    // IMPORTANT: this function never writes to .value of the manual_total input.
    // Only the user (typing) or resetRowToAuto() may write .value.

    function updateRowTotal(row) {
        var inp      = getManualTotalInput(row);
        var resetBtn = row.querySelector('.pf-row-total-reset');
        var isManual = rowIsManual(row);

        if (inp && !isManual) {
            // Auto mode — update placeholder with calculated total
            var qty   = getRowQty(row);
            var price = getRowPrice(row);
            inp.placeholder = (qty > 0 && price >= 0) ? formatAmount(qty * price) : '—';
        }

        if (resetBtn) {
            resetBtn.style.display = isManual ? '' : 'none';
        }
    }

    function resetRowToAuto(row) {
        var inp = getManualTotalInput(row);
        if (inp) {
            inp.value = '';
            inp.classList.remove('pf-manual-active');
        }
        updateRowTotal(row);
        updateGrandTotal();
    }

    // ── Grand total ──────────────────────────────────────────────

    function updateGrandTotal() {
        var rows = document.querySelectorAll('#pf-items-tbody .pf-item-row');
        var total = 0;
        rows.forEach(function (row) {
            if (row.classList.contains('pf-item-deleted')) return;
            var deleteCheck = row.querySelector('input[name$="-DELETE"]');
            if (deleteCheck && deleteCheck.checked) return;
            total += getRowEffectiveTotal(row);
        });
        var el = document.getElementById('pf-grand-total');
        if (el) el.textContent = formatAmount(Math.round(total));
    }

    // ── Item count badge ─────────────────────────────────────────

    function updateItemCount() {
        var rows   = document.querySelectorAll('#pf-items-tbody .pf-item-row');
        var active = 0;
        rows.forEach(function (row) {
            if (row.classList.contains('pf-item-deleted')) return;
            var deleteCheck = row.querySelector('input[name$="-DELETE"]');
            if (deleteCheck && deleteCheck.checked) return;
            active++;
        });
        var badge = document.getElementById('pf-items-count');
        if (badge) badge.textContent = toPersian(active);

        var emptyMsg = document.getElementById('pf-items-empty');
        if (emptyMsg) emptyMsg.style.display = active === 0 ? '' : 'none';
    }

    // ── Product lookup via API ────────────────────────────────────

    function fetchProductUnit(productId, row) {
        var unitEl = row.querySelector('.pf-unit-text');
        if (!productId) {
            if (unitEl) unitEl.textContent = '—';
            return;
        }

        fetch(API_PRODUCTS + productId + '/', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data) return;

                if (unitEl) unitEl.textContent = data.unit || '—';

                // Auto-fill unit_price from product's current purchase_price,
                // but only when the field is currently empty or zero so that
                // existing values entered by the user are never overwritten.
                var priceInp = row.querySelector('input[name$="-unit_price"]');
                if (priceInp) {
                    var currentPrice = parseFloat(priceInp.value.replace(/,/g, '')) || 0;
                    var productPrice = parseFloat(data.purchase_price) || 0;
                    if (currentPrice === 0 && productPrice > 0) {
                        priceInp.value = productPrice;
                        priceInp.dispatchEvent(new Event('input', { bubbles: true }));
                        // Only update row total placeholder if in auto mode
                        updateRowTotal(row);
                        updateGrandTotal();
                    }
                }
            })
            .catch(function () {
                if (unitEl) unitEl.textContent = '—';
            });
    }

    // ── Product selector with visible search dropdown ─────────────
    //
    // Replaces the native <select> with:
    //   • a trigger div  — shows the selected product label (stays in the row)
    //   • a dropdown div — appended to <body> with position:fixed so it escapes
    //                      the table-wrap's overflow:auto scroll container.
    //
    // The dropdown contains:
    //   • a visible search input fixed at the top
    //   • a scrollable results list below
    //
    // The native <select> is hidden but kept in the DOM so Django's formset
    // submission continues to work correctly.

    function initProductSelector(selectEl) {
        if (selectEl.dataset.psInit) return;
        selectEl.dataset.psInit = '1';
        selectEl.style.display = 'none';

        // ── Trigger ───────────────────────────────────────────────
        var trigger = document.createElement('div');
        trigger.className = 'pf-product-trigger';
        trigger.setAttribute('tabindex', '0');
        trigger.setAttribute('role', 'combobox');
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false');
        trigger.setAttribute('dir', 'rtl');

        var triggerText = document.createElement('span');
        triggerText.className = 'pf-product-trigger-text';

        var triggerArrow = document.createElement('span');
        triggerArrow.className = 'pf-product-trigger-arrow';
        triggerArrow.setAttribute('aria-hidden', 'true');

        trigger.appendChild(triggerText);
        trigger.appendChild(triggerArrow);

        // Pre-fill trigger text for edit-form rows that already have a selection
        var si = selectEl.selectedIndex;
        var so = si >= 0 ? selectEl.options[si] : null;
        if (so && so.value) {
            triggerText.textContent = so.text;
            trigger.classList.add('pf-product-trigger--has-value');
        } else {
            triggerText.textContent = 'انتخاب محصول...';
            trigger.classList.add('pf-product-trigger--empty');
        }

        // Insert trigger right before the hidden select, inside its parent
        selectEl.parentNode.insertBefore(trigger, selectEl);

        // ── Dropdown panel (body-appended, position:fixed) ────────
        var dropdown = document.createElement('div');
        dropdown.className = 'pf-product-search-dropdown';
        dropdown.style.display = 'none';
        dropdown.setAttribute('dir', 'rtl');
        dropdown.setAttribute('role', 'listbox');

        var searchHeader = document.createElement('div');
        searchHeader.className = 'pf-product-search-header';

        var searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'pf-product-search-input';
        searchInput.placeholder = 'جستجو بر اساس نام یا کد داخلی...';
        searchInput.setAttribute('autocomplete', 'off');
        searchInput.setAttribute('dir', 'rtl');
        searchInput.setAttribute('aria-label', 'جستجوی محصول');

        searchHeader.appendChild(searchInput);

        var resultsDiv = document.createElement('div');
        resultsDiv.className = 'pf-product-search-results';

        dropdown.appendChild(searchHeader);
        dropdown.appendChild(resultsDiv);
        document.body.appendChild(dropdown);

        // ── Positioning ───────────────────────────────────────────
        function positionDropdown() {
            var rect = trigger.getBoundingClientRect();
            dropdown.style.top   = (rect.bottom + 2) + 'px';
            dropdown.style.left  = rect.left + 'px';
            dropdown.style.width = Math.max(rect.width, 240) + 'px';
        }

        // ── Open / close ──────────────────────────────────────────
        var isOpen = false;

        function openDropdown() {
            if (isOpen) return;
            isOpen = true;
            positionDropdown();
            dropdown.style.display = '';
            trigger.setAttribute('aria-expanded', 'true');
            trigger.classList.add('pf-product-trigger--open');
            searchInput.value = '';
            searchInput.focus();
            doSearch('');
        }

        function closeDropdown() {
            if (!isOpen) return;
            isOpen = false;
            dropdown.style.display = 'none';
            trigger.setAttribute('aria-expanded', 'false');
            trigger.classList.remove('pf-product-trigger--open');
        }

        // ── Render results ────────────────────────────────────────
        var searchSeq = 0; // prevent stale responses from overwriting newer ones

        function renderResults(results) {
            resultsDiv.innerHTML = '';
            if (!results || results.length === 0) {
                var empty = document.createElement('div');
                empty.className = 'pf-product-result-empty';
                empty.textContent = 'محصولی پیدا نشد';
                resultsDiv.appendChild(empty);
                return;
            }
            results.forEach(function (p) {
                var label = (p.internal_code ? p.internal_code + ' — ' : '') + p.name;
                var item  = document.createElement('div');
                item.className = 'pf-product-result-item';
                item.textContent = label;
                item.setAttribute('role', 'option');
                item.addEventListener('mousedown', function (e) {
                    e.preventDefault(); // keep focus on searchInput, prevent blur
                    // Ensure the option exists in the hidden select
                    var opt = selectEl.querySelector('option[value="' + p.id + '"]');
                    if (!opt) {
                        opt = document.createElement('option');
                        opt.value = p.id;
                        opt.text  = label;
                        selectEl.appendChild(opt);
                    }
                    selectEl.value = p.id;
                    // Update trigger display
                    triggerText.textContent = label;
                    trigger.classList.remove('pf-product-trigger--empty');
                    trigger.classList.add('pf-product-trigger--has-value');
                    closeDropdown();
                    // Fire change event → fetchProductUnit fills unit + price
                    selectEl.dispatchEvent(new Event('change', { bubbles: true }));
                });
                resultsDiv.appendChild(item);
            });
        }

        // ── API search ────────────────────────────────────────────
        var searchTimer = null;

        function doSearch(term) {
            searchSeq++;
            var thisSeq = searchSeq;

            var url = API_PRODUCTS + '?page_size=20&ordering=internal_code%2Cname';
            if (term) { url += '&search=' + encodeURIComponent(term); }

            resultsDiv.innerHTML = '';
            var loading = document.createElement('div');
            loading.className = 'pf-product-result-loading';
            loading.textContent = 'در حال جستجو...';
            resultsDiv.appendChild(loading);

            fetch(url, { credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) {
                    if (thisSeq !== searchSeq) return; // stale response
                    if (!data) {
                        resultsDiv.innerHTML =
                            '<div class="pf-product-result-error">خطا در دریافت محصولات</div>';
                        return;
                    }
                    renderResults(data.results || []);
                })
                .catch(function () {
                    if (thisSeq !== searchSeq) return;
                    resultsDiv.innerHTML =
                        '<div class="pf-product-result-error">خطا در دریافت محصولات</div>';
                });
        }

        // ── Event listeners ───────────────────────────────────────

        trigger.addEventListener('click', function () {
            if (trigger.classList.contains('pf-product-trigger--locked')) return;
            if (isOpen) { closeDropdown(); } else { openDropdown(); }
        });

        trigger.addEventListener('keydown', function (e) {
            if (trigger.classList.contains('pf-product-trigger--locked')) return;
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (isOpen) { closeDropdown(); } else { openDropdown(); }
            }
            if (e.key === 'Escape') { closeDropdown(); }
        });

        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function () {
                doSearch(searchInput.value.trim());
            }, 300);
        });

        searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { closeDropdown(); trigger.focus(); }
        });

        searchInput.addEventListener('blur', function () {
            // Small delay: lets mousedown on a result item fire first.
            // If mousedown ran, isOpen is already false → no double-close.
            setTimeout(function () {
                if (isOpen) closeDropdown();
            }, 150);
        });

        // Close when clicking outside both trigger and dropdown
        document.addEventListener('click', function (e) {
            if (isOpen &&
                !trigger.contains(e.target) &&
                !dropdown.contains(e.target)) {
                closeDropdown();
            }
        });
    }

    // ── Remove row ───────────────────────────────────────────────

    function removeRow(row) {
        var deleteInput = row.querySelector('input[name$="-DELETE"]');
        if (deleteInput) {
            // Existing saved row: mark for deletion, grey out visually
            deleteInput.checked = true;
            row.classList.add('pf-item-deleted');
        } else {
            // New (unsaved) row: hide and clear all fields so Django treats it as empty.
            // Do NOT decrement TOTAL_FORM_COUNT — Django skips empty extra forms.
            row.querySelectorAll('input, select, textarea').forEach(function (el) {
                el.value = '';
                if (el.type === 'checkbox') el.checked = false;
            });
            row.style.display = 'none';
        }
        updateItemCount();
        updateGrandTotal();
    }

    // ── Bind events to a single row ──────────────────────────────

    function bindRowEvents(row) {
        // Quantity change → if auto mode, update placeholder + grand total
        var qtyInp = row.querySelector('input[name$="-quantity"]');
        if (qtyInp) {
            qtyInp.addEventListener('input', function () {
                if (!rowIsManual(row)) updateRowTotal(row);
                updateGrandTotal();
            });
        }

        // Unit price change → if auto mode, update placeholder + grand total
        var priceInp = row.querySelector('input[name$="-unit_price"]');
        if (priceInp) {
            priceInp.addEventListener('input', function () {
                if (!rowIsManual(row)) updateRowTotal(row);
                updateGrandTotal();
            });
        }

        // Manual total input — typing activates manual mode
        var manualTotalInp = getManualTotalInput(row);
        if (manualTotalInp) {
            manualTotalInp.addEventListener('input', function () {
                var isNowManual = manualTotalInp.value.trim() !== '';
                if (isNowManual) {
                    manualTotalInp.classList.add('pf-manual-active');
                } else {
                    manualTotalInp.classList.remove('pf-manual-active');
                }
                updateRowTotal(row);
                updateGrandTotal();
            });

            // On blur: if cleared, return to auto mode
            manualTotalInp.addEventListener('blur', function () {
                if (manualTotalInp.value.trim() === '') {
                    manualTotalInp.classList.remove('pf-manual-active');
                    updateRowTotal(row);
                    updateGrandTotal();
                }
            });
        }

        // Reset button — clears manual override, returns to auto mode
        var resetBtn = row.querySelector('.pf-row-total-reset');
        if (resetBtn) {
            resetBtn.addEventListener('click', function () {
                resetRowToAuto(row);
            });
        }

        // Product change → fetch unit display + price autofill
        var productSel = row.querySelector('select[name$="-product"]');
        if (productSel) {
            productSel.addEventListener('change', function () {
                fetchProductUnit(productSel.value, row);
            });
            initProductSelector(productSel);
        }

        // Remove button
        var removeBtn = row.querySelector('.pf-remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function () {
                removeRow(row);
            });
        }
    }

    // ── Add new row ──────────────────────────────────────────────

    function addRow() {
        var tplContainer = document.getElementById('pf-empty-form-container');
        if (!tplContainer) return;

        var newIndex = getTotalFormCount();
        var html = tplContainer.innerHTML.replace(/__prefix__/g, String(newIndex));
        setTotalFormCount(newIndex + 1);

        var tbody = document.getElementById('pf-items-tbody');
        if (!tbody) return;

        var placeholder = tbody.querySelector('.pf-no-items-row');
        if (placeholder) placeholder.remove();

        tbody.insertAdjacentHTML('beforeend', html);
        var newRow = tbody.lastElementChild;
        if (newRow) {
            bindRowEvents(newRow);
            updateRowTotal(newRow);
            // Open the product selector in the new row so the user can start
            // picking a product immediately
            var trigger = newRow.querySelector('.pf-product-trigger');
            if (trigger) {
                setTimeout(function () { trigger.click(); }, 60);
            }
        }

        updateItemCount();
        updateGrandTotal();

        var emptyMsg = document.getElementById('pf-items-empty');
        if (emptyMsg) emptyMsg.style.display = 'none';
    }

    // ── Lock item inputs for CONFIRMED/CANCELLED purchases ───────

    function lockItemInputs() {
        var section = document.getElementById('pf-items-section');
        if (!section || !section.classList.contains('pf-items-locked')) return;
        section.querySelectorAll('input, select, textarea').forEach(function (el) {
            el.disabled = true;
        });
        // Lock the custom product selector triggers so they cannot be clicked
        section.querySelectorAll('.pf-product-trigger').forEach(function (el) {
            el.classList.add('pf-product-trigger--locked');
            el.removeAttribute('tabindex');
        });
        // Hide reset buttons (cannot change totals on locked purchases)
        section.querySelectorAll('.pf-row-total-reset').forEach(function (el) {
            el.style.display = 'none';
            el.disabled = true;
        });
    }

    // ── Init ─────────────────────────────────────────────────────

    function init() {
        var rows = document.querySelectorAll('#pf-items-tbody .pf-item-row');
        rows.forEach(function (row) {
            bindRowEvents(row);
            // Initialize manual_total active class for rows that already have a value
            var manualInp = getManualTotalInput(row);
            if (manualInp && manualInp.value.trim() !== '') {
                manualInp.classList.add('pf-manual-active');
            }
            updateRowTotal(row);
        });

        updateItemCount();
        updateGrandTotal();
        lockItemInputs();

        var addBtn = document.getElementById('pf-add-item-btn');
        if (addBtn) {
            addBtn.addEventListener('click', addRow);
        }
    }

    return { init: init };
}());

document.addEventListener('DOMContentLoaded', PurchaseFormApp.init);
