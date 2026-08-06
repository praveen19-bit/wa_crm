// Captures console errors + JS exceptions while loading app.html
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const FRONT_URL = "http://127.0.0.1:5500/app.html";
const API_BASE = "http://127.0.0.1:8000";
const PORT = 9224;
const PROFILE = path.join(process.env.TEMP, "crm-cdp-err-" + Date.now());

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let _id = 0;
const pending = {};
const issues = [];

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
    const login = await fetch(API_BASE + "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
    if (!target) throw new Error("no chrome target");

    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.id && pending[msg.id]) { pending[msg.id](msg.result); delete pending[msg.id]; return; }
      if (msg.method === "Runtime.exceptionThrown") {
        const d = msg.params.exceptionDetails;
        issues.push("EXCEPTION: " + (d.exception?.description || d.text || JSON.stringify(d)).split("\n")[0]);
      }
      if (msg.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(msg.params.type)) {
        const txt = (msg.params.args || []).map((a) => a.value ?? a.description ?? "").join(" ");
        issues.push(msg.params.type.toUpperCase() + ": " + txt.split("\n")[0]);
      }
    };

    const evaluate = async (expr) => {
      const res = await send(ws, "Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (res.exceptionDetails) {
        issues.push("EVAL EXCEPTION: " + (res.exceptionDetails.exception?.description || res.exceptionDetails.text));
      }
      return res.result?.value;
    };

    await send(ws, "Page.enable", {});
    await send(ws, "Runtime.enable", {});
    await evaluate(`location.href = "${FRONT_URL}"; true`);
    await sleep(1200);
    await evaluate(`localStorage.setItem("crm_token", ${JSON.stringify(token)});
                    localStorage.setItem("crm_user", JSON.stringify({name:"Demo User", email:"demo@test.com"}));
                    localStorage.setItem("crm_theme", "dark");
                    location.reload(); true`);
    await sleep(3000);

    const view = await evaluate(`document.querySelector(".app") ? "rendered" : "not-rendered"`);
    console.log("APP VIEW:", view);

    // exercise every view + open conversation + toggle details
    await evaluate(`document.querySelector('.nav-item[data-view="contacts"]').click(); true`);
    await sleep(1200);
    await evaluate(`document.querySelector('.nav-item[data-view="analytics"]').click(); true`);
    await sleep(1200);
    await evaluate(`document.querySelector('.nav-item[data-view="settings"]').click(); true`);
    await sleep(1200);
    await evaluate(`document.querySelector('.nav-item[data-view="inbox"]').click(); true`);
    await sleep(800);
    await evaluate(`document.querySelector(".conv-item")?.click(); true`);
    await sleep(2500);

    console.log(issues.length ? "ISSUES:" : "NO CONSOLE ERRORS");
    issues.forEach((i) => console.log("  " + i));
    ws.close();
  } catch (e) {
    console.log("ERROR:", e.message);
    issues.forEach((i) => console.log("  " + i));
  } finally {
    chrome.kill();
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) {}
  }
})();
