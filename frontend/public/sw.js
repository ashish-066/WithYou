/*
 * Minimal service worker: makes the app installable and shows a friendly page
 * when offline. It deliberately caches nothing live: the API (/api), LiveKit
 * (WebRTC + wss) and the app's own files always come from the network, so a
 * session never runs on stale code or stale data.
 */
const OFFLINE_HTML = `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Study Buddy</title></head>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#F6F3EC;color:#1C1B18;padding:24px;text-align:center">
<div><h1 style="font-size:24px">You're offline</h1>
<p>Your study buddy needs the internet to talk. Connect and try again.</p></div></body></html>`;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  const { request } = event;
  // Only page navigations get the offline fallback; everything else is untouched
  if (request.mode !== 'navigate') return;
  event.respondWith(
    fetch(request).catch(
      () => new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8' } }),
    ),
  );
});
