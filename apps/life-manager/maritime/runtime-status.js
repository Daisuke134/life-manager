'use strict';
const http = require('node:http');
async function readRuntimeStatus({port=Number(process.env.PORT)}={}) {
  if(!Number.isInteger(port)||port<1||port>65535)throw new Error('maritime_status_invalid');
  function read(path) {
    return new Promise((resolve,reject)=>{
      const request=http.get({host:'127.0.0.1',port,path,timeout:3000},response=>{
        const chunks=[];let size=0;
        response.on('data',chunk=>{
          size+=chunk.length;
          if(size>32768){response.destroy(new Error('maritime_status_oversize'));return;}
          chunks.push(chunk);
        });
        response.on('error',reject);
        response.on('end',()=>{
          try{resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));}catch{reject(new Error('maritime_status_invalid'));}
        });
      });
      request.on('timeout',()=>request.destroy(new Error('maritime_status_timeout')));
      request.on('error',reject);
    });
  }
  const [health,schedules]=await Promise.all([read('/health'),read('/schedules')]);
  return {health,schedules};
}
if(require.main===module)readRuntimeStatus().then(result=>process.stdout.write(JSON.stringify(result)+'\n'))
 .catch(()=>{process.stderr.write('maritime_status_unavailable\n');process.exitCode=2;});
module.exports={readRuntimeStatus};
