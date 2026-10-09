import path from 'node:path';
export function buildGatewayEnv(env,paths,secretValues={}) {
  if(Object.keys(secretValues).some(k=>k!=='OPENCLAW_GATEWAY_TOKEN'))throw new Error('unapproved_gateway_secret');
  const result={};
  for(const key of ['PATH','HOME','TMPDIR'])if(typeof env[key]==='string')result[key]=env[key];
  if(!result.HOME || !path.isAbsolute(result.HOME))throw new Error('gateway_home_must_be_absolute');
  Object.assign(result,{LM_DATA_DIR:paths.dataRoot,OPENCLAW_STATE_DIR:paths.stateRoot,
    OPENCLAW_CONFIG_PATH:paths.configPath,OPENCLAW_NO_RESPAWN:'1',
    OPENCLAW_DISABLE_BONJOUR:'1',OPENCLAW_EXEC_SHELL_SNAPSHOT:'0',OPENCLAW_SKIP_CHANNELS:'1'});
  if(secretValues.OPENCLAW_GATEWAY_TOKEN)result.OPENCLAW_GATEWAY_TOKEN=secretValues.OPENCLAW_GATEWAY_TOKEN;
  return Object.freeze(result);
}
