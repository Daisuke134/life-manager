import { ApiError, createClient } from "@usenaive-sdk/managed-agents";

const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost"]);

/**
 * Read-only view of the official ESM client. Only `agents.list` is exposed.
 * `baseUrl` must be a local mock. This function does not read credentials
 * from the environment and does not call create, update, or delete.
 *
 * @param {{ baseUrl: string, apiKey: string, fetch?: typeof fetch }} options
 */
export function createReadOnlyAgentsClient({ baseUrl, apiKey, fetch }) {
  const host = new URL(baseUrl).hostname;
  if (!LOCAL_HOSTS.has(host)) {
    throw new Error("read-only client accepts only a local mock baseUrl");
  }
  if (typeof apiKey !== "string" || apiKey.length === 0) {
    throw new Error("apiKey is required and is not read from the environment");
  }
  const client = createClient({ baseUrl, apiKey, fetch });
  return {
    agents: {
      list(query) {
        return client.agents.list(query);
      },
    },
  };
}

export { ApiError };
