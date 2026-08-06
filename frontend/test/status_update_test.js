// Verifies status-update webhooks emit message.updated (NOT message.new) -> no duplicate bubbles.
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
    await sleep(500);

    const waId = "wamid.STATUS." + Date.now();
    const incoming = {
      object: "whatsapp_business_account",
      entry: [{ id: "WABA_DEMO", changes: [{ value: {
        messaging_product: "whatsapp",
        metadata: { display_phone_number: "16505551111", phone_number_id: "123456789012345" },
        contacts: [{ profile: { name: "Status Tester" }, wa_id: "15553334444" }],
        messages: [{ from: "15553334444", id: waId, timestamp: String(Math.floor(Date.now() / 1000)), type: "text", text: { body: "dedup check " + Date.now() } }],
      } }] }],
    };
    await fetch(API_BASE + "/api/webhook/whatsapp", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(incoming) });
    await sleep(1500);

    const firstNew = events.filter((e) => e.type === "message.new" && e.data.whatsapp_message_id === waId);
    record("1 message.new for incoming", firstNew.length === 1, "count=" + firstNew.length);

    // now push status updates for the SAME message id (as Meta does for sent/delivered/read)
    for (const st of ["sent", "delivered", "read"]) {
      const status = {
        object: "whatsapp_business_account",
        entry: [{ id: "WABA_DEMO", changes: [{ value: {
          messaging_product: "whatsapp",
          metadata: { display_phone_number: "16505551111", phone_number_id: "123456789012345" },
          statuses: [{ id: waId, status: st, timestamp: String(Math.floor(Date.now() / 1000)) }],
        } }] }],
      };
      await fetch(API_BASE + "/api/webhook/whatsapp", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(status) });
    }
    await sleep(2000);

    const newAfter = events.filter((e) => e.type === "message.new" && e.data.whatsapp_message_id === waId);
    const updated = events.filter((e) => e.type === "message.updated" && e.data.whatsapp_message_id === waId);
    record("still only 1 message.new (no dupes from status)", newAfter.length === 1, "count=" + newAfter.length);
    record("message.updated broadcast received", updated.length >= 3, "count=" + updated.length + " last=" + (updated[updated.length - 1]?.data?.status || "none"));

    ws.close();
  } catch (e) {
    record("error", false, e.message);
  }
  console.log(results.join("\n"));
  process.exit(results.some((r) => r.startsWith("FAIL")) ? 1 : 0);
})();
