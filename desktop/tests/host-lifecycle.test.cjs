'use strict';
// Run the actual host with a controlled Electron boundary. No native window,
// model, backend server or broker is opened by these lifecycle regressions.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const lifecycle=require('../lifecycle.cjs');

async function host(t,{duplicate=false,managed=false,deferLoad=false,failLoad=false,failReady=false,wrongHealthToken=false}={}){
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'finpilot-host-lifetime-'));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const filename=path.join(directory,'companion-window.json');
  fs.writeFileSync(filename,JSON.stringify({scale:250,roaming:false}));
  const token='a'.repeat(32),base='http://127.0.0.1:18119',runtime=path.join(directory,'runtime');
  const argv=['electron','app',`--base-url=${base}`];
  if(managed){
    fs.mkdirSync(runtime);
    const lifetime=path.join(runtime,'lifecycle.json');
    fs.writeFileSync(lifetime,JSON.stringify({schema:lifecycle.SCHEMA,run_token:token,status:'ready',project_root:directory,
      owner_pid:4321,owner_started_at:'133700000000000001',backend_pid:5432,base_url:base,heartbeat_seq:0}));
    argv.push(`--lifecycle-file=${lifetime}`,`--run-token=${token}`);
  }
  const readyFile=path.join(runtime,`pet-ready-${token}.json`),errors=[];
  let window,windows=0,tray,guard,finishLoad,stopped=false,quitCount=0,closePrevented=false,readyAfterShow=false;
  const intervals=new Set();
  const app=new EventEmitter();
  Object.assign(app,{getPath:()=>directory,setPath(){},requestSingleInstanceLock:()=>!duplicate,whenReady:()=>Promise.resolve(),
    quit(){quitCount++;app.emit('before-quit');if(window){window.emit('close',{preventDefault(){closePrevented=true;}});if(!closePrevented)window.destroyed=true;}}});
  class Window extends EventEmitter{
    constructor(){super();window=this;windows++;this.destroyed=false;this.webContents=new EventEmitter();
      Object.assign(this.webContents,{send:()=>{this.layoutCount=(this.layoutCount||0)+1;},setWindowOpenHandler(){},session:{setPermissionRequestHandler(){}}});}
    isDestroyed(){return this.destroyed;}isVisible(){return true;}
    setIgnoreMouseEvents(){}showInactive(){this.shown=true;}setFocusable(){}focus(){}blur(){}hide(){}setBounds(){}
    async loadURL(){
      if(failLoad)throw Error('controlled page load failure');
      if(deferLoad)return new Promise(resolve=>{finishLoad=()=>{this.webContents.emit('did-finish-load');resolve();};});
      this.webContents.emit('did-finish-load');
    }
  }
  class Tray{
    constructor(){tray=this;this.destroyed=false;}
    setToolTip(){}setContextMenu(){}on(){}isDestroyed(){return this.destroyed;}destroy(){this.destroyed=true;}
  }
  const display={id:1,workArea:{x:0,y:0,width:1920,height:1080}};
  const screen={getAllDisplays:()=>[display],getPrimaryDisplay:()=>display,getCursorScreenPoint:()=>({x:100,y:100}),on(){}};
  const ipcMain=new EventEmitter();
  const electron={app,BrowserWindow:Window,Tray,Menu:{buildFromTemplate:value=>value},ipcMain,screen,shell:{openExternal(){}},
    dialog:{showErrorBox(){throw Error('Unexpected startup failure');}},nativeImage:{createFromPath:()=>({})}};
  const customLifecycle={...lifecycle,createLifecycleGuard(options){guard={stop(){stopped=true;},start(){},exit:options.onExit};return guard;},
    writePetReady(ownership,pid){readyAfterShow=window?.shown===true&&window.layoutCount>0;if(failReady)throw Error('controlled ACK write failure');return lifecycle.writePetReady(ownership,pid);}};
  const code=fs.readFileSync(path.join(__dirname,'../main.cjs'),'utf8');
  const context={require(name){if(name==='electron')return electron;if(name==='./geometry.cjs')return require('../geometry.cjs');if(name==='./lifecycle.cjs')return customLifecycle;return require(name);},
    __dirname:path.join(__dirname,'..'),process:{argv,env:{},pid:process.pid},
    console:{...console,error:(...values)=>errors.push(values)},AbortSignal,URL,fetch:async()=>({ok:true,json:async()=>({application:'FinPilot',project_run_token:wrongHealthToken?'b'.repeat(32):token})}),
    setInterval(callback){const timer={callback};intervals.add(timer);return timer;},clearInterval(timer){intervals.delete(timer);},setTimeout,clearTimeout};
  vm.runInNewContext(code,context,{filename:'desktop/main.cjs'});
  // Allow startup's health/loadURL promises to complete.
  for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));
  return {app,ipcMain,filename,guard,readyFile,errors,finishLoad:()=>finishLoad(),get readyAfterShow(){return readyAfterShow;},get window(){return window;},get windows(){return windows;},get tray(){return tray;},get stopped(){return stopped;},get quitCount(){return quitCount;},get closePrevented(){return closePrevented;},intervals};
}

test('project exit persists latest position settings and actually closes window/tray',async t=>{
  const current=await host(t);
  assert.equal(current.windows,1);assert.equal(current.intervals.size,1);
  const event={sender:current.window.webContents,senderFrame:{url:'http://127.0.0.1:18119/pet'}};
  current.ipcMain.emit('pet:scale',event,300);
  current.guard.exit('launcher_exited');
  assert.equal(current.quitCount,1);
  assert.equal(current.stopped,true);
  assert.equal(current.closePrevented,false);
  assert.equal(current.window.destroyed,true);
  assert.equal(current.tray.destroyed,true);
  assert.equal(current.intervals.size,0);
  assert.equal(JSON.parse(fs.readFileSync(current.filename,'utf8')).scale,300);
  assert.deepEqual(fs.readdirSync(path.dirname(current.filename)),['companion-window.json']);
});
test('a duplicate launch exits without creating another host or overwriting settings',async t=>{
  const current=await host(t,{duplicate:true});
  assert.equal(current.windows,0);
  assert.equal(current.quitCount,1);
  assert.equal(current.intervals.size,0);
  assert.deepEqual(JSON.parse(fs.readFileSync(current.filename,'utf8')),{scale:250,roaming:false});
});
test('managed startup acknowledges the launcher only after the page finishes loading and is shown',async t=>{
  const current=await host(t,{managed:true,deferLoad:true});
  assert.equal(fs.existsSync(current.readyFile),false);
  current.finishLoad();
  assert.equal(current.readyAfterShow,true);
  const ready=JSON.parse(fs.readFileSync(current.readyFile,'utf8'));
  assert.equal(ready.schema,'finpilot.pet-ready.v1');assert.equal(ready.pet_pid,process.pid);
  assert.equal(ready.run_token,'a'.repeat(32));
  current.app.quit();
});
test('a page load failure never writes a ready acknowledgement',async t=>{
  const current=await host(t,{managed:true,failLoad:true});
  assert.equal(fs.existsSync(current.readyFile),false);
  assert.equal(current.quitCount,1);assert.equal(current.stopped,true);
  assert.equal(current.window.destroyed,true);assert.equal(current.tray.destroyed,true);
});
test('a failed ready acknowledgement closes the companion instead of leaving an unowned window',async t=>{
  const current=await host(t,{managed:true,failReady:true});
  assert.equal(fs.existsSync(current.readyFile),false);
  assert.equal(current.quitCount,1);assert.equal(current.stopped,true);
  assert.equal(current.window.destroyed,true);assert.equal(current.tray.destroyed,true);
});
test('a backend belonging to another run cannot create a managed window or ready acknowledgement',async t=>{
  const current=await host(t,{managed:true,wrongHealthToken:true});
  assert.equal(fs.existsSync(current.readyFile),false);assert.equal(current.windows,0);
  assert.equal(current.quitCount,1);assert.equal(current.stopped,true);
});
