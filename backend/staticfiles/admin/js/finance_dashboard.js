/**
 * Finance Dashboard — dynamic filtering and chart rendering.
 *
 * Summary cards are pre-populated server-side (no JS needed to see numbers).
 * This script adds:
 *  - Dynamic date/year/month filtering (updates cards via API)
 *  - Chart.js trend chart (uses window.FD_INITIAL_TREND seeded by template)
 *
 * Globals injected by the template:
 *   window.FD_INITIAL_TREND  — Array<{month,income,expense}> for first render
 *   window.FD_API_BALANCE    — URL for /api/v2/finance/reports/balance/
 *   window.FD_API_TREND      — URL for /api/v2/finance/reports/trend/
 *   window.FD_CHARTJS_FAILED — true if Chart.js CDN failed to load
 */

(function () {
  'use strict';

  var LOG_PREFIX = '[Finance Dashboard]';

  // ── Helpers ─────────────────────────────────────────────────────

  function el(id) { return document.getElementById(id); }

  function formatToman(value) {
    // Reuses window.PersianFormat (loaded in base.html via persian_format.js).
    // Same pattern as server-side _fmt_toman(): en-US thousands → swap comma for
    // U+066C (٬) → convert digits to Persian with toPersianDigits().
    var n = parseFloat(String(value).replace(/[,٬]/g, '')) || 0;
    var isNeg = n < 0;
    var enFmt = Math.round(Math.abs(n))
                    .toLocaleString('en-US', { maximumFractionDigits: 0 })
                    .replace(/,/g, '٬');           // U+066C ٬
    var persian = (window.PersianFormat && window.PersianFormat.toPersianDigits)
                  ? window.PersianFormat.toPersianDigits(enFmt)
                  : enFmt;
    return (isNeg ? '-' : '') + persian + ' تومان';
  }

  function getCsrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  // ── Card IDs ─────────────────────────────────────────────────────

  var CARD_MAP = {
    'total_income':             'fd-total-income',
    'total_expense':            'fd-total-expense',
    'final_balance':            'fd-final-balance',
    'total_employee_cost':      'fd-employee-cost',
    'total_equipment_cost':     'fd-equipment-cost',
    'total_medicine_cost':      'fd-medicine-cost',
    'center_commission_income': 'fd-center-commission',
    'university_commission':    'fd-university-commission',
    'anesthesia_cost':          'fd-anesthesia-cost',
    'daily_supplies_cost':      'fd-daily-supplies-cost',
  };

  // ── Chart ─────────────────────────────────────────────────────────

  var trendChart = null;

  function renderChart(rows) {
    var canvas = el('fd-trend-chart');
    var empty  = el('fd-chart-empty');
    if (!canvas) return;

    if (!rows || rows.length === 0) {
      canvas.style.display = 'none';
      if (empty) { empty.style.display = 'block'; }
      if (trendChart) { trendChart.destroy(); trendChart = null; }
      console.log(LOG_PREFIX, 'No trend rows — showing empty state');
      return;
    }

    canvas.style.display = 'block';
    if (empty) { empty.style.display = 'none'; }

    if (window.FD_CHARTJS_FAILED || typeof Chart === 'undefined') {
      console.warn(LOG_PREFIX, 'Chart.js not available — skipping chart render');
      if (empty) {
        empty.textContent = 'نمودار در دسترس نیست — Chart.js بارگذاری نشد';
        empty.style.display = 'block';
        canvas.style.display = 'none';
      }
      return;
    }

    var labels   = rows.map(function (r) { return r.month || ''; });
    var incomes  = rows.map(function (r) { return parseFloat(r.income)  || 0; });
    var expenses = rows.map(function (r) { return parseFloat(r.expense) || 0; });

    var dataset = {
      labels: labels,
      datasets: [
        {
          label: 'درآمد',
          data: incomes,
          borderColor: '#43a047',
          backgroundColor: 'rgba(67,160,71,.12)',
          tension: 0.3,
          fill: true,
          pointRadius: 4,
        },
        {
          label: 'هزینه',
          data: expenses,
          borderColor: '#e53935',
          backgroundColor: 'rgba(229,57,53,.08)',
          tension: 0.3,
          fill: true,
          pointRadius: 4,
        },
      ],
    };

    try {
      if (trendChart) {
        trendChart.data = dataset;
        trendChart.update();
      } else {
        trendChart = new Chart(canvas, {
          type: 'line',
          data: dataset,
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  label: function (ctx) {
                    return ctx.dataset.label + ': ' + formatToman(ctx.parsed.y);
                  },
                },
              },
            },
            scales: {
              y: {
                beginAtZero: true,
                ticks: {
                  callback: function (v) {
                    // Axis labels: abbreviated Persian number (no تومان suffix)
                    var enFmt = Math.round(Math.abs(v))
                                    .toLocaleString('en-US', { maximumFractionDigits: 0 })
                                    .replace(/,/g, '٬');
                    var p = (window.PersianFormat && window.PersianFormat.toPersianDigits)
                            ? window.PersianFormat.toPersianDigits(enFmt) : enFmt;
                    return (v < 0 ? '-' : '') + p;
                  }
                },
              },
              x: { ticks: { maxRotation: 45 } },
            },
          },
        });
      }
      console.log(LOG_PREFIX, 'Chart rendered with', rows.length, 'month(s)');
    } catch (chartErr) {
      console.error(LOG_PREFIX, 'Chart render error:', chartErr);
    }
  }

  // ── API fetch with detailed logging ───────────────────────────────

  function apiFetch(url, params) {
    var full = (params && params.toString()) ? url + '?' + params : url;
    console.log(LOG_PREFIX, 'Fetching', full);
    return fetch(full, {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json', 'X-CSRFToken': getCsrf() },
    }).then(function (resp) {
      console.log(LOG_PREFIX, 'Response', resp.status, 'from', full);
      if (!resp.ok) throw new Error('HTTP ' + resp.status + ' from ' + full);
      return resp.json();
    });
  }

  // ── Fill cards from API response ──────────────────────────────────

  function fillCards(balance) {
    console.log(LOG_PREFIX, 'Filling cards from API:', balance);
    Object.keys(CARD_MAP).forEach(function (key) {
      var cardEl = el(CARD_MAP[key]);
      if (!cardEl) { console.warn(LOG_PREFIX, 'Card element missing:', CARD_MAP[key]); return; }
      var val = balance[key];
      if (val === undefined || val === null) {
        console.warn(LOG_PREFIX, 'API missing key:', key);
        cardEl.textContent = '—';
      } else {
        cardEl.textContent = formatToman(val);
      }
    });

    // Colour balance card
    var balanceCard = el('fd-balance-card');
    if (balanceCard) {
      var bal = parseFloat(String(balance.final_balance || '0').replace(/,/g, '')) || 0;
      balanceCard.classList.toggle('fd-positive', bal >= 0);
      balanceCard.classList.toggle('fd-negative', bal  < 0);
    }
  }

  // ── Dynamic filter refresh via API ────────────────────────────────

  function buildParams() {
    var p = new URLSearchParams();
    var sd = el('fd-start-date'); if (sd && sd.value) p.set('start_date', sd.value);
    var ed = el('fd-end-date');   if (ed && ed.value) p.set('end_date',   ed.value);
    // CLI-70: Gregorian year/month filters removed from the UI; the Jalali
    // date range (start_date/end_date) covers the same need. Backend still
    // accepts year/month params for API back-compat.
    return p;
  }

  function showStatus(msg) {
    var s = el('fd-filter-status');
    if (s) { s.textContent = msg; s.style.display = msg ? 'block' : 'none'; }
  }

  function applyFilters() {
    if (!window.FD_API_BALANCE) {
      console.error(LOG_PREFIX, 'FD_API_BALANCE not defined');
      return;
    }
    var params = buildParams();
    showStatus('در حال به‌روزرسانی…');

    Promise.all([
      apiFetch(window.FD_API_BALANCE, params),
      apiFetch(window.FD_API_TREND,   params),
    ]).then(function (results) {
      fillCards(results[0]);
      renderChart(results[1]);
      showStatus('');
    }).catch(function (err) {
      console.error(LOG_PREFIX, 'Filter fetch error:', err);
      showStatus('خطا در بارگذاری: ' + err.message);
    });
  }

  // ── Wire buttons ──────────────────────────────────────────────────

  function wireButton(id, fn) {
    var btn = el(id);
    if (btn) {
      btn.addEventListener('click', fn);
    } else {
      console.warn(LOG_PREFIX, 'Button not found:', id);
    }
  }

  wireButton('fd-apply-btn', applyFilters);
  wireButton('fd-reset-btn', function () {
    ['fd-start-date', 'fd-end-date'].forEach(function (id) {
      var e = el(id); if (e) e.value = '';
    });
    applyFilters();
  });

  // ── Render initial chart from server-seeded trend data ────────────

  if (window.FD_INITIAL_TREND && window.FD_INITIAL_TREND.length) {
    // Defer chart render so Chart.js finishes loading (it's in the same <extrascript>)
    setTimeout(function () { renderChart(window.FD_INITIAL_TREND); }, 0);
  } else {
    console.log(LOG_PREFIX, 'No initial trend data from server');
  }

  // Re-fetch on bfcache restore
  window.addEventListener('pageshow', function (event) {
    if (event.persisted) {
      console.log(LOG_PREFIX, 'pageshow (persisted) — re-fetching');
      applyFilters();
    }
  });

  console.log(LOG_PREFIX, 'Initialized. Server-side card values are already visible.');

})();
