// Checks the idea view in a real browser. Usage: node run.js <base> <expectedJsonFile>
const { chromium } = require('playwright'); const fs = require('fs');
const [base, file] = process.argv.slice(2); const expected = JSON.parse(fs.readFileSync(file, 'utf8'));   // {title: {source: "...", outputs: ["..."]}}
const out = []; const check = (name, ok, detail) => out.push({ name, ok: !!ok, detail: ok ? undefined : String(detail) });
(async () => {
  const browser = await chromium.launch();
  for (const [label, size] of [['desktop', { width: 1440, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport: size }); const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/consumer-dashboard.html'); await page.waitForTimeout(1800);
    await page.evaluate(() => switchDashTab('workspace')); await page.waitForTimeout(1500);
    const title = (await page.locator('.wh-card .title').first().innerText()).trim();
    const exp = Object.entries(expected).find(([t]) => title.startsWith(t.slice(0, 40)))?.[1];
    check(`${label}: the idea card matches a known idea`, !!exp, title);
    await page.locator('.wh-card .btn-primary').first().click(); await page.waitForTimeout(1500);
    check(`${label}: opening an idea shows its header and tabs`, (await page.isVisible('#idea-header')) && (await page.locator('#idea-header [role=tab]').count()) === 4 && (await page.innerText('#idea-title')).trim().startsWith(title.slice(0, 40)));
    check(`${label}: Work tab is selected and the chat is available`, (await page.getAttribute('#idea-tab-work', 'aria-selected')) === 'true' && (await page.isVisible('#chat-input')));
    await page.click('#idea-tab-sources'); await page.waitForSelector('#idea-panel .src-msg.hit', { timeout: 8000 });
    const hit = (await page.innerText('#idea-panel .src-msg.hit')).replace(/\s+/g, ' ');
    check(`${label}: Sources shows the exact passage the idea came from, highlighted`, exp && hit.includes(exp.source), hit + ' | wanted: ' + (exp && exp.source));
    check(`${label}: Sources hides the chat`, !(await page.isVisible('#chat-input')));
    await page.click('#idea-tab-outputs'); await page.waitForTimeout(400);
    const outputs = (await page.innerText('#idea-panel')).replace(/\s+/g, ' ');
    check(`${label}: Outputs lists the work made for this idea`, (exp.outputs || []).every(t => outputs.includes(t)) && /Plan/.test(outputs) && /Note/.test(outputs), outputs);
    check(`${label}: Outputs count matches`, (await page.innerText('#idea-n-outputs')).trim() === String((exp.outputs || []).length), await page.innerText('#idea-n-outputs'));
    await page.click('#idea-tab-decisions'); await page.waitForTimeout(300);
    await page.click('#idea-panel button:has-text("Record a decision")'); await page.waitForTimeout(400);
    check(`${label}: "Record a decision" returns to Work with the prompt ready`, (await page.getAttribute('#idea-tab-work', 'aria-selected')) === 'true' && (await page.inputValue('#chat-input')).startsWith('Record a decision'));
    check(`${label}: no horizontal overflow`, !(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
    const tiny = await page.evaluate(() => [...document.querySelectorAll('#idea-header *, #idea-panel *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 12).length);
    check(`${label}: no text under 12px`, tiny === 0, tiny);
    if (label === 'desktop') {
      await page.click('#idea-header button:has-text("Workspace home")'); await page.waitForTimeout(1200);
      check('Workspace home brings the home back and hides the header', (await page.isVisible('.wh')) && !(await page.isVisible('#idea-header')));
    }
    check(`${label}: no script errors`, errors.length === 0, errors.join(' | '));
    await page.close();
  }
  await browser.close(); console.log(JSON.stringify(out)); process.exit(out.every(r => r.ok) ? 0 : 1);
})().catch(e => { console.log(JSON.stringify([{ name: 'runner crashed', ok: false, detail: String(e) }])); process.exit(1); });
