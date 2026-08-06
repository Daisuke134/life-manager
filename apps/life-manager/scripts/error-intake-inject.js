#!/usr/bin/env node
"use strict";

const http = require("node:http");
const { execFileSync } = require("node:child_process");
const { Pool } = require("pg");
const { persistFeedback } = require("../lib/feedback-intake.js");
const {
  runControlledErrorInjection,
  runtimeRegressionDetected,
} = require("../lib/error-injection.js");


const RAILWAY_PROJECT = "f9c524cb-ba4a-43bb-9639-ff736afd9ec1";
const RAILWAY_APP_SERVICE = "life-call";
const RAILWAY_POSTGRES_SERVICE = "Postgres-1nl0";


function railwayVariables(service) {
  return JSON.parse(execFileSync(
    "railway",
    [
      "variables",
      "-p", RAILWAY_PROJECT,
      "-s", service,
      "-e", "production",
      "--json",
    ],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  ));
}


function timeoutProbe() {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("controlled_timeout")), 25);
    Promise.resolve(new Promise(() => {})).then(() => {
      clearTimeout(timer);
      resolve();
    });
  });
}


async function sideEffectProbe() {
  execFileSync(process.execPath, ["-e", "process.exit(23)"], {
    stdio: "ignore",
  });
}


async function runtimeProbe() {
  const server = http.createServer((_request, response) => {
    response.writeHead(503, { "content-type": "text/plain" });
    response.end("controlled");
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let httpStatus = 0;
  try {
    const address = server.address();
    const response = await fetch(`http://127.0.0.1:${address.port}/health`);
    httpStatus = response.status;
    await response.arrayBuffer();
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
  let evalFailed = false;
  try {
    execFileSync(process.execPath, ["-e", "process.exit(1)"], {
      stdio: "ignore",
    });
  } catch {
    evalFailed = true;
  }
  if (runtimeRegressionDetected({ httpStatus, evalFailed })) {
    throw new Error("controlled_runtime_regression");
  }
}


async function main() {
  const database = railwayVariables(RAILWAY_POSTGRES_SERVICE).DATABASE_PUBLIC_URL;
  const appVariables = railwayVariables(RAILWAY_APP_SERVICE);
  const provenanceKey = appVariables.LM_FEEDBACK_PROVENANCE_KEY || appVariables.LM_UID_SECRET;
  if (!database || !provenanceKey) throw new Error("error_intake_production_variables_unavailable");
  const pool = new Pool({ connectionString: database });
  try {
    const results = await runControlledErrorInjection({
      provenanceKey,
      timeoutProbe,
      sideEffectProbe,
      runtimeProbe,
      persist: (intake) => persistFeedback(intake, { query: pool.query.bind(pool) }),
    });
    process.stdout.write(`${JSON.stringify({ incidents: results })}\n`);
  } finally {
    await pool.end();
  }
}


main().catch((error) => {
  process.stderr.write(`error-intake-inject failed: ${error.message}\n`);
  process.exitCode = 1;
});
