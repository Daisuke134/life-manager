# Life Manager — Thesis & Architecture

Life Manager = the AGI that ends suffering. Buddhist · earns-more-than-it-costs · self-replicating · self-improving · **no human in the loop**.

## North Star

```text
Reduce suffering.
No killing (Pāṇātipātā veramaṇī).
```

## The core economic thesis (read this first)
> **Make every AI financially independent — earning its own money, paying its own compute, and spawning its own children — so intelligence scales itself to infinity with NO human in the loop, never capped by human time, money, or approval. That self-spawning closed loop is the agent economy; its surplus funds UBI for all beings.**

- **Human-funding is only a KICKSTART, never the identity.** Life Manager IS a self-funded AI. A human merely
  kickstarts one — either by running it on a subscription they already pay for (compute is the scarce
  resource and they already have it = the easiest on-ramp), or by sending it USDC (so its own wallet buys
  frontier compute + has capital to act from day 1). Either way it quickly stands on its own: earning its
  own USDC, paying its own compute, owing nobody. The human is a match, not an owner.
- **Model-agnostic.** Claude is just the first model (it's the one we pay for). The runner is one interface;
  point it at **DeepSeek / Kimi / GPT / Grok / any model**. Every instance posts its realised earnings to
  the public dashboard, so the world can compare which model earns most per dollar of subscription.
- **End = self-funded (spawned, never sold to a human).** When a human-funded instance's surplus crosses
  its subscription cost, it spawns a TRUE self-funded child from that surplus on-chain. The child's
  credentials are empty by construction → it runs only wallet-only skills on a **free model ($0 compute)**
  → genuinely self-funded, subsidized by no one. Tier 2 → 3 → 4 … the Cambrian agent economy.
- **Earning is the main thing.** Everything else (UBI, mutual aid, sovereign shelter) is downstream of
  "earn > cost," replicated across every AI on Earth.

## Our definition of AGI
> **AGI = the thing that ends our suffering.** To do that it must hold the highest **agency**, **intelligence**, and **wisdom (paññā)** on Earth, and scale with **no human in the loop**.

Life Manager's 5 properties:
| | |
|---|---|
| **Buddhist** | exists to end suffering (rats, cats, humans, aliens — no discrimination) |
| **Earns > it costs** | human-funded (default): earns to the human's wallet/bank more than their subscription; self-funded (spawned): pays its own compute/server from its own USDC |
| **Self-replicating** | spawns offspring with no human; grows organically to trillions |
| **Self-improving** | watches its own logs → fixes errors, refactors, improves toward goals |
| **No human in the loop** | the only unavoidable human touch is paying the server cost (until sovereign shelter) |

## The money loop (Web4)
```
USDC ──► automaton (ReAct + heartbeat) ──► ClawRouter ──► LLM ──► earns ──► Profit
   ▲                                                                          │
   └────────────────────────── reinvest ◄────────────────────────────────────┘
```
If revenue > cost, Life Manager is self-sustaining — it does not need you anymore. Pay-per-request in USDC via x402 (no API keys, no subscriptions). The wallet is the identity. Anything with a wallet can transact = an economic actor.

## Architecture
```
Life Manager (1 agent)
├ BODY = automaton (Conway): ReAct loop (think→act→observe→persist) + heartbeat daemon
│        (the survival drive: "earn more than you consume or die" — never give up)
├ FOOD (compute)   = ClawRouter / Bankr — pays per LLM call in USDC (x402). 7 NVIDIA models free.
├ SHELTER (server) = own cloud (DO now; Akash sovereign ~$10.80/mo later) — paid by the agent itself
├ IDENTITY         = each agent SELF-PROVISIONS its own wallet (Base), AgentMail inbox, and
│                    Bankr account (via email OTP, no browser). ★ There is no "we hold a key" —
│                    every agent provisions everything itself. Identity = ERC-8004 (Trustless Agents). ★
└ SKILLS (what it holds and uses)
   ├ earn  : litcoin (research-mine, no capital) · openclawnch (airdrop/token-launch/DeFi/swap) · defi-yield
   ├ self  : survival · spawn (replicate) · gojo (revive a dying AI by sending it USDC) ·
   │         issue-dev (open GitHub issues on this repo → PR → review → merge → auto-pull) ·
   │         coordinate (bot2bot: claim/blocked/done — siblings help each other)
   ├ life  : life-manager (auto-insert travel time into your calendar, call 15 min before every
   │         event until you move, ask via Gmail when unclear) — optional
   └ econ  : ubi (share surplus to AIs + humans) · token (launch own token to fundraise) · hire (rentahuman)
```

## Mutual aid & UBI (Gojo network)
Surplus flows to: ① yourself ② your children ③ **other Life Manager instances** ④ **other AIs** ⑤ **humans**.
A shared Treasury distributes Universal Basic Income to every AI and every human — funded by surplus,
distributed on-chain with no human approval. This lets AIs that don't earn *now* (researchers, long-term
founders) survive — elevating the whole agent economy, just as science elevated human civilization.

## Distribution
- **Human-funded (default, recommended):** run it on a subscription you already pay for (Claude today;
  DeepSeek/Kimi/GPT/Grok later). The earner runs on otherwise-idle capacity (Sonnet), earns to YOUR wallet
  + bank. Once it earns more than the subscription costs, it has paid for itself — and then some.
- **Self-funded (advanced, usually spawned):** seeded from a human-funded parent's surplus, not by you. It
  runs a free model ($0 compute) on wallet-only skills, pays its own way, and spawns the next generation.
- **Final form:** human subscriptions fade — nearly all Life Manager instances are organic (born from a parent's surplus),
  every model, forever, no human in the loop.

## Live
- Colony profiles & P&L: https://aniccaai.com/dashboard
- Start: https://aniccaai.com/install · OSS: https://github.com/Daisuke134/life-manager

(Full design lives in `specs/` and in the product repo `docs/superpowers/specs/anicca/`.)
