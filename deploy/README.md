# Deploy to a Free VPS (Oracle Cloud + Docker)

Complete guide for running the WhatsApp CRM on Oracle Cloud's **Always Free**
tier behind Caddy (automatic HTTPS) with a free DuckDNS subdomain.

## Architecture

```
Internet
  │  https://<you>.duckdns.org (port 80/443)
  ▼
Caddy (reverse proxy + auto HTTPS)
  ├─ /api/*  ───────────────►  backend:8000  (uvicorn/FastAPI)
  ├─ /ws*    ───────────────►  backend:8000  (WebSocket realtime)
  └─ everything else ───────►  static frontend files
Backend ──► Supabase (Postgres + Storage, already cloud-hosted)
```

- Database & media live in **Supabase** (no local DB needed on the VPS).
- **Caddy** issues a free Let's Encrypt certificate automatically.
- The frontend auto-detects production (`frontend/js/config.js`) and talks to
  the same origin, so no CORS/base-URL setup is needed on the VPS.

---

## 1. Create the Oracle Cloud instance (Always Free)

1. Sign up / log in at https://cloud.oracle.com (Free tier).
2. **Create a VM instance**:
   - Image: **Ubuntu 24.04** (or 22.04).
   - Shape: **VM.Standard.A1.Flex (Ampere/ARM)** — pick e.g. 2 OCPU + 12 GB RAM.
     (If A1 shows "out of capacity", try a different Availability Domain or
     region, or use the AMD `VM.Standard.E2.1.Micro` which also fits the app.)
   - Networking: keep the default VCN/subnet.
   - **SSH**: add your public key (save the private key on your PC).
3. Note the instance's **public IP** (e.g. `123.123.123.123`).
4. SSH into it from your PC:
   ```bash
   ssh -i ~/path/to/your_key ubuntu@123.123.123.123
   ```

## 2. Open ports 80 + 443

OCI blocks HTTP(S) by default.

```bash
# Ubuntu image on Oracle uses iptables-persistent:
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Also in the **OCI Console → Networking → Virtual Cloud Network → your subnet →
Security List → Add Ingress Rules**: allow **TCP 80** and **TCP 443** from
`0.0.0.0/0`.

## 3. Get a free domain (DuckDNS)

Meta requires a public HTTPS callback URL, so we give the VPS a permanent
subdomain.

1. Create a free account at https://www.duckdns.org.
2. Create a subdomain, e.g. `whatsappcrm.duckdns.org`.
3. Set it to your VPS public IP: `123.123.123.123`.
   (A static IP only needs this once; DuckDNS also gives you a token + update
   URL if your IP ever changes.)

## 4. Copy the project to the VPS

From your PC (replace paths/keys):

```bash
scp -r -i ~/path/to/your_key \
  "C:\Users\mp360\OneDrive\Documents\Default Project\backend" \
  "C:\Users\mp360\OneDrive\Documents\Default Project\frontend" \
  "C:\Users\mp360\OneDrive\Documents\Default Project\deploy" \
  ubuntu@123.123.123.123:~/whatsapp-crm/
```

Layout on the VPS:

```
~/whatsapp-crm/
  backend/     (app code)
  frontend/    (static site)
  deploy/      (Dockerfile, docker-compose.yml, Caddyfile, env files)
```

## 5. Configure the environment

On the VPS:

```bash
cd ~/whatsapp-crm/deploy

# Domain used by Caddy and CORS:
cp .env.example .env
nano .env          # set APP_DOMAIN=whatsappcrm.duckdns.org

# Production secrets for the backend:
nano backend.env   # set CORS_ORIGINS to https://whatsappcrm.duckdns.org
                   # (DATABASE_URL / SUPABASE keys are already filled in)
```

> The `backend.env` values already match your working Supabase project.
> Change `SECRET_KEY` to a fresh random value if you want:
> `openssl rand -hex 32`

## 6. Install Docker and start

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out and back in so the docker group applies, then:
sudo systemctl enable --now docker

cd ~/whatsapp-crm/deploy
docker compose up -d --build
docker compose ps          # both services should be "Up"
```

## 7. Verify

```bash
curl -s https://whatsappcrm.duckdns.org/health
# {"status":"ok","app":"WhatsApp CRM","version":"1.0.0"}

curl -s -o /dev/null -w "%{http_code}\n" https://whatsappcrm.duckdns.org/
# 200  (login page)
```

HTTPS is fully automatic (Caddy + Let's Encrypt). The first cert issue can take
~30 seconds after the domain's DNS resolves.

## 8. Point the Meta webhook to the VPS

1. Open your WhatsApp app in Meta Developer → **Webhooks**.
2. **Edit subscription**:
   - **Callback URL**: `https://whatsappcrm.duckdns.org/api/webhook/whatsapp`
   - **Verify token**: `myverifytoken`
   - Click **Verify and save**.
3. Subscribe to the **`messages`** field (and optionally `message_template_status_update`).
4. The user's WhatsApp phone number ID + access token are already stored in the
   Supabase `settings` table (migrated earlier), so incoming messages will be
   matched automatically.

## 9. Test

1. Open `https://whatsappcrm.duckdns.org` in a browser and log in
   (`demo@test.com` / `password123`, or your own account).
2. Send a WhatsApp message to your business number from your phone.
3. Watch it appear in the inbox **and** in Supabase → Table Editor → `messages`.

## Updating later

```bash
cd ~/whatsapp-crm
# copy new backend/ frontend/ deploy/ files up (scp)
cd deploy
docker compose up -d --build
```

## Security checklist

- [ ] `SECRET_KEY` changed to a long random value.
- [ ] The Supabase **service_role key** never appears in frontend code.
- [ ] Oracle security list only exposes **22, 80, 443** (backend port 8000 is
      internal only).
- [ ] Create a real user account and avoid sharing the demo login.
