/* ============================================================
   WhatsApp CRM — Cold DM Campaign module
   Dashboard, wizard, live run view, templates, blacklist.
   ============================================================ */
(function () {
  "use strict";

  const { $, $$, escapeHtml, toast } = window.CRM;
  const api = window.CRM.api;

  let state = {
    campaigns: [],
    templates: [],
    current: null,
    preview: null,
    progressTimer: null,
  };

  function q(id) { return document.getElementById(id); }

  const HTML = `
<div class="camp-chrome">
  <header class="camp-head">
    <h1>Campaigns</h1>
    <p class="page-sub">Run cold DM outreach with the WhatsApp Cloud API</p>
  </header>

  <!-- dashboard -->
  <section id="campaigns-dashboard" class="camp-dashboard">
    <div class="page-actions">
      <button class="btn btn-primary" id="btn-new-campaign">🚀 New campaign</button>
      <button class="btn btn-ghost" id="btn-back-dashboard" style="display:none;">← Dashboard</button>
    </div>
    <div class="camp-rows" id="campaign-list"></div>
  </section>

  <!-- live run -->
  <section id="campaigns-live" class="camp-live" style="display:none;">
    <div class="page-actions">
      <button class="btn btn-ghost" id="btn-back-dashboard">← Dashboard</button>
    </div>
    <div class="camp-live-head">
      <h2 id="camp-live-title">Campaign</h2>
      <span class="camp-live-status camp-status camp-status-draft" id="camp-live-status">DRAFT</span>
    </div>
    <div class="camp-stats">
      <div class="camp-stat"><span class="camp-stat-v" id="camp-sent">0</span><span class="camp-stat-l">Sent</span></div>
      <div class="camp-stat"><span class="camp-stat-v" id="camp-failed">0</span><span class="camp-stat-l">Failed</span></div>
      <div class="camp-stat"><span class="camp-stat-v" id="camp-total">0</span><span class="camp-stat-l">Total</span></div>
    </div>
    <div class="camp-progress"><div class="camp-progress-bar" id="camp-progress-bar"></div></div>
    <div class="camp-actions">
      <button class="btn btn-primary" id="camp-start">▶ Start</button>
      <button class="btn btn-ghost" id="camp-pause">⏸ Pause</button>
      <button class="btn btn-ghost" id="camp-stop">⏹ Stop</button>
      <label class="btn btn-ghost" for="csv-upload" id="camp-seed" style="display:none;">⬆ Upload leads</label>
      <input type="file" id="csv-upload" accept=".csv,.xlsx,.xls" hidden />
    </div>
    <div class="camp-preview" id="camp-preview" style="display:none;">
      <div class="camp-preview-head">
        <strong>Lead preview</strong><span id="csv-meta"></span>
      </div>
      <select id="csv-columns" multiple style="width:100%;margin-bottom:8px;"></select>
      <table class="table camp-preview-table">
        <tbody id="csv-sample"></tbody>
      </table>
      <ul id="csv-errors"></ul>
      <div class="camp-preview-actions"><button class="btn btn-primary" id="btn-seed">Seed contacts</button></div>
    </div>
  </section>

  <!-- wizard -->
  <section id="campaigns-wizard" class="camp-wizard" style="display:none;">
    <div class="page-actions"><button class="btn btn-ghost" id="btn-cancel-wizard">← Back</button></div>
    <div class="wizard-grid">
      <div class="wizard-col">
        <h2>1. Campaign settings</h2>
        <div class="field"><label for="wiz-name">Campaign name</label><input id="wiz-name" class="input" placeholder="Q3 launch outreach" /></div>
        <div class="field"><label for="wiz-desc">Description</label><input id="wiz-desc" class="input" placeholder="Optional" /></div>
        <div class="field"><label for="wiz-type">Type</label>
          <select id="wiz-type">
            <option value="cold_outreach">Cold outreach</option>
            <option value="promotion">Promotion</option>
            <option value="follow_up">Follow-up</option>
            <option value="custom">Custom</option>
          </select></div>
      </div>
      <div class="wizard-col">
        <h2>2. Message template</h2>
        <div class="field"><label for="wiz-message">Message text</label>
          <textarea id="wiz-message" class="textarea" rows="4" placeholder="Hi {{name}}, quick note..."></textarea></div>
        <div class="wiz-templates-row">
          <div class="wiz-templates" id="wiz-templates"></div>
          <div class="wiz-template-save">
            <input id="wiz-template-name" class="input" placeholder="template name" />
            <button class="btn btn-ghost btn-sm" id="btn-wiz-save-template">Save as template</button>
          </div>
        </div>
        <p class="hint">Use <code>{{name}}</code>, <code>{{phone}}</code>, <code>{{company}}</code>, <code>{{email}}</code>, <code>{{city}}</code>, <code>{{country}}</code>, <code>{{notes}}</code>. Add <code>|fallback</code> text after a variable to use if empty.</p>
      </div>
      <div class="wizard-col">
        <h2>3. Send settings</h2>
        <div class="field"><label>Delay between sends</label><input id="wiz-min-delay" class="input" type="number" min="0" value="20" />–<input id="wiz-max-delay" class="input" type="number" min="0" value="45" />s</label></div>
        <label class="switch-row"><input type="checkbox" id="wiz-typing" /><span class="switch"></span><span>Simulate typing before each send</span></label>
        <div class="field"><label>Typing duration</label><input id="wiz-typing-min" class="input" type="number" min="0" value="2" />–<input id="wiz-typing-max" class="input" type="number" min="0" value="5" />s</label></div>
        <label class="switch-row"><input type="checkbox" id="wiz-work-hours" /><span class="switch"></span><span>Only send during working hours</span></label>
        <div class="field"><label>Work window</label><input id="wiz-work-start" type="time" value="09:00" />–<input id="wiz-work-end" type="time" value="18:00" /></label></div>
        <div class="field"><label for="wiz-tz">Timezone</label><input id="wiz-tz" class="input" value="UTC" /></div>
        <div class="field"><label for="wiz-daily-limit">Daily send limit (0 = unlimited)</label><input id="wiz-daily-limit" class="input" type="number" min="0" value="0" /></div>
        <div class="field"><label for="wiz-schedule">Schedule for later (optional)</label><input id="wiz-schedule" type="datetime-local" /></div>
        <label class="switch-row"><input type="checkbox" id="wiz-retry" /><span class="switch"></span><span>Auto-retry failed sends</span></label>
        <div class="field"><label>Retries / delay</label><input id="wiz-retry-count" class="input" type="number" min="0" value="1" /> / <input id="wiz-retry-delay" class="input" type="number" min="0" value="120" />s</label></div>
        <label class="switch-row"><input type="checkbox" id="wiz-skip-dup" checked /><span class="switch"></span><span>Skip duplicates within this campaign</span></label>
        <label class="switch-row"><input type="checkbox" id="wiz-skip-blocked" checked /><span class="switch"></span><span>Skip globally blacklisted contacts</span></label>
        <label class="switch-row"><input type="checkbox" id="wiz-skip-contacted" /><span class="switch"></span><span>Skip contacts already messaged</span></label>
      </div>
    </div>
    <div class="wizard-foot">
      <button class="btn btn-primary" id="btn-create-campaign">Create campaign</button>
    </div>
  </section>
</div>`;

  function render() {
    const host = q("campaigns-app");
    if (!host) return;
    host.innerHTML = HTML;
    wire();
  }

  function renderList() {
    const list = q("campaign-list");
    if (!list) return;
    if (!state.current) {
      if (!state.campaigns.length) {
        list.innerHTML = '<div class="camp-empty">No campaigns yet. Click "New campaign" to launch your first cold outreach.</div>';
        return;
      }
      list.innerHTML = state.campaigns.map(c => `
        <div class="camp-row" data-id="${c.id}">
          <div class="camp-row-main">
            <div class="camp-row-title">${escapeHtml(c.name)}</div>
            <div class="camp-row-sub">${escapeHtml(c.campaign_type)} · ${c.sent_count} sent · ${c.failed_count} failed</div>
          </div>
          <span class="camp-status camp-status-${c.status}">${c.status.toUpperCase()}</span>
        </div>
      `).join("");
      $$(".camp-row").forEach(row => {
        row.addEventListener("click", () => openCampaign(row.dataset.id));
      });
    }
  }

  async function refresh() {
    try { state.campaigns = await api.listCampaigns(); }
    catch (e) { toast(e.message, "error"); state.campaigns = []; }
    renderList();
  }

  function openCampaign(id) {
    const c = state.campaigns.find(x => x.id === id);
    if (!c) return;
    state.current = c;
    state.preview = null;
    q("campaigns-dashboard").style.display = "none";
    q("campaigns-live").style.display = "block";
    renderLive(c);
    q("btn-back-dashboard").style.display = "inline-flex";
  }

  function renderLive(c) {
    q("camp-live-title").textContent = c.name;
    const st = q("camp-live-status");
    st.textContent = c.status.toUpperCase();
    st.className = "camp-live-status camp-status camp-status-" + c.status;
    q("camp-sent").textContent = c.sent_count;
    q("camp-failed").textContent = c.failed_count;
    q("camp-total").textContent = c.contact_count || 0;

    const pb = q("camp-progress-bar");
    const pct = c.contact_count ? Math.round((c.sent_count / c.contact_count) * 100) : 0;
    pb.style.width = Math.min(100, pct) + "%";

    ["camp-start", "camp-pause", "camp-stop", "camp-seed"].forEach(id => {
      const el = q(id); if (el) el.style.display = "none";
    });
    if (c.status === "draft" || c.status === "paused" || c.status === "scheduled") {
      q("camp-start").style.display = "inline-flex";
      q("camp-seed").style.display = "inline-flex";
    } else if (c.status === "running") {
      q("camp-pause").style.display = "inline-flex";
      q("camp-stop").style.display = "inline-flex";
    }

    q("camp-start").onclick = async (e) => {
      try { state.current = await api.startCampaign(c.id); toast("Campaign started", "success"); renderLive(state.current); }
      catch (err) { toast(err.message, "error"); }
    };
    q("camp-pause").onclick = async () => {
      try { state.current = await api.pauseCampaign(c.id); toast("Paused", "success"); renderLive(state.current); }
      catch (err) { toast(err.message, "error"); }
    };
    q("camp-stop").onclick = async () => {
      try { state.current = await api.stopCampaign(c.id); toast("Stopped", "success"); renderLive(state.current); }
      catch (err) { toast(err.message, "error"); }
    };
    q("camp-seed").onclick = () => {
      q("csv-upload").click();
    };
    q("csv-upload").onchange = (e) => {
      if (e.target.files[0]) uploadLeads(e.target.files[0]);
      e.target.value = "";
    };

    if (c.status === "running" || c.status === "scheduled") kickProgress(c.id);
    else { if (state.progressTimer) clearInterval(state.progressTimer); state.progressTimer = null; }
  }

  function kickProgress(id) {
    if (state.progressTimer) clearInterval(state.progressTimer);
    fetchProgress(id);
    state.progressTimer = setInterval(() => fetchProgress(id), 5000);
  }

  async function fetchProgress(id) {
    try {
      const p = await api.campaignProgress(id);
      if (p && p.campaign) { state.current = p.campaign; renderLive(state.current); }
      if (state.current && state.current.status !== "running" && state.current.status !== "scheduled") {
        if (state.progressTimer) { clearInterval(state.progressTimer); state.progressTimer = null; }
    }
    } catch (e) { /* ignore network errors while offline */ }
  }

  // ---- wizard
  function showWizard() {
    if (state.current) {
      api.getCampaign(state.current.id).then(c => { state.current = c; renderLive(state.current); });
      q("campaigns-dashboard").style.display = "none";
      q("campaigns-live").style.display = "block";
      return;
    }
    q("campaigns-dashboard").style.display = "none";
    q("campaigns-wizard").style.display = "block";
    loadWizardDeps();
  }

  function hideWizard() {
    q("campaigns-wizard").style.display = "none";
    q("campaigns-dashboard").style.display = "block";
    q("btn-back-dashboard").style.display = "none";
  }

  async function loadWizardDeps() {
    try { state.templates = await api.listTemplates(); } catch (e) { state.templates = []; }
    renderTemplateList();
  }

  function renderTemplateList() {
    const list = q("wiz-templates");
    if (!list) return;
    if (!state.templates.length) { list.innerHTML = '<div class="camp-empty camp-empty-sm">No saved templates.</div>'; return; }
    list.innerHTML = state.templates.map(t => `
      <div class="wiz-template" data-id="${t.id}">
        <div class="wiz-template-name">${escapeHtml(t.name)}</div>
        <div class="wiz-template-body">${escapeHtml((t.body || "").slice(0, 120))}</div>
      </div>
    `).join("");
    $$(".wiz-template").forEach(el => {
      el.addEventListener("click", () => {
        q("wiz-message").value = state.templates.find(x => x.id === el.dataset.id).body;
      });
    });
  }

  async function createCampaign() {
    const name = q("wiz-name").value.trim();
    const body = q("wiz-message").value.trim();
    if (!name) return toast("Campaign name is required", "error");
    if (!body) return toast("Message text is required", "error");
    const payload = {
      name, description: q("wiz-desc").value.trim() || null,
      campaign_type: q("wiz-type").value, message_text: body, media_id: q("wiz-media-id")?.value.trim() || null,
      scheduled_at: q("wiz-schedule").value ? new Date(q("wiz-schedule").value).toISOString() : null,
      config: {
        min_delay_seconds: +(q("wiz-min-delay").value || 20),
        max_delay_seconds: +(q("wiz-max-delay").value || 45),
        typing_enabled: q("wiz-typing").checked,
        typing_min_seconds: +(q("wiz-typing-min").value || 2),
        typing_max_seconds: +(q("wiz-typing-max").value || 5),
        working_hours_enabled: q("wiz-work-hours").checked,
        work_start_time: q("wiz-work-start").value || null,
        work_end_time: q("wiz-work-end").value || null,
        timezone_name: q("wiz-tz").value || "UTC",
        daily_limit: q("wiz-daily-limit").value ? +q("wiz-daily-limit").value : null,
        retry_enabled: q("wiz-retry").checked,
        retry_count: +(q("wiz-retry-count").value || 1),
        retry_delay_seconds: +(q("wiz-retry-delay").value || 120),
        skip_duplicates: q("wiz-skip-dup").checked,
        skip_blocked: q("wiz-skip-blocked").checked,
        skip_contacted: q("wiz-skip-contacted").checked,
      },
    };
    try {
      const c = await api.createCampaign(payload);
      state.current = c;
      hideWizard();
      q("campaigns-dashboard").style.display = "none";
      q("campaigns-live").style.display = "block";
      q("btn-back-dashboard").style.display = "inline-flex";
      renderLive(c);
      await refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function uploadLeads(file) {
    if (!state.current) return;
    try {
      state.preview = await api.uploadLeads(state.current.id, file);
      renderPreview();
    } catch (e) { toast(e.message, "error"); }
  }

  function renderPreview() {
    const container = q("camp-preview");
    if (!container) return;
    container.style.display = "block";
    const p = state.preview;
    const cols = q("csv-columns");
    const headers = p.headers || [];
    cols.innerHTML = headers.map((h, i) => `<option value="${i}">${escapeHtml(h || "")}</option>`).join("");
    const meta = q("csv-meta");
    meta.textContent = `Total: ${p.meta.total} · Valid: ${p.meta.valid} · Invalid: ${p.meta.invalid} · Duplicates: ${p.meta.duplicate}`;
    const errors = q("csv-errors");
    errors.innerHTML = (p.errors || []).map(e => `<li>${escapeHtml(e)}</li>`).join("");
    const sample = q("csv-sample");
    const rows = (p.sample && p.sample.length ? p.sample : p.rows).slice(0, 8);
    sample.innerHTML = rows.map(r => `<tr><td>${escapeHtml(r.name||"")}</td><td>${escapeHtml(r.phone||"")}</td><td>${escapeHtml(r.company||"")}</td><td>${escapeHtml(r.email||"")}</td></tr>`).join("");
  }

  async function confirmSeed() {
    if (!state.preview) return;
    try {
      const res = await api.seedLeads(state.current.id, state.preview.rows);
      toast(`Added ${res.added} contacts (${res.skipped_invalid} invalid skipped)`, "success");
      q("camp-preview").style.display = "none";
      const c = await api.getCampaign(state.current.id);
      state.current = c;
      renderLive(c);
    } catch (e) { toast(e.message, "error"); }
  }

  async function saveTemplate() {
    const name = q("wiz-template-name").value.trim();
    const body = q("wiz-message").value.trim();
    if (!name || !body) return toast("Template name and body required", "error");
    try {
      await api.createTemplate({ name, body });
      toast("Template saved", "success");
      q("wiz-template-name").value = "";
      await loadWizardDeps();
    } catch (e) { toast(e.message, "error"); }
  }

  function wire() {
    q("btn-new-campaign").addEventListener("click", () => { q("campaigns-dashboard").style.display="none"; q("campaigns-wizard").style.display="block"; loadWizardDeps(); });
    q("btn-cancel-wizard").addEventListener("click", hideWizard);
    q("btn-back-dashboard").addEventListener("click", () => { state.current = null; hideWizard(); q("campaigns-live").style.display="none"; q("campaigns-dashboard").style.display="block"; });
    q("btn-create-campaign").addEventListener("click", createCampaign);
    q("btn-seed").addEventListener("click", confirmSeed);
    q("btn-wiz-save-template").addEventListener("click", saveTemplate);
  }

  // expose helpers
  window.CRM.campaigns = { refresh, showWizard };

  window.CRM.campaigns.init = () => { render(); refresh(); };
})();
