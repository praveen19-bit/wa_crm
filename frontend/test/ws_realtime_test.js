// WebSocket realtime test: connect, then push a webhook and verify the event arrives.
const API_BASE = "http://127.0.0.1:8000";
const results = [];
function record(name, ok, detail) {
  results.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  try {
    const login = await fetch(API_BASE + "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "demo@test.com", password: "password123" }),
    });
    const token = (await login.json()).access_token;
    record("login", !!token);

    const ws = new WebSocket("ws://127.0.0.1:8000/ws?token=" + encodeURIComponent(token));
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    record("ws connected", ws.readyState === WebSocket.OPEN);

    const events = [];
    ws.onmessage = (e) => events.push(JSON.parse(e.data));

    const waId = "wamid.REALTIME." + Date.now();
    const payload = {
      object: "whatsapp_business_account",
      entry: [{
        id: "WABA_DEMO",
        changes: [{
          value: {
            messaging_product: "whatsapp",
            metadata: { display_phone_number: "16505551111", phone_number_id: "123456789012345" },
            contacts: [{ profile: { name: "Realtime Tester" }, wa_id: "15551112222" }],
            messages: [{
              from: "15551112222",
              id: waId,
              timestamp: String(Math.floor(Date.now() / 1000)),
              type: "text",
              text: { body: "⚡ realtime message " + Date.now() },
            }],
          },
        }],
      }],
    };

    const wb = await fetch(API_BASE + "/api/webhook/whatsapp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const wbJson = await wb.json();
    record("webhook processed", wbJson.ok && wbJson.messages === 1, JSON.stringify(wbJson));

    await sleep(2000);

    const msgEvent = events.find((e) => e.type === "message.new");
    record("message.new received over WS", !!msgEvent && msgEvent.data.text.includes("realtime message"),
      msgEvent ? msgEvent.data.text : "no event");
    const convEvent = events.find((e) => e.type === "conversation.updated");
    record("conversation.updated received over WS", !!convEvent);

    ws.close();
  } catch (e) {
    record("error", false, e.message);
  }
  console.log(results.join("\n"));
  process.exit(results.some((r) => r.startsWith("FAIL")) ? 1 : 0);
})();
