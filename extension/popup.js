(function () {
  var S = globalThis.__seedSend;
  var $ = function (id) { return document.getElementById(id); };
  var captured = null;

  function setStatus(msg) { $('status').textContent = msg || ''; }
  function setError(msg) { $('error').textContent = msg || ''; }
  function show(id, on) { $(id).hidden = !on; }
  function originPattern(server) { var u = new URL(server); return u.protocol + '//' + u.hostname + '/*'; }
  function store() { return chrome.storage.local; }

  async function load() {
    var saved = await store().get(['server', 'token']);
    var paired = !!(saved.server && saved.token);
    show('pair', !paired); show('capture', paired);
    if (paired) $('paired-to').textContent = 'Connected to ' + saved.server;
  }

  $('pair-form').addEventListener('submit', async function (event) {
    event.preventDefault(); setError(''); setStatus('');
    var token = $('token').value.trim(), server;
    try { server = S.normalizeServer($('server').value); } catch (e) { setError(e.message); return; }
    try {
      var granted = await chrome.permissions.request({ origins: [originPattern(server)] });   // must come straight from the click
      if (!granted) { setError('Chrome permission to reach your SeedReflections address was not granted.'); return; }
      await S.ping(server, token);
      await store().set({ server: server, token: token });
      $('token').value = ''; setStatus('Connected.'); await load();
    } catch (e) { setError(e.message || 'Could not connect.'); }
  });

  $('read').addEventListener('click', async function () {
    setError(''); setStatus(''); show('preview', false); show('diag-box', false); captured = null;
    try {
      var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      var tab = tabs[0]; if (!tab) throw new Error('No active tab.');
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['lib/extract.js'] });
      var run = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: function () { return globalThis.__seedExtract.extract(document, location); } });
      var result = run && run[0] && run[0].result;
      if (!result || !result.ok) { setError((result && result.message) || 'This page could not be read.'); if (result && result.platform) show('diag-box', true); return; }
      captured = result;
      $('p-title').textContent = result.title;
      $('p-meta').textContent = result.messages.length + ' messages from ' + result.platform;
      $('p-first').textContent = result.messages[0].text.slice(0, 200);
      $('p-notice').textContent = result.notice;
      show('preview', true);
    } catch (e) { setError('This page could not be read. Open a supported conversation (ChatGPT, Claude or Gemini) and try again.'); }
  });

  $('diag').addEventListener('click', async function () {
    try {
      var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      var run = await chrome.scripting.executeScript({ target: { tabId: tabs[0].id }, func: function () { return globalThis.__seedExtract.diagnose(document, location); } });
      await navigator.clipboard.writeText(run[0].result); setStatus('Copied. Paste it into your message.');
    } catch (e) { setError('Could not copy the report.'); }
  });

  $('send').addEventListener('click', async function () {
    if (!captured) return;
    var button = $('send'); button.disabled = true; setError(''); setStatus('Saving…');
    try {
      var saved = await store().get(['server', 'token']);
      var result = await S.send(saved.server, saved.token, captured);
      setStatus('Saved ' + (result.message_count || captured.messages.length) + ' messages. Open SeedReflections to review them.');
      show('preview', false); captured = null;
    } catch (e) { setStatus(''); setError(e.message || 'Could not save.'); }
    button.disabled = false;
  });

  $('disconnect').addEventListener('click', async function () {
    var saved = await store().get(['server']);
    await store().remove(['server', 'token']);
    try { if (saved.server) await chrome.permissions.remove({ origins: [originPattern(saved.server)] }); } catch (e) {}
    captured = null; show('preview', false); setStatus('Disconnected.'); await load();
  });

  load();
})();
