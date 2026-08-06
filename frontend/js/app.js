/* ============================================================
   WhatsApp CRM — main shell: nav, theme, session guard
   ============================================================ */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    const { api, $, $$ } = window.CRM;

    // ---------- session guard ----------
    if (!window.CRM.getToken()) {
      location.href = "index.html";
      return;
    }

    // ---------- theme ----------
    const savedTheme = localStorage.getItem("crm_theme") || "dark";
    document.documentElement.dataset.theme = savedTheme;

    // ---------- user ----------
    const user = window.CRM.getSessionUser() || {};
    const userName = $("#user-name");
    const userAvatar = $("#user-avatar");
    if (userName) userName.textContent = user.name || "User";
    if (userAvatar) {
      userAvatar.textContent = window.CRM.initials(user.name || user.email || "U", "U");
      userAvatar.style.background = window.CRM.avatarColor(user.email || user.name);
    }

    // ---------- navigation ----------
    function showView(name) {
      $$(".view").forEach((v) => v.classList.remove("active"));
      $$(".nav-item").forEach((n) => n.classList.remove("active"));
      const view = $("#view-" + name);
      if (view) view.classList.add("active");
      const nav = document.querySelector('.nav-item[data-view="' + name + '"]');
      if (nav) nav.classList.add("active");

      if (name === "contacts" && window.CRM.contacts) window.CRM.contacts.refresh();
      if (name === "analytics" && window.CRM.analytics) window.CRM.analytics.refresh();
      if (name === "settings" && window.CRM.settings) window.CRM.settings.refresh();
      if (name === "inbox" && window.CRM.inbox) window.CRM.inbox.refreshList();
    }
    window.CRM.showView = showView;

    $$(".nav-item").forEach((btn) => {
      btn.addEventListener("click", () => showView(btn.dataset.view));
    });

    // ---------- theme toggle ----------
    const themeBtn = $("#theme-toggle");
    if (themeBtn) {
      themeBtn.querySelector(".theme-ico").textContent = savedTheme === "dark" ? "🌙" : "☀️";
      themeBtn.addEventListener("click", () => {
        const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        localStorage.setItem("crm_theme", next);
        themeBtn.querySelector(".theme-ico").textContent = next === "dark" ? "🌙" : "☀️";
      });
    }

    // ---------- logout ----------
    $("#logout-btn").addEventListener("click", () => {
      window.CRM.clearSession();
      window.CRM.ws.disconnect();
      location.href = "index.html";
    });

    // ---------- modal helper ----------
    function openModal(title, bodyHtml, buttons) {
      return new Promise((resolve) => {
        const backdrop = $("#modal-backdrop");
        const modal = $("#modal");
        $("#modal-title").textContent = title;
        $("#modal-body").innerHTML = bodyHtml;
        backdrop.hidden = false;

        const close = (value) => {
          backdrop.hidden = true;
          // clear AFTER the awaiting handler reads input values (resolve queues a microtask)
          setTimeout(() => {
            $("#modal-body").innerHTML = "";
          }, 0);
          resolve(value);
        };

        $("#modal-close").onclick = () => close(null);
        // clicking the backdrop dismisses the modal too
        backdrop.onclick = (evt) => {
          if (evt.target === backdrop) close(null);
        };

        // rebuild action buttons
        const oldBtns = modal.querySelectorAll("[data-modal-action]");
        oldBtns.forEach((b) => b.remove());
        (buttons || []).forEach((btn) => {
          const b = document.createElement("button");
          b.className = "btn " + (btn.cls || "btn-ghost");
          b.textContent = btn.label;
          b.dataset.modalAction = "1";
          b.addEventListener("click", () => close(btn.value));
          $("#modal-body").appendChild(b);
          if (btn.cls === "btn-primary") {
            b.style.marginTop = "10px";
            b.style.width = "100%";
          }
        });
      });
    }
    window.CRM.openModal = openModal;
    window.CRM.closeModal = () => {
      const backdrop = $("#modal-backdrop");
      if (!backdrop.hidden) backdrop.hidden = true;
    };

    // ---------- websocket ----------
    window.CRM.wsBus.on("open", () => {
      if (window.CRM.inbox) window.CRM.inbox.refreshList();
    });
    window.CRM.ws.connect();

    // ---------- global escape key closes modals ----------
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && window.CRM.closeModal) window.CRM.closeModal();
    });
  });
})();
