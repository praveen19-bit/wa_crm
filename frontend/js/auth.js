/* ============================================================
   Auth pages: login + register
   ============================================================ */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    const { api, setSession } = window.CRM;

    // If already logged in, jump straight to the app
    if (window.CRM.getToken() && window.CRM.getSessionUser()) {
      location.href = "app.html";
      return;
    }

    const themeSwitch = document.getElementById("theme-switch");
    if (themeSwitch) {
      themeSwitch.textContent = document.documentElement.dataset.theme === "dark" ? "🌙" : "☀️";
      themeSwitch.addEventListener("click", () => {
        const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        localStorage.setItem("crm_theme", next);
        themeSwitch.textContent = next === "dark" ? "🌙" : "☀️";
      });
    }

    const apiLabel = document.getElementById("api-base-label");
    if (apiLabel) apiLabel.textContent = api.base;

    function showError(msg) {
      const el = document.getElementById("form-error");
      if (el) {
        el.textContent = msg;
        el.hidden = false;
      }
    }

    function setLoading(btn, loading) {
      if (!btn) return;
      btn.disabled = loading;
      const label = btn.querySelector(".btn-label");
      if (label) label.textContent = loading ? "Please wait…" : btn.dataset.label;
    }

    const loginForm = document.getElementById("login-form");
    if (loginForm) {
      const btn = document.getElementById("login-btn");
      btn.dataset.label = "Sign in";
      loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        setLoading(btn, true);
        try {
          const res = await api.login({
            email: document.getElementById("email").value.trim(),
            password: document.getElementById("password").value,
          });
          setSession(res.access_token, res.user);
          location.href = "app.html";
        } catch (err) {
          showError(err.message);
          setLoading(btn, false);
        }
      });
    }

    const registerForm = document.getElementById("register-form");
    if (registerForm) {
      const btn = document.getElementById("register-btn");
      btn.dataset.label = "Create account";
      registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const password = document.getElementById("password").value;
        if (password.length < 8) {
          showError("Password must be at least 8 characters.");
          return;
        }
        setLoading(btn, true);
        try {
          const res = await api.register({
            name: document.getElementById("name").value.trim(),
            email: document.getElementById("email").value.trim(),
            password,
          });
          setSession(res.access_token, res.user);
          location.href = "app.html";
        } catch (err) {
          showError(err.message);
          setLoading(btn, false);
        }
      });
    }
  });
})();
