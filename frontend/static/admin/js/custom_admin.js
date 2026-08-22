/* Global Django Admin behaviours — hamburger sidebar, accordion nav. */
(function () {
    'use strict';

    /* ── Mobile hamburger ───────────────────────────────────────── */
    function initSidebarCollapse() {
        var hamburger = document.getElementById('ca-hamburger');
        var sidebar   = document.getElementById('ca-sidebar');
        if (!hamburger || !sidebar) return;

        hamburger.addEventListener('click', function (e) {
            e.stopPropagation();
            sidebar.classList.toggle('ca-open');
        });

        document.addEventListener('click', function (e) {
            if (sidebar.classList.contains('ca-open') &&
                !sidebar.contains(e.target) &&
                e.target !== hamburger) {
                sidebar.classList.remove('ca-open');
            }
        });
    }

    /* ── Sidebar accordion ──────────────────────────────────────── */
    function initSidebarAccordion() {
        var sections = document.querySelectorAll('[data-sidebar-section]');

        /* Step 1: Wire click handlers first — before any open/close state is set.
           Each section's toggle independently toggles its own is-open class. */
        sections.forEach(function (section) {
            var toggle = section.querySelector('.ca-nav-toggle');
            if (!toggle) return;

            toggle.addEventListener('click', function (e) {
                e.preventDefault();
                var nowOpen = section.classList.toggle('is-open');
                toggle.setAttribute('aria-expanded', nowOpen ? 'true' : 'false');

                var key = section.getAttribute('data-sidebar-section');
                if (key) {
                    try {
                        localStorage.setItem('sidebar-' + key, nowOpen ? '1' : '0');
                    } catch (_) {}
                }
            });
        });

        /* Step 2: Find the single globally best-matching active link.
           Uses the longest href that the current path starts with. */
        var currentPath = window.location.pathname;
        var bestMatch   = null;

        document.querySelectorAll('.ca-nav-submenu .ca-nav-link').forEach(function (link) {
            var href = link.getAttribute('href') || '';
            if (href && currentPath.startsWith(href)) {
                if (!bestMatch || href.length > bestMatch.href.length) {
                    bestMatch = { link: link, href: href };
                }
            }
        });

        /* Step 3: Mark the active link and open its parent section. */
        var activeSection = null;
        if (bestMatch) {
            bestMatch.link.classList.add('is-active');
            activeSection = bestMatch.link.closest('[data-sidebar-section]');
            if (activeSection) {
                activeSection.classList.add('is-open');
            }
        }

        /* Step 4: Restore manually-opened sections from localStorage
           (only for sections that are NOT the active section). */
        sections.forEach(function (section) {
            if (section === activeSection) return;
            var key = section.getAttribute('data-sidebar-section');
            if (!key) return;
            var saved = null;
            try { saved = localStorage.getItem('sidebar-' + key); } catch (_) {}
            if (saved === '1') {
                section.classList.add('is-open');
            }
        });

        /* Step 5: Sync all aria-expanded attributes with final visual state. */
        sections.forEach(function (section) {
            var toggle = section.querySelector('.ca-nav-toggle');
            if (toggle) {
                toggle.setAttribute(
                    'aria-expanded',
                    section.classList.contains('is-open') ? 'true' : 'false'
                );
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initSidebarCollapse();
        initSidebarAccordion();
    });
}());
