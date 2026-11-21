#!/usr/bin/env node
/**
 * Installability check for the PWA (what Chrome requires to offer "Install"),
 * run against the built app in dist/:
 *   - index.html links a manifest, sets theme-color and a viewport
 *   - manifest: name/short_name, start_url, display standalone|fullscreen|minimal-ui,
 *     icons of 192 and 512 px (PNG, files present), plus a maskable icon
 *   - a service worker file with a fetch handler, registered by the app bundle
 * (Lighthouse removed its PWA audit; HTTPS is the remaining requirement and
 * comes from the host or the tunnel.)
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'dist');
const problems = [];
const need = (ok, msg) => ok || problems.push(msg);

const html = readFileSync(join(dist, 'index.html'), 'utf8');
const manifestHref = html.match(/<link[^>]+rel="manifest"[^>]+href="([^"]+)"/)?.[1];
need(manifestHref, 'index.html: no <link rel="manifest">');
need(/name="theme-color"/.test(html), 'index.html: no theme-color');
need(/name="viewport"/.test(html), 'index.html: no viewport');

if (manifestHref) {
  const m = JSON.parse(readFileSync(join(dist, manifestHref), 'utf8'));
  need(m.name && m.short_name, 'manifest: name and short_name');
  need(m.start_url, 'manifest: start_url');
  need(['standalone', 'fullscreen', 'minimal-ui'].includes(m.display), 'manifest: display');
  for (const size of ['192x192', '512x512']) {
    const icon = (m.icons || []).find((i) => i.sizes === size && i.type === 'image/png');
    need(icon, `manifest: a ${size} PNG icon`);
    if (icon) need(existsSync(join(dist, icon.src)), `icon file missing: ${icon.src}`);
  }
  need((m.icons || []).some((i) => (i.purpose || '').includes('maskable')), 'manifest: a maskable icon');
}

need(existsSync(join(dist, 'sw.js')), 'dist/sw.js missing');
if (existsSync(join(dist, 'sw.js'))) {
  need(/addEventListener\(\s*['"]fetch['"]/.test(readFileSync(join(dist, 'sw.js'), 'utf8')), 'sw.js: no fetch handler');
}
const bundles = readdirSync(join(dist, 'assets')).filter((f) => f.endsWith('.js'));
need(
  bundles.some((f) => readFileSync(join(dist, 'assets', f), 'utf8').includes('/sw.js')),
  'app bundle does not register /sw.js',
);

if (problems.length) {
  console.error(`PWA check: ${problems.length} problem(s)`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log('PWA check: installable (manifest, icons, service worker, registration)');
