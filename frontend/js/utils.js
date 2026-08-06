/* ============================================================
   WhatsApp CRM — shared UI utilities
   ============================================================ */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function initials(name, fallback) {
    if (!name || !name.trim()) return (fallback || "?").slice(0, 1).toUpperCase();
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  const AVATAR_COLORS = [
    "linear-gradient(135deg,#6d5df6,#3aa0ff)",
    "linear-gradient(135deg,#f472b6,#fb923c)",
    "linear-gradient(135deg,#34d399,#06b6d4)",
    "linear-gradient(135deg,#a78bfa,#ec4899)",
    "linear-gradient(135deg,#fbbf24,#f97316)",
    "linear-gradient(135deg,#2dd4bf,#3b82f6)",
  ];

  function avatarColor(seed) {
    let h = 0;
    const s = String(seed || "");
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return AVATAR_COLORS[h % AVATAR_COLORS.length];
  }

  function avatarEl(name, seed, size) {
    const el = document.createElement("div");
    el.className = "avatar";
    if (size) {
      el.style.width = size + "px";
      el.style.height = size + "px";
      el.style.fontSize = Math.round(size * 0.38) + "px";
    }
    el.style.background = avatarColor(seed);
    el.textContent = initials(name, seed);
    return el;
  }

  /* ---------------- time formatting ---------------- */
  function fmtTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return fmtTime(iso);
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    if (d.getFullYear() === now.getFullYear()) {
      return d.toLocaleDateString([], { month: "short", day: "numeric" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  }

  function fmtFull(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function dayLabel(iso) {
    const d = new Date(iso);
    const now = new Date();
    const today = now.toDateString();
    if (d.toDateString() === today) return "Today";
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
  }

  /* ---------------- toasts ---------------- */
  function toast(message, type) {
    const stack = $("#toast-stack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = "toast " + (type || "");
    const icon = type === "error" ? "⚠️" : type === "success" ? "✅" : "💬";
    el.innerHTML = "<span>" + icon + "</span><span>" + escapeHtml(message) + "</span>";
    el.title = "Click to dismiss";
    el.addEventListener("click", () => {
      el.classList.add("out");
      setTimeout(() => el.remove(), 320);
    });
    stack.appendChild(el);
    setTimeout(() => {
      if (el.isConnected) {
        el.classList.add("out");
        setTimeout(() => el.remove(), 320);
      }
    }, 3400);
  }

  /* ---------------- debounce ---------------- */
  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  window.CRM = window.CRM || {};
  Object.assign(window.CRM, {
    $,
    $$,
    escapeHtml,
    initials,
    avatarColor,
    avatarEl,
    fmtTime,
    fmtDate,
    fmtFull,
    dayLabel,
    toast,
    debounce,
  });
})();
