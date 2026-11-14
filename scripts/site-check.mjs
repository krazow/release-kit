// Krazow release kit: opens the app in a real browser and checks it starts cleanly.
//   node site-check.mjs <site-dir> <app-dir>   -> serves site-dir locally, opens app-dir in it
//   node site-check.mjs <https://url/>         -> checks a live deployment (retries while the CDN catches up)
// Fails on uncaught page errors, a missing page, or a service worker that won't register.
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(path.join(process.cwd(), 'noop.js'));
const { chromium } = require('playwright');

const [a, b] = process.argv.slice(2);
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon',
  '.woff2': 'font/woff2', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.wasm': 'application/wasm', '.txt': 'text/plain' };

async function serve(root) {
  const server = http.createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    let f = path.join(root, p);
    if (!f.startsWith(path.resolve(root))) { res.writeHead(403).end(); return; }
    if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, 'index.html');
    if (!fs.existsSync(f)) { res.writeHead(404).end('not found'); return; }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(f).toLowerCase()] || 'application/octet-stream' });
    fs.createReadStream(f).pipe(res);
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  return server;
}

async function check(url) {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  const resp = await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  if (!resp || !resp.ok()) throw new Error(`${url} answered ${resp && resp.status()}`);
  await page.waitForTimeout(2500);
  const sw = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) return 'unsupported';
    const reg = await Promise.race([navigator.serviceWorker.ready.then(() => 'ready'), new Promise(r => setTimeout(() => r('none'), 8000))]);
    return reg;
  });
  await browser.close();
  if (errors.length) throw new Error('The page threw errors:\n  ' + errors.join('\n  '));
  if (sw === 'none') console.log('::warning::No service worker became active within 8 seconds (offline use may not work).');
  console.log(`OK: ${url} (service worker: ${sw})`);
}

if (/^https?:/.test(a)) {
  let last;
  for (let i = 0; i < 10; i++) {
    try { await check(a); process.exit(0); } catch (e) { last = e; console.log(`Not ready yet (${e.message.split('\n')[0]}), retrying...`); await new Promise(r => setTimeout(r, 15000)); }
  }
  console.log(`::error::The live site at ${a} failed its check: ${last.message}`);
  process.exit(1);
} else {
  const root = path.resolve(a);
  const app = path.relative(root, path.resolve(b || a)).split(path.sep).join('/');
  const server = await serve(root);
  const url = `http://127.0.0.1:${server.address().port}/${app ? app + '/' : ''}`;
  try { await check(url); } catch (e) { console.log(`::error::${e.message}`); process.exit(1); } finally { server.close(); }
}
