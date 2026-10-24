# codex-limit-fallback-env.sh -- sourced by the Capafy distribution loops.
# Codex is out for a usage limit until 2026-10-31 10:54 JST (epoch 1793415240). Until 12:00 JST that
# day (epoch 1793415600) these loops may use the scoped Claude fallback config, which adds Claude as
# the LAST composition-agent candidate and only for a Codex usage-limit failure. After the cutoff the
# default Codex-only config applies again with no change needed.
CAPAFY_CODEX_LIMIT_FALLBACK_UNTIL_EPOCH=1793415600
capafy_use_codex_limit_fallback() {
  local repo="${1:?repo root}"
  local config="$repo/runtime/agent-runner/config.codex-limit-fallback.json"
  [ "$(date -u +%s)" -lt "$CAPAFY_CODEX_LIMIT_FALLBACK_UNTIL_EPOCH" ] || return 0
  [ -f "$config" ] || return 0
  export AGENT_RUNNER_CONFIG="$config"
}
