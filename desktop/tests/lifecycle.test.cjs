'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {SCHEMA,readOwnership,projectProfile,writeJSONAtomic,writePetReady,createLifecycleGuard}=require('../lifecycle.cjs');

function fixture(overrides={}){
  const base='http://127.0.0.1:18119';
  const filename=path.join(os.tmpdir(),'finpilot-controlled-lifecycle.json');
  const record={schema:SCHEMA,project_root:path.resolve('controlled-project'),run_token:'a'.repeat(32),status:'ready',
    owner_pid:4321,owner_started_at:'133700000000000001',backend_pid:5432,backend_started_at:'133700000000000002',
    base_url:base,heartbeat_seq:0,pet_pid:null,...overrides};
  const args=[`--lifecycle-file=${filename}`,`--run-token=${record.run_token}`,`--owner-pid=${record.owner_pid}`,`--owner-start-time=${record.owner_started_at}`];
  return {base,filename,record,args};
}
function guarded({managed=true,health=async()=>true}={}){
  const f=fixture();let current={...f.record},time=0,readFails=false;
  const exits=[],alive=new Set([f.record.owner_pid,f.record.backend_pid]);
  const read=()=>{if(readFails)throw Error('temporary file sharing issue');return current;};
  const ownership=managed?readOwnership(f.args,f.base,{read}):null;
  const guard=createLifecycleGuard({base:f.base,ownership,read,health,isAlive:pid=>alive.has(pid),now:()=>time,onExit:reason=>exits.push(reason)});
  return {...f,guard,exits,alive,setRecord:record=>{current=record;},getRecord:()=>current,advance:ms=>{time+=ms;},failReads:value=>{readFails=value;}};
}

test('manual mode is allowed only when no partial ownership options are supplied',()=>{
  assert.equal(readOwnership([],fixture().base),null);
  for(const args of [['--owner-pid=4321'],['--run-token='+'a'.repeat(32)],['--lifecycle-file=relative.json']]){
    assert.throws(()=>readOwnership(args,fixture().base));
  }
});
test('managed launch binds exact owner creation time and run token before a window is created',()=>{
  const f=fixture();
  const ownership=readOwnership(f.args,f.base,{read:()=>f.record});
  assert.equal(ownership.identity.owner_started_at,'133700000000000001');
  assert.equal(ownership.identity.backend_started_at,'133700000000000002');
  assert(Object.isFrozen(ownership.identity));
  assert.throws(()=>readOwnership([...f.args,'--owner-pid=9999'],f.base,{read:()=>f.record}));
  assert.throws(()=>readOwnership(f.args.map(a=>a.startsWith('--owner-start-time=')?'--owner-start-time=133700000000000099':a),f.base,{read:()=>f.record}));
});
for(const [field,value] of Object.entries({schema:'other',run_token:'b'.repeat(32),owner_pid:-1,owner_started_at:133700000000000001,
  backend_pid:0,backend_started_at:'bad',project_root:'relative',base_url:'https://example.com',heartbeat_seq:NaN,status:'unknown'})){
  test(`invalid initial lifecycle field ${field} is rejected`,()=>{
    const f=fixture();assert.throws(()=>readOwnership(f.args,f.base,{read:()=>({...f.record,[field]:value})}));
  });
}
test('owner disappearance exits once and ignores any subsequent callbacks',async()=>{
  const f=guarded();f.alive.delete(f.record.owner_pid);await f.guard.tick();await f.guard.tick();
  assert.deepEqual(f.exits,['launcher_exited']);
});
test('backend disappearance exits without touching another process',async()=>{
  const f=guarded();f.alive.delete(f.record.backend_pid);await f.guard.tick();
  assert.deepEqual(f.exits,['backend_exited']);
});
test('a reused owner PID cannot renew an old frozen heartbeat',async()=>{
  const f=guarded();await f.guard.tick();f.advance(7999);await f.guard.tick();assert.deepEqual(f.exits,[]);
  // isAlive intentionally keeps returning true, modelling PID reuse.
  f.advance(1);await f.guard.tick();assert.deepEqual(f.exits,['launcher_heartbeat_expired']);
});
test('normal heartbeat updates keep the matching lifetime running',async()=>{
  const f=guarded();
  for(let sequence=1;sequence<=10;sequence++){
    f.advance(1000);f.setRecord({...f.record,heartbeat_seq:sequence,pet_pid:6543});await f.guard.tick();
  }
  assert.deepEqual(f.exits,[]);
});
test('system sleep does not race a live launcher heartbeat on resume',async()=>{
  const f=guarded();f.advance(500);await f.guard.tick();
  f.advance(60000);await f.guard.tick();assert.deepEqual(f.exits,[]);
  f.advance(1000);f.setRecord({...f.record,heartbeat_seq:1});await f.guard.tick();assert.deepEqual(f.exits,[]);
  f.alive.delete(f.record.owner_pid);f.advance(60000);await f.guard.tick();
  assert.deepEqual(f.exits,['launcher_exited']);
});
for(const field of ['run_token','owner_started_at','backend_started_at','project_root','base_url','owner_pid','backend_pid']){
  test(`a replaced lifetime cannot be adopted by changing ${field}`,async()=>{
    const f=guarded();const value=typeof f.record[field]==='number'?f.record[field]+1:String(f.record[field])+'-replacement';
    f.setRecord({...f.record,[field]:value});await f.guard.tick();assert.deepEqual(f.exits,['lifecycle_identity_changed']);
  });
}
for(const status of ['starting','stopping','stopped']){
  test(`${status} closes the host instead of hiding the window`,async()=>{
    const f=guarded();f.setRecord({...f.record,status});await f.guard.tick();assert.deepEqual(f.exits,['project_stopping']);
  });
}
test('one read race is tolerated but a missing lifetime cannot leave a pet indefinitely',async()=>{
  const f=guarded();f.failReads(true);await f.guard.tick();assert.deepEqual(f.exits,[]);
  f.failReads(false);f.setRecord({...f.record,heartbeat_seq:1});await f.guard.tick();assert.deepEqual(f.exits,[]);
  f.failReads(true);await f.guard.tick();await f.guard.tick();await f.guard.tick();
  assert.deepEqual(f.exits,['lifecycle_record_unavailable']);
});
test('a transient backend health failure recovers instead of closing a healthy pet',async()=>{
  const answers=[false,true,false,true];
  const f=guarded({managed:false,health:async()=>answers.shift()});
  for(let i=0;i<4;i++){f.advance(2100);await f.guard.tick();}
  assert.deepEqual(f.exits,[]);
});
test('manual-mode pets also exit after consecutive backend failures',async()=>{
  const f=guarded({managed:false,health:async()=>{throw Error('connection refused');}});
  for(let i=0;i<3;i++){f.advance(2100);await f.guard.tick();}
  assert.deepEqual(f.exits,['backend_unavailable']);
});
test('managed backend health binds the service to the same project run token',async t=>{
  const f=fixture(),exits=[];let token=f.record.run_token;
  const read=()=>f.record,ownership=readOwnership(f.args,f.base,{read});
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({application:'FinPilot',project_run_token:token})}));
  const guard=createLifecycleGuard({base:f.base,ownership,read,isAlive:()=>true,now:()=>0,healthIntervalMs:0,onExit:reason=>exits.push(reason)});
  await guard.tick();assert.deepEqual(exits,[]);
  token='b'.repeat(32);
  await guard.tick();await guard.tick();assert.deepEqual(exits,[]);
  await guard.tick();assert.deepEqual(exits,['backend_unavailable']);
});
test('stopping a guard prevents late rejected health probes from requesting quit',async()=>{
  let rejectProbe;const f=guarded({health:()=>new Promise((_resolve,reject)=>{rejectProbe=reject;})});
  const tick=f.guard.tick();f.guard.stop();rejectProbe(Error('aborted'));await tick;assert.deepEqual(f.exits,[]);
});
test('project profiles are stable and differ between source projects',()=>{
  const location=path.join(os.tmpdir(),'FinPilot-profile-check');
  assert.equal(projectProfile(location,'first-project'),projectProfile(location,'first-project'));
  assert.notEqual(projectProfile(location,'first-project'),projectProfile(location,'second-project'));
});
test('settings replace atomically and never leave a truncated old file on rename failure',t=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'finpilot-settings-'));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const filename=path.join(directory,'settings.json');
  writeJSONAtomic(filename,{scale:200});assert.deepEqual(JSON.parse(fs.readFileSync(filename,'utf8')),{scale:200});
  const io={...fs,renameSync(){throw Error('controlled sharing violation');}};
  assert.throws(()=>writeJSONAtomic(filename,{scale:250},{io}));
  assert.deepEqual(JSON.parse(fs.readFileSync(filename,'utf8')),{scale:200});
  assert.deepEqual(fs.readdirSync(directory),['settings.json']);
});
test('ready acknowledgement binds the actual host PID to the managed launcher and backend',t=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'finpilot-pet-ready-'));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const f=fixture();f.args[0]=`--lifecycle-file=${path.join(directory,'lifecycle.json')}`;
  const ownership=readOwnership(f.args,f.base,{read:()=>f.record});
  const filename=writePetReady(ownership,6543);
  assert.equal(filename,path.join(directory,`pet-ready-${f.record.run_token}.json`));
  assert.deepEqual(JSON.parse(fs.readFileSync(filename,'utf8')),{schema:'finpilot.pet-ready.v1',run_token:f.record.run_token,
    owner_pid:f.record.owner_pid,owner_started_at:f.record.owner_started_at,pet_pid:6543,base_url:f.base});
  assert.deepEqual(fs.readdirSync(directory),[path.basename(filename)]);
  assert.throws(()=>writePetReady({...ownership,token:'../escaped'},6543));
  assert.throws(()=>writePetReady(ownership,0));
});
