// Reproduce: index.html -> type temp creds -> click LOG IN -> capture app.html screen + errors
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9229;
const PROFILE = path.join(process.env.TEMP, "crm-cdp-login-temp-" + Date.now());
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
      if (msg.method === "Runtime.exceptionThrown") {
        issues.push("EXC: " + (msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text).split("\n")[0]);
      }
      if (msg.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(msg.params.type)) {
        issues.push(msg.params.type + ": " + (msg.params.args.map(a => a.value ?? a.description ?? "").join(" ")).split("\n")[0]);
      }
      if (msg.method === "Network.responseReceived") {
        const r = msg.params.response;
        if (r.status >= 400) issues.push("HTTP " + r.status + ": " + r.url.replace("http://127.0.0.1:8000", ""));
      }
    };
    const evaluate = async (expr) => {
      const res = await send(ws, "Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (res.exceptionDetails) issues.push("EVAL-EXC: " + (res.exceptionDetails.exception?.description || res.exceptionDetails.text).split("\n")[0]);
      return res?.result?.value;
    };
    await send(ws, "Page.enable", {});
    await send(ws, "Runtime.enable", {});
    await send(ws, "Network.enable", {});

    await evaluate(`location.href = "http://127.0.0.1:5500/index.html"; true`);
    await sleep(2500);

    // type + submit the real login form
    await evaluate(`document.getElementById("email").value = "temp195048@test.com";
                    document.getElementById("password").value = "temp12345";
                    document.getElementById("login-form").dispatchEvent(new Event("submit", { cancelable: true })); true`);
    await sleep(5000);

    const screen = await evaluate(`(() => {
      const q = (s) => document.querySelector(s);
      const vis = (el) => !!el && !el.hidden;
      const text = (sel) => { const el = q(sel); return el ? el.textContent.trim().slice(0, 120) : null; };
      return {
        url: location.href.split("/").pop(),
        appRendered: !!q(".app"),
        toasts: [...(q("#toast-stack")?.children || [])].map(t => t.textContent.trim().slice(0, 90)),
        formError: text("#form-error"),
        modalOpen: q("#modal-backdrop") ? !q("#modal-backdrop").hidden : null,
        modalDisplay: q("#modal-backdrop") ? getComputedStyle(q("#modal-backdrop")).display : null,
        modalTitle: text("#modal-title"),
        chatWindowDisplay: q("#chat-window") ? getComputedStyle(q("#chat-window")).display : null,
        detailsDisplay: q("#inbox-details") ? getComputedStyle(q("#inbox-details")).display : null,
        bigHeading: [...document.querySelectorAll("h1,h2")].map(h => h.textContent.trim()).filter(Boolean).slice(0, 5),
      };
    })()`);
    console.log(JSON.stringify({ screen, issues }, null, 2));
    ws.close();
  } catch (e) {
    console.log("ERROR:", e.message);
  } finally {
    chrome.kill();
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) {}
  }
})();
