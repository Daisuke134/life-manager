#!/usr/bin/env node
"use strict";
const { evaluateWebAppFactory } = require("../lib/web-app-factory.js");
const LIMIT = 1_048_576;
async function main(argv = process.argv.slice(2)) {
  let now = new Date().toISOString();
  if (argv.length) {
    if (argv.length !== 2 || argv[0] !== "--now") throw new Error("invalid arguments");
    now = argv[1];
  }
  const chunks = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > LIMIT) throw new Error("input too large");
    chunks.push(chunk);
  }
  const report = evaluateWebAppFactory(JSON.parse(Buffer.concat(chunks).toString("utf8")), { now });
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}
if (require.main === module) {
  main().catch(() => {
    // Do not print input, stack traces, credentials or untrusted field values.
    process.stderr.write("web-app-factory: invalid input or arguments\n");
    process.exitCode = 1;
  });
}
module.exports = { main };
