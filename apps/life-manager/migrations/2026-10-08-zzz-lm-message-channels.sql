-- Web tenants may opt into Telegram or iMessage without changing the Web identity
-- or lm_users.telegram_chat_id. This registry owns one sender per channel globally.

CREATE TABLE IF NOT EXISTS public.lm_web_message_link_tokens (
  token_hash text PRIMARY KEY CHECK (token_hash ~ '^[a-f0-9]{64}$'),
  uid text NOT NULL REFERENCES public.lm_users(uid),
  channel text NOT NULL CHECK (channel IN ('telegram', 'imessage')),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL CHECK (expires_at > created_at)
);

CREATE TABLE IF NOT EXISTS public.lm_message_channels (
  uid text NOT NULL REFERENCES public.lm_users(uid),
  channel text NOT NULL CHECK (channel IN ('telegram', 'imessage')),
  sender_id text NOT NULL CHECK (length(sender_id) BETWEEN 1 AND 255 AND sender_id !~ '[[:cntrl:]]'),
  owner_kind text NOT NULL CHECK (owner_kind IN ('legacy', 'web_link')),
  token_hash text UNIQUE REFERENCES public.lm_web_message_link_tokens(token_hash),
  linked_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (channel, sender_id),
  UNIQUE (uid, channel),
  CHECK (
    (owner_kind = 'legacy' AND channel = 'telegram' AND token_hash IS NULL)
    OR (owner_kind = 'web_link' AND token_hash IS NOT NULL)
  ),
  CHECK (channel <> 'telegram' OR sender_id ~ '^-?[1-9][0-9]{0,19}$')
);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM public.lm_users
     WHERE telegram_chat_id IS NOT NULL AND trim(telegram_chat_id::text) <> ''
     GROUP BY telegram_chat_id::text
    HAVING count(DISTINCT uid) > 1
  ) THEN
    RAISE EXCEPTION 'telegram_channel_owner_conflict';
  END IF;
END;
$$;

INSERT INTO public.lm_message_channels(uid, channel, sender_id, owner_kind)
SELECT uid, 'telegram', telegram_chat_id::text, 'legacy'
  FROM public.lm_users
 WHERE telegram_chat_id IS NOT NULL AND trim(telegram_chat_id::text) <> ''
ON CONFLICT (channel, sender_id) DO NOTHING;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM public.lm_users AS users
      LEFT JOIN public.lm_message_channels AS channels
        ON channels.channel = 'telegram'
       AND channels.sender_id = users.telegram_chat_id::text
     WHERE users.telegram_chat_id IS NOT NULL AND trim(users.telegram_chat_id::text) <> ''
       AND (channels.uid IS DISTINCT FROM users.uid OR channels.owner_kind IS DISTINCT FROM 'legacy')
  ) THEN
    RAISE EXCEPTION 'telegram_channel_owner_conflict';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.lm_message_channels_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
  RAISE EXCEPTION 'Life Manager message-channel records are append-only';
END;
$$;

DROP TRIGGER IF EXISTS lm_message_channels_update_delete_guard ON public.lm_message_channels;
CREATE TRIGGER lm_message_channels_update_delete_guard
  BEFORE UPDATE OR DELETE ON public.lm_message_channels
  FOR EACH ROW EXECUTE FUNCTION public.lm_message_channels_guard();

DROP TRIGGER IF EXISTS lm_message_channels_truncate_guard ON public.lm_message_channels;
CREATE TRIGGER lm_message_channels_truncate_guard
  BEFORE TRUNCATE ON public.lm_message_channels
  FOR EACH STATEMENT EXECUTE FUNCTION public.lm_message_channels_guard();

DROP TRIGGER IF EXISTS lm_web_message_link_tokens_update_delete_guard ON public.lm_web_message_link_tokens;
CREATE TRIGGER lm_web_message_link_tokens_update_delete_guard
  BEFORE UPDATE OR DELETE ON public.lm_web_message_link_tokens
  FOR EACH ROW EXECUTE FUNCTION public.lm_message_channels_guard();

DROP TRIGGER IF EXISTS lm_web_message_link_tokens_truncate_guard ON public.lm_web_message_link_tokens;
CREATE TRIGGER lm_web_message_link_tokens_truncate_guard
  BEFORE TRUNCATE ON public.lm_web_message_link_tokens
  FOR EACH STATEMENT EXECUTE FUNCTION public.lm_message_channels_guard();

CREATE OR REPLACE FUNCTION public.lm_register_legacy_telegram_channel()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  sender text;
  owner_uid text;
  owner_kind_value text;
BEGIN
  IF NEW.telegram_chat_id IS NULL OR trim(NEW.telegram_chat_id::text) = '' THEN
    RETURN NEW;
  END IF;
  IF NEW.uid ~* '^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'web_identity_requires_message_link';
  END IF;

  sender := trim(NEW.telegram_chat_id::text);
  IF TG_OP = 'UPDATE'
     AND OLD.telegram_chat_id IS NOT NULL
     AND OLD.telegram_chat_id::text IS DISTINCT FROM sender THEN
    RAISE EXCEPTION 'telegram_channel_identity_immutable';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended('lm-message-channel:telegram:' || sender, 0));
  SELECT uid, owner_kind INTO owner_uid, owner_kind_value
    FROM public.lm_message_channels
   WHERE channel = 'telegram' AND sender_id = sender
   FOR UPDATE;
  IF FOUND THEN
    IF owner_uid = NEW.uid AND owner_kind_value = 'legacy' THEN RETURN NEW; END IF;
    RAISE EXCEPTION 'telegram_channel_owner_conflict';
  END IF;

  INSERT INTO public.lm_message_channels(uid, channel, sender_id, owner_kind)
  VALUES (NEW.uid, 'telegram', sender, 'legacy');
  RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.lm_register_legacy_telegram_channel() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS lm_users_register_legacy_telegram_channel ON public.lm_users;
CREATE TRIGGER lm_users_register_legacy_telegram_channel
  AFTER INSERT OR UPDATE OF telegram_chat_id ON public.lm_users
  FOR EACH ROW EXECUTE FUNCTION public.lm_register_legacy_telegram_channel();

CREATE OR REPLACE FUNCTION public.create_lm_web_message_link(
  p_uid text,
  p_channel text,
  p_token_hash text,
  p_expires_at timestamptz
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE eligible_uid text;
BEGIN
  IF p_uid IS NULL OR p_uid !~ '^lm_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
     OR p_channel NOT IN ('telegram', 'imessage')
     OR p_token_hash IS NULL OR p_token_hash !~ '^[a-f0-9]{64}$'
     OR p_expires_at IS NULL OR p_expires_at <= now()
     OR p_expires_at > now() + interval '15 minutes' THEN
    RETURN false;
  END IF;

  SELECT uid INTO eligible_uid
    FROM public.lm_users
   WHERE uid = p_uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF eligible_uid IS NULL THEN RETURN false; END IF;
  IF EXISTS (
    SELECT 1 FROM public.lm_message_channels
     WHERE uid = p_uid AND channel = p_channel
  ) THEN RETURN false; END IF;

  INSERT INTO public.lm_web_message_link_tokens(token_hash, uid, channel, expires_at)
  VALUES (p_token_hash, p_uid, p_channel, p_expires_at);
  RETURN true;
EXCEPTION WHEN unique_violation THEN
  RETURN false;
END;
$$;

CREATE OR REPLACE FUNCTION public.consume_lm_web_message_link(
  p_token_hash text,
  p_channel text,
  p_sender_id text
) RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  link public.lm_web_message_link_tokens%ROWTYPE;
  eligible_uid text;
  inserted_count integer;
BEGIN
  IF p_token_hash IS NULL OR p_token_hash !~ '^[a-f0-9]{64}$'
     OR p_channel NOT IN ('telegram', 'imessage')
     OR p_sender_id IS NULL OR length(p_sender_id) < 1 OR length(p_sender_id) > 255
     OR p_sender_id ~ '[[:cntrl:]]'
     OR (p_channel = 'telegram' AND p_sender_id !~ '^[1-9][0-9]{0,19}$') THEN
    RETURN NULL;
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended('lm-message-channel:' || p_channel || ':' || p_sender_id, 0));
  SELECT * INTO link
    FROM public.lm_web_message_link_tokens
   WHERE token_hash = p_token_hash AND channel = p_channel AND expires_at > now()
   FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;

  SELECT uid INTO eligible_uid
    FROM public.lm_users
   WHERE uid = link.uid AND telegram_chat_id IS NULL
   FOR UPDATE;
  IF eligible_uid IS NULL THEN RETURN NULL; END IF;

  IF p_channel = 'telegram' AND EXISTS (
    SELECT 1 FROM public.lm_users WHERE telegram_chat_id::text = p_sender_id
  ) THEN RETURN NULL; END IF;
  IF EXISTS (
    SELECT 1 FROM public.lm_message_channels
     WHERE (channel = p_channel AND sender_id = p_sender_id)
        OR (channel = p_channel AND uid = link.uid)
  ) THEN RETURN NULL; END IF;

  INSERT INTO public.lm_message_channels(uid, channel, sender_id, owner_kind, token_hash)
  VALUES (link.uid, p_channel, p_sender_id, 'web_link', p_token_hash)
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS inserted_count = ROW_COUNT;
  IF inserted_count <> 1 THEN RETURN NULL; END IF;
  RETURN link.uid;
EXCEPTION WHEN unique_violation THEN
  RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.create_lm_web_message_link(text, text, text, timestamptz)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.consume_lm_web_message_link(text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_lm_web_message_link(text, text, text, timestamptz) TO service_role;
GRANT EXECUTE ON FUNCTION public.consume_lm_web_message_link(text, text, text) TO service_role;

ALTER TABLE public.lm_web_message_link_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lm_message_channels ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_web_message_link_tokens FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.lm_message_channels FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.lm_message_channels TO service_role;
