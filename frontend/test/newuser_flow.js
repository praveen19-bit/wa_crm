// Registers a brand-new user and inspects the first screen they see in app.html
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9226;
const PROFILE = path.join(process.env.TEMP, "crm-cdp-new-" + Date.now());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let _id = 0;
const pending = {};

function send(cdp, method, params) {
  return new Promise((resolve) => {
    const id = ++_id;
    pending[id] = resolve;
    cdp.send(JSON.stringify({ id, method, params: params || {} }));
  });
}

(async () => {
  const chrome = spawn(CHROME, [
    "--headless=new", "--disable-gpu", "--no-first-run",
    `--user-data-dir=${PROFILE}`, `--remote-debugging-port=${PORT}`, "about:blank",
  ], { stdio: "ignore" });
  try {
    let target;
    for (let i = 0; i < 40; i++) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
        const page = list.find((t) => t.type === "page");
        if (page) { target = page; break; }
      } catch (e) {}
      await sleep(250);
    }
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.id && pending[msg.id]) { pending[msg.id](msg.result); delete pending[msg.id]; return; }
    };
    const evaluate = async (expr) => {
      const res = await send(ws, "Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      return res?.result?.value;
    };
    await send(ws, "Page.enable", {});
    await send(ws, "Runtime.enable", {});

    await evaluate(`location.href = "http://127.0.0.1:5500/register.html"; true`);
    await sleep(2500);

    const email = "newuser" + Date.now() + "@test.com";
    await evaluate(`document.getElementById("name").value = "New User";
                    document.getElementById("email").value = ${JSON.stringify(email)};
                    document.getElementById("password").value = "password123";
                    document.getElementById("register-form").dispatchEvent(new Event("submit", { cancelable: true })); true`);
    await sleep(4500);

    const state = await evaluate(`(() => {
      const q = (s) => document.querySelector(s);
      const vis = (el) => !!el && !el.hidden;
      return {
        url: location.href,
        appRendered: !!q(".app"),
        inboxActive: !!q("#view-inbox.active"),
        convCount: q("#conv-list") ? q("#conv-list").children.length : -1,
        convEmptyText: q("#conv-list .conv-list-empty") ? q("#conv-list .conv-list-empty").textContent : "",
        chatEmptyVisible: vis(q("#chat-empty")),
        chatEmptyText: q("#chat-empty") ? q("#chat-empty").textContent.trim().slice(0, 80) : "",
        modalVisible: vis(q("#modal-backdrop")),
        toasts: Array.from(document.querySelectorAll("#toast-stack .toast")).map(t => t.textContent),
      };
    })()`);
    console.log(JSON.stringify(state, null, 2));
    ws.close();
  } catch (e) {
    console.log("ERROR:", e.message);
  } finally {
    chrome.kill();
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) {}
  }
})();
