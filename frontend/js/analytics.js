/* ============================================================
   WhatsApp CRM — Analytics (canvas charts, no libraries)
   ============================================================ */
(function () {
  "use strict";

  const state = { days: 30 };

  const analytics = {
    state,

    init() {
      document.getElementById("analytics-range").addEventListener("change", (e) => {
        state.days = parseInt(e.target.value, 10) || 30;
        this.refresh();
      });
    },

    async refresh() {
      const { api } = window.CRM;
      try {
        const data = await api.analytics(state.days);
        this.renderCards(data.overview);
        this.renderDailyChart(data.daily);
        this.renderMixChart(data);
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    renderCards(o) {
      const grid = document.getElementById("analytics-cards");
      const cards = [
        { icon: "👥", value: o.total_contacts, label: "Total contacts" },
        { icon: "💬", value: o.total_messages, label: "Total messages" },
        { icon: "🔔", value: o.unread_messages, label: "Unread messages" },
        { icon: "↩️", value: o.today_replies, label: "Today's replies" },
        { icon: "🔥", value: o.active_conversations, label: "Active (7d)" },
        { icon: "📥", value: o.incoming_messages, label: "Incoming" },
        { icon: "📤", value: o.outgoing_messages, label: "Outgoing" },
        { icon: "🗂️", value: o.total_conversations, label: "Conversations" },
      ];
      grid.innerHTML = "";
      cards.forEach((c, i) => {
        const card = document.createElement("div");
        card.className = "stat-card glass";
        card.style.animationDelay = i * 0.04 + "s";
        card.innerHTML =
          '<div class="stat-ico">' + c.icon + "</div>" +
          '<div class="stat-value">' + c.value.toLocaleString() + "</div>" +
          '<div class="stat-label">' + c.label + "</div>";
        grid.appendChild(card);
      });
    },

    /* ---------------- daily bars ---------------- */
    renderDailyChart(points) {
      const canvas = document.getElementById("chart-daily");
      const ctx = canvas.getContext("2d");
      this.sizeCanvas(canvas);

      const dpr = window.devicePixelRatio || 1;
      canvas.width = canvas.offsetWidth * dpr;
      canvas.height = canvas.offsetHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, canvas.offsetWidth, canvas.offsetHeight);

      const W = canvas.offsetWidth;
      const H = canvas.offsetHeight;
      const pad = { top: 18, right: 12, bottom: 28, left: 34 };

      const incoming = points.map((p) => p.incoming);
      const outgoing = points.map((p) => p.outgoing);
      const max = Math.max(1, ...incoming, ...outgoing);
      const chartW = W - pad.left - pad.right;
      const chartH = H - pad.top - pad.bottom;
      const slot = chartW / Math.max(1, points.length);
      const barW = Math.min(22, Math.max(3, slot * 0.38));

      const css = getComputedStyle(document.documentElement);
      const cIn = css.getPropertyValue("--accent").trim() || "#25d366";
      const cOut = css.getPropertyValue("--blue").trim() || "#5b8cff";
      const cText = css.getPropertyValue("--text-3").trim() || "#94a3b8";
      const cGrid = css.getPropertyValue("--border").trim() || "rgba(255,255,255,0.07)";

      // grid + y labels
      ctx.strokeStyle = cGrid;
      ctx.fillStyle = cText;
      ctx.font = "11px " + css.fontFamily;
      ctx.lineWidth = 1;
      const steps = 4;
      for (let i = 0; i <= steps; i++) {
        const y = pad.top + (chartH / steps) * i;
        const val = Math.round(max - (max / steps) * i);
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(W - pad.right, y);
        ctx.stroke();
        ctx.textAlign = "right";
        ctx.fillText(String(val), pad.left - 8, y + 4);
      }

      // bars
      points.forEach((p, i) => {
        const x = pad.left + slot * i + slot / 2;
        const hIn = (p.incoming / max) * chartH;
        const hOut = (p.outgoing / max) * chartH;
        ctx.fillStyle = cIn;
        roundRect(ctx, x - barW - 1.5, pad.top + chartH - hIn, barW, hIn, 4);
        ctx.fill();
        ctx.fillStyle = cOut;
        roundRect(ctx, x + 1.5, pad.top + chartH - hOut, barW, hOut, 4);
        ctx.fill();

        // x labels (sparse)
        if (points.length <= 31 || i % Math.ceil(points.length / 14) === 0) {
          const label = p.date.slice(5);
          ctx.fillStyle = cText;
          ctx.textAlign = "center";
          ctx.fillText(label, x, H - 8);
        }
      });

      // legend
      ctx.textAlign = "left";
      ctx.fillStyle = cIn;
      ctx.fillRect(4, 4, 10, 10);
      ctx.fillStyle = cText;
      ctx.fillText("Incoming", 18, 13);
      ctx.fillStyle = cOut;
      ctx.fillRect(84, 4, 10, 10);
      ctx.fillStyle = cText;
      ctx.fillText("Outgoing", 98, 13);
    },

    /* ---------------- mix donut ---------------- */
    renderMixChart(data) {
      const canvas = document.getElementById("chart-mix");
      const ctx = canvas.getContext("2d");
      this.sizeCanvas(canvas);
      const dpr = window.devicePixelRatio || 1;
      canvas.width = canvas.offsetWidth * dpr;
      canvas.height = canvas.offsetHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, canvas.offsetWidth, canvas.offsetHeight);

      const W = canvas.offsetWidth;
      const H = canvas.offsetHeight;
      const cx = W / 2;
      const cy = H / 2;
      const radius = Math.min(W, H) * 0.34;

      const css = getComputedStyle(document.documentElement);
      const cText = css.getPropertyValue("--text-3").trim() || "#94a3b8";

      const total = data.overview.incoming_messages + data.overview.outgoing_messages;
      const out = data.overview.outgoing_messages;
      const inMsgs = data.overview.incoming_messages;

      if (total === 0) {
        ctx.fillStyle = cText;
        ctx.font = "13px " + css.fontFamily;
        ctx.textAlign = "center";
        ctx.fillText("No messages yet", cx, cy);
        return;
      }

      const palette = ["#25d366", "#5b8cff", "#fbbf24", "#f472b6", "#a78bfa", "#06b6d4"];
      const mix = [
        { label: "Incoming", v: inMsgs },
        { label: "Outgoing", v: out },
      ];

      let angle = -Math.PI / 2;
      const segments = mix.map((m) => {
        const a = (m.v / total) * Math.PI * 2;
        const seg = { ...m, a };
        return seg;
      });

      segments.forEach((seg, i) => {
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, angle, angle + seg.a);
        ctx.closePath();
        ctx.fillStyle = palette[i % palette.length];
        ctx.fill();
        angle += seg.a;
      });

      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.62, 0, Math.PI * 2);
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--panel-solid").trim() || "#1b2334";
      ctx.fill();

      ctx.fillStyle = css.getPropertyValue("--text").trim() || "#fff";
      ctx.font = "700 22px " + css.fontFamily;
      ctx.textAlign = "center";
      ctx.fillText(String(total), cx, cy + 2);
      ctx.fillStyle = cText;
      ctx.font = "11px " + css.fontFamily;
      ctx.fillText("messages", cx, cy + 18);

      // legend
      const legendY = H - 22;
      ctx.font = "12px " + css.fontFamily;
      mix.forEach((m, i) => {
        const label = m.label + " · " + m.v;
        const textW = ctx.measureText(label).width;
        const x = W / 2 - (textW + 30) / 2 + i * (textW + 60) - (i === 0 ? 15 : 15);
        ctx.fillStyle = palette[i];
        ctx.fillRect(x, legendY - 8, 12, 12);
        ctx.fillStyle = cText;
        ctx.textAlign = "left";
        ctx.fillText(label, x + 17, legendY);
      });
    },

    sizeCanvas(canvas) {
      canvas.style.height = "280px";
    },
  };

  function roundRect(ctx, x, y, w, h, r) {
    if (w <= 0 || h <= 0) return;
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  window.CRM = window.CRM || {};
  window.CRM.analytics = analytics;

  document.addEventListener("DOMContentLoaded", () => analytics.init());
})();
