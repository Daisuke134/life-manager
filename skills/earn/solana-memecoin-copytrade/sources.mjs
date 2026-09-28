const DEFAULT_RPC_URL = process.env.SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com";
const DEFAULT_DEXSCREENER_URL = "https://api.dexscreener.com/tokens/v1/solana";
const DEFAULT_JUPITER_QUOTE_URL = process.env.JUPITER_QUOTE_URL || "https://lite-api.jup.ag/swap/v1/quote";

function requireUrl(value, name) {
  if (typeof value !== "string" || !/^https:\/\//.test(value)) throw new Error(`${name}_url_invalid`);
  return value.replace(/\/+$/, "");
}

async function fetchJson(url, init = {}, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") throw new Error("fetch_unavailable");
  const response = await fetchImpl(url, {
    ...init,
    signal: init.signal || AbortSignal.timeout(15_000),
  });
  if (!response || !response.ok) throw new Error(`provider_http_${response?.status || "unknown"}`);
  try {
    return await response.json();
  } catch {
    throw new Error("provider_json_invalid");
  }
}

async function rpcCall(rpcUrl, method, params, fetchImpl) {
  const body = await fetchJson(rpcUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  }, fetchImpl);
  if (body?.error) throw new Error(`rpc_${method}_error`);
  return body?.result;
}

function gmgnTokenUrl(template, mint) {
  if (typeof template !== "string" || !template) throw new Error("gmgn_endpoint_missing");
  if (!template.includes("{mint}")) throw new Error("gmgn_endpoint_requires_mint_placeholder");
  return template.replaceAll("{mint}", encodeURIComponent(mint));
}

function normalizedJupiterResponse(body) {
  return body?.data?.quote || body?.quote || body;
}

export function createPublicAdapters(options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const rpcUrl = requireUrl(options.rpcUrl || DEFAULT_RPC_URL, "rpc");
  const dexscreenerUrl = requireUrl(options.dexscreenerUrl || DEFAULT_DEXSCREENER_URL, "dexscreener");
  const jupiterQuoteUrl = requireUrl(options.jupiterQuoteUrl || DEFAULT_JUPITER_QUOTE_URL, "jupiter");
  const gmgnEndpoint = options.gmgnTokenUrl || process.env.GMGN_TOKEN_URL;
  const gmgnApiKey = options.gmgnApiKey || process.env.GMGN_API_KEY;

  const rpc = {
    async getSignatures(address, limit = 20) {
      if (typeof address !== "string" || !address) throw new Error("target_address_invalid");
      const result = await rpcCall(rpcUrl, "getSignaturesForAddress", [address, {
        commitment: "confirmed",
        limit,
      }], fetchImpl);
      if (!Array.isArray(result)) throw new Error("rpc_signatures_invalid");
      return result;
    },
    async getTransaction(signature) {
      if (typeof signature !== "string" || !signature) throw new Error("source_signature_invalid");
      return rpcCall(rpcUrl, "getTransaction", [signature, {
        commitment: "confirmed",
        encoding: "jsonParsed",
        maxSupportedTransactionVersion: 0,
      }], fetchImpl);
    },
  };

  const gmgn = {
    async readToken(mint) {
      const url = gmgnTokenUrl(gmgnEndpoint, mint);
      const headers = gmgnApiKey ? { "x-route-key": gmgnApiKey } : undefined;
      const body = await fetchJson(url, headers ? { headers } : {}, fetchImpl);
      return body?.data?.token || body?.data || body?.token || body;
    },
  };

  const dexscreener = {
    async readPairs(mint) {
      const body = await fetchJson(`${dexscreenerUrl}/${encodeURIComponent(mint)}`, {}, fetchImpl);
      return Array.isArray(body) ? body : body?.pairs || [];
    },
  };

  const jupiter = {
    async quote(event, quoteOptions = {}) {
      if (!event || typeof event !== "object") throw new Error("quote_event_invalid");
      const inputMint = event.sourceMint;
      const outputMint = event.destinationMint;
      const amount = event.sourceRawAmount;
      if (typeof inputMint !== "string" || typeof outputMint !== "string" || amount == null) {
        throw new Error("quote_amount_invalid");
      }
      const params = new URLSearchParams({
        inputMint,
        outputMint,
        amount: String(amount),
        slippageBps: String(quoteOptions.slippageBps ?? options.slippageBps ?? 100),
      });
      const body = await fetchJson(`${jupiterQuoteUrl}?${params}`, {}, fetchImpl);
      return normalizedJupiterResponse(body);
    },
  };

  return { rpc, gmgn, dexscreener, jupiter };
}

export const createDefaultAdapters = createPublicAdapters;

