/* Reads the conversation that is open in the current tab. Nothing here runs unless the person
   clicks the extension button: it is injected on demand, never declared as an always-on script.
   It only reads the page text. It does not click, scroll, type or call any network API. */
(function () {
  var SITES = [
    { platform: 'chatgpt', hosts: ['chatgpt.com', 'chat.openai.com'], idPattern: /\/c\/([0-9a-zA-Z-]{8,})/, titleSuffix: /\s*[|\-–]\s*ChatGPT\s*$/i, genericTitle: /^ChatGPT$/i },
    { platform: 'claude', hosts: ['claude.ai'], idPattern: /\/chat\/([0-9a-zA-Z-]{8,})/, titleSuffix: /\s*[|\-–]\s*Claude\s*$/i, genericTitle: /^Claude$/i },
    { platform: 'gemini', hosts: ['gemini.google.com'], idPattern: /\/app\/([0-9a-zA-Z_-]{6,})/, titleSuffix: /\s*[|\-–]\s*Gemini\s*$/i, genericTitle: /^(Google )?Gemini$/i }
  ];

  function siteFor(hostname) {
    for (var i = 0; i < SITES.length; i++) if (SITES[i].hosts.indexOf(hostname) !== -1) return SITES[i];
    return null;
  }

  function clean(text) {
    return String(text || '').replace(/ /g, ' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  }

  function textOf(el) { return clean(el.innerText !== undefined ? el.innerText : el.textContent); }

  // Each reader returns [{role, text}] in page order.
  var READERS = {
    chatgpt: function (doc) {
      var out = [];
      doc.querySelectorAll('[data-message-author-role]').forEach(function (el) {
        var role = el.getAttribute('data-message-author-role');
        if (role === 'user' || role === 'assistant') out.push({ role: role, text: textOf(el) });
      });
      return out;
    },
    claude: function (doc) {
      var out = [];
      var user = '[data-testid="user-message"]';
      var assistant = '.font-claude-response, .font-claude-message, [data-testid="assistant-message"]';
      doc.querySelectorAll(user + ', ' + assistant).forEach(function (el) {
        if (el.parentElement && el.parentElement.closest(assistant)) return;          // skip nested matches
        out.push({ role: el.matches(user) ? 'user' : 'assistant', text: textOf(el) });
      });
      return out;
    },
    gemini: function (doc) {
      var out = [];
      doc.querySelectorAll('user-query, model-response').forEach(function (el) {
        var isUser = el.tagName.toLowerCase() === 'user-query';
        var body = isUser ? (el.querySelector('.query-text') || el) : (el.querySelector('message-content, .model-response-text') || el);
        out.push({ role: isUser ? 'user' : 'assistant', text: textOf(body) });
      });
      return out;
    }
  };

  function extract(doc, loc) {
    var site = siteFor(loc.hostname);
    if (!site) return { ok: false, reason: 'unsupported_site', message: 'This page is not a supported conversation page. Use the export from that service instead.' };
    var found = READERS[site.platform](doc).filter(function (m) { return m.text; });
    if (!found.length) {
      return { ok: false, reason: 'no_messages', platform: site.platform,
        message: 'No messages were found on this page. Open a conversation first. If one is open, the site may have changed its layout; use that service’s export instead.' };
    }
    var idMatch = loc.pathname.match(site.idPattern);
    var title = clean(doc.title || '').replace(site.titleSuffix, '');
    if (!title || site.genericTitle.test(title)) title = found[0].text.replace(/\s+/g, ' ').slice(0, 80);
    return {
      ok: true, platform: site.platform, title: title,
      sourceId: idMatch ? idMatch[1] : null, url: loc.origin + loc.pathname,
      messages: found,
      notice: 'Only the messages loaded on this page are included. Scroll up to load older ones before saving.'
    };
  }

  // A report of the page's structure for fixing a reader when a site changes. It lists tag names, attribute
  // names and counts only. It never includes any message text, titles or addresses beyond the host.
  function diagnose(doc, loc) {
    function tally(list, limit) {
      var counts = {}; list.forEach(function (k) { counts[k] = (counts[k] || 0) + 1; });
      return Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).slice(0, limit)
        .map(function (k) { return k + ' x' + counts[k]; });
    }
    var all = Array.prototype.slice.call(doc.querySelectorAll('*'));
    var probes = ['[data-message-author-role]', '[data-testid="user-message"]', '.font-claude-response', '.font-claude-message',
      '[data-testid="assistant-message"]', 'user-query', 'model-response', 'message-content'];
    var report = {
      host: loc.hostname, supported: !!siteFor(loc.hostname),
      readerProbes: probes.map(function (q) { return q + ' => ' + doc.querySelectorAll(q).length; }),
      customElements: tally(all.map(function (e) { return e.tagName.toLowerCase(); }).filter(function (t) { return t.indexOf('-') !== -1; }), 25),
      dataTestIds: tally(all.map(function (e) { return e.getAttribute('data-testid'); }).filter(Boolean), 30),
      authorRoles: tally(all.map(function (e) { return e.getAttribute('data-message-author-role'); }).filter(Boolean), 10),
      fontClasses: tally(all.reduce(function (a, e) { (e.className && e.className.split ? e.className.split(/\s+/) : []).forEach(function (c) { if (/^font-/.test(c)) a.push(c); }); return a; }, []), 15)
    };
    return JSON.stringify(report, null, 2);
  }

  var api = { extract: extract, siteFor: siteFor, diagnose: diagnose };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof globalThis !== 'undefined') globalThis.__seedExtract = api;
})();
