// Checks that the beta build keeps its own storage: taps in /beta/ never change the real app's count.
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const { chromium } = createRequire(path.join(process.cwd(), 'noop.js'))('playwright');
const root = '/tmp/www';
const server = http.createServer((req, res) => {
  let f = path.join(root, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, 'index.html');
  if (!fs.existsSync(f)) return res.writeHead(404).end();
  const type = { '.html': 'text/html', '.js': 'text/javascript', '.webmanifest': 'application/manifest+json', '.png': 'image/png' }[path.extname(f)];
  res.writeHead(200, { 'Content-Type': type || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch();
const page = await browser.newPage();
const fail = m => { console.error('FAIL: ' + m); process.exit(1); };

await page.goto(base + '/prod/');
await page.click('#tap'); await page.click('#tap');
if (await page.textContent('#n') !== '2') fail('production count should be 2');

await page.goto(base + '/beta/');
if (await page.textContent('#n') !== '0') fail('beta should start with its own empty storage');
await page.click('#tap');
if (!(await page.textContent('body')).includes('BETA')) fail('beta badge missing');

await page.goto(base + '/prod/');
if (await page.textContent('#n') !== '2') fail('beta changed the production data');
const raw = await page.evaluate(() => Object.keys(window.localStorage));
await page.goto(base + '/beta/');
const betaView = await page.evaluate(() => { const a = []; for (let i = 0; i < localStorage.length; i++) a.push(localStorage.key(i)); return a; });
if (betaView.join() !== 'sample-taps') fail('beta should list only its own keys, got ' + betaView);
if (!raw.includes('beta:sample-taps') || !raw.includes('sample-taps')) fail('expected separate keys, got ' + raw);

console.log('OK: beta and production keep separate data');
await browser.close();
server.close();
