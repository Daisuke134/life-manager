"use strict";

const LIFE_MANAGER_WEB_APP_URL = "https://life-call-production.up.railway.app/lm?start_calendar=1";
const WRITER_KEYS = Object.freeze(["product_id", "run_id", "artifact_id", "variant_id", "click_id"]);
const UTM_LIMITS = Object.freeze({
  utm_source: 120,
  utm_medium: 120,
  utm_campaign: 200,
  utm_content: 200,
  utm_term: 120,
});
const SAFE = /^[A-Za-z0-9._-]{1,120}$/;
const RUN = /^\d{8}-\d{6}$/;

function lifeManagerCtaHref(search) {
  const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
  const values = Object.fromEntries(WRITER_KEYS.map((key) => [key, params.get(key) || ""]));
  if (values.product_id === "anicca" && RUN.test(values.run_id)
      && SAFE.test(values.artifact_id) && SAFE.test(values.variant_id) && SAFE.test(values.click_id)) {
    const writerParams = new URLSearchParams(WRITER_KEYS.map((key) => [key, values[key]]));
    return "/.netlify/functions/writer-cta?" + writerParams.toString();
  }

  const target = new URL(LIFE_MANAGER_WEB_APP_URL);
  for (const [key, maxBytes] of Object.entries(UTM_LIMITS)) {
    const candidates = params.getAll(key);
    if (candidates.length !== 1) continue;
    const value = candidates[0].trim();
    if (!value || new TextEncoder().encode(value).length > maxBytes) continue;
    target.searchParams.set(key, value);
  }
  return target.toString();
}

export { LIFE_MANAGER_WEB_APP_URL, WRITER_KEYS, lifeManagerCtaHref };
