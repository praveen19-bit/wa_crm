// CDP-based UI smoke test: loads app.html with a real session via Chrome DevTools Protocol.
// Run: node cdp_ui_test.js <chrome-path> <url> <api-base>
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME = process.argv[2] || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const FRONT_URL = process.argv[3] || "http://127.0.0.1:5500/app.html";
const API_BASE = process.argv[4] || "http://127.0.0.1:8000";

const PORT = 9223;
const PROFILE = path.join(process.env.TEMP, "crm-cdp-profile-" + Date.now());

const results = [];
function record(name, ok, detail) {
  results.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function send(cdp, method, params) {
  return new Promise((resolve) => {
    const id = ++send._id;
    send._pending[id] = resolve;
    cdp.send(JSON.stringify({ id, method, params: params || {} }));
  });
}
send._id = 0;
send._pending = {};

async function main() {
  const chrome = spawn(CHROME, [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    `--user-data-dir=${PROFILE}`,
    `--remote-debugging-port=${PORT}`,
    "about:blank",
  ], { stdio: "ignore" });

  try {
    // 1. get a real token
    const login = await fetch(API_BASE + "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "demo@test.com", password: "password123" }),
    });
    const token = (await login.json()).access_token;
    record("fetch token", !!token);

    // 2. wait for debugger
    let target = null;
    for (let i = 0; i < 40; i++) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
        const page = list.find((t) => t.type === "page");
        if (page) {
          target = page;
          break;
        }
      } catch (e) {}
      await sleep(250);
    }
    if (!target) {
      record("chrome debugging", false, "no page target");
      return;
    }

    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((res, rej) => {
      ws.onopen = res;
      ws.onerror = rej;
    });
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.id && send._pending[msg.id]) {
        send._pending[msg.id](msg.result);
        delete send._pending[msg.id];
      }
    };

    const evaluate = async (expr) => {
      const res = await send(ws, "Runtime.evaluate", {
        expression: expr,
        awaitPromise: true,
        returnByValue: true,
      });
      if (res.exceptionDetails) {
        throw new Error(res.exceptionDetails.exception?.description || res.exceptionDetails.text);
      }
      return res.result.value;
    };

    // 3. seed localStorage on the right origin, then navigate to app
    await send(ws, "Page.enable", {});
    await evaluate(`location.href = "${FRONT_URL}"; true`);
    await sleep(1200);
    await evaluate(`localStorage.setItem("crm_token", ${JSON.stringify(token)});
                    localStorage.setItem("crm_user", JSON.stringify({name:"Demo User", email:"demo@test.com"}));
                    localStorage.setItem("crm_theme", "dark");
                    location.reload(); true`);
    await sleep(3500);

    const state = await evaluate(`(() => {
      const q = (s) => document.querySelector(s);
      return {
        appLoaded: !!q(".app"),
        inboxVisible: !!q("#view-inbox.active"),
        convCount: q("#conv-list") ? q("#conv-list").children.length : -1,
        chatVisible: !!q("#chat-window") && !q("#chat-window").hidden,
        chatEmptyVisible: !!q("#chat-empty") && !q("#chat-empty").hidden,
        navItems: document.querySelectorAll(".nav-item").length,
        username: q("#user-name") ? q("#user-name").textContent : "",
      };
    })()`);

    record("app shell rendered", !!state.appLoaded, JSON.stringify(state));
    record("inbox view active", !!state.inboxVisible);
    record("nav has 4 items", state.navItems === 4);
    record("conversations listed", state.convCount >= 1, "count=" + state.convCount);
    record("chat empty state OR chat open", state.chatEmptyVisible || state.chatVisible);

    // open the first conversation and verify messages render
    const opened = await evaluate(`(() => {
      const first = document.querySelector(".conv-item");
      if (!first) return false;
      first.click();
      return true;
    })()`);
    await sleep(2500);
    const chat = await evaluate(`(() => {
      const msgs = document.querySelectorAll("#chat-body .msg");
      const title = document.querySelector("#chat-title");
      const detail = document.querySelector("#inbox-details");
      return {
        msgCount: msgs.length,
        title: title ? title.textContent : "",
        hasBubbles: document.querySelectorAll("#chat-body .msg-bubble").length,
        detailsVisible: detail ? !detail.hidden : false,
        bodyText: document.querySelector("#chat-body") ? document.querySelector("#chat-body").textContent.slice(0, 120) : "",
      };
    })()`);
    record("opened conversation", opened);
    record("messages rendered", chat.msgCount >= 1, JSON.stringify(chat));

    // switch views
    const nav = await evaluate(`(() => {
      document.querySelector('.nav-item[data-view="contacts"]').click();
      return true;
    })()`);
    await sleep(1500);
    const contactsView = await evaluate(`(() => {
      const tbody = document.querySelector("#contacts-body");
      return {
        active: !!document.querySelector("#view-contacts.active"),
        rows: tbody ? tbody.children.length : -1,
      };
    })()`);
    record("contacts view", contactsView.active && contactsView.rows >= 1, JSON.stringify(contactsView));

    const analyticsView = await evaluate(`(() => {
      document.querySelector('.nav-item[data-view="analytics"]').click();
      return true;
    })()`);
    await sleep(1500);
    const an = await evaluate(`(() => ({
      active: !!document.querySelector("#view-analytics.active"),
      cards: document.querySelectorAll("#analytics-cards .stat-card").length,
    }))()`);
    record("analytics view", an.active && an.cards === 8, JSON.stringify(an));

    const settingsView = await evaluate(`(() => {
      document.querySelector('.nav-item[data-view="settings"]').click();
      return true;
    })()`);
    await sleep(1500);
    const st = await evaluate(`(() => ({
      active: !!document.querySelector("#view-settings.active"),
      webhook: document.querySelector("#webhook-url") ? document.querySelector("#webhook-url").textContent.slice(0, 60) : "",
    }))()`);
    record("settings view", st.active, JSON.stringify(st));

    ws.close();
  } catch (e) {
    record("cdp error", false, e.message);
  } finally {
    chrome.kill();
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) {}
  }

  console.log(results.join("\n"));
  const failed = results.filter((r) => r.startsWith("FAIL")).length;
  process.exit(failed ? 1 : 0);
}

main();
