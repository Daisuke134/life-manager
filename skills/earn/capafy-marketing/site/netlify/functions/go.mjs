import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { getStore } from "@netlify/blobs";

// Legacy /go/<agent_id> links (IG bio) keep this exact campaign.
const CAMPAIGN =
  "utm_source=instagram_bio&utm_medium=bio_link&utm_campaign=capafy_marketing";
const allowedAgents = new Set(
  JSON.parse(readFileSync(new URL("./allowed-agents.json", import.meta.url), "utf8")),
);
const TOKEN = /^[A-Za-z0-9_-]{1,80}$/;

const redirect = (location) =>
  new Response(null, { status: 302, headers: { location, "cache-control": "no-store" } });

// /go/<agent_id>[/<platform>[/<post>]][?ct=<capafy ct token>]
export const parseClick = (requestUrl) => {
  const url = new URL(requestUrl);
  const segments = url.pathname.split("/").filter(Boolean);
  const start = segments.indexOf("go");
  const parts = (start >= 0 ? segments.slice(start + 1) : segments.slice(-1)).map((s) =>
    decodeURIComponent(s),
  );
  const [agentId = "", platform = "", post = ""] = parts;
  const clean = (value) => (TOKEN.test(value) ? value : "");
  return {
    agentId,
    platform: clean(platform),
    post: clean(post),
    ct: clean(url.searchParams.get("ct") || ""),
  };
};

export const targetUrl = ({ agentId, platform, post, ct }) => {
  const base = `https://capafy.ai/agent/${encodeURIComponent(agentId)}`;
  if (!platform) return `${base}?${CAMPAIGN}${ct ? `&ct=${ct}` : ""}`;
  const params = new URLSearchParams({
    utm_source: platform,
    utm_medium: "capafy_distribute",
    utm_campaign: "capafy_marketing",
  });
  if (post) params.set("utm_content", post);
  if (ct) params.set("ct", ct);
  return `${base}?${params}`;
};

export const clickKey = ({ agentId, platform, post }, now = Date.now(), id = randomUUID()) =>
  platform
    ? `clicks/${agentId}/${platform}/${post || "_"}/${now}-${id}`
    : `clicks/${agentId}/${now}-${id}`;

export default async (request) => {
  if (request.method !== "GET") {
    return new Response("Method Not Allowed", { status: 405, headers: { allow: "GET" } });
  }
  let click;
  try {
    click = parseClick(request.url);
  } catch {
    return redirect("https://capafy.ai/");
  }
  if (!allowedAgents.has(click.agentId)) return redirect("https://capafy.ai/");

  const store = getStore("capafy-attribution-clicks");
  await store.set(clickKey(click), "1");
  return redirect(targetUrl(click));
};
