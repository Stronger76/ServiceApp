
const VERSION='v1.0.0'; const STATIC_CACHE=`serviceapp-static-${VERSION}`;
const STATIC_ASSETS=['/','/login','/static/manifest.webmanifest','/static/icons/icon-192.png','/static/icons/icon-512.png','/static/offline.html'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(STATIC_CACHE).then(c=>c.addAll(STATIC_ASSETS)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==STATIC_CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{const req=e.request; if(req.method!=='GET')return;
  if(req.mode==='navigate'){e.respondWith(fetch(req).catch(()=>caches.match('/static/offline.html')));return;}
  const url=new URL(req.url); if(url.pathname.startsWith('/static/')){e.respondWith(caches.match(req).then(c=>c||fetch(req).then(res=>{const cl=res.clone(); caches.open(STATIC_CACHE).then(cache=>cache.put(req,cl)); return res;}))); return;}
  e.respondWith(fetch(req).then(res=>{const cl=res.clone(); caches.open(STATIC_CACHE).then(cache=>cache.put(req,cl)); return res;}).catch(()=>caches.match(req)));
});
