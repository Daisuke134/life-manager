// Canonical core-mode catalog shared by the serving process and the revenue controller.
// Keep this list limited to routes that serve-v2 actually exposes in its default catalog.
export const CORE_PATHS = Object.freeze([
  '/web-search',
  '/funding-rates',
  '/funding-rate-arb',
  '/research',
  '/llm',
]);

export const CORE_PATH_SET = new Set(CORE_PATHS);
