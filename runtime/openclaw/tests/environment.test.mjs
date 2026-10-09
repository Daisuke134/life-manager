import assert from 'node:assert/strict';
import test from 'node:test';
import {buildGatewayEnv} from '../environment.mjs';
import {resolveHarnessPaths} from '../paths.mjs';
test('Gateway child gets its private root and no ambient account or API secrets',()=>{
 const env={HOME:'/home/alice',PATH:'/usr/bin',TMPDIR:'/tmp',AWS_SECRET_ACCESS_KEY:'secret',
 OPENAI_API_KEY:'api-secret',CODEX_HOME:'/foreign/account',OPENCLAW_STATE_DIR:'/foreign/state',
 LM_TELEGRAM_BOT_TOKEN:'telegram-secret',SHELL:'/bin/zsh'};
 const before=structuredClone(env);const paths=resolveHarnessPaths({},'/home/alice');
 const result=buildGatewayEnv(env,paths,{OPENCLAW_GATEWAY_TOKEN:'private-token'});
 assert.deepEqual(env,before);
 assert.equal(result.OPENCLAW_STATE_DIR,'/home/alice/.local/state/life-manager/openclaw');
 assert.equal(result.OPENCLAW_CONFIG_PATH,paths.configPath);
 assert.equal(result.OPENCLAW_GATEWAY_TOKEN,'private-token');
 for(const key of ['AWS_SECRET_ACCESS_KEY','OPENAI_API_KEY','CODEX_HOME','LM_TELEGRAM_BOT_TOKEN','SHELL'])assert.equal(result[key],undefined);
 for(const key of ['OPENCLAW_NO_RESPAWN','OPENCLAW_DISABLE_BONJOUR','OPENCLAW_SKIP_CHANNELS'])assert.equal(result[key],'1');
 assert.equal(result.OPENCLAW_EXEC_SHELL_SNAPSHOT,'0');
 assert.throws(()=>buildGatewayEnv(env,paths,{OPENAI_API_KEY:'not-approved'}));
});
