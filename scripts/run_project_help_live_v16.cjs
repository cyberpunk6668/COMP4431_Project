'use strict';
// Opt-in, one-run owned backend lifecycle. No GUI/desktop automation.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net');
const {spawn}=require('node:child_process');const crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8016';
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function environment(){const out={};for(const key of Object.keys(process.env)){if(!/api.?key|secret|token|password|credential|authorization/i.test(key))out[key]=process.env[key];}return out;}
async function free(){await new Promise((resolve,reject)=>{const probe=net.createServer();probe.once('error',()=>reject(Error('Port 8016 is occupied; no existing service was touched.')));probe.listen(8016,'127.0.0.1',()=>probe.close(resolve));});}
function stopped(){return new Promise(resolve=>{const socket=net.connect(8016,'127.0.0.1');socket.once('connect',()=>{socket.destroy();resolve(false);});socket.once('error',()=>resolve(true));});}
async function run(){
  const stamp=new Date().toISOString().replace(/[:.]/g,'-'),nonce=crypto.randomUUID();
  const report={checked_at:new Date().toISOString(),status:'running',scope:'One opt-in two-turn real-model verifier over a newly owned isolated :8016 backend; no native UI, user database, broker collection or response mocking.',maximum_model_generations:2,automatic_retries:0,cleanup:{}};
  let server,exit,log,dir;
  const target=path.join(root,'reports',`project_help_harness_v16-${stamp}.json`);
  try{
    await free();fs.mkdirSync(path.join(root,'tmp'),{recursive:true});dir=fs.mkdtempSync(path.join(root,'tmp','project-help-live-v16-'));
    const env={...environment(),FINPILOT_DB:path.join(dir,'acceptance.sqlite3'),IBKR_ENABLED:'false',FINPILOT_OFFLINE:'false',PYTHONIOENCODING:'utf-8',FINPILOT_HELP_OWNER:nonce};
    const python=path.join(root,'.venv','Scripts','python.exe');log=fs.openSync(path.join(dir,'backend.log'),'w');
    const wrapper=`import os,sys,threading,uvicorn
from app.main import app
app.add_api_route('/__help_acceptance_owner__',lambda:{'nonce':os.environ['FINPILOT_HELP_OWNER']},methods=['GET'],include_in_schema=False)
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8016,log_level='warning',timeout_graceful_shutdown=5))
def eof():
    try:
        while sys.stdin.buffer.read(1):pass
    finally:server.should_exit=True
threading.Thread(target=eof,daemon=True).start()
server.run()
`;
    server=spawn(python,['-u','-c',wrapper],{cwd:root,env,windowsHide:true,stdio:['pipe',log,log]});server.stdin.on('error',()=>{});
    exit=new Promise(resolve=>{server.once('error',e=>resolve({code:null,error:e.message}));server.once('close',code=>resolve({code}));});
    let ready=false;
    for(let i=0;i<40;i++){
      if(server.exitCode!==null)throw Error('Owned backend exited before readiness.');
      try{const response=await fetch(base+'/__help_acceptance_owner__',{signal:AbortSignal.timeout(500)});if(response.ok){const owner=await response.json();if(owner.nonce!==nonce)throw Error('Backend ownership mismatch.');ready=true;break;}}catch(error){if(error.message.includes('ownership'))throw error;}
      await pause(150);
    }
    if(!ready)throw Error('Owned backend unavailable; no model verifier was started.');
    report.isolated_audit_directory=path.relative(root,dir).replaceAll('\\','/');
    const verifier=spawn(python,['-B','scripts/check_project_help_live_v16.py','--live'],{cwd:root,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
    let output='';verifier.stdout.on('data',data=>{output=(output+data.toString('utf8')).slice(-12000);process.stdout.write(data);});
    verifier.stderr.on('data',data=>fs.appendFileSync(path.join(dir,'verifier.stderr.log'),data));
    const code=await new Promise((resolve,reject)=>{verifier.once('error',reject);verifier.once('close',resolve);});
    report.verifier_exit_code=code;
    for(const line of output.trim().split(/\r?\n/).reverse()){try{const item=JSON.parse(line);if(item.status){report.verifier_summary=item;break;}}catch{}}
    report.status=code===0&&report.verifier_summary?.status==='passed'?'passed':'failed';
  }catch(error){report.status='failed';report.error=String(error.message).replace(/\bsk-[A-Za-z0-9_-]{6,}/g,'[redacted]');}
  finally{
    if(server){server.stdin.end();report.cleanup.stdin_eof=true;let timer;const result=await Promise.race([exit,new Promise(resolve=>{timer=setTimeout(()=>resolve({error:'Graceful stop deadline exceeded'}),12000);})]);clearTimeout(timer);report.cleanup.backend_exit=result;if(result.code!==0)report.status='failed';}
    if(log!==undefined)fs.closeSync(log);
    report.cleanup.owned_port_closed=await stopped();if(!report.cleanup.owned_port_closed)report.status='failed';
    fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,JSON.stringify(report,null,2)+'\n');
    process.stdout.write(JSON.stringify({status:report.status,report:path.relative(root,target).replaceAll('\\','/'),cleanup:report.cleanup})+'\n');
  }
  return report.status==='passed'?0:1;
}
if(!process.argv.includes('--live'))process.stdout.write('Dry run: zero process, HTTP, browser, model, broker or report actions. --live runs one isolated two-turn verifier.\n');
else run().then(code=>{process.exitCode=code;}).catch(error=>{process.stderr.write(error.message+'\n');process.exitCode=1;});
