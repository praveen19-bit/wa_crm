/* ============================================================
   WhatsApp CRM — Settings view
   ============================================================ */
(function () {
  "use strict";

  const settings = {
    state: null,

    init() {
      document.getElementById("btn-save-settings").addEventListener("click", () =>
        this.save()
      );
      document.getElementById("btn-test-connection").addEventListener("click", () =>
        this.testConnection()
      );
      document.getElementById("btn-copy-webhook").addEventListener("click", () =>
        this.copyWebhook()
      );
      document.getElementById("btn-save-account").addEventListener("click", () =>
        this.saveAccount()
      );
      document.getElementById("btn-change-password").addEventListener("click", () =>
        this.changePassword()
      );
    },

    async refresh() {
      const { api } = window.CRM;
      try {
        const s = await api.getSettings();
        this.state = s;
        const token = document.getElementById("set-token");
        token.placeholder = s.whatsapp_access_token || "EAAG…";
        token.value = "";
        document.getElementById("set-pnid").value = s.whatsapp_phone_number_id || "";
        document.getElementById("set-waba").value = s.whatsapp_business_account_id || "";
        document.getElementById("set-bname").value = s.business_name || "";
        document.getElementById("set-verify").value = s.webhook_verify_token || "";
        document.getElementById("set-autoreply").checked = !!s.auto_reply_enabled;
        document.getElementById("set-autoreply-text").value = s.auto_reply_text || "";

        const user = window.CRM.getSessionUser();
        document.getElementById("set-account-name").value = (user && user.name) || "";

        this.loadWebhookUrl();
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    async loadWebhookUrl() {
      try {
        const w = await window.CRM.api.webhookUrl();
        document.getElementById("webhook-url").textContent = w.webhook_url;
        if (!w.verify_token) {
          document.getElementById("webhook-url").textContent +=
            "\n(Add a verify token above and save, then paste it in Meta)";
        }
      } catch (e) {
        /* ignore */
      }
    },

    buildPayload() {
      const payload = {};
      const token = document.getElementById("set-token").value.trim();
      if (token) payload.whatsapp_access_token = token;
      const pnid = document.getElementById("set-pnid").value.trim();
      if (pnid) payload.whatsapp_phone_number_id = pnid;
      const waba = document.getElementById("set-waba").value.trim();
      if (waba) payload.whatsapp_business_account_id = waba;
      const bname = document.getElementById("set-bname").value.trim();
      if (bname) payload.business_name = bname;
      const verify = document.getElementById("set-verify").value.trim();
      if (verify) payload.webhook_verify_token = verify;
      payload.auto_reply_enabled = document.getElementById("set-autoreply").checked;
      payload.auto_reply_text = document.getElementById("set-autoreply-text").value.trim();
      return payload;
    },

    async save() {
      try {
        const payload = this.buildPayload();
        if (Object.keys(payload).length === 2 && !payload.auto_reply_enabled && !payload.auto_reply_text) {
          // nothing meaningful changed
        }
        await window.CRM.api.updateSettings(payload);
        window.CRM.toast("Settings saved", "success");
        this.refresh();
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    async testConnection() {
      try {
        await this.save();
      } catch (e) {
        return;
      }
      window.CRM
        .openModal(
          "Test connection",
          '<div id="conn-result"><p>Checking your Meta credentials…</p></div>',
          [
            { label: "Close", cls: "btn-ghost", value: true },
          ]
        )
        .then(() => {});
      try {
        const res = await window.CRM.api.testConnection();
        const list = res.phone_numbers
          .map((n) => "<li><code>" + window.CRM.escapeHtml(n.display_phone_number) + "</code></li>")
          .join("");
        document.getElementById("conn-result").innerHTML =
          "<p style='color:var(--accent-2);font-weight:600'>✅ " +
          window.CRM.escapeHtml(res.detail) +
          "</p><ul>" + list + "</ul>";
      } catch (e) {
        window.CRM.closeModal();
        window.CRM.toast(e.message, "error");
      }
    },

    async copyWebhook() {
      const url = document.getElementById("webhook-url").textContent.split("\n")[0];
      try {
        await navigator.clipboard.writeText(url);
        window.CRM.toast("Webhook URL copied", "success");
      } catch (e) {
        window.prompt("Copy the webhook URL:", url);
      }
    },

    async saveAccount() {
      const name = document.getElementById("set-account-name").value.trim();
      if (!name) {
        window.CRM.toast("Name cannot be empty", "error");
        return;
      }
      try {
        await window.CRM.api.updateProfile(name);
        const user = window.CRM.getSessionUser();
        user.name = name;
        window.CRM.setSession(window.CRM.getToken(), user);
        document.getElementById("user-name").textContent = name;
        document.getElementById("user-avatar").textContent = window.CRM.initials(name, "U");
        window.CRM.toast("Profile updated", "success");
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    changePassword() {
      const body =
        '<div class="field"><label>Current password</label><input id="pw-old" type="password" /></div>' +
        '<div class="field"><label>New password</label><input id="pw-new" type="password" placeholder="Min. 8 characters" /></div>';
      window.CRM
        .openModal("Change password", body, [
          { label: "Cancel", cls: "btn-ghost", value: null },
          { label: "Update", cls: "btn-primary", value: "submit" },
        ])
        .then(async (result) => {
          if (result !== "submit") return;
          const oldPw = document.getElementById("pw-old").value;
          const newPw = document.getElementById("pw-new").value;
          if (newPw.length < 8) {
            window.CRM.toast("New password must be at least 8 characters", "error");
            return;
          }
          try {
            await window.CRM.api.changePassword({
              current_password: oldPw,
              new_password: newPw,
            });
            window.CRM.toast("Password updated", "success");
          } catch (e) {
            window.CRM.toast(e.message, "error");
          }
        });
    },
  };

  window.CRM = window.CRM || {};
  window.CRM.settings = settings;

  document.addEventListener("DOMContentLoaded", () => settings.init());
})();
