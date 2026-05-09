/* eslint-disable no-restricted-globals */

// This service worker is processed by CRA's Workbox integration at build time.
// In development it does nothing; in production it caches the app shell.

import { clientsClaim } from 'workbox-core';
import { ExpirationPlugin } from 'workbox-expiration';
import { precacheAndRoute, createHandlerBoundToURL } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { StaleWhileRevalidate, NetworkFirst } from 'workbox-strategies';

clientsClaim();

// Precache all assets injected by Workbox at build time
precacheAndRoute(self.__WB_MANIFEST);

// Handle SPA navigation — always serve index.html for non-file routes
const fileExtensionRegexp = new RegExp('/[^/?]+\\.[^/]+$');
registerRoute(
  ({ request, url: { pathname }, sameOrigin }) => {
    if (!sameOrigin) return false;
    if (request.mode !== 'navigate') return false;
    if (pathname.startsWith('/_')) return false;
    if (pathname.match(fileExtensionRegexp)) return false;
    return true;
  },
  createHandlerBoundToURL(process.env.PUBLIC_URL + '/index.html')
);

// Cache app icons with stale-while-revalidate
registerRoute(
  ({ url: { origin, pathname } }) =>
    origin === self.location.origin && pathname.startsWith('/icons/'),
  new StaleWhileRevalidate({
    cacheName: 'bahi-khata-icons',
    plugins: [new ExpirationPlugin({ maxEntries: 20 })],
  })
);

// API calls — network first, fall back gracefully (no offline cache for sensitive data)
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/'),
  new NetworkFirst({ cacheName: 'bahi-khata-api', networkTimeoutSeconds: 10 })
);

// Allow the app to trigger a SW update without waiting
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
