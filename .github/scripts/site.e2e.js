// Browser tests for the page's interactive parts: the mobile menu and phone
// layout. Run from the repo root with Playwright available:
//   node .github/scripts/site.e2e.js
// It serves the repo itself, so nothing else needs to be running.
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const TYPES = { '.html': 'text/html', '.png': 'image/png', '.jpg': 'image/jpeg', '.mp4': 'video/mp4', '.txt': 'text/plain', '.ico': 'image/x-icon' };

function serve() {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      let p = decodeURIComponent(req.url.split('?')[0]);
      if (p.endsWith('/')) p += 'index.html';
      const file = path.join(ROOT, p);
      if (!file.startsWith(ROOT) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    }).listen(0, () => resolve(srv));
  });
}

(async () => {
  const srv = await serve();
  const U = `http://localhost:${srv.address().port}/`;
  const browser = await chromium.launch();
  let fails = 0;
  const t = async (name, fn) => { try { await fn(); console.log('PASS', name); } catch (e) { fails++; console.log('FAIL', name, '\n  ', e.message); } };
  const open = async (w, opts = {}) => {
    const ctx = await browser.newContext({ viewport: { width: w, height: 800 }, ...opts });
    // Third-party scripts are irrelevant here and may be unreachable.
    await ctx.route(/^(?!http:\/\/localhost)/, r => r.abort());
    const p = await ctx.newPage();
    await p.goto(U, { waitUntil: 'load' });
    return p;
  };
  const expanded = p => p.locator('.nav-toggle').getAttribute('aria-expanded');
  const focused = p => p.evaluate(() => { const e = document.activeElement; return e.className + '|' + (e.textContent || '').trim(); });
  const linksShown = p => p.locator('#site-menu a').first().isVisible();

  let p = await open(375);
  await t('phone: Menu shown, links hidden, collapsed', async () => {
    assert(await p.locator('.nav-toggle').isVisible());
    assert(!(await linksShown(p)));
    assert.strictEqual(await expanded(p), 'false');
    assert.strictEqual(await p.locator('.nav-toggle').getAttribute('aria-controls'), 'site-menu');
    assert.strictEqual((await p.locator('.nav-toggle').textContent()).trim(), 'Menu');
  });
  await t('click opens and focuses the first link', async () => {
    await p.click('.nav-toggle');
    assert.strictEqual(await expanded(p), 'true');
    assert(await linksShown(p));
    assert.match(await focused(p), /\|Examples$/);
  });
  await t('Escape closes and returns focus to Menu', async () => {
    await p.keyboard.press('Escape');
    assert.strictEqual(await expanded(p), 'false');
    assert(!(await linksShown(p)));
    assert.match(await focused(p), /nav-toggle/);
  });
  await t('Enter opens and Tab walks every link in order', async () => {
    await p.keyboard.press('Enter');
    const seen = [await focused(p)];
    for (let i = 0; i < 5; i++) { await p.keyboard.press('Tab'); seen.push(await focused(p)); }
    assert.deepStrictEqual(seen.map(s => s.split('|')[1]), ['Examples', 'How it works', 'Why now', 'Pricing', 'FAQ', 'Docs']);
  });
  await t('tabbing within the header keeps it open, leaving closes it', async () => {
    await p.keyboard.press('Tab');
    assert.match(await focused(p), /Get started/);
    assert.strictEqual(await expanded(p), 'true');
    await p.keyboard.press('Tab');
    await p.keyboard.press('Tab');
    assert.strictEqual(await expanded(p), 'false');
  });
  await t('choosing a link closes the menu and navigates', async () => {
    await p.click('.nav-toggle');
    await p.click('#site-menu a[href="#pricing"]');
    assert.strictEqual(await expanded(p), 'false');
    assert(p.url().endsWith('#pricing'));
  });
  await t('clicking outside closes', async () => {
    await p.click('.nav-toggle');
    await p.mouse.click(180, 600);
    assert.strictEqual(await expanded(p), 'false');
  });
  await t('growing to desktop while open resets the menu', async () => {
    await p.click('.nav-toggle');
    await p.setViewportSize({ width: 1280, height: 800 });
    await p.waitForTimeout(100);
    assert.strictEqual(await expanded(p), 'false');
    assert(!(await p.locator('.nav-toggle').isVisible()));
    assert(await linksShown(p));
  });
  await p.close();

  for (const w of [320, 360, 375, 414, 600, 768, 960]) {
    p = await open(w);
    await t(`${w}px: no sideways scroll, header fits, menu fits with 44px targets`, async () => {
      assert.strictEqual(await p.evaluate(() => document.documentElement.scrollWidth), w);
      await p.click('.nav-toggle');
      const boxes = await p.evaluate(() => [...document.querySelectorAll('#site-menu a')].map(a => { const r = a.getBoundingClientRect(); return [r.left, r.right, r.height]; }));
      for (const [l, r, h] of boxes) { assert(l >= 0 && r <= w, `link at ${l}..${r}`); assert(h >= 44, `link height ${h}`); }
      assert.strictEqual(await p.evaluate(() => document.documentElement.scrollWidth), w);
    });
    await p.close();
  }

  p = await open(1280);
  await t('desktop: links inline, no Menu button', async () => {
    assert(await linksShown(p));
    assert(!(await p.locator('.nav-toggle').isVisible()));
  });
  await p.close();

  p = await open(375, { javaScriptEnabled: false });
  await t('without JavaScript: no dead Menu button, footer carries the links', async () => {
    assert(!(await p.locator('.nav-toggle').isVisible()));
    for (const h of ['#examples', '#how', '#why-now', '#pricing', '#faq']) assert(await p.locator(`footer a[href="${h}"]`).count() > 0, h);
  });
  await p.close();

  await browser.close();
  srv.close();
  console.log(fails ? `\n${fails} failed` : '\nall passed');
  process.exit(fails ? 1 : 0);
})();
