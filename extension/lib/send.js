/* Turns a captured conversation into the payload SeedReflections already accepts, and sends it
   to the person's own server with their connection token. Used by the popup and by the tests. */
(function () {
  function normalizeServer(value) {
    var url;
    try { url = new URL(String(value || '').trim()); } catch (e) { throw new Error('Enter the full address of your SeedReflections server, for example https://app.example.com'); }
    var local = url.hostname === 'localhost' || url.hostname === '127.0.0.1' || url.hostname === '[::1]';
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) throw new Error('Use an https:// address. Plain http is only allowed for localhost.');
    return url.origin;
  }

  function stableId(captured) {
    // "ext-" keeps a page capture from overwriting a fuller conversation imported from an export file.
    if (captured.sourceId) return 'ext-' + captured.platform + '-' + captured.sourceId;
    var seed = captured.platform + '|' + captured.title + '|' + captured.messages.map(function (m) { return m.text.slice(0, 40); }).join('|');
    var h = 5381; for (var i = 0; i < seed.length; i++) h = ((h << 5) + h + seed.charCodeAt(i)) >>> 0;
    return 'ext-' + captured.platform + '-' + h.toString(16);
  }

  function buildPayload(captured) {
    return {
      conversation: {
        id: stableId(captured), title: captured.title, source_platform: captured.platform, url: captured.url,
        captured_at: new Date().toISOString(),
        messages: captured.messages.map(function (m, i) { return { id: 'm' + (i + 1), role: m.role, content: m.text }; })
      }
    };
  }

  async function post(server, token, path, body, fetchImpl) {
    var response = await (fetchImpl || fetch)(normalizeServer(server) + path, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token }, body: JSON.stringify(body || {})
    });
    var data = {}; try { data = await response.json(); } catch (e) {}
    if (response.status === 401) throw new Error('The connection token was not accepted. Create a new one in SeedReflections settings.');
    if (!response.ok) throw new Error(data.error || 'The server answered with an error (' + response.status + ').');
    return data;
  }

  var api = {
    normalizeServer: normalizeServer, buildPayload: buildPayload,
    ping: function (s, t, f) { return post(s, t, '/api/v2/integrations/ping', {}, f); },
    send: function (s, t, captured, f) { return post(s, t, '/api/v2/integrations/import', buildPayload(captured), f); }
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof globalThis !== 'undefined') globalThis.__seedSend = api;
})();
