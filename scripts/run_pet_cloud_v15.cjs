'use strict';
/* Opt-in owned harness, never a model-response mock. Default: zero actions.
 * The isolated Python process alone reads server .env; this Node file does not.
 * stdin EOF stops uvicorn even when a venv launcher owns a child interpreter. */
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');

const ROOT=path.resolve(__dirname,'..');
const BASE='http://127.0.0.1:8020';
const CDP='http://127.0.0.1:9438';
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const safe=value=>String(value??'').replace(/\bsk-[A-Za-z0-9_-]{6,}/g,'[credential-redacted]').replace(/\bBearer\s+[^\s"']+/gi,'Bearer [credential-redacted]').slice(0,1200);
function bounded(promise,ms,label){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(label)),ms);})]).finally(()=>clearTimeout(timer));}
function cleanEnvironment(){
  const env={};
  // Do not read secret-valued environment entries or forward them to Electron.
  for(const name of Object.keys(process.env)){
    if(/api.?key|secret|token|password|passwd|credential|authorization/i.test(name)||['NODE_OPTIONS','ELECTRON_RUN_AS_NODE'].includes(name))continue;
    env[name]=process.env[name];
  }
  return env;
}
async function requireFreePort(port){
  await new Promise((resolve,reject)=>{
    const probe=net.createServer();probe.once('error',()=>reject(Error(`Port ${port} is occupied; no existing process was touched`)));
    probe.listen({host:'127.0.0.1',port,exclusive:true},()=>probe.close(resolve));
  });
}
function portOpen(port){
  return new Promise(resolve=>{
    const socket=net.createConnection({host:'127.0.0.1',port});let done=false;
    const finish=value=>{if(done)return;done=true;socket.destroy();resolve(value);};
    socket.once('connect',()=>finish(true));socket.once('error',()=>finish(false));socket.setTimeout(500,()=>finish(true));
  });
}
async function waitClosed(ports,deadline=10000){
  const until=Date.now()+deadline;
  do {if(!(await Promise.all(ports.map(portOpen))).some(Boolean))return true;await pause(200);}while(Date.now()<until);
  return false;
}
function ownedChild(command,args,env,cwd,logPrefix,stdin){
  const stdout=fs.createWriteStream(logPrefix+'.stdout.log'),stderr=fs.createWriteStream(logPrefix+'.stderr.log');
  const child=spawn(command,args,{env,cwd,windowsHide:true,stdio:[stdin?'pipe':'ignore','pipe','pipe']});
  let text='';child.stdout?.on('data',data=>{stdout.write(data);text=(text+data.toString('utf8')).slice(-16000);});
  child.stderr?.on('data',data=>stderr.write(data));
  const exited=new Promise(resolve=>{
    let closed=false;
    const finish=value=>{if(closed)return;closed=true;stdout.end();stderr.end();resolve(value);};
    child.once('error',error=>finish({exited:true,code:null,error:safe(error.message)}));
    child.once('close',(code,signal)=>finish({exited:true,code,signal}));
  });
  return {child,exited,getStdout:()=>text};
}
function pythonSummary(output){
  for(const line of output.trim().split(/\r?\n/).reverse()){
    try {const parsed=JSON.parse(line);if(typeof parsed.status==='string')return {
      status:parsed.status,phase:parsed.phase,report:parsed.report,counters:parsed.counters,error:parsed.error?safe(parsed.error):undefined,
    };}catch{}
  }
  return null;
}

async function run(){
  const started=Date.now(),runId=crypto.randomUUID(),stamp=new Date().toISOString().replace(/[:.]/g,'-');
  const report={checked_at:new Date().toISOString(),status:'running',phase:'port_preflight',
    scope:'Owned isolated backend :8020 and packaged Electron :9438; one Python two-surface real-model verifier run. Focus methods are suppressed by this harness only; native mouse/tray acceptance is separate.',
    no_financial_response_mocking:true,automatic_model_retries:0,new_broker_requests:0,
    model_budget:{python_check_runs:1,answer_turns:2,maximum_generations:4},model_test_started:false,
    normal_user_backend_or_database_touched:false,native_focus_suppression:'pending',cleanup:{}};
  const reportRoot=path.join(ROOT,'reports');
  let target=path.join(reportRoot,'pet_cloud_harness_v15.json');
  if(fs.existsSync(target))target=path.join(reportRoot,`pet_cloud_harness_v15-${stamp}.json`);
  let server=null,electronApp=null,test=null,runDir=null,serverExit=null;
  try {
    await requireFreePort(8020);await requireFreePort(9438);
    const scratch=path.join(ROOT,'tmp','pet-cloud-v15');fs.mkdirSync(scratch,{recursive:true});
    runDir=fs.mkdtempSync(path.join(scratch,'run-'));
    if(path.relative(scratch,path.resolve(runDir)).startsWith('..'))throw Error('Unsafe harness directory');
    const db=path.join(runDir,'acceptance.sqlite3'),profile=path.join(runDir,'electron-profile');
    fs.mkdirSync(profile,{recursive:true});report.audit_directory=path.relative(ROOT,runDir).replaceAll('\\','/');
    const python=path.join(ROOT,'.venv','Scripts','python.exe');
    const executable=path.join(ROOT,'desktop','artifacts','win-unpacked','FinPilotPet.exe');
    const playwright=path.join(ROOT,'.venv','Lib','site-packages','playwright','driver','package');
    for(const file of [python,executable,path.join(playwright,'package.json'),path.join(ROOT,'scripts/check_pet_cloud_v15.py')]){
      if(!fs.existsSync(file))throw Error('Required local harness runtime or packaged app is missing');
    }
    const environment=cleanEnvironment();
    const serverEnv={...environment,FINPILOT_DB:db,IBKR_ENABLED:'false',FINPILOT_OFFLINE:'false',
      FINPILOT_OPTIONS_MODEL_DIAGNOSTICS:'1',FINPILOT_HARNESS_RUN_ID:runId,PYTHONIOENCODING:'utf-8'};
    const wrapper=`import os,sys,threading,uvicorn
from pathlib import Path
from app.main import app
assert app.state.store.path.resolve()==Path(os.environ['FINPILOT_DB']).resolve()
def owner():return {'run_id':os.environ['FINPILOT_HARNESS_RUN_ID'],'pid':os.getpid()}
app.add_api_route('/__v15_harness_owner__',owner,methods=['GET'],include_in_schema=False)
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8020,log_level='warning',timeout_graceful_shutdown=8))
def eof():
    try:
        while sys.stdin.buffer.read(1):pass
    finally:server.should_exit=True
threading.Thread(target=eof,daemon=True).start()
server.run()
`;
    report.phase='backend_startup';server=ownedChild(python,['-u','-c',wrapper],serverEnv,ROOT,path.join(runDir,'backend'),true);
    server.child.stdin.on('error',()=>{});
    let ready=false;
    for(let attempt=0;attempt<40;attempt++){
      if(server.child.exitCode!==null)throw Error('Owned backend exited before readiness');
      try {
        const ownerResponse=await fetch(BASE+'/__v15_harness_owner__',{signal:AbortSignal.timeout(500)});
        if(ownerResponse.ok){const identity=await ownerResponse.json();if(identity.run_id!==runId)throw Error('Backend ownership mismatch');
          const health=await fetch(BASE+'/api/health',{signal:AbortSignal.timeout(1500)}).then(r=>r.json());
          if(health.application!=='FinPilot'||health.version!=='15.0.0'||health.mode!=='deepseek')throw Error('Owned backend is not the configured v15 cloud service');
          report.backend_serving_pid=identity.pid;ready=true;break;
        }
      }catch(error){if(/ownership mismatch|not the configured/.test(error.message))throw error;}
      await pause(250);
    }
    if(!ready)throw Error('Owned backend did not become ready; no model test started');
    report.backend_launcher_pid=server.child.pid;
    report.phase='packaged_electron_startup';
    const {_electron}=require(playwright);
    electronApp=await _electron.launch({executablePath:executable,cwd:ROOT,timeout:25000,
      env:{...environment,FINPILOT_BASE_URL:BASE},
      // Playwright puts --remote-debugging-port=0 before user args; Chromium
      // takes this final explicit switch for the separate Python CDP client.
      args:[`--base-url=${BASE}`,`--pet-data-dir=${profile}`,'--remote-debugging-port=9438']});
    report.phase='owned_focus_instrumentation';
    report.native_focus_suppression=await bounded(electronApp.evaluate(({app,BrowserWindow})=>{
      const windows=BrowserWindow.getAllWindows();
      BrowserWindow.prototype.focus=function(){};BrowserWindow.prototype.blur=function(){};
      for(const win of windows){win.focus=function(){};win.blur=function(){};}
      return {enabled:true,packaged:app.isPackaged,version:app.getVersion(),existing_window_count:windows.length,
        scope:'Only focus/blur overridden in this owned process. showInactive, real renderers, APIs and model responses unchanged.'};
    }),10000,'Native focus instrumentation timed out');
    if(!report.native_focus_suppression.packaged||report.native_focus_suppression.version!=='15.0.0')throw Error('The owned instance is not the v15 packaged application');
    await bounded(electronApp.firstWindow(),10000,'Owned pet window did not appear');
    let cdpReady=false;
    for(let attempt=0;attempt<30;attempt++){
      try {const r=await fetch(CDP+'/json/version',{signal:AbortSignal.timeout(500)});if(r.ok&&typeof(await r.json()).webSocketDebuggerUrl==='string'){cdpReady=true;break;}}catch{}
      await pause(200);
    }
    if(!cdpReady)throw Error('Owned CDP endpoint is unavailable; no model test started');
    const asar=path.join(ROOT,'desktop','artifacts','win-unpacked','resources','app.asar');
    report.packaged_asar_sha256=crypto.createHash('sha256').update(fs.readFileSync(asar)).digest('hex');
    report.phase='one_python_model_verification';report.model_test_started=true;
    test=ownedChild(python,['scripts/check_pet_cloud_v15.py','--live'],
      {...environment,FINPILOT_DB:db,IBKR_ENABLED:'false',FINPILOT_OFFLINE:'false',PYTHONIOENCODING:'utf-8'},
      ROOT,path.join(runDir,'python-check'),false);
    const result=await bounded(test.exited,300000,'Owned Python model verifier exceeded its one-run deadline');
    report.python_check_exit=result;
    report.python_summary=pythonSummary(test.getStdout());
    if(report.python_summary)process.stdout.write(JSON.stringify(report.python_summary)+'\n');
    if(result.code!==0||report.python_summary?.status!=='passed')throw Error('The single Python verification failed; see its retained report. No automatic retry performed.');
    report.status='passed';report.phase='complete';
  }catch(error){report.status='failed';report.error=safe(error.message);}
  finally {
    if(electronApp){
      try {await bounded(electronApp.close(),20000,'Owned Electron graceful close timed out');report.cleanup.electron_closed=true;}
      catch(error){report.cleanup.electron_closed=false;report.cleanup.electron_error=safe(error.message);report.status='failed';}
    }
    if(server){
      try {server.child.stdin.end();report.cleanup.backend_stdin_closed=true;}catch(error){report.cleanup.backend_stdin_error=safe(error.message);}
      try {serverExit=await bounded(server.exited,15000,'Owned uvicorn did not exit after stdin EOF');report.cleanup.backend_exit=serverExit;if(serverExit.code!==0)report.status='failed';}
      catch(error){report.cleanup.backend_exit={exited:false,error:safe(error.message)};report.status='failed';}
    }
    if(test){
      try {report.cleanup.verifier_exit=await bounded(test.exited,15000,'Owned Python verifier did not finish after server/native cleanup');}
      catch(error){report.cleanup.verifier_exit={exited:false,error:safe(error.message)};report.status='failed';}
    }
    // These ports were verified free before this harness created anything.
    if(runDir){report.cleanup.owned_ports_closed=await waitClosed([8020,9438]);if(!report.cleanup.owned_ports_closed)report.status='failed';}
    report.elapsed_seconds=Math.round((Date.now()-started)/100)/10;
    report.logs_retained_in_tmp=Boolean(runDir);report.normal_user_processes_killed=false;
    fs.mkdirSync(reportRoot,{recursive:true});fs.writeFileSync(target,JSON.stringify(report,null,2)+'\n');
    process.stdout.write(JSON.stringify({status:report.status,phase:report.phase,report:path.relative(ROOT,target).replaceAll('\\','/'),
      model_test_started:report.model_test_started,cleanup:report.cleanup,error:report.error})+'\n');
  }
  return report.status==='passed'?0:1;
}

if(!process.argv.includes('--live')){
  process.stdout.write('Dry run: zero HTTP, browser, process, model or broker actions. --live runs one isolated two-surface verification.\n');
}else{
  run().then(code=>{process.exitCode=code;}).catch(error=>{process.stderr.write(safe(error.message)+'\n');process.exitCode=1;});
}
