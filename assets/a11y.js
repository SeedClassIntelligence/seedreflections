/* Keyboard access for controls built as clickable <div>/<span>.
   - Anything with an inline onclick that is not natively interactive becomes focusable
     (tabindex=0), gets a role, and responds to Enter and Space.
   - Single-choice groups (plan pickers, wizard cards) become role="radio" inside a
     role="radiogroup", with aria-checked kept in step with the .selected/.active class.
   Modal backdrops (.modal-overlay) are left alone: they dismiss on click. Dialog semantics, focus and Escape live in dialogs.js. */
(function () {
  'use strict';
  var NATIVE = /^(BUTTON|A|INPUT|SELECT|TEXTAREA|SUMMARY|LABEL|OPTION)$/;
  var CHOICE = '.plan-opt, .plan-tier-card, .wiz-card, .snippet-select-card';
  var ON = /(^|\s)(selected|active)(\s|$)/;

  function groupName(group) {
    var scope = group.closest('.form-section, .plan-select, .card-body, section') || group;
    var t = scope.querySelector('.plan-select-title, .form-section-title, h2, h3, h4');
    return t ? t.textContent.trim() : '';
  }

  function sync(el) { el.setAttribute('aria-checked', ON.test(el.className) ? 'true' : 'false'); }

  function upgrade(el) {
    if (el.__a11y || NATIVE.test(el.tagName) || el.classList.contains('modal-overlay')) return;
    if (!el.hasAttribute('onclick')) return;
    el.__a11y = true;
    var choice = el.matches(CHOICE);
    if (!el.hasAttribute('role')) el.setAttribute('role', choice ? 'radio' : 'button');
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
    if (choice) {
      sync(el);
      new MutationObserver(function () { sync(el); }).observe(el, { attributes: true, attributeFilter: ['class'] });
      var g = el.parentElement;
      if (g && !g.hasAttribute('role')) {
        g.setAttribute('role', 'radiogroup');
        var n = groupName(g);
        if (n && !g.hasAttribute('aria-label')) g.setAttribute('aria-label', n);
      }
    }
    el.addEventListener('keydown', function (e) {
      if (e.target !== el) return;
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); el.click(); }
    });
  }

  function scan(root) {
    if (root.nodeType !== 1) return;
    if (root.hasAttribute && root.hasAttribute('onclick')) upgrade(root);
    var all = root.querySelectorAll ? root.querySelectorAll('[onclick]') : [];
    for (var i = 0; i < all.length; i++) upgrade(all[i]);
  }

  var style = document.createElement('style');
  style.textContent = '[role="button"][tabindex]:focus-visible,[role="radio"][tabindex]:focus-visible{outline:3px solid #3fb950;outline-offset:2px}';
  document.head.appendChild(style);

  function start() {
    scan(document.body);
    new MutationObserver(function (list) {
      list.forEach(function (m) { m.addedNodes.forEach(scan); });
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
})();
