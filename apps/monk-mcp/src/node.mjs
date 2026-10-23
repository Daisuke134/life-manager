// Local dev: node src/node.mjs  -> http://localhost:8787/mcp
import { createServer } from 'node:http';
import { handle } from './server.mjs';
createServer(async (req, res) => {
  const chunks = []; for await (const c of req) chunks.push(c);
  const r = await handle(new Request('http://localhost' + req.url, { method: req.method, headers: req.headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks) }));
  res.writeHead(r.status, Object.fromEntries(r.headers)); res.end(Buffer.from(await r.arrayBuffer()));
}).listen(process.env.PORT ?? 8787);
