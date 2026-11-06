import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";
import { ApiError, createReadOnlyAgentsClient } from "../src/read-only-client.mjs";

test("agents.list reports the local mock error code and request id", async () => {
  const seen = [];
  const server = createServer((req, res) => {
    seen.push({ method: req.method, url: req.url });
    res.writeHead(402, { "content-type": "application/json" });
    res.end(JSON.stringify({
      error: {
        type: "billing_error",
        code: "subscription_required",
        message: "local mock only",
        request_id: "req_local_mock_agents_list",
      },
    }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  try {
    const client = createReadOnlyAgentsClient({
      baseUrl: `http://127.0.0.1:${port}`,
      apiKey: "local-mock-token",
    });
    await assert.rejects(() => client.agents.list(), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.code, "subscription_required");
      assert.equal(error.requestId, "req_local_mock_agents_list");
      return true;
    });
    assert.deepEqual(seen, [{ method: "GET", url: "/v1/agents" }]);
  } finally {
    await new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
  }
});

test("agents.list refuses a non-local baseUrl before any request", () => {
  assert.throws(
    () => createReadOnlyAgentsClient({ baseUrl: "https://api.vetta.sh", apiKey: "local-mock-token" }),
    /local mock/,
  );
});
