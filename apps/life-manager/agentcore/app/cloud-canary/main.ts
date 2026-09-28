import { hostname } from "node:os";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { z } from "zod";

export const requestSchema = z.object({
  tenant_id: z.string().trim().min(1),
  job_id: z.string().trim().min(1),
  release_sha: z.string().regex(/^[a-f0-9]{40}$/),
  probe: z.literal("read_only"),
}).strict();

type ReadOnlyRequest = z.infer<typeof requestSchema>;
type RuntimeContext = { sessionId?: string };
type SystemIdentity = { hostname: string; workingDirectory: string };

export function buildReadOnlyProbe(
  request: ReadOnlyRequest,
  context: RuntimeContext,
  system: SystemIdentity = {
    hostname: hostname(),
    workingDirectory: process.cwd(),
  },
) {
  const runtimeSessionId = String(context.sessionId || "").trim();
  if (!runtimeSessionId) {
    throw new Error("AgentCore runtime session identity is required");
  }

  return Object.freeze({
    tenant_id: request.tenant_id,
    job_id: request.job_id,
    release_sha: request.release_sha,
    probe: request.probe,
    effect: "none" as const,
    runtime_session_id: runtimeSessionId,
    isolation: Object.freeze({
      hostname: system.hostname,
      working_directory: system.workingDirectory,
    }),
  });
}

async function run() {
  const { BedrockAgentCoreApp } = await import("bedrock-agentcore/runtime");
  const app = new BedrockAgentCoreApp({
    invocationHandler: {
      requestSchema,
      async *process(payload, context) {
        yield { data: JSON.stringify(buildReadOnlyProbe(payload, context)) };
      },
    },
  });
  app.run({ port: Number.parseInt(process.env.PORT || "8080", 10) });
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath && fileURLToPath(import.meta.url) === invokedPath) {
  void run();
}
