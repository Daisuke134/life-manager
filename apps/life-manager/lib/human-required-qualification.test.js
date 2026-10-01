"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  qualifyHumanRequirement,
} = require("./human-required-qualification.js");

const SKIP_REQUIREMENTS = [
  "interview",
  "assessment",
  "recording",
  "camera",
  "screen_share",
  "free_form_response",
  "ongoing_approval",
];

test("continuous human work is skipped without delegating it to a person", () => {
  for (const requirement of SKIP_REQUIREMENTS) {
    const decision = qualifyHumanRequirement({
      requirements: [requirement],
      evidence_ref: `provider-readback://lancers/job-1/${requirement}`,
    });
    assert.equal(decision.state, "human_required");
    assert.equal(decision.disposition, "skip");
    assert.equal(decision.delegate_to_human, false);
    assert.equal(decision.bypass_allowed, false);
    assert.deepEqual(decision.reason_codes, [requirement]);
  }
});

test("identity gates hold the provider lane and are never bypassed", () => {
  for (const requirement of ["captcha", "kyc", "identity_verification"]) {
    const decision = qualifyHumanRequirement({
      requirements: [requirement],
      evidence_ref: `provider-readback://crowdworks/job-2/${requirement}`,
    });
    assert.equal(decision.disposition, "hold");
    assert.equal(decision.delegate_to_human, false);
    assert.equal(decision.bypass_allowed, false);
    assert.equal(decision.bootstrap_boundary, null);
  }
});

test("one-time legal or provider authorization is recorded only as a bootstrap boundary", () => {
  for (const requirement of [
    "legal_bootstrap_authorization",
    "provider_bootstrap_authorization",
  ]) {
    const decision = qualifyHumanRequirement({
      requirements: [requirement],
      evidence_ref: `provider-readback://mercor/account-1/${requirement}`,
    });
    assert.equal(decision.disposition, "hold");
    assert.equal(decision.bootstrap_boundary, "one_time_bootstrap_authorization");
    assert.match(decision.qualification_id, /^[0-9a-f]{64}$/);
  }
});

test("identity and bootstrap holds take priority over skip work in mixed requirements", () => {
  const identity = qualifyHumanRequirement({
    requirements: ["interview", "captcha"],
    evidence_ref: "provider-readback://lancers/job-4/requirements",
  });
  assert.equal(identity.disposition, "hold");
  assert.equal(identity.bootstrap_boundary, null);

  const bootstrap = qualifyHumanRequirement({
    requirements: ["free_form_response", "provider_bootstrap_authorization"],
    evidence_ref: "provider-readback://mercor/account-2/requirements",
  });
  assert.equal(bootstrap.disposition, "hold");
  assert.equal(bootstrap.bootstrap_boundary, "one_time_bootstrap_authorization");
});

test("unknown or unbound requirements fail closed", () => {
  assert.throws(
    () => qualifyHumanRequirement({
      requirements: ["write_cover_letter"],
      evidence_ref: "provider-readback://upwork/job-3/requirements",
    }),
    /requirement/i,
  );
  assert.throws(
    () => qualifyHumanRequirement({ requirements: ["interview"] }),
    /evidence/i,
  );
});
