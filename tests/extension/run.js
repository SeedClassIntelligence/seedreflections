// Checks the extension's reader, payload and delivery. Usage: node run.js <serverBase> <token>
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const fixtures = require('./fixtures');
const extractSrc = fs.readFileSync(path.join(__dirname, '../../extension/lib/extract.js'), 'utf8');
const sendSrc = fs.readFileSync(path.join(__dirname, '../../extension/lib/send.js'), 'utf8');
const [server, token] = process.argv.slice(2);
const results = []; const check = (name, ok, detail) => results.push({ name, ok: !!ok, detail: ok ? undefined : detail });

(async () => {
  const browser = await chromium.launch(); const page = await browser.newPage();
  await page.setContent('<html><body></body></html>');
  await page.addScriptTag({ content: extractSrc });
  const read = async (key) => page.evaluate((f) => {
    document.title = f.title; document.body.innerHTML = f.html;
    return globalThis.__seedExtract.extract(document, { hostname: f.host, pathname: f.path, origin: 'https://' + f.host });
  }, fixtures[key]);

  const gpt = await read('chatgpt');
  check('chatgpt reads user and assistant only, in order', gpt.ok && gpt.messages.map(m => m.role).join() === 'user,assistant,user', JSON.stringify(gpt));
  check('chatgpt keeps paragraphs, drops tool output', gpt.messages[1].text.includes('Start at $19') && gpt.messages[1].text.includes('free tier') && !JSON.stringify(gpt).includes('hidden tool'), JSON.stringify(gpt.messages));
  check('chatgpt title and id', gpt.title === 'Pricing plan' && gpt.sourceId === '6a1b2c3d-1111-2222-3333-444455556666', JSON.stringify([gpt.title, gpt.sourceId]));

  const cl = await read('claude');
  check('claude reads 3 messages without double-counting nested blocks', cl.ok && cl.messages.length === 3 && cl.messages.map(m => m.role).join() === 'user,assistant,user', JSON.stringify(cl.messages));
  check('claude title and id', cl.title === 'Launch checklist' && cl.sourceId === 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', JSON.stringify([cl.title, cl.sourceId]));

  const gm = await read('gemini');
  check('gemini reads both roles', gm.ok && gm.messages.length === 2 && gm.messages[1].role === 'assistant' && gm.messages[1].text.includes('Tuesday: hosting'), JSON.stringify(gm));
  check('gemini generic title falls back to the first question', gm.title === 'Plan my launch week', gm.title);

  const rep = await page.evaluate((f) => { document.title = f.title; document.body.innerHTML = f.html; return globalThis.__seedExtract.diagnose(document, { hostname: f.host }); }, fixtures.chatgpt);
  check('layout report lists structure but none of the message text or title', rep.includes('data-message-author-role') && !/Start at|beta pricing|Pricing plan|Why three/.test(rep), rep);

  const em = await read('empty'); check('empty page is refused with a reason', !em.ok && em.reason === 'no_messages', JSON.stringify(em));
  const ot = await read('other'); check('unsupported site is refused', !ot.ok && ot.reason === 'unsupported_site', JSON.stringify(ot));

  // Delivery to a real server, through the same code the popup uses.
  const S = (() => { const m = { exports: {} }; new Function('module', 'globalThis', sendSrc)(m, {}); return m.exports; })();
  for (const bad of ['ftp://x.com', 'http://example.com', 'not a url']) {
    let threw = false; try { S.normalizeServer(bad); } catch (e) { threw = true; } check('rejects server address ' + bad, threw);
  }
  check('allows http only for localhost', S.normalizeServer('http://127.0.0.1:8476/x') === 'http://127.0.0.1:8476');
  if (server) {
    const withOrigin = (f) => (url, init) => f(url, { ...init, headers: { ...init.headers, Origin: 'chrome-extension://abcdefghijklmnopabcdefghijklmnop' } });
    const ext = (url, init) => fetch(url, { ...init, headers: { ...init.headers } });
    const ping = await S.ping(server, token, ext).catch(e => ({ error: e.message }));
    check('ping with a valid token', ping.status === 'connected', JSON.stringify(ping));
    const badPing = await S.ping(server, token + 'x', ext).then(() => null, e => e.message);
    check('ping with a wrong token is refused', badPing && /not accepted/.test(badPing), badPing);
    const first = await S.send(server, token, gpt, ext).catch(e => ({ error: e.message }));
    check('first save is imported', first.status === 'imported' && first.message_count === 3, JSON.stringify(first));
    const again = await S.send(server, token, gpt, ext).catch(e => ({ error: e.message }));
    check('saving the same page again does not duplicate', again.status === 'imported' && (again.reconciliation || {}).added === 0, JSON.stringify(again));
    await S.send(server, token, cl, ext); await S.send(server, token, gm, ext);
  }
  await browser.close();
  console.log(JSON.stringify(results));
  process.exit(results.every(r => r.ok) ? 0 : 1);
})().catch(e => { console.log(JSON.stringify([{ name: 'runner crashed', ok: false, detail: String(e) }])); process.exit(1); });
