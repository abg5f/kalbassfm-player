/* KALBASS FM — service worker minimal.
   Network-first pour la navigation (les mises à jour passent toujours),
   cache seulement la coquille + icônes pour l'installation PWA / mode hors-ligne.
   Ne met JAMAIS en cache le flux audio ni l'API now-playing. */
const V = 'kfm-v6'; // bump : reconnexion durcie (backoff + cache-bust)
const SHELL = ['/', '/index.html', '/icon-192.png', '/icon-512.png', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== V).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Navigation : réseau d'abord, coquille en secours hors-ligne
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/')));
    return;
  }

  // Icônes / manifest same-origin : cache-first
  if (url.origin === location.origin && /\.(png|ico|webmanifest)$/.test(url.pathname)) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(V).then((c) => c.put(req, copy));
        return resp;
      }))
    );
    return;
  }
  // Tout le reste (API, flux audio, polices) : réseau direct, pas de cache
});
