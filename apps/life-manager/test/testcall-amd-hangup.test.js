"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { applyTestCallDetection } = require("../lib/late-notice.js");

for (const result of ["machine", "not_sure", "human", ""]) {
  test(`test-call ${result || "unreadable"} never cuts off the caller on an AMD guess`, async () => {
    let requests = 0;
    const out = await applyTestCallDetection({ result, callControlId: "v2:abc",
      fetchImpl: async () => { requests++; throw new Error("provider request forbidden"); } });
    assert.equal(out.result, result);
    assert.equal(out.hangup, null);
    assert.equal(requests, 0);
  });
}
