// End-to-end: fresh user registers, sees empty-state tile, starts a conversation, types in chat.
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9227;
const PROFILE = path.join(process.env.TEMP, "crm-cdp-cta-" + Date.now());
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

    const email = "cta" + Date.now() + "@test.com";
    await evaluate(`location.href = "http://127.0.0.1:5500/register.html"; true`);
    await sleep(2500);
    await evaluate(`document.getElementById("name").value = "CTA User";
                    document.getElementById("email").value = ${JSON.stringify(email)};
                    document.getElementById("password").value = "password123";
                    document.getElementById("register-form").dispatchEvent(new Event("submit", { cancelable: true })); true`);
    await sleep(4500);

    // 1. empty-state tile visible with CTA
    const tile = await evaluate(`(() => {
      const t = document.getElementById("chat-empty");
      return { visible: !!t && !t.hidden, hasCta: !!document.getElementById("btn-start-conv"), text: t ? t.textContent.trim().slice(0,60) : "" };
    })()`);

    // 2. click "New conversation" -> contact modal should open
    await evaluate(`document.getElementById("btn-start-conv").click(); true`);
    await sleep(800);
    const modal = await evaluate(`(() => ({
      open: !!document.querySelector("#modal-backdrop") && !document.querySelector("#modal-backdrop").hidden,
      title: document.querySelector("#modal-title") ? document.querySelector("#modal-title").textContent : "",
    }))()`);

    // 3. fill + submit the contact editor (click the Create button, not Cancel)
    await evaluate(`document.getElementById("ed-name").value = "Leah Prospect";
                    document.getElementById("ed-phone").value = "+15557778888";
                    [...document.querySelectorAll("[data-modal-action]")].find(b => b.textContent.trim() === "Create").click(); true`);
    await sleep(3000);

    const chat = await evaluate(`(() => {
      const q = (s) => document.querySelector(s);
      return {
        url: location.href.split("/").pop(),
        inboxActive: !!q("#view-inbox.active"),
        chatOpen: !!q("#chat-window") && !q("#chat-window").hidden,
        title: q("#chat-title") ? q("#chat-title").textContent : "",
        composerVisible: !!q("#compose-input"),
        composerDisabled: q("#compose-input") ? q("#compose-input").disabled : null,
        sendDisabled: q("#btn-send") ? q("#btn-send").disabled : null,
        listHasItem: q("#conv-list") ? [...q("#conv-list").children].filter(c => !c.id || !c.id.includes("empty")).length >= 1 : false,
      };
    })()`);

    // 4. type into the composer (send will fail gracefully without Meta creds -> toast, but input stays usable)
    await evaluate(`document.getElementById("compose-input").value = "Hi Leah, checking in!"; true`);
    const typed = await evaluate(`document.getElementById("compose-input").value`);

    console.log(JSON.stringify({ tile, modal, chat, typed }, null, 2));
    ws.close();
  } catch (e) {
    console.log("ERROR:", e.message);
  } finally {
    chrome.kill();
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) {}
  }
})();
