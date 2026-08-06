-- ============================================================
-- WhatsApp CRM — Supabase schema (Postgres)
-- Run this in the Supabase SQL editor, or:
--   supabase db push
-- ============================================================

-- ===================== Tables =====================

CREATE TABLE IF NOT EXISTS public.users (
  id            VARCHAR(36) PRIMARY KEY,
  email         VARCHAR(255) NOT NULL UNIQUE,
  name          VARCHAR(120) NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  avatar_url    VARCHAR(500),
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.tags (
  id         VARCHAR(36) PRIMARY KEY,
  user_id    VARCHAR(36) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  name       VARCHAR(80) NOT NULL,
  color      VARCHAR(20) NOT NULL DEFAULT '#6366f1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS public.contacts (
  id         VARCHAR(36) PRIMARY KEY,
  user_id    VARCHAR(36) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  name       VARCHAR(255),
  phone      VARCHAR(32) NOT NULL,
  email      VARCHAR(255),
  company    VARCHAR(255),
  avatar_url VARCHAR(500),
  notes      TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, phone)
);

CREATE TABLE IF NOT EXISTS public.contact_tags (
  contact_id VARCHAR(36) NOT NULL REFERENCES public.contacts(id) ON DELETE CASCADE,
  tag_id     VARCHAR(36) NOT NULL REFERENCES public.tags(id) ON DELETE CASCADE,
  PRIMARY KEY (contact_id, tag_id)
);

CREATE TABLE IF NOT EXISTS public.notes (
  id          VARCHAR(36) PRIMARY KEY,
  user_id     VARCHAR(36) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  contact_id  VARCHAR(36) NOT NULL REFERENCES public.contacts(id) ON DELETE CASCADE,
  content     TEXT NOT NULL,
  author_name VARCHAR(120) NOT NULL DEFAULT 'You',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.conversations (
  id                      VARCHAR(36) PRIMARY KEY,
  user_id                 VARCHAR(36) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  contact_id              VARCHAR(36) NOT NULL REFERENCES public.contacts(id) ON DELETE CASCADE,
  whatsapp_phone_number_id VARCHAR(64),
  subject                 VARCHAR(255),
  unread_count            INTEGER NOT NULL DEFAULT 0,
  is_active               BOOLEAN NOT NULL DEFAULT TRUE,
  is_archived             BOOLEAN NOT NULL DEFAULT FALSE,
  last_message_at         TIMESTAMPTZ,
  last_message_preview    VARCHAR(500),
  last_message_type       VARCHAR(20),
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.media_files (
  id               VARCHAR(36) PRIMARY KEY,
  user_id          VARCHAR(36) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  conversation_id  VARCHAR(36),
  storage_path     VARCHAR(600) NOT NULL,
  file_name        VARCHAR(255) NOT NULL,
  mime_type        VARCHAR(120) NOT NULL,
  size_bytes       BIGINT NOT NULL DEFAULT 0,
  media_type       VARCHAR(20) NOT NULL, -- image | document | video | audio
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.messages (
  id                   VARCHAR(36) PRIMARY KEY,
  user_id              VARCHAR(36) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  conversation_id      VARCHAR(36) NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
  contact_id           VARCHAR(36) NOT NULL REFERENCES public.contacts(id) ON DELETE CASCADE,
  direction            VARCHAR(10) NOT NULL, -- incoming | outgoing
  msg_type             VARCHAR(20) NOT NULL DEFAULT 'text',
  text                 TEXT,
  caption              TEXT,
  whatsapp_message_id  VARCHAR(128),
  media_id             VARCHAR(36) REFERENCES public.media_files(id) ON DELETE SET NULL,
  status               VARCHAR(20) NOT NULL DEFAULT 'sent', -- sent | delivered | read | failed | received
  timestamp            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.settings (
  id                        VARCHAR(36) PRIMARY KEY,
  user_id                   VARCHAR(36) NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
  whatsapp_access_token     VARCHAR(1000),
  whatsapp_phone_number_id  VARCHAR(64),
  whatsapp_business_account_id VARCHAR(64),
  webhook_verify_token      VARCHAR(255),
  business_name             VARCHAR(120),
  business_phone            VARCHAR(32),
  auto_reply_enabled        BOOLEAN NOT NULL DEFAULT FALSE,
  auto_reply_text           VARCHAR(1000),
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===================== Indexes =====================

CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_contacts_user   ON public.contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_contacts_phone  ON public.contacts(phone);
CREATE INDEX IF NOT EXISTS idx_tags_user       ON public.tags(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_contact   ON public.notes(contact_id);
CREATE INDEX IF NOT EXISTS idx_conv_user       ON public.conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_contact    ON public.conversations(contact_id);
CREATE INDEX IF NOT EXISTS idx_conv_last_msg   ON public.conversations(last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_msg_conv        ON public.messages(conversation_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_waid        ON public.messages(whatsapp_message_id);
CREATE INDEX IF NOT EXISTS idx_msg_user_ts     ON public.messages(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_contact_ts  ON public.messages(contact_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_media_user      ON public.media_files(user_id);

-- ===================== updated_at trigger =====================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['users','tags','contacts','notes','conversations','media_files','settings']
  LOOP
    EXECUTE format(
      'CREATE TRIGGER set_updated_at BEFORE UPDATE ON public.%I
       FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()', t);
  END LOOP;
END $$;

-- ===================== Row Level Security =====================
-- The backend uses its own authentication (JWT) and connects with the
-- service role key, which bypasses RLS. Policies below are a safety net
-- so table access stays scoped to the owning user via the `auth.uid()`
-- convention if you ever expose the tables to the anon key.
-- IMPORTANT: change `auth.uid()` mapping if your app uses custom user ids.

ALTER TABLE public.users         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tags          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contacts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_tags  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.media_files   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.settings      ENABLE ROW LEVEL SECURITY;

-- users: an authenticated user can read/update only themselves
CREATE POLICY users_select ON public.users FOR SELECT USING (id = auth.uid()::text);
CREATE POLICY users_update ON public.users FOR UPDATE USING (id = auth.uid()::text);
CREATE POLICY users_insert ON public.users FOR INSERT WITH CHECK (id = auth.uid()::text);

CREATE POLICY tags_all ON public.tags FOR ALL USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY contacts_all ON public.contacts FOR ALL USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY notes_all ON public.notes FOR ALL USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY conversations_all ON public.conversations FOR ALL USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY media_all ON public.media_files FOR ALL USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY messages_all ON public.messages FOR ALL USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);
CREATE POLICY settings_all ON public.settings FOR ALL USING (user_id = auth.uid()::text) WITH CHECK (user_id = auth.uid()::text);

-- contact_tags has no user_id column; join through contacts
CREATE POLICY ct_select ON public.contact_tags FOR SELECT
  USING (contact_id IN (SELECT id FROM public.contacts WHERE user_id = auth.uid()::text));
CREATE POLICY ct_insert ON public.contact_tags FOR INSERT
  WITH CHECK (contact_id IN (SELECT id FROM public.contacts WHERE user_id = auth.uid()::text));
CREATE POLICY ct_delete ON public.contact_tags FOR DELETE
  USING (contact_id IN (SELECT id FROM public.contacts WHERE user_id = auth.uid()::text));

-- ===================== Storage =====================

-- Bucket for WhatsApp media (private by default; served via signed URLs)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('whatsapp-media', 'whatsapp-media', FALSE, 209715200, NULL)
ON CONFLICT (id) DO NOTHING;

-- Storage policy: only authenticated users of the owner can read/write
DROP POLICY IF EXISTS media_authenticated_select ON storage.objects;
CREATE POLICY media_authenticated_select ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'whatsapp-media'
    AND (storage.foldername(name))[1] = auth.uid()::text);

DROP POLICY IF EXISTS media_authenticated_insert ON storage.objects;
CREATE POLICY media_authenticated_insert ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'whatsapp-media'
    AND (storage.foldername(name))[1] = auth.uid()::text);

DROP POLICY IF EXISTS media_authenticated_delete ON storage.objects;
CREATE POLICY media_authenticated_delete ON storage.objects
  FOR DELETE TO authenticated
  USING (bucket_id = 'whatsapp-media'
    AND (storage.foldername(name))[1] = auth.uid()::text);

-- Allow the service role to manage everything (already bypasses RLS).
