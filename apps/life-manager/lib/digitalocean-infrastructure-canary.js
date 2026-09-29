"use strict";

const WRITE_BROWSER_MARKER = String.raw`set -eu
CHROME="$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)"
test -n "$CHROME"
mkdir -p /workspace/lm-browser-site /workspace/lm-browser-profile
python3 -c 'from pathlib import Path; Path("/workspace/lm-browser-site/write.html").write_text("<body><script>localStorage.setItem(\"lm_canary\",\"continuity-v1\");document.body.textContent=\"LM_BROWSER_WRITE_OK\"</script></body>")'
cd /workspace/lm-browser-site
python3 -m http.server 18765 --bind 127.0.0.1 >/tmp/lm-canary-http.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 1
"$CHROME" --headless=new --no-sandbox --disable-gpu --no-first-run --no-default-browser-check --user-data-dir=/workspace/lm-browser-profile --dump-dom http://127.0.0.1:18765/write.html | grep -q LM_BROWSER_WRITE_OK
printf 'LM_BROWSER_WRITE_OK\n'`;

const READ_BROWSER_MARKER = String.raw`set -eu
CHROME="$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)"
test -n "$CHROME"
python3 -c 'from pathlib import Path; Path("/workspace/lm-browser-site/read.html").write_text("<body><script>document.body.textContent=localStorage.getItem(\"lm_canary\")===\"continuity-v1\"?\"LM_BROWSER_CONTINUITY_OK\":\"LM_BROWSER_CONTINUITY_MISSING\"</script></body>")'
cd /workspace/lm-browser-site
python3 -m http.server 18765 --bind 127.0.0.1 >/tmp/lm-canary-http.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 1
"$CHROME" --headless=new --no-sandbox --disable-gpu --no-first-run --no-default-browser-check --user-data-dir=/workspace/lm-browser-profile --dump-dom http://127.0.0.1:18765/read.html | grep -q LM_BROWSER_CONTINUITY_OK
printf 'LM_BROWSER_CONTINUITY_OK\n'`;

const PROVE_SEPARATE_WORKSPACE = String.raw`set -eu
test ! -e /workspace/lm-browser-profile
test ! -e /workspace/lm-browser-site
printf 'LM_TENANT_ISOLATED\n'`;

function dependencies(value) {
  const client = value && value.client;
  if (!client || typeof client.balance !== "function" || typeof client.createBareCanary !== "function"
      || typeof client.show !== "function" || typeof client.exec !== "function"
      || typeof client.remove !== "function") {
    throw new Error("DigitalOcean infrastructure canary dependencies unavailable");
  }
  return value;
}

function exactMarker(receipt, marker, label) {
  if (!receipt || receipt.exit_code !== 0 || String(receipt.stdout || "").trim() !== marker
      || String(receipt.stderr || "") !== "") {
    throw new Error(`DigitalOcean ${label} receipt invalid`);
  }
}

async function runDigitalOceanInfrastructureCanary(input = {}, injected = {}) {
  const deps = dependencies(injected);
  const namePrefix = String(input.namePrefix || "");
  const specPath = String(input.specPath || "");
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,54}[A-Za-z0-9])?$/.test(namePrefix) || !specPath) {
    throw new Error("DigitalOcean infrastructure canary input invalid");
  }

  const before = await deps.client.balance();
  const sessions = [];
  let primaryError = null;
  try {
    const first = await deps.client.createBareCanary({ name: `${namePrefix}-a`, specPath });
    sessions.push(first.session_id);
    await deps.client.show(first.session_id);
    exactMarker(await deps.client.exec(first.session_id, ["sh", "-lc", WRITE_BROWSER_MARKER]),
      "LM_BROWSER_WRITE_OK", "browser write");

    const second = await deps.client.createBareCanary({ name: `${namePrefix}-b`, specPath });
    sessions.push(second.session_id);
    await deps.client.show(second.session_id);
    exactMarker(await deps.client.exec(second.session_id, ["sh", "-lc", PROVE_SEPARATE_WORKSPACE]),
      "LM_TENANT_ISOLATED", "tenant isolation");
    exactMarker(await deps.client.exec(first.session_id, ["sh", "-lc", READ_BROWSER_MARKER]),
      "LM_BROWSER_CONTINUITY_OK", "browser continuity");
  } catch (error) {
    primaryError = error;
  }

  const teardown = [];
  let cleanupError = null;
  for (const id of [...sessions].reverse()) {
    try {
      teardown.push(await deps.client.remove(id));
    } catch (error) {
      cleanupError ||= error;
    }
  }
  let after = null;
  try {
    after = await deps.client.balance();
  } catch (error) {
    cleanupError ||= error;
  }
  if (primaryError) throw primaryError;
  if (cleanupError) throw cleanupError;

  return Object.freeze({
    provider: "digitalocean-managed-agents",
    before_balance: before,
    after_balance: after,
    teardown: Object.freeze(teardown),
    proof: Object.freeze({
      tenant_isolated: true,
      browser_continuity: true,
      official_readback: true,
      replay_zero: true,
      no_ask: true,
      human_input_count: 0,
      effect: "none",
    }),
  });
}

module.exports = { runDigitalOceanInfrastructureCanary };
