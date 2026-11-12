/* Dialog semantics for the app's existing modals (dashboard .modal-overlay, admin [data-dialog]).
   It does not open or close anything itself. It watches the overlays the page already
   shows and hides, and when one becomes visible it:
   - gives the panel role="dialog", aria-modal and an accessible name,
   - makes everything behind it inert (no Tab stops, no clicks, hidden from screen readers),
   - moves focus into the dialog, and returns it to the opener on close,
   - closes on Escape through the page's own close function or close button. */
(function () {
  'use strict';
  var FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  var opened = [];          // overlays currently shown, last = topmost
  var openers = new Map();  // overlay -> element that had focus before it opened
  var inerted = [];
  var uid = 0;

  function panelOf(overlay) {
    return overlay.querySelector(':scope > .modal, :scope > .modal-content') || overlay.firstElementChild || overlay;
  }

  function isShown(el) {
    var cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getClientRects().length > 0;
  }

  function label(overlay) {
    var panel = panelOf(overlay);
    if (panel.getAttribute('role') === 'dialog') return;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    var h = panel.querySelector('h1,h2,h3,h4');
    if (h) {
      if (!h.id) h.id = 'dlg-title-' + (++uid);
      panel.setAttribute('aria-labelledby', h.id);
    } else {
      panel.setAttribute('aria-label', overlay.getAttribute('data-dialog') || 'Dialog');
    }
    if (!panel.hasAttribute('tabindex')) panel.setAttribute('tabindex', '-1');
  }

  function clearInert() {
    inerted.forEach(function (el) { el.inert = false; });
    inerted = [];
  }

  function applyInert(overlay) {
    clearInert();
    for (var node = overlay; node && node !== document.body; node = node.parentElement) {
      var parent = node.parentElement;
      if (!parent) break;
      Array.prototype.forEach.call(parent.children, function (sib) {
        if (sib !== node && !/^(SCRIPT|STYLE|LINK)$/.test(sib.tagName) && !sib.inert) {
          sib.inert = true;
          inerted.push(sib);
        }
      });
    }
  }

  function onOpen(overlay) {
    if (opened.indexOf(overlay) !== -1) return;
    openers.set(overlay, document.activeElement);
    opened.push(overlay);
    label(overlay);
    applyInert(overlay);
    var panel = panelOf(overlay);
    var first = Array.prototype.filter.call(panel.querySelectorAll(FOCUSABLE), function (e) {
      return e.getBoundingClientRect().width > 0;
    })[0];
    (first || panel).focus({ preventScroll: true });
  }

  function onClose(overlay) {
    var i = opened.indexOf(overlay);
    if (i === -1) return;
    opened.splice(i, 1);
    if (opened.length) applyInert(opened[opened.length - 1]); else clearInert();
    var back = openers.get(overlay);
    openers.delete(overlay);
    if (back && document.contains(back) && !back.inert && back.focus) back.focus({ preventScroll: true });
  }

  function check(overlay) {
    if (isShown(overlay)) onOpen(overlay); else onClose(overlay);
  }

  function closeTop() {
    var overlay = opened[opened.length - 1];
    if (!overlay) return;
    if (overlay.id && typeof window.closeModal === 'function' && overlay.classList.contains('modal-overlay')) {
      window.closeModal(overlay.id);
      return;
    }
    var btns = overlay.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      if (/^\s*(cancel|close|done|✕|×)\s*$/i.test(btns[i].textContent) || btns[i].hasAttribute('data-dialog-close')) {
        btns[i].click();
        return;
      }
    }
  }

  document.addEventListener('keydown', function (e) {
    if (!opened.length) return;
    if (e.key === 'Escape') { e.preventDefault(); closeTop(); return; }
    if (e.key !== 'Tab') return;
    var panel = panelOf(opened[opened.length - 1]);
    var stops = Array.prototype.filter.call(panel.querySelectorAll(FOCUSABLE), function (el) {
      return el.getBoundingClientRect().width > 0;
    });
    if (!stops.length) { e.preventDefault(); panel.focus(); return; }
    var first = stops[0], last = stops[stops.length - 1];
    if (!panel.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  function watch(overlay) {
    if (overlay.__dlg) return;
    overlay.__dlg = true;
    label(overlay);
    new MutationObserver(function () { check(overlay); })
      .observe(overlay, { attributes: true, attributeFilter: ['class', 'style', 'hidden'] });
    check(overlay);
  }

  function start() {
    document.querySelectorAll('.modal-overlay, [data-dialog]').forEach(watch);
    new MutationObserver(function (list) {
      list.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (n.nodeType !== 1) return;
          if (n.matches('.modal-overlay, [data-dialog]')) watch(n);
          n.querySelectorAll && n.querySelectorAll('.modal-overlay, [data-dialog]').forEach(watch);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
