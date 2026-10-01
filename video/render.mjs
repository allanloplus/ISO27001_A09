// 將 HTML 動畫簡報逐格渲染為 1080p MP4（含旁白）。
// 用法：node video/render.mjs [fps=24] [workers=4]
import { chromium } from 'playwright';
import { spawn, execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const FPS = Number(process.argv[2] || 24);
const WORKERS = Number(process.argv[3] || 4);
const html = 'file://' + path.join(ROOT, 'presentation/index.html') + '#render';
const outDir = path.join(ROOT, 'video');
const final = path.join(outDir, 'ISO27001_應用程式安全_動畫課程.mp4');

async function openPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
  // 字型由 Node 端抓取（沿用系統的 CA 與代理設定），再交給瀏覽器
  await page.route(/fonts\.(googleapis|gstatic)\.com/, async route => {
    const r = await fetch(route.request().url(), { headers: { 'user-agent': route.request().headers()['user-agent'] } });
    await route.fulfill({ status: r.status, headers: { 'content-type': r.headers.get('content-type') || '', 'access-control-allow-origin': '*' }, body: Buffer.from(await r.arrayBuffer()) });
  });
  page.on('pageerror', e => console.error('pageerror:', e.message));
  await page.goto(html);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1500);
  return page;
}

const browser = await chromium.launch();
const probe = await openPage(browser);
const duration = await probe.evaluate(() => window.DECK.duration);
await probe.close();
const total = Math.ceil(duration * FPS);
const per = Math.ceil(total / WORKERS);
console.log(`duration=${duration}s frames=${total} workers=${WORKERS}`);

const t0 = Date.now();
let done = 0;
async function work(w) {
  const from = w * per, to = Math.min(total, from + per);
  const part = path.join(outDir, `seg${w}.part.mp4`);
  const ff = spawn('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '23', '-pix_fmt', 'yuv420p', '-r', String(FPS), part], { stdio: ['pipe', 'inherit', 'inherit'] });
  const page = await openPage(browser);
  for (let f = from; f < to; f++) {
    await page.evaluate(t => window.renderAt(t), f / FPS);
    const buf = await page.screenshot({ type: 'jpeg', quality: 90 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (++done % 500 === 0) console.log(`${done}/${total} frames, ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await page.close();
  return part;
}
const parts = await Promise.all([...Array(WORKERS).keys()].map(work));
await browser.close();

const list = path.join(outDir, 'segments.txt');
fs.writeFileSync(list, parts.map(p => `file '${p}'`).join('\n'));
execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list,
  '-i', path.join(ROOT, 'presentation/narration.mp3'), '-map', '0:v', '-map', '1:a',
  '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest', '-movflags', '+faststart', final]);
parts.forEach(p => fs.unlinkSync(p));
fs.unlinkSync(list);
console.log('done ->', final, `${((Date.now() - t0) / 60000).toFixed(1)} min`);
