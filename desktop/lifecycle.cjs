'use strict';
// Local lifetime information is supplied by the project launcher, never by a
// renderer or a remote endpoint. This module has no process-termination API.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {performance}=require('node:perf_hooks');
const {localBase}=require('./geometry.cjs');

const SCHEMA='finpilot.project-lifecycle.v1';
const RUN_TOKEN=/^[a-f0-9]{32}$/i;
const PID=value=>Number.isSafeInteger(value)&&value>0&&value<=2147483647;
const creationTime=value=>typeof value==='string'&&/^[0-9]{1,30}$/.test(value);
const identityKeys=['project_root','run_token','base_url','owner_pid','owner_started_at','backend_pid','backend_started_at'];

function readJSON(filename){
  if(fs.statSync(filename).size>65536)throw Error('Lifecycle record is too large');
  return JSON.parse(fs.readFileSync(filename,'utf8').replace(/^\uFEFF/,''));
}
function processAlive(pid){
  try{process.kill(pid,0);return true;}catch(error){return error.code==='EPERM';}
}
function normalizeRecord(record,{token,base,ownerPid,ownerStartedAt}){
  if(!record||typeof record!=='object'||Array.isArray(record)||record.schema!==SCHEMA)throw Error('Invalid project lifecycle record');
  if(record.run_token!==token||!['starting','ready','stopping','stopped'].includes(record.status))throw Error('Project lifecycle identity changed');
  if(typeof record.project_root!=='string'||!path.isAbsolute(record.project_root))throw Error('Missing project identity');
  if(!PID(record.owner_pid)||!PID(record.backend_pid)||!creationTime(record.owner_started_at))throw Error('Invalid project process identity');
  if(record.backend_started_at!==undefined&&!creationTime(record.backend_started_at))throw Error('Invalid backend process identity');
  if(ownerPid!==undefined&&record.owner_pid!==ownerPid)throw Error('Launcher process does not match');
  if(ownerStartedAt!==undefined&&record.owner_started_at!==ownerStartedAt)throw Error('Launcher creation time does not match');
  if(typeof record.base_url!=='string'||localBase(record.base_url)!==base)throw Error('Lifecycle points to another backend');
  if(!Number.isSafeInteger(record.heartbeat_seq)||record.heartbeat_seq<0)throw Error('Missing launcher heartbeat');
  return {...record,project_root:path.resolve(record.project_root),base_url:base,backend_started_at:record.backend_started_at??null};
}
function readOwnership(argv,base,{read=readJSON}={}){
  const names=['lifecycle-file','run-token','lifecycle-token','owner-pid','owner-start-time'];
  const values={};
  for(const name of names){
    const matches=argv.filter(value=>value.startsWith(`--${name}=`));
    if(matches.length>1)throw Error(`Duplicate ${name} option`);
    if(matches.length)values[name]=matches[0].slice(name.length+3);
  }
  if(!Object.keys(values).length)return null;
  const file=values['lifecycle-file'],token=values['run-token']||values['lifecycle-token'];
  if(!file||!path.isAbsolute(file)||!token||!RUN_TOKEN.test(token))throw Error('A managed pet needs an absolute lifecycle file and a 32-character hexadecimal run token');
  if(values['run-token']&&values['lifecycle-token']&&values['run-token']!==values['lifecycle-token'])throw Error('Conflicting run tokens');
  const ownerPid=values['owner-pid']===undefined?undefined:Number(values['owner-pid']);
  const ownerStartedAt=values['owner-start-time'];
  if(ownerPid!==undefined&&(!/^\d+$/.test(values['owner-pid'])||!PID(ownerPid)))throw Error('Invalid launcher PID');
  if(ownerStartedAt!==undefined&&!creationTime(ownerStartedAt))throw Error('Invalid launcher creation time');
  const expected={token,base:localBase(base),ownerPid,ownerStartedAt};
  const record=normalizeRecord(read(file),expected);
  if(record.status!=='ready')throw Error('Project is no longer ready');
  return Object.freeze({file:path.resolve(file),token,expected:Object.freeze(expected),identity:Object.freeze(Object.fromEntries(identityKeys.map(key=>[key,record[key]]))),heartbeat:record.heartbeat_seq});
}
function projectProfile(appData,projectRoot){
  const canonical=path.resolve(projectRoot);
  const id=crypto.createHash('sha256').update(process.platform==='win32'?canonical.toLowerCase():canonical).digest('hex').slice(0,16);
  return path.join(appData,'FinPilotPet','projects',id);
}
function writeJSONAtomic(filename,value,{io=fs}={}){
  const temporary=filename+`.${process.pid}.tmp`;
  io.mkdirSync(path.dirname(filename),{recursive:true});
  let handle;
  try{
    handle=io.openSync(temporary,'w');
    io.writeFileSync(handle,JSON.stringify(value,null,2),'utf8');
    io.fsyncSync(handle);io.closeSync(handle);handle=undefined;
    io.renameSync(temporary,filename);
  }finally{
    if(handle!==undefined)io.closeSync(handle);
    try{io.unlinkSync(temporary);}catch(error){if(error.code!=='ENOENT')throw error;}
  }
}
function writePetReady(ownership,pid=process.pid){
  if(!ownership||!path.isAbsolute(ownership.file)||!RUN_TOKEN.test(ownership.token)||!PID(pid))throw Error('Invalid companion readiness identity');
  const filename=path.join(path.dirname(ownership.file),`pet-ready-${ownership.token}.json`);
  writeJSONAtomic(filename,{schema:'finpilot.pet-ready.v1',run_token:ownership.token,
    owner_pid:ownership.identity.owner_pid,owner_started_at:ownership.identity.owner_started_at,
    pet_pid:pid,base_url:ownership.identity.base_url});
  return filename;
}
function createLifecycleGuard({base,ownership=null,onExit,read=readJSON,isAlive=processAlive,now=()=>performance.now(),health,
  intervalMs=750,healthIntervalMs=2000,heartbeatTimeoutMs=8000,healthFailureLimit=3,
  setIntervalImpl=setInterval,clearIntervalImpl=clearInterval}={}){
  base=localBase(base);
  if(typeof onExit!=='function')throw Error('Lifecycle exit callback is required');
  let timer,disposed=false,exited=false,checking=false,unavailable=0,healthFailures=0;
  let lastSequence=ownership?.heartbeat,lastHeartbeat=now(),lastTick=lastHeartbeat,lastHealth=-Infinity;
  const stop=()=>{disposed=true;if(timer!==undefined){clearIntervalImpl(timer);timer=undefined;}};
  const exit=reason=>{if(disposed||exited)return;exited=true;stop();onExit(reason);};
  const checkOwnership=()=>{
    if(!ownership)return null;
    if(!isAlive(ownership.identity.owner_pid))return 'launcher_exited';
    if(!isAlive(ownership.identity.backend_pid))return 'backend_exited';
    let record;
    try{record=read(ownership.file);}catch{unavailable++;return unavailable>=3?'lifecycle_record_unavailable':null;}
    let normalized;
    try{normalized=normalizeRecord(record,ownership.expected);}catch{return 'lifecycle_identity_changed';}
    unavailable=0;
    if(identityKeys.some(key=>normalized[key]!==ownership.identity[key]))return 'lifecycle_identity_changed';
    if(normalized.status!=='ready')return 'project_stopping';
    if(normalized.heartbeat_seq<lastSequence)return 'launcher_heartbeat_regressed';
    if(normalized.heartbeat_seq>lastSequence){lastSequence=normalized.heartbeat_seq;lastHeartbeat=now();}
    if(now()-lastHeartbeat>=heartbeatTimeoutMs)return 'launcher_heartbeat_expired';
    return null;
  };
  const checkHealth=health||async function(){
    const response=await fetch(base+'/api/health',{signal:AbortSignal.timeout(1500)});
    if(!response.ok)return false;
    const body=await response.json();
    return body.application==='FinPilot'&&(!ownership||body.project_run_token===ownership.token);
  };
  const tick=async()=>{
    if(disposed)return;
    const currentTime=now(),pause=currentTime-lastTick;
    // Sleep/resume can suspend both the launcher and Electron. Preserve the
    // pre-sleep heartbeat age instead of racing the launcher's first wake tick.
    if(ownership&&pause>heartbeatTimeoutMs)lastHeartbeat+=pause;
    lastTick=currentTime;
    const reason=checkOwnership();
    if(reason){exit(reason);return;}
    if(checking||now()-lastHealth<healthIntervalMs)return;
    checking=true;lastHealth=now();
    try{
      const healthy=await checkHealth();
      if(disposed)return;
      healthFailures=healthy?0:healthFailures+1;
    }catch{if(!disposed)healthFailures++;}
    finally{checking=false;}
    if(!disposed&&healthFailures>=healthFailureLimit)exit('backend_unavailable');
  };
  return {start(){if(disposed||timer!==undefined)return;timer=setIntervalImpl(()=>{void tick();},intervalMs);void tick();},stop,tick};
}
module.exports={SCHEMA,readOwnership,projectProfile,writeJSONAtomic,writePetReady,createLifecycleGuard};
