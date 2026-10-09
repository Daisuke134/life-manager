import path from 'node:path';
import os from 'node:os';
import runtimePaths from '../../apps/life-manager/lib/runtime-paths.js';

export function resolveHarnessPaths(env = {}, homedir = os.homedir()) {
  const dataRoot = runtimePaths.resolveDataRoot({...env, HOME: homedir});
  const stateRoot = path.join(dataRoot, 'openclaw');
  const credentialFile = env.LM_CREDENTIALS_FILE || path.join(homedir, '.local/share/anicca/credentials.json');
  if (!path.isAbsolute(credentialFile)) throw new Error('LM_CREDENTIALS_FILE must be absolute');
  return Object.freeze({dataRoot, stateRoot, configPath: path.join(stateRoot, 'config.json'),
    dispatchRoot: path.join(stateRoot, 'dispatch'), workspaceRoot: path.join(stateRoot, 'workspaces'),
    credentialFile});
}
