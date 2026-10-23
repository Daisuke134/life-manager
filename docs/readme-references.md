# README references

[README](../README.md) · [Mac setup guide](getting-started.md)

## Observed examples

The following GitHub README snapshots inform the structure. Star counts are observations from
`gh api repos/{owner}/{repo}` and can change. They indicate audience scale, not quality,
conversion, or proof that a README caused adoption. No conversion measurements are available.

| Repository | Observed stars | README lines | Mechanism adopted |
|---|---:|---:|---|
| [n8n](https://github.com/n8n-io/n8n/blob/d10f2ef8c160b3aa071eddab80ab5b76d8db14af/README.md) | 208,370 | 73 | One clear use statement, a small capability list, quick start, then documentation links |
| [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT/blob/9eefeb9a586c8f616ef434e3fa9153ab5bc34556/README.md) | 187,713 | 185 | Concrete use cases, separate hosted/self-hosted entry points, explicit current limits |
| [OpenHands](https://github.com/OpenHands/OpenHands/blob/801a3c72886f731ffb7c4af130b46d10e1906e4c/README.md) | 91,618 | 185 | Visible beta status, prerequisites beside commands, a clear next action after launch |
| [Open Interpreter](https://github.com/openinterpreter/openinterpreter/blob/ac1fcc8fe57aba51fcc3c79afd57a0883237fe87/README.md) | 68,640 | 152 | Installation near the top, a named start command, detailed setup in separate guides |

These are popular public repositories with different licenses: n8n is fair-code, and AutoGPT's
platform uses Polyform Shield. Their copy and licensing are not adopted by Life Manager.

## Installer implementation examples

- [Open Interpreter installer](https://github.com/openinterpreter/openinterpreter/blob/ac1fcc8fe57aba51fcc3c79afd57a0883237fe87/scripts/install/install.sh):
  detect OS/CPU and Rosetta, select a release, verify SHA-256, stage the package, switch the
  current symlink, and execute the installed command's version check. This is the closest
  native-Mac reference; its package runtime is not added as a dependency.
- [AutoGPT installer](https://github.com/Significant-Gravitas/AutoGPT/blob/9eefeb9a586c8f616ef434e3fa9153ab5bc34556/autogpt_platform/installer/install.sh):
  preflight, validate existing installation ownership, pin an image digest, reuse matching
  resources, and wait for concrete health with a time limit. Docker is not adopted here.
- [OpenHands launcher](https://github.com/OpenHands/OpenHands/blob/801a3c72886f731ffb7c4af130b46d10e1906e4c/bin/agent-canvas.mjs):
  expose a published CLI with packaged assets and an explicit local-stack launch command.
- n8n's README requires Docker for its quick-start installer. The `get.n8n.io` implementation
  is not part of this source comparison because its retrieval did not complete.

## Life Manager structure

The earlier English README has 614 lines and 5,840 whitespace-separated words, with Quick
Start on line 302. The revised entry point follows this order:

1. A short product description and visible early-development status.
2. ChatGPT Plus or higher, an awake Mac, and the user's own service accounts.
3. One existing Mac bootstrap command, within the first 30 lines.
4. A few concrete capability groups, linked to the full [agent catalog](agents.md).
5. User documentation, a cloud-service link, and license.

Installer details and operation move to [getting started](getting-started.md). Internal owner
names, provider incident timelines, long flowcharts, and deployment receipts stay in their
existing engineering documents. WebMCP and challenge material stay in their
[dedicated guide](webmcp-judge-guide.md). They are not the product's main introduction.

The changes are structural, not borrowed performance or revenue claims. Useful checks are
README length, position of the first working command, valid documentation links, and an
independent user's ability to complete setup. The last item requires real device evidence;
it is not inferred from stars or local tests.
