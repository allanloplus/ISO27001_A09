import { chromium } from 'playwright';
import path from 'path';
const file = 'file://' + path.resolve('presentation/index.html') + '#render';
const times = process.argv.slice(2).map(Number);
const browser = await chromium.launch({ proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.route(/fonts\.(googleapis|gstatic)\.com/, async route => {
  const r = await fetch(route.request().url(), { headers: { 'user-agent': route.request().headers()['user-agent'] } });
  route.fulfill({ status: r.status, headers: { 'content-type': r.headers.get('content-type') || '', 'access-control-allow-origin': '*' }, body: Buffer.from(await r.arrayBuffer()) });
});
page.on('console', m => console.log('console:', m.text()));
page.on('pageerror', e => console.log('pageerror:', e.message));
await page.goto(file);
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(1500);
for (const t of times) {
  await page.evaluate(t => window.renderAt(t), t);
  await page.screenshot({ path: `/tmp/claude-0/-home-user-ISO27001-A09/94d7df90-f3a1-5377-b3ee-d2d64328b182/scratchpad/s_${t}.png` });
}
console.log(await page.evaluate(() => [...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family).filter((v,i,a)=>a.indexOf(v)===i).join(',')));
await browser.close();
