# Anicca Monk DB — remote MCP server

Read-only Buddhist teachings database exposed over MCP (stateless Streamable HTTP, JSON responses). One endpoint serves ChatGPT apps, Claude connectors, Muse connectors and any MCP client.

- Tools: `search_teachings`, `get_teaching`, `daily_dhamma` (all `readOnlyHint: true`).
- Data: `data/teachings.json`. Seed = full Dhammapada (423 verses), Bhikkhu Sujato translation, CC0 via SuttaCentral bilara-data. Rebuild with `npm run build-data`.
- Run locally: `npm run dev` → `http://localhost:8787/mcp`. Test: `npm test`.
- Deploy (free): `npx wrangler deploy` (Cloudflare Workers free plan). `src/server.mjs` exports `{ fetch }`, so it also runs on Vercel/Netlify/Deno edge.

Spec and store submission steps: `docs/team/specs/monk-db-plugin.md`.
