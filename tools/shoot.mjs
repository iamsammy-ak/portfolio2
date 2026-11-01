// Screenshots the page with real Chrome over the DevTools protocol, after scrolling and moving the mouse,
// so the hero's WebGL, the sticky story and the fluid reveal can be checked without a browser extension.
//
//   node tools/shoot.mjs out.png [--url=file:///...index.html] [--w=1440] [--h=900] [--dpr=1]
//        [--at=0.5]            scroll to this fraction of the page (0..1), or --y=1234 pixels
//        [--mouse=x,y;x,y;…]   move the pointer through these points (viewport px) before the shot
//        [--wait=1500]         ms to let the page animate after scrolling and moving
//        [--eval=js]           JavaScript to run in the page before the shot (its result is printed)
//        [--touch]             emulate a touch screen (phone checks)
//        [--swipe=x,y;x,y;…]   drag a finger through these points (touch events); --hold keeps it down for the shot
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(3).map(a => { const m = a.match(/^--([^=]+)(?:=(.*))?$/); return m ? [m[1], m[2] ?? true] : [a, true]; }));
const out = process.argv[2] || 'shot.png';
const W = +(args.w || 1440), H = +(args.h || 900), DPR = +(args.dpr || 1);
const url = args.url || pathToFileURL(path.resolve('index.html')).href;
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const port = 9222 + Math.floor(Math.random() * 500);
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--allow-file-access-from-files', '--hide-scrollbars', '--no-first-run', '--remote-debugging-port=' + port, '--window-size=' + W + ',' + H, `--user-data-dir=${path.join(process.env.TEMP || '.', 'shoot-profile-' + port)}`, 'about:blank'], { stdio: 'ignore' });
let ws, id = 0; const pending = new Map();
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
try {
  let targets;
  for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(200); } }
  if (!targets) throw new Error('Chrome did not start');
  const page = targets.find(t => t.type === 'page');
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); } else if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') console.log('console.error:', m.params.args.map(a => a.value || a.description).join(' ')); else if (m.method === 'Runtime.exceptionThrown') console.log('exception:', m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); };
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: DPR, mobile: !!args.touch });
  if (args.touch) await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  await send('Page.navigate', { url });
  await sleep(+(args.load || 1500));
  const ev = async (expression) => (await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })).result.value;
  if (args.at !== undefined || args.y !== undefined) {
    // Scroll in steps so scroll-driven work (and Lenis, if on) keeps up.
    const target = args.y !== undefined ? +args.y : await ev(`${+args.at} * (document.documentElement.scrollHeight - innerHeight)`);
    await ev(`window.__lenis && window.__lenis.destroy && window.__lenis.destroy()`);
    for (let k = 1; k <= 8; k++) { await ev(`scrollTo(0, ${target} * ${k / 8})`); await sleep(60); }
    await ev(`scrollTo(0, ${target}); dispatchEvent(new Event('scroll'))`);
  }
  if (args.mouse) {
    const pts = String(args.mouse).split(';').map(p => p.split(',').map(Number));
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pts[0][0], y: pts[0][1] });
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], n = 12;
      for (let k = 1; k <= n; k++) { await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x0 + (x1 - x0) * k / n, y: y0 + (y1 - y0) * k / n }); await sleep(16); }
    }
  }
  if (args.swipe) {
    const pts = String(args.swipe).split(';').map(p => p.split(',').map(Number));
    const tp = (x, y) => ({ touchPoints: [{ x, y, radiusX: 4, radiusY: 4, force: 1 }] });
    await send('Input.dispatchTouchEvent', { type: 'touchStart', ...tp(pts[0][0], pts[0][1]) });
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], n = 14;
      for (let k = 1; k <= n; k++) { await send('Input.dispatchTouchEvent', { type: 'touchMove', ...tp(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) }); await sleep(16); }
    }
    if (!args.hold) await send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  }
  await sleep(+(args.wait || 1200));
  if (args.eval) console.log('eval:', JSON.stringify(await ev(String(args.eval))));
  const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(out, Buffer.from(shot.data, 'base64'));
  console.log('wrote', out, 'scrollY', await ev('scrollY'), 'of', await ev('document.documentElement.scrollHeight'));
} finally {
  try { ws && ws.close(); } catch {}
  chrome.kill();
}
