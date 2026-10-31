import { getStore } from "@netlify/blobs";
import { readFileSync } from "node:fs";

const allowedAgents = JSON.parse(
  readFileSync(new URL("./allowed-agents.json", import.meta.url), "utf8"),
);

// Keys: clicks/<agent>/<ts>-<uuid> (legacy) or clicks/<agent>/<platform>/<post>/<ts>-<uuid>.
export const summarize = (keys, agents = allowedAgents) => {
  const counts = Object.fromEntries(agents.map((agentId) => [agentId, 0]));
  const byAgent = Object.fromEntries(
    agents.map((agentId) => [agentId, { total: 0, platforms: {}, posts: {} }]),
  );
  const platforms = {};
  let total = 0;
  for (const key of keys) {
    const parts = key.split("/");
    const agentId = parts[1];
    if (!agentId) continue;
    const platform = parts.length >= 5 ? parts[2] : "legacy";
    const post = parts.length >= 5 ? `${parts[2]}/${parts[3]}` : null;
    counts[agentId] = (counts[agentId] || 0) + 1;
    const row = (byAgent[agentId] ||= { total: 0, platforms: {}, posts: {} });
    row.total += 1;
    row.platforms[platform] = (row.platforms[platform] || 0) + 1;
    if (post) row.posts[post] = (row.posts[post] || 0) + 1;
    platforms[platform] = (platforms[platform] || 0) + 1;
    total += 1;
  }
  return { counts, detail: { total, platforms, agents: byAgent } };
};

export default async (request) => {
  if (request.method !== "GET") {
    return new Response("Method Not Allowed", { status: 405, headers: { allow: "GET" } });
  }
  const keys = [];
  const store = getStore("capafy-attribution-clicks");
  let cursor;
  do {
    const page = await store.list({ prefix: "clicks/", cursor });
    for (const blob of page.blobs) keys.push(blob.key);
    cursor = page.cursor;
  } while (cursor);

  const { counts, detail } = summarize(keys);
  // Default body stays the flat {agent_id: clicks} map for existing readers.
  const body = new URL(request.url).searchParams.get("detail") === "1" ? detail : counts;
  return Response.json(body, { headers: { "cache-control": "no-store" } });
};
