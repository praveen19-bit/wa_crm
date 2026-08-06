// Verify chat bubble time renders in local time from UTC timestamps.
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9232;
const PROFILE = path.join(process.env.TEMP, "crm-cdp-time-" + Date.now());
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
    const login = await fetch("http://127.0.0.1:8000/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "demo@test.com", password: "password123" }),
    });
    const token = (await login.json()).access_token;

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
    await evaluate(`location.href = "http://127.0.0.1:5500/app.html"; true`);
    await sleep(1200);
    await evaluate(`localStorage.setItem("crm_token", ${JSON.stringify(token)});
                    localStorage.setItem("crm_user", JSON.stringify({name:"Demo User", email:"demo@test.com"}));
                    location.reload(); true`);
    await sleep(3000);
    await evaluate(`document.querySelector(".conv-item")?.click(); true`);
    await sleep(2500);

    const result = await evaluate(`(() => {
      const q = (s) => document.querySelector(s);
      const metas = [...document.querySelectorAll("#chat-body .msg-meta")].map(m => m.textContent.trim());
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      // first message timestamp from the API, rendered by the page
      const rendered = metas[0] || "";
      // expected local time of that same message
      const firstEl = document.querySelector("#chat-body .msg");
      const expected = "";
      return { tz, metas: metas.slice(0, 4) };
    })()`);
    console.log(JSON.stringify(result, null, 2));
    ws.close();
  } catch (e) {
    console.log("ERROR:", e.message);
  } finally {
    chrome.kill();
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) {}
  }
})();
