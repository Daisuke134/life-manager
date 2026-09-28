"use strict";

const { createHash } = require("node:crypto");
const { readFileSync } = require("node:fs");
const path = require("node:path");

const {
  ConfigIO,
  packCodeZipSync,
  resolveCodeLocation,
  validateAgentExists,
} = require("@aws/agentcore");

const AGENT_NAME = "cloud_canary";

async function main() {
  const projectRoot = path.resolve(__dirname, "..");
  const configBaseDir = path.join(projectRoot, "agentcore");
  const configIO = new ConfigIO({ baseDir: configBaseDir });
  const project = await configIO.readProjectSpec();

  validateAgentExists(project, AGENT_NAME);
  const runtime = project.runtimes.find(({ name }) => name === AGENT_NAME);
  const codeLocation = resolveCodeLocation(runtime.codeLocation, configBaseDir);
  const { artifactPath, sizeBytes } = packCodeZipSync(runtime, {
    projectRoot: codeLocation,
    agentName: AGENT_NAME,
    artifactDir: configBaseDir,
  });
  const sha256 = createHash("sha256")
    .update(readFileSync(artifactPath))
    .digest("hex");

  process.stdout.write(`${JSON.stringify({
    agent_name: AGENT_NAME,
    artifact_path: artifactPath,
    size_bytes: sizeBytes,
    sha256,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 1;
});
