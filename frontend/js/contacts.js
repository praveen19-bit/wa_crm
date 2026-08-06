/* ============================================================
   WhatsApp CRM — Contacts view
   ============================================================ */
(function () {
  "use strict";

  const state = {
    contacts: [],
    search: "",
    tagFilter: "",
    page: 1,
    tags: [],
  };

  const contacts = {
    state,

    init() {
      const { $ } = window.CRM;

      $("#btn-add-contact").addEventListener("click", () => this.openEditor(null));
      $("#btn-export-csv").addEventListener("click", () => {
        window.CRM.api
          .exportCsv()
          .then(() => window.CRM.toast("Contacts exported", "success"))
          .catch((e) => window.CRM.toast(e.message, "error"));
      });
      $("#csv-import").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        e.target.value = "";
        if (!file) return;
        try {
          const res = await window.CRM.api.importCsv(file);
          window.CRM.toast(
            "Import complete: " + res.created + " created, " + res.skipped + " skipped, " + res.failed + " failed",
            res.failed ? "error" : "success"
          );
          this.refresh();
        } catch (err) {
          window.CRM.toast(err.message, "error");
        }
      });

      $("#contact-search").addEventListener("input", window.CRM.debounce((e) => {
        state.search = e.target.value.trim();
        this.refresh();
      }, 300));

      $("#contact-tag-filter").addEventListener("change", (e) => {
        state.tagFilter = e.target.value;
        this.refresh();
      });

      this.loadTags();
    },

    async loadTags() {
      try {
        state.tags = await window.CRM.api.listTags();
        const select = document.getElementById("contact-tag-filter");
        select.innerHTML = '<option value="">All tags</option>';
        state.tags.forEach((t) => {
          const o = document.createElement("option");
          o.value = t.id;
          o.textContent = t.name;
          select.appendChild(o);
        });
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    async refresh() {
      const { api, $, avatarEl, escapeHtml, fmtDate } = window.CRM;
      try {
        const params = { limit: 200 };
        if (state.search) params.search = state.search;
        if (state.tagFilter) params.tag_id = state.tagFilter;
        state.contacts = await api.listContacts(params);

        $("#contacts-sub").textContent = state.contacts.length + " contacts";
        const tbody = $("#contacts-body");
        tbody.innerHTML = "";
        $("#contacts-empty").hidden = state.contacts.length > 0;

        state.contacts.forEach((c) => {
          const tr = document.createElement("tr");

          const tdContact = document.createElement("td");
          const cell = document.createElement("div");
          cell.className = "cell-contact";
          cell.appendChild(avatarEl(c.name, c.phone, 36));
          const wrap = document.createElement("div");
          wrap.innerHTML =
            '<div class="cell-name">' + escapeHtml(c.name || "Unknown") + "</div>" +
            (c.email ? '<div class="cell-sub">' + escapeHtml(c.email) + "</div>" : "");
          cell.appendChild(wrap);
          cell.addEventListener("click", () => {
            if (c.conversation_id) {
              window.CRM.showView("inbox");
              window.CRM.inbox.openConversation(c.conversation_id);
            } else {
              this.openEditor(c);
            }
          });
          tdContact.appendChild(cell);
          tr.appendChild(tdContact);

          const tdPhone = textTd(escapeHtml(c.phone || "—"));
          tdPhone.dataset.label = "Phone";
          tr.appendChild(tdPhone);

          const tdCompany = textTd(escapeHtml(c.company || "—"));
          tdCompany.dataset.label = "Company";
          tr.appendChild(tdCompany);

          const tdTags = document.createElement("td");
          tdTags.dataset.label = "Tags";
          (c.tags || []).forEach((t) => {
            const pill = document.createElement("span");
            pill.className = "tag-mini";
            pill.style.background = t.color;
            pill.textContent = t.name;
            tdTags.appendChild(pill);
          });
          if (!(c.tags || []).length) tdTags.textContent = "—";
          tr.appendChild(tdTags);

          const tdLast = textTd(escapeHtml(c.last_message_preview || "—"));
          tdLast.dataset.label = "Last message";
          tr.appendChild(tdLast);

          const tdAdded = textTd(escapeHtml(fmtDate(c.created_at)));
          tdAdded.dataset.label = "Added";
          tr.appendChild(tdAdded);

          const tdAct = document.createElement("td");
          tdAct.dataset.label = "Manage";
          const actions = document.createElement("div");
          actions.className = "row-actions";
          const editBtn = mkIconBtn("✏️", "Edit");
          editBtn.addEventListener("click", () => this.openEditor(c));
          const delBtn = mkIconBtn("🗑️", "Delete");
          delBtn.addEventListener("click", () => this.confirmDelete(c));
          actions.appendChild(editBtn);
          actions.appendChild(delBtn);
          tdAct.appendChild(actions);
          tr.appendChild(tdAct);

          tbody.appendChild(tr);
        });
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    confirmDelete(c) {
      window.CRM.openModal(
        "Delete contact",
        "<p>Delete <b>" + window.CRM.escapeHtml(c.name || c.phone) + "</b>? " +
          "Their conversations and messages will also be removed.</p>",
        [
          { label: "Cancel", cls: "btn-ghost", value: false },
          { label: "Delete", cls: "btn-danger", value: true },
        ]
      ).then(async (confirmed) => {
        if (!confirmed) return;
        try {
          await window.CRM.api.deleteContact(c.id);
          window.CRM.toast("Contact deleted", "success");
          this.refresh();
        } catch (e) {
          window.CRM.toast(e.message, "error");
        }
      });
    },

    /* ---------------- editor modal ---------------- */
    openEditor(contact) {
      const isEdit = !!contact;
      const c = contact || {};
      const body =
        '<div class="field"><label>Name</label><input id="ed-name" type="text" value="' +
        window.CRM.escapeHtml(c.name || "") + '" placeholder="John Carter" /></div>' +
        '<div class="field"><label>Phone (with country code)</label><input id="ed-phone" type="text" value="' +
        window.CRM.escapeHtml(c.phone || "") + '" placeholder="+15551234567" /></div>' +
        '<div class="field"><label>Email</label><input id="ed-email" type="email" value="' +
        window.CRM.escapeHtml(c.email || "") + '" placeholder="john@acme.io" /></div>' +
        '<div class="field"><label>Company</label><input id="ed-company" type="text" value="' +
        window.CRM.escapeHtml(c.company || "") + '" placeholder="Acme Inc" /></div>';

      window.CRM
        .openModal(isEdit ? "Edit contact" : "New contact", body, [
          { label: "Cancel", cls: "btn-ghost", value: null },
          { label: isEdit ? "Save" : "Create", cls: "btn-primary", value: "submit" },
        ])
        .then(async (result) => {
          if (result !== "submit") return;
          const data = {
            name: document.getElementById("ed-name").value.trim(),
            phone: document.getElementById("ed-phone").value.trim(),
            email: document.getElementById("ed-email").value.trim() || null,
            company: document.getElementById("ed-company").value.trim() || null,
          };
          if (!data.phone) {
            window.CRM.toast("Phone is required", "error");
            return;
          }
          try {
            if (isEdit) {
              await window.CRM.api.updateContact(c.id, data);
              window.CRM.toast("Contact updated", "success");
            } else {
              const created = await window.CRM.api.createContact(data);
              window.CRM.toast("Contact created — start the conversation", "success");
              let convId = null;
              try {
                const conv = await window.CRM.api.createConversation(created.id);
                convId = conv.id;
              } catch (e) {
                /* conversation may already exist */
              }
              this.refresh();
              if (window.CRM.inbox) window.CRM.inbox.refreshList();
              if (convId) {
                window.CRM.showView("inbox");
                window.CRM.inbox.openConversation(convId);
              }
              return;
            }
            this.refresh();
            if (window.CRM.inbox) window.CRM.inbox.refreshList();
          } catch (e) {
            window.CRM.toast(e.message, "error");
          }
        });
    },
  };

  function textTd(html) {
    const td = document.createElement("td");
    td.innerHTML = html;
    return td;
  }

  function mkIconBtn(icon, title) {
    const b = document.createElement("button");
    b.className = "icon-btn";
    b.innerHTML = icon;
    b.title = title;
    return b;
  }

  window.CRM = window.CRM || {};
  window.CRM.contacts = contacts;

  document.addEventListener("DOMContentLoaded", () => contacts.init());
})();
