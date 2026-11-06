# naive-migration

Local fixture for the official Naïve SDK migration. It is not a production blueprint and it is not wired to `apps/naive-capafy-browser`.

Pinned packages, installed for tests only:

- `@usenaive-sdk/managed-agents` 0.12.0 (ESM). Tests call `client.agents.list` against a Node HTTP server on `127.0.0.1`.
- `@usenaive-sdk/blueprints` 0.18.0. Tests call `loadConfig` on `fixture/naive.config.ts`.
- `@usenaive-sdk/cli` 1.0.0. The published package exposes the `naive` bin and the `init` and `up` aliases. This package does not spawn it.

`npm test` does not use a network API, an API key, an agent, a session, or `naive up`.

The checked-in fixture has a name and no blueprint, template, app, or agent. Do not run `naive up` on it.

`apps/naive-capafy-browser` still depends on `@usenaive-sdk/vetta` 0.10.0. No `@usenaive-sdk/vetta-cli` dependency was found. Those files were left unchanged because they are an application, not a prototype SDK package.
