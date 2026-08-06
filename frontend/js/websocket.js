/* ============================================================
   WhatsApp CRM — WebSocket realtime client
   Reconnects automatically. Dispatches typed events on window.CRM.wsBus.
   ============================================================ */
(function () {
  "use strict";

  const events = {};

  function on(type, fn) {
    (events[type] = events[type] || []).push(fn);
  }

  function emit(type, data) {
    (events[type] || []).forEach((fn) => {
      try {
        fn(data);
      } catch (e) {
        console.error("[ws] handler error", e);
      }
    });
  }

  const ws = {
    socket: null,
    connected: false,
    reconnectDelay: 1200,
    retries: 0,
    maxRetries: 30,

    connect() {
      const token = window.CRM.getToken();
      if (!token) return;
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const base = window.CRM.api.base.replace(/^http/, "ws");
      const url = base + "/ws?token=" + encodeURIComponent(token);

      try {
        this.socket = new WebSocket(url);
      } catch (e) {
        return;
      }

      this.socket.onopen = () => {
        this.connected = true;
        this.retries = 0;
        emit("open", null);
      };

      this.socket.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg && msg.type) emit(msg.type, msg.data);
        } catch (e) {
          console.warn("[ws] bad message", evt.data);
        }
      };

      this.socket.onclose = () => {
        this.connected = false;
        emit("close", null);
        if (this.retries >= this.maxRetries) return;
        this.retries++;
        const delay = Math.min(30000, this.reconnectDelay * this.retries);
        setTimeout(() => this.connect(), delay);
      };

      this.socket.onerror = () => this.socket && this.socket.close();
    },

    disconnect() {
      if (this.socket) {
        this.socket.onclose = null;
        this.socket.close();
        this.socket = null;
        this.connected = false;
      }
    },
  };

  window.CRM = window.CRM || {};
  Object.assign(window.CRM, { ws, wsBus: { on, emit } });
})();
