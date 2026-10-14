-- Avoid re-enumerating pg_timezone_names for each managed allowance or voice reservation.
-- The web control path validates IANA names; invalid legacy values safely fall back to UTC.
CREATE OR REPLACE FUNCTION public.lm_managed_period(p_uid text)
RETURNS date
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $function$
DECLARE
  time_zone text;
  local_time timestamp;
BEGIN
  SELECT NULLIF(btrim(p.call_time_zone), '') INTO time_zone
    FROM public.lm_panel_preferences AS p
   WHERE p.uid = p_uid;

  time_zone := COALESCE(time_zone, 'UTC');
  BEGIN
    local_time := statement_timestamp() AT TIME ZONE time_zone;
  EXCEPTION WHEN invalid_parameter_value THEN
    local_time := statement_timestamp() AT TIME ZONE 'UTC';
  END;

  RETURN date_trunc('month', local_time)::date;
END;
$function$;

NOTIFY pgrst, 'reload schema';
