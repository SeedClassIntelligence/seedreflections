// Checks the Workspace home in a real browser. Usage: node run.js <populatedBase> <emptyBase> <pendingFindings>
const { chromium } = require('playwright');
const [populated, empty, pendingArg] = process.argv.slice(2); const pending = Number(pendingArg);
const waitingPhrase = pending === 1 ? '1 finding is waiting for your decision' : `${pending} findings are waiting for your decision`;
const out = []; const check = (name, ok, detail) => out.push({ name, ok: !!ok, detail: ok ? undefined : String(detail) });
(async () => {
  const browser = await chromium.launch();
  const open = async (base, size) => {
    const page = await browser.newPage({ viewport: size }); const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/consumer-dashboard.html'); await page.waitForTimeout(1800);
    await page.evaluate(() => switchDashTab('workspace')); await page.waitForTimeout(1500);
    return { page, errors };
  };
  for (const [label, size] of [['desktop', { width: 1440, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
    const { page, errors } = await open(populated, size);
    const text = (await page.innerText('.wh')).replace(/\s+/g, ' ');
    check(`${label}: says exactly what is waiting for a decision`, text.includes(waitingPhrase), waitingPhrase + ' / ' + text.slice(0, 200));
    check(`${label}: offers ideas to pick up, with Continue`, (await page.locator('.wh-card .btn-primary').count()) >= 1);
    check(`${label}: lists recent work`, /Beta launch plan/.test(text));
    check(`${label}: offers ways to start something`, /From a finding/.test(text) && /From a blank page/.test(text));
    check(`${label}: no horizontal overflow`, !(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
    check(`${label}: no stock next-action sentence`, !/Review the source context/.test(text), text);
    const small = await page.evaluate(() => [...document.querySelectorAll('.wh *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 12).length);
    check(`${label}: no text under 12px`, small === 0, small);
    if (label === 'desktop') {
      await page.click('.wh-card .btn-primary'); await page.waitForTimeout(1500);
      check('Continue opens the idea and hides the home', !(await page.isVisible('.wh')) && (await page.isVisible('.work-context')));
      await page.evaluate(() => clearActiveSeedFocus()); await page.waitForTimeout(1500);
      check('clearing the focus brings the home back', await page.isVisible('.wh'));
    }
    check(`${label}: no script errors`, errors.length === 0, errors.join(' | '));
    await page.close();
  }
  const { page, errors } = await open(empty, { width: 1440, height: 900 });
  const first = (await page.innerText('.wh')).replace(/\s+/g, ' ');
  check('first run: invites the person to bring in their history', /Start by bringing in your history/.test(first) && (await page.locator('.wh-first .btn-primary').count()) === 1, first);
  check('first run: no script errors', errors.length === 0, errors.join(' | '));
  await browser.close(); console.log(JSON.stringify(out)); process.exit(out.every(r => r.ok) ? 0 : 1);
})().catch(e => { console.log(JSON.stringify([{ name: 'runner crashed', ok: false, detail: String(e) }])); process.exit(1); });
