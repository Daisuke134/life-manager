import { createRemoteJWKSet, jwtVerify } from "jose";

export const STATE_ENDPOINT = "https://ulhsqqkyejzvqgoyjwte.supabase.co/functions/v1/manager-owned-state";
export const PROJECT_URL = "https://ulhsqqkyejzvqgoyjwte.supabase.co";
const issuer = "https://token.actions.githubusercontent.com";
const githubKeys = createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks`), {
  timeoutDuration: 5000,
});
const claims = {
  repository: "Daisuke134/life-manager",
  repository_id: "1248111245",
  repository_owner_id: "140220114",
  ref: "refs/heads/main",
  ref_type: "branch",
  workflow_ref: "Daisuke134/life-manager/.github/workflows/manager-phase06-service.yml@refs/heads/main",
  runner_environment: "github-hosted",
};

// A key resolver is the standard jose verification boundary, also used by the
// RSA-signed fixture tests. Production always uses GitHub's fixed JWKS URL.
export async function verifyGithubToken(token, key = githubKeys) {
  const { payload } = await jwtVerify(token, key, {
    issuer,
    audience: STATE_ENDPOINT,
    algorithms: ["RS256"],
    requiredClaims: ["exp", "iat", "nbf", "sub", "jti"],
    maxTokenAge: "5m",
    clockTolerance: 5,
  });
  const denied = Object.entries(claims).some(([name, value]) => payload[name] !== value)
    || !["schedule", "workflow_dispatch"].includes(payload.event_name)
    || typeof payload.sha !== "string" || !/^[0-9a-f]{40}$/.test(payload.sha)
    || payload.workflow_sha !== payload.sha
    || ![payload.run_id, payload.run_attempt].every(
      value => typeof value === "string" && /^[1-9][0-9]{0,19}$/.test(value),
    )
    || ![payload.sub, payload.jti].every(
      value => typeof value === "string" && value.length > 0 && value.length <= 512,
    );
  if (denied) throw new Error("untrusted workflow");
  return { runId: payload.run_id, runAttempt: payload.run_attempt, sourceSha: payload.sha };
}
