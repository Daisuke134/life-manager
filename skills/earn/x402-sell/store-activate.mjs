#!/usr/bin/env node
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { forceUpdate } from './store-update.mjs';

export function sellerLabelFor(env = process.env) {
  const home = String(env.ANICCA_HOME || '');
  if (home.includes('.franklin2-home')) return 'ai.anicca.x402-franklin2';
  if (home.endsWith('/.blockrun')) return 'ai.anicca.x402-franklin1';
  if (home.endsWith('/.anicca-founder')) return 'ai.anicca.x402-claude-p';
  return null;
}

function restartLaunchd(label) {
  return new Promise((resolve, reject) => {
    const operator = fileURLToPath(new URL('../../../bin/lm-loop', import.meta.url));
    const owner = label.slice('ai.anicca.'.length);
    execFile(operator, ['restart', owner], { timeout: 15_000 }, (error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

const waitForSeller = () => new Promise((resolve) => setTimeout(resolve, 2500));

export async function activateExperiment(env = process.env, deps = {}) {
  const label = sellerLabelFor(env);
  if (!label) return { activated: false, restarted: false, reason: 'unknown seller instance' };
  const {
    restart = restartLaunchd,
    wait = waitForSeller,
    update = (runtimeEnv) => forceUpdate(runtimeEnv),
  } = deps;

  try {
    await restart(label);
    await wait();
  } catch (error) {
    return {
      activated: false,
      restarted: false,
      reason: `seller restart failed: ${String(error?.message || error).slice(0, 160)}`,
    };
  }

  const registration = await update(env);
  return {
    activated: registration.registered === true,
    restarted: true,
    ...registration,
  };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  activateExperiment()
    .then((result) => process.stdout.write(`${JSON.stringify(result)}\n`))
    .catch((error) => process.stdout.write(`${JSON.stringify({ activated: false, reason: String(error?.message || error) })}\n`));
}
