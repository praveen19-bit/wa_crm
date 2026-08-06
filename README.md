# WhatsApp CRM

A modern, production-ready WhatsApp CRM web application for managing cold DM conversations via the **Meta WhatsApp Cloud API**.

When you run outreach with n8n (or any automation) through your WhatsApp Business number, **every client reply lands automatically** in the CRM via a webhook, and you can reply with text, images, PDFs, videos, audio and documents **directly from the web app** — without ever opening WhatsApp.

---

## Highlights

- 🔐 **Auth** — Register / login, JWT, bcrypt password hashing
- 💬 **Inbox** — Intercom/Respond.io-style 3-panel chat UI
  - Contact list with unread badges, search & last-message previews
  - Real-time chat (WebSockets), timestamps, day dividers
  - Message status: Sent ✓ / Delivered ✓✓ / Read ✓✓
  - Send text, images, PDFs, videos, audio + emoji picker
  - Customer detail panel: profile, tags, notes, conversation info
- 👥 **Contacts** — CRUD, search, tag filter, CSV import/export
- ⚡ **WhatsApp integration** — Meta Cloud API webhook (receive + send all media types), status updates, auto-reply
- 🗃️ **Database** — Supabase Postgres, every message persisted
- 📦 **Media** — Supabase Storage (signed URLs), local filesystem fallback for dev
- 📊 **Analytics** — totals, daily message chart, message-mix donut, reply rate, active contacts
- 🎨 **UI** — Apple-style minimal, glassmorphism, dark/light mode, fully responsive

---

## Tech stack

| Layer     | Technology                                              |
| --------- | ------------------------------------------------------- |
| Backend   | FastAPI (async) · SQLAlchemy 2.0 · asyncpg/aiosqlite    |
| Database  | Supabase PostgreSQL                                     |
| Storage   | Supabase Storage (with local FS fallback for dev)       |
| Auth      | JWT (PyJWT) · bcrypt                                    |
| Realtime  | WebSockets                                              |
| Frontend  | HTML5 · CSS3 · Vanilla JS (no framework)                |
| WhatsApp  | Meta WhatsApp Cloud API (Graph API)                     |
| Deploy    | Render (one service: API + frontend)                    |

---

## Project structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, WebSocket endpoint
│   │   ├── config.py            # pydantic-settings env config
│   │   ├── database.py          # async engine + sessions (Postgres/SQLite)
│   │   ├── api/                 # routers
│   │   │   ├── auth.py  contacts.py  tags.py  conversations.py
│   │   │   ├── messages.py  media.py  analytics.py  settings.py  webhook.py
│   │   │   └── deps.py
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── core/                # security, whatsapp client, ws manager, storage
│   │   └── services/            # messaging, webhook processing, media helpers
│   ├── supabase/schema.sql      # Postgres schema + RLS + storage bucket
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
└── frontend/
    ├── index.html  register.html  app.html
    ├── css/styles.css
    ├── js/  api.js utils.js websocket.js app.js
    │         inbox.js contacts.js analytics.js settings.js
    └── test/                    # headless browser + realtime smoke tests
```

---

## Quickstart (local)

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env          # default .env already uses local SQLite

uvicorn app.main:app --reload --port 8000
```

The app boots with **SQLite** out of the box (`dev.db`) so you can try everything locally with zero setup.

### 2. Frontend

```bash
cd frontend
python -m http.server 5500
```

Open **http://127.0.0.1:5500** → create an account → you're in.

> The frontend talks to `http://127.0.0.1:8000` by default. To point it at a different backend, run
> `localStorage.setItem('crm_api_base', 'https://your-backend.onrender.com')` from the console once.

### 3. Verify

- `http://127.0.0.1:8000/health` → `{"status":"ok"}`
- Swagger docs: `http://127.0.0.1:8000/docs`
- Realtime + API smoke tests:

```bash
cd frontend/test
node cdp_ui_test.js    # loads the UI headlessly and exercises every view
node ws_realtime_test.js
```

---

## WhatsApp Cloud API setup (one-time)

1. Create a **Meta Developer app** → add the **WhatsApp** product.
2. Register a **business phone number** (or use a test number).
3. Create a **System User** token with the `whatsapp_business_messaging` permission, or use the temporary token from the dashboard.
4. In the CRM go to **Settings** and enter:
   - **Access token**
   - **Phone number ID**
   - **Webhook verify token** (any secret string you invent)
   - Business name (optional) → **Save**
5. Press **Test connection** — it should list your registered numbers.
6. Copy the **Webhook URL** shown in Settings and paste it into Meta Developer:
   - WhatsApp → **Configuration** → **Webhook** → `Edit`
   - Enter the URL + verify token → **Verify and Save**
   - Under **Webhook fields**, subscribe to **`messages`**.
7. Send a WhatsApp message to your business number — it appears in the inbox instantly. Reply from the CRM.

### n8n note

Any message your business number receives (including n8n-sent cold DMs' replies) triggers the webhook. Nothing else needs wiring.

---

## Architecture notes

### Incoming flow
```
Meta → POST /api/webhook/whatsapp
     → route to the user owning whatsapp_phone_number_id (settings)
     → upsert contact (by wa_id)
     → get-or-create conversation
     → media: download from Meta → store in Supabase Storage → MediaFile row
     → persist Message (dedup by whatsapp_message_id)
     → update conversation preview + unread_count
     → broadcast over WebSocket (message.new, conversation.updated)
     → optional auto-reply
```

### Outgoing flow
```
Frontend → POST /api/conversations/{id}/messages
         → WhatsAppClient.send_text / upload_media + send_media
         → persist Message (status=sent)
         → WS broadcast
         → Meta status webhooks flip status → sent → delivered → read
```

### Auth
JWT in `Authorization: Bearer <token>`, 7-day expiry, per-user data scoping on every query. WebSockets authenticate via `?token=...`.

### Storage
Files are stored under `{user_id}/{media_type}/{uuid}.{ext}` in the `whatsapp-media` bucket and served through time-limited **signed URLs**. In local dev (no Supabase creds) files are written to `backend/media_storage/` and served by the backend itself.

---

## Supabase production setup

1. Create a Supabase project.
2. Open the SQL editor and run **`backend/supabase/schema.sql`** (tables, indexes, updated_at triggers, RLS, storage bucket + policies).
3. Storage bucket `whatsapp-media` is created with `public=false` and a 200 MB file cap.
4. Copy the DB connection string, Project URL and Service Role key into your backend env:

```
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.<ref>.supabase.co:5432/postgres?sslmode=require
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>
SUPABASE_BUCKET=whatsapp-media
```

---

## API reference

### Authentication
| Method | Path                     | Description                |
| ------ | ------------------------ | -------------------------- |
| POST   | `/api/auth/register`     | Create account → token     |
| POST   | `/api/auth/login`        | Login → token              |
| GET    | `/api/auth/me`           | Current user               |
| PUT    | `/api/auth/me`           | Update name                |
| PUT    | `/api/auth/me/password`  | Change password            |

### Contacts
| Method | Path                              | Description                       |
| ------ | --------------------------------- | --------------------------------- |
| GET    | `/api/contacts`                   | List (search, tag filter, paging) |
| POST   | `/api/contacts`                   | Create                            |
| GET    | `/api/contacts/{id}`              | Detail                            |
| PUT    | `/api/contacts/{id}`              | Update                            |
| DELETE | `/api/contacts/{id}`              | Delete                            |
| POST   | `/api/contacts/import`            | CSV import (multipart)            |
| GET    | `/api/contacts/export`            | CSV download                      |
| PUT    | `/api/contacts/{id}/tags`         | Assign tags                       |
| GET    | `/api/contacts/{id}/notes`        | List notes                        |
| POST   | `/api/contacts/{id}/notes`        | Add note                          |
| DELETE | `/api/contacts/notes/{id}`        | Delete note                       |

### Conversations & messages
| Method | Path                                    | Description                      |
| ------ | --------------------------------------- | -------------------------------- |
| GET    | `/api/conversations`                    | List (search, unread filter)     |
| GET    | `/api/conversations/counts`             | Totals + unread count            |
| POST   | `/api/conversations?contact_id=`        | Create conversation              |
| GET    | `/api/conversations/{id}`               | Detail                           |
| POST   | `/api/conversations/{id}/read`          | Mark as read                     |
| PUT    | `/api/conversations/{id}/archive`       | Archive / unarchive              |
| GET    | `/api/conversations/{id}/messages`      | Message history                  |
| POST   | `/api/conversations/{id}/messages`      | Send text/media (type ∈ text, image, document, video, audio) |
| GET    | `/api/messages/search?q=`               | Full-text search across messages |

### Media
| Method | Path                   | Description                          |
| ------ | ---------------------- | ------------------------------------ |
| POST   | `/api/media/upload`    | Upload file → MediaFile + signed URL |
| GET    | `/api/media/{id}`      | Media metadata + signed URL          |
| DELETE | `/api/media/{id}`      | Delete media + stored object         |
| GET    | `/api/media/file?path=`| Dev fallback streaming endpoint      |

### Analytics
| Method | Path                   | Description                                  |
| ------ | ---------------------- | -------------------------------------------- |
| GET    | `/api/analytics/overview` | Dashboard cards                           |
| GET    | `/api/analytics/daily?days=` | Daily incoming/outgoing counts          |
| GET    | `/api/analytics/stats` | Reply rate, avg msgs, active contacts        |
| GET    | `/api/analytics?days=` | Everything at once                            |

### Settings & Webhook
| Method | Path                            | Description                       |
| ------ | ------------------------------- | --------------------------------- |
| GET    | `/api/settings`                 | Current config (token masked)     |
| PUT    | `/api/settings`                 | Update config                     |
| POST   | `/api/settings/test-connection` | Validate Meta credentials         |
| GET    | `/api/settings/webhook-url`     | Webhook URL + verify token hint   |
| GET    | `/api/webhook/whatsapp`         | Meta verification handshake       |
| POST   | `/api/webhook/whatsapp`         | Incoming messages / status updates |

### Realtime
`GET /ws?token=<jwt>` — events: `message.new`, `message.updated`, `conversation.updated`, `conversation.read`.

---

## Deployment

### Render (one service — API + frontend)
1. Push the repo, then **New + → Blueprint** in Render and connect this repo.
   `render.yaml` at the repo root provisions the `whatsapp-crm` service
   (build: `pip install -r backend/requirements.txt`, start:
   `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
2. In the service's **Environment** tab set the secrets: `DATABASE_URL`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `CORS_ORIGINS` (and a long
   `SECRET_KEY`; `render.yaml` can generate it for you).
3. Point Meta's webhook at `https://<your-service>.onrender.com/api/webhook/whatsapp`.

> ⚠️ **WebSocket note:** if you put a proxy/CDN in front of the backend, enable WebSocket support. Render passes them through natively.

---

## Security

- bcrypt password hashing, JWT with explicit expiry, bearer tokens required on every endpoint
- Per-user data scoping on all queries (multi-tenant safe)
- RLS policies on every Supabase table + storage folder isolation (`{user_id}/...`)
- Webhook verify-token handshake, dedup on `whatsapp_message_id`, always-200 to Meta
- No secrets in code — everything via environment variables

## License

MIT — use it, fork it, ship it.
