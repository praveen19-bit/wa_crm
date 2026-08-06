/* ============================================================
   WhatsApp CRM — Runtime configuration
   Loaded before js/api.js on every page.

   In production the frontend is served from the same origin as
   the API (Caddy reverse proxy), so API + WebSocket calls use
   same-origin URLs. Local dev keeps its own defaults.
   ============================================================ */
(function () {
  "use strict";
  var host = location.hostname;
  if (host !== "localhost" && host !== "127.0.0.1") {
    window.__API_BASE__ = location.origin;
  }
})();
