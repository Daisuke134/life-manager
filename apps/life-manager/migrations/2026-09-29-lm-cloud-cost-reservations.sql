-- A22: reserve maximum cloud cost before claim/invoke, then settle provider-receipted actual cost.

CREATE TABLE IF NOT EXISTS public.lm_cloud_cost_reservations (
  reservation_ref text PRIMARY KEY CHECK (reservation_ref ~ '^lm-cost:[A-Za-z0-9_-]{8,200}$'),
  tenant_id text NOT NULL REFERENCES public.lm_cloud_tenants(tenant_id),
  job_id text NOT NULL,
  attempt integer NOT NULL CHECK (attempt > 0),
  plan_version text NOT NULL REFERENCES public.lm_plan_entitlements(plan_version),
  month_start date NOT NULL,
  reserved_usd_micros bigint NOT NULL CHECK (reserved_usd_micros > 0),
  actual_cost_usd_micros bigint CHECK (actual_cost_usd_micros IS NULL OR actual_cost_usd_micros >= 0),
  activation_credit_applied_usd_micros bigint NOT NULL DEFAULT 0 CHECK (activation_credit_applied_usd_micros >= 0),
  status text NOT NULL CHECK (status IN ('active', 'reconciling', 'settled', 'released')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  settled_at timestamptz,
  UNIQUE (tenant_id, job_id, attempt),
  FOREIGN KEY (job_id, tenant_id) REFERENCES public.lm_runtime_jobs(job_id, tenant_id),
  CHECK (
    (status = 'active' AND actual_cost_usd_micros IS NULL AND settled_at IS NULL AND expires_at IS NOT NULL)
    OR (status IN ('reconciling', 'released') AND actual_cost_usd_micros IS NULL AND settled_at IS NULL AND expires_at IS NULL)
    OR (status = 'settled' AND actual_cost_usd_micros IS NOT NULL AND settled_at IS NOT NULL AND expires_at IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS lm_cloud_cost_reservations_budget_idx
  ON public.lm_cloud_cost_reservations(tenant_id, month_start, status);

CREATE OR REPLACE FUNCTION public.reserve_lm_cloud_cost(
  p_tenant_id text, p_job_id text, p_attempt integer, p_plan_version text,
  p_estimated_micros bigint, p_reservation_ref text, p_now timestamptz DEFAULT clock_timestamp()
) RETURNS TABLE(decision text, reservation_ref text, reserved_usd_micros bigint, replay_zero boolean)
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
DECLARE
  v_tenant public.lm_cloud_tenants%ROWTYPE;
  v_limits jsonb;
  v_month date := date_trunc('month', p_now)::date;
  v_monthly_cap bigint;
  v_activation_cap bigint;
  v_activation_used bigint;
  v_activation_remaining bigint;
  v_settled_billable bigint;
  v_reserved bigint;
  v_existing public.lm_cloud_cost_reservations%ROWTYPE;
BEGIN
  IF p_estimated_micros <= 0 OR p_attempt <= 0 THEN RAISE EXCEPTION 'invalid cost reservation'; END IF;
  SELECT * INTO v_tenant FROM public.lm_cloud_tenants WHERE tenant_id = p_tenant_id FOR UPDATE;
  IF NOT FOUND OR v_tenant.plan_version <> p_plan_version THEN RETURN QUERY SELECT 'plan_inactive', NULL::text, NULL::bigint, false; RETURN; END IF;
  IF v_tenant.status <> 'active' THEN RETURN QUERY SELECT v_tenant.status, NULL::text, NULL::bigint, false; RETURN; END IF;
  SELECT limits_json INTO v_limits FROM public.lm_plan_entitlements WHERE plan_version = p_plan_version;
  v_monthly_cap := (v_limits->>'monthly_cost_cap_usd_micros')::bigint;
  v_activation_cap := (v_limits->>'activation_credit_usd_micros')::bigint;

  SELECT * INTO v_existing FROM public.lm_cloud_cost_reservations
  WHERE tenant_id=p_tenant_id AND job_id=p_job_id AND attempt=p_attempt;
  IF FOUND THEN
    IF v_existing.plan_version <> p_plan_version OR v_existing.reserved_usd_micros <> p_estimated_micros THEN
      RAISE EXCEPTION 'cost reservation collision';
    END IF;
    IF v_existing.status IN ('active','released') AND (v_existing.status='released' OR v_existing.expires_at <= p_now) THEN
      UPDATE public.lm_cloud_cost_reservations r SET reservation_ref=p_reservation_ref,status='active',
        created_at=p_now,expires_at=p_now+interval '5 minutes'
      WHERE r.tenant_id=p_tenant_id AND r.job_id=p_job_id AND r.attempt=p_attempt;
      RETURN QUERY SELECT 'allow',p_reservation_ref,p_estimated_micros,false; RETURN;
    END IF;
    RETURN QUERY SELECT 'duplicate', v_existing.reservation_ref, v_existing.reserved_usd_micros, true;
    RETURN;
  END IF;

  SELECT COALESCE(sum(r.activation_credit_applied_usd_micros),0) INTO v_activation_used
  FROM public.lm_cloud_cost_reservations r WHERE r.tenant_id=p_tenant_id AND r.status='settled';
  v_activation_remaining := greatest(0, v_activation_cap-v_activation_used);
  SELECT COALESCE(sum(r.actual_cost_usd_micros-r.activation_credit_applied_usd_micros),0) INTO v_settled_billable
  FROM public.lm_cloud_cost_reservations r WHERE r.tenant_id=p_tenant_id AND r.month_start=v_month AND r.status='settled';
  SELECT COALESCE(sum(r.reserved_usd_micros),0) INTO v_reserved
  FROM public.lm_cloud_cost_reservations r WHERE r.tenant_id=p_tenant_id AND r.month_start=v_month AND r.status IN ('active','reconciling');
  IF v_settled_billable+v_reserved+p_estimated_micros > v_monthly_cap+v_activation_remaining THEN
    RETURN QUERY SELECT 'budget_exhausted', NULL::text, NULL::bigint, false; RETURN;
  END IF;
  INSERT INTO public.lm_cloud_cost_reservations(
    reservation_ref,tenant_id,job_id,attempt,plan_version,month_start,reserved_usd_micros,status,created_at,expires_at
  ) VALUES (p_reservation_ref,p_tenant_id,p_job_id,p_attempt,p_plan_version,v_month,p_estimated_micros,'active',p_now,p_now+interval '5 minutes');
  RETURN QUERY SELECT 'allow', p_reservation_ref, p_estimated_micros, false;
END $$;

CREATE OR REPLACE FUNCTION public.reconcile_lm_cloud_cost(
  p_tenant_id text, p_job_id text, p_attempt integer, p_reservation_ref text
) RETURNS TABLE(status text, held_usd_micros bigint)
LANGUAGE sql SET search_path = public, pg_temp AS $$
  UPDATE public.lm_cloud_cost_reservations SET status='reconciling',expires_at=NULL
  WHERE tenant_id=p_tenant_id AND job_id=p_job_id AND attempt=p_attempt
    AND reservation_ref=p_reservation_ref AND status IN ('active','reconciling')
  RETURNING status, reserved_usd_micros
$$;

CREATE OR REPLACE FUNCTION public.settle_lm_cloud_cost(
  p_tenant_id text, p_job_id text, p_attempt integer, p_reservation_ref text,
  p_usage jsonb, p_now timestamptz DEFAULT clock_timestamp()
) RETURNS TABLE(status text, actual_cost_usd_micros bigint, released_usd_micros bigint,
  activation_credit_applied_usd_micros bigint, replay_zero boolean)
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
DECLARE
  v_res public.lm_cloud_cost_reservations%ROWTYPE;
  v_item jsonb;
  v_total bigint := 0;
  v_activation_cap bigint;
  v_activation_used bigint;
  v_activation bigint;
  v_existing public.lm_cloud_usage_ledger%ROWTYPE;
  v_all_receipts boolean := true;
BEGIN
  IF jsonb_typeof(p_usage) <> 'array' OR jsonb_array_length(p_usage)=0 THEN RAISE EXCEPTION 'provider usage required'; END IF;
  SELECT * INTO v_res FROM public.lm_cloud_cost_reservations
  WHERE tenant_id=p_tenant_id AND job_id=p_job_id AND attempt=p_attempt AND reservation_ref=p_reservation_ref FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'cost reservation unavailable'; END IF;
  FOR v_item IN SELECT value FROM jsonb_array_elements(p_usage) LOOP
    IF v_item->>'tenant_id' <> p_tenant_id OR v_item->>'job_id' <> p_job_id
      OR (v_item->>'cost_usd_micros')::bigint < 0 THEN RAISE EXCEPTION 'provider usage invalid'; END IF;
    v_total := v_total + (v_item->>'cost_usd_micros')::bigint;
    SELECT * INTO v_existing FROM public.lm_cloud_usage_ledger WHERE provider_receipt_id=v_item->>'provider_receipt_id';
    IF NOT FOUND THEN v_all_receipts := false; END IF;
    IF FOUND AND (v_existing.tenant_id <> p_tenant_id OR v_existing.job_id <> p_job_id
      OR v_existing.provider <> v_item->>'provider' OR v_existing.resource <> v_item->>'resource'
      OR v_existing.quantity <> (v_item->>'quantity')::bigint OR v_existing.unit <> v_item->>'unit'
      OR v_existing.cost_usd_micros <> (v_item->>'cost_usd_micros')::bigint) THEN
      RAISE EXCEPTION 'provider receipt collision';
    END IF;
  END LOOP;
  IF v_total > v_res.reserved_usd_micros THEN RAISE EXCEPTION 'actual cost exceeds reservation'; END IF;
  IF v_res.status='settled' THEN
    IF v_res.actual_cost_usd_micros <> v_total OR NOT v_all_receipts THEN RAISE EXCEPTION 'cost settlement collision'; END IF;
    RETURN QUERY SELECT 'settled',v_total,v_res.reserved_usd_micros-v_total,v_res.activation_credit_applied_usd_micros,true; RETURN;
  END IF;
  SELECT (limits_json->>'activation_credit_usd_micros')::bigint INTO v_activation_cap
  FROM public.lm_plan_entitlements WHERE plan_version=v_res.plan_version;
  SELECT COALESCE(sum(r.activation_credit_applied_usd_micros),0) INTO v_activation_used
  FROM public.lm_cloud_cost_reservations r WHERE r.tenant_id=p_tenant_id AND r.status='settled';
  v_activation := least(v_total,greatest(0,v_activation_cap-v_activation_used));
  FOR v_item IN SELECT value FROM jsonb_array_elements(p_usage) LOOP
    INSERT INTO public.lm_cloud_usage_ledger(tenant_id,job_id,provider,resource,quantity,unit,cost_usd_micros,provider_receipt_id)
    VALUES (p_tenant_id,p_job_id,v_item->>'provider',v_item->>'resource',(v_item->>'quantity')::bigint,v_item->>'unit',(v_item->>'cost_usd_micros')::bigint,v_item->>'provider_receipt_id')
    ON CONFLICT (provider_receipt_id) DO NOTHING;
  END LOOP;
  UPDATE public.lm_cloud_cost_reservations SET status='settled',actual_cost_usd_micros=v_total,
    activation_credit_applied_usd_micros=v_activation,settled_at=p_now,expires_at=NULL WHERE reservation_ref=p_reservation_ref;
  RETURN QUERY SELECT 'settled',v_total,v_res.reserved_usd_micros-v_total,v_activation,false;
END $$;

CREATE OR REPLACE FUNCTION public.release_lm_cloud_cost(p_tenant_id text,p_reservation_ref text)
RETURNS boolean LANGUAGE sql SET search_path = public, pg_temp AS $$
  WITH released AS (UPDATE public.lm_cloud_cost_reservations SET status='released',expires_at=NULL
    WHERE tenant_id=p_tenant_id AND reservation_ref=p_reservation_ref AND status='active' RETURNING 1)
  SELECT EXISTS(SELECT 1 FROM released)
$$;

ALTER TABLE public.lm_cloud_cost_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lm_cloud_cost_reservations FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reserve_lm_cloud_cost(text,text,integer,text,bigint,text,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reconcile_lm_cloud_cost(text,text,integer,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.settle_lm_cloud_cost(text,text,integer,text,jsonb,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.release_lm_cloud_cost(text,text) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_cloud_cost_reservations FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    EXECUTE 'REVOKE ALL ON TABLE public.lm_cloud_cost_reservations FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
    EXECUTE 'GRANT SELECT,INSERT,UPDATE ON TABLE public.lm_cloud_cost_reservations TO service_role';
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.reserve_lm_cloud_cost(text,text,integer,text,bigint,text,timestamptz) TO service_role';
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.reconcile_lm_cloud_cost(text,text,integer,text) TO service_role';
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.settle_lm_cloud_cost(text,text,integer,text,jsonb,timestamptz) TO service_role';
    EXECUTE 'GRANT EXECUTE ON FUNCTION public.release_lm_cloud_cost(text,text) TO service_role';
  END IF;
END $$;
