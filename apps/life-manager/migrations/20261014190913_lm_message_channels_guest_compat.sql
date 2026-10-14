-- Keep already-migrated environments aligned with production-safe legacy sender rules.

SET lock_timeout = '5s';
SET statement_timeout = '120s';
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
  IF sender !~ '^-?[1-9][0-9]{0,19}$' THEN
    RETURN NEW;
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
    SELECT 1 FROM public.lm_message_channels
     WHERE channel = 'telegram' AND sender_id = p_sender_id
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

REVOKE ALL ON FUNCTION public.consume_lm_web_message_link(text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.consume_lm_web_message_link(text, text, text) TO service_role;

RESET statement_timeout;
RESET lock_timeout;
