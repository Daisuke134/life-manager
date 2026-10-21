const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('node:fs');
const pages = ['index.html','finance.html','mental.html','physical.html','control.html','proof.html'];
for (const name of pages) {
  test(`${name}: real Chromium keyboard/mobile/axe checks`, async ({page}, info) => {
    const response = await page.goto(name);
    expect(response.status()).toBe(200);
    await expect(page.locator('html')).toHaveAttribute('lang','ja');
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('main')).toHaveCount(1);
    await expect(page.locator('[data-outcome]')).toHaveText(/NOT_MEASURED/);
    const results = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();
    expect(results.violations).toEqual([]);
    expect(await page.locator('form,input,script,iframe').count()).toBe(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.keyboard.press('Tab');
    await expect(page.locator(':focus')).toHaveAttribute('href','#main');
    await page.keyboard.press('Enter');
    await expect(page.locator('main')).toBeFocused();
    const links = await page.locator('a[href^="https:"]').evaluateAll(xs=>xs.map(x=>x.href));
    for (const url of links) expect(['www.mhlw.go.jp','kennet.mhlw.go.jp','www.fsa.go.jp','github.com']).toContain(new URL(url).hostname);
    expect(await page.context().cookies()).toEqual([]);
    expect(await page.evaluate(()=>Object.keys(localStorage))).toEqual([]);
    fs.mkdirSync('../../output/service/screenshots',{recursive:true});
    await page.screenshot({path:`../../output/service/screenshots/${info.project.name}-${name}.png`,fullPage:true});
  });
}
test('three journeys reach official information, NOT a completed welfare service', async ({page})=>{
  for (const [domain,caption] of [['finance','生活費・仕事・借入'],['mental','こころの相談'],['physical','健康づくり']]) {
    await page.goto('index.html');
    await page.locator('main').getByRole('link',{name:caption,exact:true}).click();
    await expect(page).toHaveURL(new RegExp(domain+'\\.html$'));
    await expect(page.locator('a[data-official]').first()).toHaveAttribute('href',/^https:\/\/(www\.mhlw\.go\.jp|www\.fsa\.go\.jp|kennet\.mhlw\.go\.jp)\//);
    await expect(page.locator('[data-limit]')).toContainText('申請・診断・治療');
  }
});
test('no hidden experimentation, trackers or third-party requests', async ({page})=>{
  const requests=[];
  page.on('request', req=>requests.push(req.url()));
  await page.goto('mental.html');
  const host = new URL(page.url()).origin;
  expect(requests.every(u=>u.startsWith(host+'/'))).toBe(true);
  await expect(page.locator('[data-experiment]')).toContainText('実施していません');
});
