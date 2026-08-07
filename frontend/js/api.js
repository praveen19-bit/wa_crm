/* ============================================================
   WhatsApp CRM — API client
   All backend calls are routed here.
   Override the API base with: localStorage.setItem('crm_api_base', 'https://...')
   ============================================================ */
(function () {
  "use strict";

  const API_BASE = (
    window.__API_BASE__ ||
    localStorage.getItem("crm_api_base") ||
    "http://127.0.0.1:8000"
  ).replace(/\/+$/, "");

  const TOKEN_KEY = "crm_token";
  const USER_KEY = "crm_user";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function getSessionUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null");
    } catch (e) {
      return null;
    }
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  class ApiError extends Error {
    constructor(message, status, detail) {
      super(message);
      this.status = status;
      this.detail = detail;
    }
  }

  function extractError(status, body) {
    if (body && typeof body === "object") {
      if (Array.isArray(body.detail)) {
        return body.detail.map((d) => d.msg).join("; ");
      }
      if (body.detail) return body.detail;
      if (body.message) return body.message;
    }
    return "Request failed (" + status + ")";
  }

  async function request(path, options = {}) {
    const opts = Object.assign({}, options);
    opts.headers = Object.assign(
      {
        Accept: "application/json",
      },
      opts.headers || {}
    );

    const token = getToken();
    if (token) opts.headers.Authorization = "Bearer " + token;

    if (opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }

    let resp;
    try {
      resp = await fetch(API_BASE + path, opts);
    } catch (e) {
      throw new ApiError("Cannot reach the server. Is the backend running?", 0, null);
    }

    let body = null;
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      try {
        body = await resp.json();
      } catch (e) {
        body = null;
      }
    }

    if (!resp.ok) {
      const msg = extractError(resp.status, body);
      if (resp.status === 401) {
        // Session expired -> send the app back to login
        clearSession();
        if (!location.pathname.includes("index.html") && !location.pathname.endsWith("/")) {
          location.href = "index.html";
        }
      }
      throw new ApiError(msg, resp.status, body);
    }
    return body;
  }

  const api = {
    base: API_BASE,

    /* ---------------- auth ---------------- */
    register: (data) => request("/api/auth/register", { method: "POST", body: data }),
    login: (data) => request("/api/auth/login", { method: "POST", body: data }),
    me: () => request("/api/auth/me"),
    updateProfile: (name) => request("/api/auth/me?name=" + encodeURIComponent(name), { method: "PUT" }),
    changePassword: (data) => request("/api/auth/me/password", { method: "PUT", body: data }),

    /* ---------------- contacts ---------------- */
    listContacts: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return request("/api/contacts?" + qs);
    },
    getContact: (id) => request("/api/contacts/" + id),
    createContact: (data) => request("/api/contacts", { method: "POST", body: data }),
    updateContact: (id, data) => request("/api/contacts/" + id, { method: "PUT", body: data }),
    deleteContact: (id) => request("/api/contacts/" + id, { method: "DELETE" }),
    assignTags: (id, tagIds) =>
      request("/api/contacts/" + id + "/tags", { method: "PUT", body: { tag_ids: tagIds } }),
    addNote: (id, content) =>
      request("/api/contacts/" + id + "/notes", { method: "POST", body: { content: content } }),
    listNotes: (id) => request("/api/contacts/" + id + "/notes"),
    deleteNote: (noteId) => request("/api/contacts/notes/" + noteId, { method: "DELETE" }),
    exportCsv: async () => {
      const resp = await fetch(API_BASE + "/api/contacts/export", {
        headers: { Authorization: "Bearer " + (getToken() || "") },
      });
      if (!resp.ok) throw new ApiError("Export failed", resp.status, null);
      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "contacts.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    },
    importCsv: (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return request("/api/contacts/import", { method: "POST", body: fd });
    },

    /* ---------------- tags ---------------- */
    listTags: () => request("/api/tags"),
    createTag: (data) => request("/api/tags", { method: "POST", body: data }),
    deleteTag: (id) => request("/api/tags/" + id, { method: "DELETE" }),

    /* ---------------- conversations ---------------- */
    listConversations: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return request("/api/conversations?" + qs);
    },
    conversationCounts: () => request("/api/conversations/counts"),
    getConversation: (id) => request("/api/conversations/" + id),
    createConversation: (contactId) => request("/api/conversations?contact_id=" + contactId, { method: "POST" }),
    markRead: (id) => request("/api/conversations/" + id + "/read", { method: "POST" }),
    toggleArchive: (id, archived) =>
      request("/api/conversations/" + id + "/archive?archived=" + archived, { method: "PUT" }),

    /* ---------------- messages ---------------- */
    listMessages: (convId) => request("/api/conversations/" + convId + "/messages"),
    sendMessage: (convId, data) =>
      request("/api/conversations/" + convId + "/messages", { method: "POST", body: data }),
    searchMessages: (q) => request("/api/messages/search?q=" + encodeURIComponent(q)),

    /* ---------------- media ---------------- */
    uploadMedia: (file, conversationId) => {
      const fd = new FormData();
      fd.append("file", file);
      if (conversationId) fd.append("conversation_id", conversationId);
      return request("/api/media/upload", { method: "POST", body: fd });
    },

    /* ---------------- analytics ---------------- */
    analytics: (days) => request("/api/analytics?days=" + days),

    /* ---------------- campaigns ---------------- */
    listCampaigns: (params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return request("/api/campaigns?" + qs);
    },
    getCampaign: (id) => request("/api/campaigns/" + id),
    createCampaign: (data) => request("/api/campaigns", { method: "POST", body: data }),
    updateCampaign: (id, data) => request("/api/campaigns/" + id, { method: "PATCH", body: data }),
    deleteCampaign: (id) => request("/api/campaigns/" + id, { method: "DELETE" }),
    startCampaign: (id) => request("/api/campaigns/" + id + "/start", { method: "POST" }),
    pauseCampaign: (id) => request("/api/campaigns/" + id + "/pause", { method: "POST" }),
    resumeCampaign: (id) => request("/api/campaigns/" + id + "/resume", { method: "POST" }),
    stopCampaign: (id) => request("/api/campaigns/" + id + "/stop", { method: "POST" }),
    uploadLeads: (id, file, columnMap) => {
      const fd = new FormData();
      fd.append("file", file);
      if (columnMap) fd.append("column_map", JSON.stringify(columnMap));
      return request("/api/campaigns/" + id + "/upload", { method: "POST", body: fd });
    },
    seedLeads: (id, rows) => request("/api/campaigns/" + id + "/seed", { method: "POST", body: rows }),
    campaignProgress: (id) => request("/api/campaigns/" + id + "/progress"),
    campaignContacts: (id, params = {}) => {
      const qs = new URLSearchParams(params).toString();
      return request("/api/campaigns/" + id + "/contacts?" + qs);
    },
    campaignLogs: (id) => request("/api/campaigns/" + id + "/logs"),
    campaignAnalytics: (id) => request("/api/campaigns/" + id + "/analytics"),
    exportCampaign: (id, fmt = "csv") => {
      const url = API_BASE + "/api/campaigns/" + id + "/export?fmt=" + encodeURIComponent(fmt);
      const a = document.createElement("a");
      a.href = url + "&token=" + encodeURIComponent(getToken() || "");
      a.download = "campaign-" + id + "." + fmt;
      a.click();
    },
    listTemplates: () => request("/api/campaigns/templates"),
    createTemplate: (data) => request("/api/campaigns/templates", { method: "POST", body: data }),
    toggleTemplate: (id) => request("/api/campaigns/templates/" + id + "/favorite", { method: "POST" }),
    deleteTemplate: (id) => request("/api/campaigns/templates/" + id, { method: "DELETE" }),
    listBlacklist: () => request("/api/campaigns/blacklist"),
    addBlacklist: (phone, reason) => request("/api/campaigns/blacklist?phone=" + encodeURIComponent(phone) + (reason ? "&reason=" + encodeURIComponent(reason) : ""), { method: "POST" }),
    removeBlacklist: (id) => request("/api/campaigns/blacklist/" + id, { method: "DELETE" }),

    /* ---------------- settings ---------------- */
    getSettings: () => request("/api/settings"),
    updateSettings: (data) => request("/api/settings", { method: "PUT", body: data }),
    testConnection: () => request("/api/settings/test-connection", { method: "POST" }),
    webhookUrl: () => request("/api/settings/webhook-url"),
  };

  window.CRM = window.CRM || {};
  Object.assign(window.CRM, { api, ApiError, getToken, setSession, getSessionUser, clearSession });
})();
