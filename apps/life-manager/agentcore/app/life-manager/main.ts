import { createRequire } from "node:module";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const {
  validateRuntimeRequest,
  validateRuntimeResult,
} = require("../../../../lib/agentcore-runtime-envelope.js");

type RuntimeRequest = {
  schema_version: 1;
  tenant_id: string;
  job_id: string;
  attempt: number;
  wake_id: string;
  release_sha: string;
  input_refs: string[];
};

type UsageReceipt = {
  provider: string;
  resource: string;
  quantity: number;
  unit: string;
  cost_usd_micros: number;
  provider_receipt_id: string;
};

type HostResult = {
  receipt: {
    status: string;
    evidence_hash: string;
  };
  official_readback: {
    verified: boolean;
    receipt_ref: string;
  };
};

type RuntimeHost = {
  executeReferencedTask(taskRef: string, expectedJobId: string): Promise<HostResult>;
};

type RuntimeDependencies = {
  approvedReleaseSha: string;
  host: RuntimeHost;
  usage: UsageReceipt[];
};

function stateTaskRef(request: RuntimeRequest): string {
  const matches = request.input_refs.filter((ref) => ref.startsWith("lm-resource://state/"));
  if (matches.length !== 1) {
    throw new Error("AgentCore request requires exactly one state task reference");
  }
  return matches[0];
}

export async function executeRuntimeRequest(
  value: unknown,
  dependencies: RuntimeDependencies,
) {
  const request = validateRuntimeRequest(value, {
    approvedReleaseSha: dependencies.approvedReleaseSha,
  }) as RuntimeRequest;
  const execution = await dependencies.host.executeReferencedTask(
    stateTaskRef(request),
    request.job_id,
  );
  if (!execution.official_readback?.verified) {
    throw new Error("AgentCore official receipt readback is not verified");
  }
  return validateRuntimeResult({
    tenant_id: request.tenant_id,
    job_id: request.job_id,
    attempt: request.attempt,
    release_sha: request.release_sha,
    status: execution.receipt.status,
    receipt_ref: execution.official_readback.receipt_ref,
    evidence_sha256: execution.receipt.evidence_hash,
    usage: dependencies.usage,
  }, request);
}

async function loadDependencies(): Promise<RuntimeDependencies> {
  const modulePath = String(process.env.LIFE_MANAGER_RUNTIME_BOOTSTRAP || "").trim();
  if (!modulePath) throw new Error("LIFE_MANAGER_RUNTIME_BOOTSTRAP is required");
  const loaded = await import(pathToFileURL(resolve(modulePath)).href);
  if (typeof loaded.createRuntimeDependencies !== "function") {
    throw new Error("Life Manager Runtime bootstrap is invalid");
  }
  return loaded.createRuntimeDependencies();
}

async function run() {
  const [{ BedrockAgentCoreApp }, dependencies] = await Promise.all([
    import("bedrock-agentcore/runtime"),
    loadDependencies(),
  ]);
  const app = new BedrockAgentCoreApp({
    invocationHandler: {
      async *process(payload: unknown) {
        const result = await executeRuntimeRequest(payload, dependencies);
        yield { data: JSON.stringify(result) };
      },
    },
  });
  app.run({ port: Number.parseInt(process.env.PORT || "8080", 10) });
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath && fileURLToPath(import.meta.url) === invokedPath) {
  void run();
}
