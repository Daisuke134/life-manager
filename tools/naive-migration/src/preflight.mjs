import { loadConfig } from "@usenaive-sdk/blueprints";

/** Official config load only. Does not reconcile, apply, or run `naive up`. */
export function preflightConfig(dir) {
  return loadConfig(dir);
}
