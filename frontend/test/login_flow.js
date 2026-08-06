// Reproduces: user enters credentials on index.html, submits, then inspects what appears.
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9225;
const PROFILE = path.join(process.env.TEMP, "crm-cdp-login-" + Date.now());
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
        issues.push("EXCEPTION: " + (msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text));
      }
    };
    const evaluate = async (expr) => {
      const res = await send(ws, "Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
      if (!res) return null;
      if (res.exceptionDetails) {
        issues.push("EVAL: " + (res.exceptionDetails.exception?.description || res.exceptionDetails.text));
        return null;
      }
      return res.result?.value;
    };

    await send(ws, "Page.enable", {});
    await send(ws, "Runtime.enable", {});

    // go to login page
    await evaluate(`location.href = "http://127.0.0.1:5500/index.html"; true`);
    await sleep(2500);

    // fill the form
    await evaluate(`document.getElementById("email").value = "demo@test.com"; 
                    document.getElementById("password").value = "password123"; true`);
    // submit (returns immediately)
    await evaluate(`document.getElementById("login-form").dispatchEvent(new Event("submit", { cancelable: true })); true`);
    await sleep(4000);

    const result = await evaluate(`(() => {
      const sel = (s) => document.querySelector(s);
      return {
        url: location.href,
        modalVisible: !!sel("#modal-backdrop") && !sel("#modal-backdrop").hidden,
        modalTitle: (sel("#modal-title")||{textContent:""}).textContent,
        toastCount: document.querySelectorAll("#toast-stack .toast").length,
        toastTexts: Array.from(document.querySelectorAll("#toast-stack .toast")).map(t => t.textContent),
        formError: (sel("#form-error")||{textContent:""}).textContent,
        formErrorHidden: sel("#form-error") ? sel("#form-error").hidden : true,
        appRendered: !!sel(".app"),
        hasInbox: !!sel("#view-inbox.active"),
        chatEmpty: !!sel("#chat-empty") && !sel("#chat-empty").hidden,
      };
    })()`);

    console.log(JSON.stringify(result, null, 2));
    console.log("ISSUES:", issues.length ? issues : "none");
    ws.close();
  } catch (e) {
    console.log("ERROR:", e.message);
  } finally {
    chrome.kill();
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) {}
  }
})();
