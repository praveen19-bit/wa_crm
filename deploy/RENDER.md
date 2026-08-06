# Deploy to Render (free tier)

Render is simpler than a VPS for this app: it provides a public HTTPS URL
automatically, so you don't need a domain, DuckDNS, or Caddy. The backend
serves the static frontend too (see `backend/app/main.py`), so everything
lives behind **one** URL and there are no CORS or WebSocket cross-origin
problems.

## The setup

- **One free Web Service** (`whatsapp-crm`), Python runtime.
- Database + media stay in **Supabase** (already cloud-hosted).
- Env vars are set in the Render dashboard (not committed to git).
- Webhooks and WebSockets work over the same `https://<service>.onrender.com`.

## Steps

### 1. Push the code to GitHub

Create a repo (e.g. `whatsapp-crm`) and push the project root — it must
include `backend/`, `frontend/`, and `render.yaml`:

```bash
git init
git add .
git commit -m "WhatsApp CRM"
git branch -M main
git remote add origin https://github.com/<you>/whatsapp-crm.git
git push -u origin main
```

> Make sure `backend/.env` and `deploy/backend.env` are NOT committed
> (add a `.gitignore` with `.env`, `*.pid`, `dev.db`, `.venv/`).

### 2. Create the service on Render

1. https://render.com -> **New + -> Blueprint**.
2. Connect your GitHub repo. Render reads `render.yaml` automatically.
3. It provisions the `whatsapp-crm` web service and starts a build.

### 3. Set environment variables (Render dashboard)

Service -> **Environment** -> add:

```
ENVIRONMENT            production
DEBUG                  false
SECRET_KEY             <openssl rand -hex 32>
DATABASE_URL           postgresql+asyncpg://postgres.tbqvlzukxebcalnujrib:67QR-4Scz#dH6m6@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
SUPABASE_URL           https://tbqvlzukxebcalnujrib.supabase.co
SUPABASE_SERVICE_KEY   <your service_role key>
SUPABASE_BUCKET        whatsapp-media
CORS_ORIGINS           https://whatsapp-crm.onrender.com
```

(The `DATABASE_URL` password contains a `#` — Render stores env vars as
literal values, so it is preserved correctly.)

Then **Deploy** / restart the service.

### 4. Verify

```bash
curl -s https://whatsapp-crm.onrender.com/health
# {"status":"ok","app":"WhatsApp CRM","version":"1.0.0"}
```

Open `https://whatsapp-crm.onrender.com/` in a browser — you should see the
login page. Log in with `demo@test.com` / `password123`.

### 5. Point Meta's webhook at Render

- **Callback URL**: `https://whatsapp-crm.onrender.com/api/webhook/whatsapp`
- **Verify token**: `myverifytoken`
- Subscribe to the **`messages`** field.

The phone number ID / access token stored in Supabase `settings` map incoming
messages automatically.

## Free-tier caveats (important)

- **Sleep**: free web services go to sleep after ~15 minutes of no traffic.
  Incoming WhatsApp messages wake it up (cold start up to ~60 s — Meta retries
  until it succeeds, so nothing is lost, but delivery can be delayed).
- **Keep it awake**: add a free uptime ping (e.g. UptimeRobot) hitting
  `https://whatsapp-crm.onrender.com/health` every 5 minutes. That prevents
  sleeping for as long as pings keep arriving.
- **Real-time**: while a browser tab is open the WebSocket keeps the service
  warm and messages appear instantly.

## Updates

```bash
git add .
git commit -m "..."
git push
```

`autoDeploy: true` rebuilds Render automatically on push.
