/* ============================================================
   WhatsApp CRM — Inbox (conversations, chat, details panel)
   ============================================================ */
(function () {
  "use strict";

  const state = {
    conversations: [],
    activeId: null,
    search: "",
    unreadOnly: false,
    contactTags: [],
    loadedTags: false,
  };

  const EMOJIS = [
    "😀","😄","😁","😂","🤣","😊","😇","🙂","😉","😍","🥰","😘","😎","🤗","🤔","😴","😅","😭",
    "👍","👎","👏","🙌","🤝","💪","🙏","👋","🤙","✌️","🤞","🫶","❤️","🧡","💛","💚","💙","💜",
    "🔥","✨","🎉","🎊","🥳","🎯","🚀","⭐","💡","📈","📊","💰","🏆","✅","❌","⚠️","❗","❓",
    "👀","🤯","🥺","😤","😱","🤑","🤫","😶","🤷","🙈","🙉","🙊","🐱","🐶","🦋","🌈","🍀","🪄",
  ];

  const inbox = {
    state,

    init() {
      const { $ } = window.CRM;

      // ----- conversation list interactions -----
      $("#conv-search").addEventListener("input", window.CRM.debounce((e) => {
        state.search = e.target.value.trim();
        this.refreshList();
      }, 300));

      $("#conv-filter-unread").addEventListener("click", (e) => {
        state.unreadOnly = !state.unreadOnly;
        e.currentTarget.classList.toggle("toggled", state.unreadOnly);
        this.refreshList();
      });

      // ----- composer -----
      const input = $("#compose-input");
      const sendBtn = $("#btn-send");

      const updateSendState = () => {
        sendBtn.disabled = !state.activeId;
      };

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.sendText();
        }
      });
      sendBtn.addEventListener("click", () => this.sendText());

      $("#btn-emoji").addEventListener("click", () => {
        const picker = $("#emoji-picker");
        picker.hidden = !picker.hidden;
        if (!picker.hidden && !picker.children.length) {
          EMOJIS.forEach((em) => {
            const b = document.createElement("button");
            b.textContent = em;
            b.type = "button";
            b.addEventListener("click", () => {
              input.value += em;
              input.focus();
            });
            picker.appendChild(b);
          });
        }
      });

      $("#btn-archive").addEventListener("click", async () => {
        if (!state.activeId) return;
        try {
          await window.CRM.api.toggleArchive(state.activeId, true);
          window.CRM.toast("Conversation archived", "success");
          this.openConversation(null);
          this.refreshList();
        } catch (e) {
          window.CRM.toast(e.message, "error");
        }
      });

      // Start a fresh conversation from the empty state
      const startBtn = $("#btn-start-conv");
      if (startBtn) {
        startBtn.addEventListener("click", () => {
          if (window.CRM.contacts) window.CRM.contacts.openEditor(null);
        });
      }

      $("#btn-open-contact").addEventListener("click", () => {
        const conv = this.currentConversation();
        if (conv && window.CRM.contacts) window.CRM.contacts.openEditor(conv.contact);
      });

      // ----- mobile navigation -----
      const inboxList = document.querySelector(".inbox-list");
      const detailsPanel = $("#inbox-details");
      const setListOpen = (open) => inboxList.classList.toggle("open", open);

      const showListBtn = $("#btn-show-list");
      if (showListBtn) showListBtn.addEventListener("click", () => setListOpen(true));

      $("#conv-list-close").addEventListener("click", () => setListOpen(false));
      $("#btn-back-list").addEventListener("click", () => setListOpen(true));

      $("#btn-toggle-details").addEventListener("click", () => {
        detailsPanel.hidden = false;
        detailsPanel.classList.toggle("open");
      });

      $("#details-close").addEventListener("click", () => detailsPanel.classList.remove("open"));

      // ----- media upload -----
      const fileInput = $("#file-input");
      fileInput.addEventListener("change", async () => {
        const files = Array.from(fileInput.files);
        fileInput.value = "";
        if (!files.length) return;
        await this.sendFiles(files);
      });

      // ----- realtime -----
      window.CRM.wsBus.on("message.new", (msg) => this.onNewMessage(msg));
      window.CRM.wsBus.on("message.updated", (upd) => this.onStatusUpdate(upd));
      window.CRM.wsBus.on("conversation.updated", () => this.refreshList(true));
      window.CRM.wsBus.on("conversation.read", () => this.refreshList(true));

      this.refreshList();
      updateSendState();
    },

    /* ================= list ================= */
    async refreshList(silent) {
      const { api } = window.CRM;
      try {
        const params = { limit: 200 };
        if (state.search) params.search = state.search;
        if (state.unreadOnly) params.unread_only = true;
        state.conversations = await api.listConversations(params);
        this.renderList();

        if (!silent) {
          api.conversationCounts().then((c) => {
            const badge = document.getElementById("nav-unread");
            if (badge) {
              badge.hidden = !c.unread;
              badge.textContent = c.unread > 99 ? "99+" : c.unread;
            }
          });
        }
      } catch (e) {
        if (!silent) window.CRM.toast(e.message, "error");
      }
    },

    renderList() {
      const list = document.getElementById("conv-list");
      const { $, escapeHtml, avatarEl, fmtDate } = window.CRM;

      if (!state.conversations.length) {
        list.innerHTML =
          '<div class="conv-list-empty">' +
          (state.search
            ? "No conversations match your search."
            : "No conversations yet. Incoming replies will appear here.") +
          "</div>";
        return;
      }

      list.innerHTML = "";
      state.conversations.forEach((conv) => {
        const c = conv.contact || {};
        const item = document.createElement("div");
        item.className = "conv-item" + (conv.id === state.activeId ? " active" : "");
        item.dataset.id = conv.id;

        const unread = conv.unread_count || 0;
        const preview = conv.last_message_preview || "No messages yet";
        const name = c.name || c.phone || "Unknown";
        const lastAt = conv.last_message_at
          ? fmtDate(conv.last_message_at)
          : (c.created_at ? fmtDate(c.created_at) : "");

        const av = avatarEl(name, c.phone, 42);

        const main = document.createElement("div");
        main.className = "conv-main";
        main.innerHTML =
          '<div class="conv-top">' +
          '<span class="conv-name">' + escapeHtml(name) + "</span>" +
          '<span class="conv-time">' + escapeHtml(lastAt) + "</span>" +
          "</div>" +
          '<div class="conv-preview' + (unread ? " unread" : "") + '">' +
          (conv.last_message_type && conv.last_message_type !== "text"
            ? "📎 "
            : "") + escapeHtml(preview) +
          "</div>";

        item.appendChild(av);
        item.appendChild(main);

        if (unread) {
          const b = document.createElement("span");
          b.className = "conv-unread";
          b.textContent = unread > 99 ? "99+" : unread;
          item.appendChild(b);
        }

        item.addEventListener("click", () => {
          if (state.activeId !== conv.id) this.openConversation(conv.id);
          else this.renderDetails();
        });

        list.appendChild(item);
      });
    },

    currentConversation() {
      return state.conversations.find((c) => c.id === state.activeId) || null;
    },

    /* ================= open / chat ================= */
    async openConversation(id) {
      const { api, $ } = window.CRM;
      state.activeId = id;

      // enable/disable the composer + send button based on selection
      const sendBtn = $("#btn-send");
      if (sendBtn) sendBtn.disabled = !id;
      const input = $("#compose-input");
      if (input) input.disabled = !id;

      $("#chat-empty").hidden = !!id;
      const windowEl = $("#chat-window");
      windowEl.hidden = !id;
      if (!id) {
        $("#inbox-details").hidden = true;
        $("#chat-body").innerHTML = "";
        this.renderList();
        return;
      }

      this.renderList();
      const inboxList = document.querySelector(".inbox-list");
      if (inboxList) inboxList.classList.remove("open");
      const detailsPanel = $("#inbox-details");
      if (detailsPanel) detailsPanel.classList.remove("open");
      await this.loadMessages(id);
      api.markRead(id).catch(() => {});

      const conv = this.currentConversation();
      if (conv) {
        $("#chat-title").textContent = conv.contact
          ? conv.contact.name || conv.contact.phone
          : "Contact";
        $("#chat-avatar").textContent = window.CRM.initials(
          conv.contact ? conv.contact.name || conv.contact.phone : "?", "?"
        );
        $("#chat-avatar").style.background = window.CRM.avatarColor(
          conv.contact ? conv.contact.phone : ""
        );
      }
      this.renderDetails();
    },

    async loadMessages(id) {
      const { api } = window.CRM;
      try {
        const msgs = await api.listMessages(id);
        this.renderMessages(msgs);
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    renderMessages(msgs) {
      const body = document.getElementById("chat-body");
      body.innerHTML = "";
      if (!msgs.length) {
        const empty = document.createElement("div");
        empty.className = "conv-list-empty";
        empty.textContent = "No messages yet. Send the first one below.";
        body.appendChild(empty);
        return;
      }

      let lastDay = null;
      msgs.forEach((m) => {
        const day = new Date(m.timestamp).toDateString();
        if (day !== lastDay) {
          lastDay = day;
          const div = document.createElement("div");
          div.className = "day-divider";
          div.textContent = window.CRM.dayLabel(m.timestamp);
          body.appendChild(div);
        }
        body.appendChild(this.messageEl(m));
      });

      this.scrollToBottom(true);
    },

    messageEl(m) {
      const el = document.createElement("div");
      el.className = "msg " + (m.direction === "outgoing" ? "out" : "in");
      el.dataset.msgId = m.id;
      el.dataset.waId = m.whatsapp_message_id || "";
      el.dataset.status = m.status || "";

      const bubble = document.createElement("div");
      bubble.className = "msg-bubble";

      if (m.msg_type === "text") {
        if (m.text) {
          const t = document.createElement("div");
          t.className = "msg-text";
          t.textContent = m.text;
          bubble.appendChild(t);
        }
      } else if (m.media) {
        bubble.appendChild(this.mediaEl(m));
        if (m.text || m.caption) {
          const c = document.createElement("div");
          c.className = "msg-caption";
          c.textContent = m.caption || m.text;
          bubble.appendChild(c);
        }
      } else {
        const t = document.createElement("div");
        t.textContent = "[Media message]";
        bubble.appendChild(t);
      }

      el.appendChild(bubble);

      if (m.direction === "outgoing") {
        el.appendChild(this.statusEl(m.status, m.timestamp));
      } else if (m.timestamp) {
        const meta = document.createElement("div");
        meta.className = "msg-meta";
        meta.textContent = window.CRM.fmtTime(m.timestamp);
        el.appendChild(meta);
      }

      return el;
    },

    mediaEl(m) {
      const media = m.media;
      const url = media.url
        ? (media.url.startsWith("/") ? window.CRM.api.base + media.url : media.url)
        : null;

      if ((m.msg_type === "image" || m.msg_type === "sticker") && url) {
        const img = document.createElement("img");
        img.className = "msg-media" + (m.msg_type === "sticker" ? " sticker" : "");
        img.src = url;
        img.loading = "lazy";
        img.addEventListener("click", () => window.open(url, "_blank"));
        return img;
      }
      if (m.msg_type === "video" && url) {
        const v = document.createElement("video");
        v.className = "msg-media";
        v.controls = true;
        v.preload = "metadata";
        v.src = url;
        return v;
      }
      if (m.msg_type === "audio" && url) {
        const a = document.createElement("audio");
        a.controls = true;
        a.preload = "metadata";
        a.style.width = "240px";
        a.src = url;
        return a;
      }
      // document (or anything else)
      const a = document.createElement("a");
      a.className = "msg-media doc";
      a.href = url || "#";
      a.target = "_blank";
      a.rel = "noopener";
      a.innerHTML =
        '<span style="font-size:22px">📄</span>' +
        '<span style="min-width:0"><strong style="display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' +
        window.CRM.escapeHtml(media.file_name) +
        "</strong><small>" + window.CRM.escapeHtml(media.mime_type) + "</small></span>";
      return a;
    },

    statusEl(status, timestamp) {
      const meta = document.createElement("div");
      meta.className = "msg-meta";
      const icons = {
        sent: { icon: "✓", cls: "pending", label: "Sent" },
        delivered: { icon: "✓✓", cls: "", label: "Delivered" },
        read: { icon: "✓✓", cls: "read", label: "Read" },
        failed: { icon: "⚠", cls: "pending", label: "Failed" },
        received: { icon: "", cls: "pending", label: "Received" },
      };
      const s = icons[status] || icons.sent;
      meta.innerHTML =
        window.CRM.escapeHtml(window.CRM.fmtTime(timestamp)) +
        ' <span class="status-ico ' + s.cls + '" title="' + s.label + '">' + s.icon + "</span>";
      return meta;
    },

    scrollToBottom(smooth) {
      const body = document.getElementById("chat-body");
      body.scrollTo({ top: body.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    },

    /* ================= send ================= */
    async sendText() {
      const input = document.getElementById("compose-input");
      const text = input.value.trim();
      if (!text || !state.activeId) return;
      input.value = "";
      document.getElementById("emoji-picker").hidden = true;

      try {
        const msg = await window.CRM.api.sendMessage(state.activeId, { type: "text", text });
        this.appendMessage(msg);
      } catch (e) {
        input.value = text;
        window.CRM.toast(e.message, "error");
      }
    },

    async sendFiles(files) {
      const progressWrap = document.getElementById("upload-progress");
      const fill = document.getElementById("progress-fill");
      const label = document.getElementById("upload-label");
      progressWrap.hidden = false;

      try {
        for (let i = 0; i < files.length; i++) {
          const f = files[i];
          label.textContent = "Uploading " + f.name + "…";
          fill.style.width = "20%";
          const res = await window.CRM.api.uploadMedia(f, state.activeId);
          fill.style.width = "70%";
          const type = res.media_type || "document";
          const msg = await window.CRM.api.sendMessage(state.activeId, {
            type,
            media_id: res.id,
            caption: "",
          });
          this.appendMessage(msg);
          fill.style.width = "100%";
        }
      } catch (e) {
        window.CRM.toast(e.message, "error");
      } finally {
        fill.style.width = "0%";
        progressWrap.hidden = true;
      }
    },

    appendMessage(msg) {
      const body = document.getElementById("chat-body");
      // dedupe: never render the same message twice
      if (msg && msg.id && body.querySelector('[data-msg-id="' + msg.id + '"]')) {
        this.refreshList(true);
        return;
      }
      const empty = body.querySelector(".conv-list-empty");
      if (empty) empty.remove();
      body.appendChild(this.messageEl(msg));
      this.scrollToBottom(true);
      this.refreshList(true);
    },

    /* ================= realtime ================= */
    onNewMessage(msg) {
      if (msg.conversation_id === state.activeId) {
        this.appendMessage(msg);
      } else {
        this.refreshList(true);
      }
    },

    onStatusUpdate(upd) {
      const body = document.getElementById("chat-body");
      const items = window.CRM.$$("[data-wa-id]", body).filter(
        (el) => el.dataset.waId === upd.whatsapp_message_id
      );
      if (items.length) {
        items.forEach((el) => {
          el.dataset.status = upd.status;
          const meta = el.querySelector(".msg-meta");
          if (meta) {
            const s = el.querySelector(".status-ico");
            if (s) {
              const icons = {
                sent: { icon: "✓", cls: "pending" },
                delivered: { icon: "✓✓", cls: "" },
                read: { icon: "✓✓", cls: "read" },
                failed: { icon: "⚠", cls: "pending" },
              };
              const i = icons[upd.status] || icons.sent;
              s.className = "status-ico " + i.cls;
              s.textContent = i.icon;
            }
          }
        });
      }
      this.refreshList(true);
    },

    /* ================= details panel ================= */
    renderDetails() {
      const conv = this.currentConversation();
      const panel = document.getElementById("inbox-details");
      const body = document.getElementById("details-body");
      if (!conv) {
        panel.hidden = true;
        return;
      }
      panel.hidden = false;
      const c = conv.contact || {};
      const { escapeHtml, avatarEl, fmtFull } = window.CRM;

      body.innerHTML = "";
      const profile = document.createElement("div");
      profile.className = "details-profile";
      const av = avatarEl(c.name || c.phone, c.phone, 64);
      profile.appendChild(av);
      profile.innerHTML +=
        '<div class="details-name">' + escapeHtml(c.name || "Unknown") + "</div>" +
        '<div class="details-phone">' + escapeHtml(c.phone || "") + "</div>";
      body.appendChild(profile);

      const tagsSection = document.createElement("div");
      tagsSection.className = "details-section";
      tagsSection.innerHTML = "<h4>Tags</h4><div class='tag-row' id='details-tags'></div>";
      body.appendChild(tagsSection);

      const info = document.createElement("div");
      info.className = "details-section";
      info.innerHTML =
        "<h4>Information</h4>" +
        "<div class='info-row'><span>Email</span><span>" +
        (c.email ? '<a href="mailto:' + escapeHtml(c.email) + '">' + escapeHtml(c.email) + "</a>" : "—") +
        "</span></div>" +
        "<div class='info-row'><span>Company</span><span>" + escapeHtml(c.company || "—") + "</span></div>" +
        "<div class='info-row'><span>Added</span><span>" + (c.created_at ? fmtFull(c.created_at) : "—") + "</span></div>" +
        "<div class='info-row'><span>Conversation</span><span>" + escapeHtml(conv.id.slice(0, 8)) + "</span></div>";
      body.appendChild(info);

      const notes = document.createElement("div");
      notes.className = "details-section";
      notes.innerHTML = "<h4>Notes</h4>";
      const noteForm = document.createElement("div");
      noteForm.style.display = "flex";
      noteForm.style.gap = "8px";
      noteForm.style.marginBottom = "10px";
      noteForm.innerHTML =
        '<input class="compose-input" id="note-input" placeholder="Add a note…" />' +
        '<button class="btn btn-primary btn-sm" id="note-add">Add</button>';
      notes.appendChild(noteForm);
      const noteList = document.createElement("div");
      noteList.id = "note-list";
      notes.appendChild(noteList);
      body.appendChild(notes);

      this.renderTags(conv.contact_id, c.tags || []);
      this.loadNotes(conv.contact_id, noteList);

      const noteInput = document.getElementById("note-input");
      noteInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this.addNote(conv.contact_id, noteInput, noteList);
      });
      document.getElementById("note-add").addEventListener("click", () =>
        this.addNote(conv.contact_id, noteInput, noteList)
      );
    },

    async renderTags(contactId, currentTags) {
      const container = document.getElementById("details-tags");
      if (!container) return;
      let tags = currentTags;
      if (!state.loadedTags) {
        try {
          window.CRM.stateTags = await window.CRM.api.listTags();
          state.loadedTags = true;
        } catch (e) {
          window.CRM.stateTags = [];
        }
      }
      const allTags = window.CRM.stateTags || [];
      const currentIds = new Set(tags.map((t) => t.id));

      container.innerHTML = "";
      if (!allTags.length) {
        container.innerHTML = '<span style="color:var(--text-3);font-size:12.5px">No tags yet — create them in Settings.</span>';
        return;
      }
      allTags.forEach((t) => {
        const pill = document.createElement("button");
        pill.className = "tag-pill" + (currentIds.has(t.id) ? " selected" : "");
        pill.style.background = t.color;
        pill.textContent = t.name;
        pill.addEventListener("click", async () => {
          const next = new Set(currentIds);
          if (next.has(t.id)) next.delete(t.id);
          else next.add(t.id);
          try {
            await window.CRM.api.assignTags(contactId, Array.from(next));
            const conv = this.currentConversation();
            if (conv && conv.contact) {
              conv.contact.tags = allTags.filter((x) => next.has(x.id));
              this.renderDetails();
            }
          } catch (e) {
            window.CRM.toast(e.message, "error");
          }
        });
        container.appendChild(pill);
      });
    },

    async loadNotes(contactId, listEl) {
      try {
        const notes = await window.CRM.api.listNotes(contactId);
        listEl.innerHTML = "";
        if (!notes.length) {
          listEl.innerHTML =
            '<div style="color:var(--text-3);font-size:12.5px">No notes yet.</div>';
          return;
        }
        notes.forEach((n) => {
          const item = document.createElement("div");
          item.className = "note-item";
          item.innerHTML =
            "<div>" + window.CRM.escapeHtml(n.content) + "</div>" +
            '<div class="note-meta"><span>' + window.CRM.escapeHtml(n.author_name) +
            " · " + window.CRM.fmtDate(n.created_at) + "</span>" +
            '<button class="note-del" title="Delete">✕</button></div>';
          item.querySelector(".note-del").addEventListener("click", async () => {
            try {
              await window.CRM.api.deleteNote(n.id);
              this.loadNotes(contactId, listEl);
            } catch (e) {
              window.CRM.toast(e.message, "error");
            }
          });
          listEl.appendChild(item);
        });
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },

    async addNote(contactId, input, listEl) {
      const content = input.value.trim();
      if (!content) return;
      try {
        await window.CRM.api.addNote(contactId, content);
        input.value = "";
        this.loadNotes(contactId, listEl);
      } catch (e) {
        window.CRM.toast(e.message, "error");
      }
    },
  };

  window.CRM = window.CRM || {};
  window.CRM.inbox = inbox;

  document.addEventListener("DOMContentLoaded", () => inbox.init());
})();
