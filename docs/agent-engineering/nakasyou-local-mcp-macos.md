# Mac mini: ChatGPT ↔ nakasyou/local-mcp (Life Manager)

**State: prepared bootstrap only; not installed or connected on the Mac.** This is an optional development integration. Do not treat a GitHub commit, tunnel definition, or MCP initialization alone as proof that ChatGPT can operate the host.

## Scope and prerequisites

- Target: https://github.com/nakasyou/local-mcp — NOT the unrelated local-mcp.com installer or npm package.
- Upstream source is pinned to `21025d048f54cc9f948c26ac42fa36183dc453c2` and built using its lockfile; review the upstream code and dependency chain before running.
- macOS host with Apple Command Line Tools (`xcode-select -p`), Git, and a Rust/rustup installation able to use the upstream Rust 1.96.0 toolchain.
- Canonical Life Manager checkout according to `AGENTS.md`: `/Users/anicca/Projects/life-manager-main` (adjust only after confirming the actual checkout and `origin`).
- This installer deliberately changes neither Life Manager's application code nor its launchd/runtime owners. It creates a separate source checkout under `~/.local/share/life-manager/vendor/` and a user-scoped binary under `~/.local/bin/`.

## 1. Install on the actual Mac mini

Review the script first, then from an updated trusted Life Manager checkout run:

```bash
bash scripts/install-nakasyou-local-mcp-macos.sh
```

The script does not install Rust automatically or overwrite an existing, different executable. It compiles pinned upstream code, verifies its binary and performs a local JSON-RPC initialize smoke check. A successful check confirms only the Mac-local process, NOT ChatGPT connectivity.

## 2. Start a Life Manager session (Terminal 1)

```bash
cd /Users/anicca/Projects/life-manager-main
git remote get-url origin  # must match https://github.com/Daisuke134/life-manager.git
$HOME/.local/bin/life-manager-local-mcp start life-manager
```

Use the printed session ID `life-manager` in requests to MCP tools. Keep the session's approval UI running. Leave `/permission ask` enabled. Do **not** use `/permissions yolo` or broad additional sandbox roots. A local `without_sandbox` command can run with your Mac user's permissions, including network access, after approval.

## 3. Reach the Mac from ChatGPT cloud

`nakasyou/local-mcp mcp` is a **stdio** server, not a remote HTTPS endpoint. ChatGPT cloud cannot directly attach to Mac-local stdio. Prefer OpenAI's outbound-only **Secure MCP Tunnel** instead of exposing arbitrary shell tools using an unauthenticated public URL.

Official: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels and https://developers.openai.com/api/docs/guides/custom-mcp-server

1. In OpenAI Platform tunnel settings, create a tunnel and obtain a tunnel ID and an authorized runtime API key. Never commit or paste the key into chat.
2. Download/install `tunnel-client` on the Mac following the official tunnel guide. Supply `CONTROL_PLANE_API_KEY` securely in its environment; do not save it in this repository or shell history.
3. Configure a named stdio profile (replace the tunnel ID; do not reuse the documentation example):

```bash
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile life-manager-local \
  --tunnel-id YOUR_TUNNEL_ID \
  --mcp-command "$HOME/.local/bin/life-manager-local-mcp mcp"
tunnel-client doctor --profile life-manager-local --explain
tunnel-client run --profile life-manager-local
```

4. On **ChatGPT web**, open https://chatgpt.com/plugins → Add custom MCP server → Connection: **Tunnel** → select the tunnel. Review permissions and complete plugin setup.
5. In an eligible chat, enable the custom plugin and have it call `session_info` with `session_id: life-manager`; confirm its reported working directory is the intended checkout **before** any file operation.

**Plan caveat (verified 2026-10-08):** OpenAI's ChatGPT developer-mode help currently says Pro custom MCP connections are read/fetch-only and full write/command MCP tools are in beta for Business, Enterprise, and Edu. Even if the Mac and tunnel are set up, the desired ChatGPT Pro → edit/run local code path may be unavailable. Check the current eligibility/permissions before relying on this design.
Official: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt

## 4. Alternative that may be better for ChatGPT Pro

ChatGPT Work on the **Mac desktop app** can access local projects through its supported local execution environment (subject to rollout/permissions). Set up the `life-manager` project in Work and use Remote or Local computer access with Work Cloud where available. This is a separate path from Codex and may avoid the custom-MCP write-access limitation, though Work still has its own usage and permission limits.

Official: https://learn.chatgpt.com/docs/remote-connections and https://learn.chatgpt.com/docs/enterprise/chatgpt-work-local-security

Independently, ChatGPT's already-connected GitHub plugin can review and modify `Daisuke134/life-manager` through reviewed branches/PRs; the owner can merge and pull those changes on the Mac without a custom MCP connection or Codex execution.

## Security and verification checklist

- Never expose an unprotected file/command MCP endpoint to the public internet.
- Keep sensitive application files, login sessions, wallet material, and `.env` files out of chat and commits.
- In the local-mcp approvals UI use the default prompt mode, not `yolo`.
- Verify the binary locally, then the tunnel health, then tool discovery and the `session_info` working directory; test one **sandboxed, non-production** read before considering writes.
- Do not start/restart production Life Manager loops or alter launchd owners as part of installing developer tooling. Follow the repository's existing source-boundary and worktree/promotion contracts separately.
- An installed binary does not prove a ChatGPT plugin is connected; a connected plugin does not prove an approved write succeeded.

**Handoff:** Current GitHub work only stages installer/documentation. Mac execution, tunnel credentials, tunnel health, actual plugin authorization, and command/write capability remain unverified until run on the user's Mac and read back through the appropriate tool.
