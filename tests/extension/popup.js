// Loads the real extension in Chromium and checks the popup opens, shows the pairing form, and refuses unsafe addresses.
const { chromium } = require('playwright'); const path = require('path'); const crypto = require('crypto'); const os = require('os'); const fs = require('fs');
(async () => {
  const ext = path.resolve(__dirname, '../../extension');
  const id = [...crypto.createHash('sha256').update(ext).digest('hex').slice(0, 32)].map(c => String.fromCharCode(97 + parseInt(c, 16))).join('');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'seed-ext-'));
  const ctx = await chromium.launchPersistentContext(profile, { channel: 'chromium', headless: true, args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`, '--headless=new'] });
  const page = await ctx.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const out = [];
  const check = (name, ok, detail) => out.push({ name, ok: !!ok, detail: ok ? undefined : String(detail) });
  const response = await page.goto(`chrome-extension://${id}/popup.html`);
  check('popup opens from the real extension', response && response.status() === 200, response && response.status());
  check('unpaired browser sees the pairing form only', await page.isVisible('#pair') && !(await page.isVisible('#capture')));
  await page.fill('#server', 'http://example.com'); await page.fill('#token', 'sr_live_x'); await page.click('#pair-form button');
  await page.waitForTimeout(300);
  check('plain http to a remote server is refused', /https/.test(await page.innerText('#error')), await page.innerText('#error'));
  check('no script errors', errors.length === 0, errors.join(' | '));
  await ctx.close(); console.log(JSON.stringify(out)); process.exit(out.every(r => r.ok) ? 0 : 1);
})().catch(e => { console.log(JSON.stringify([{ name: 'runner crashed', ok: false, detail: String(e) }])); process.exit(1); });
