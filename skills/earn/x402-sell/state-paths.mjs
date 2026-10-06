import { homedir } from 'node:os';
import { join } from 'node:path';

export function resolveX402StateDir(env = process.env) {
  return env.X402_STATE_DIR
    || env.LIFE_MANAGER_STATE_ROOT
    || join(env.HOME || homedir(), '.local', 'state', 'life-manager', 'x402-sell');
}

export const X402_STATE_DIR = resolveX402StateDir();
