'use strict';
// Original minimal host. Coopanion informed the interaction design; no upstream
// desktop-agent, screen reading, ASR, account or computer-control code is used.
const {app,BrowserWindow,Tray,Menu,ipcMain,screen,shell,dialog,nativeImage}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {ROUTES,localBase,finiteRect,contains,position}=require('./geometry.cjs');
const arg=name=>process.argv.find(v=>v.startsWith(`--${name}=`))?.slice(name.length+3);
let base;
try {base=localBase(arg('base-url')||process.env.FINPILOT_BASE_URL||'http://127.0.0.1:8000');}
catch {app.whenReady().then(()=>{dialog.showErrorBox('FinPilot','The backend must use http://127.0.0.1:<port>.');app.quit();});}
if(arg('pet-data-dir'))app.setPath('userData',path.resolve(arg('pet-data-dir')));
const primaryInstance=app.requestSingleInstanceLock();
if(!primaryInstance)app.quit();
let win,tray,display,settings={},rects=[],panelOpen=false,dragging=false,dragLease=0,forceThrough=false,poll,saveTimer,ignored=true;
const settingsFile=()=>path.join(app.getPath('userData'),'companion-window.json');
function persist(){clearTimeout(saveTimer);saveTimer=setTimeout(()=>{try{fs.mkdirSync(app.getPath('userData'),{recursive:true});fs.writeFileSync(settingsFile(),JSON.stringify(settings,null,2));}catch{}},150);}
function readSettings(){try{const raw=JSON.parse(fs.readFileSync(settingsFile(),'utf8'));settings={scale:[150,200,250,300].includes(raw.scale)?raw.scale:200,position:raw.position,displayId:raw.displayId,roaming:raw.roaming===true};}catch{settings={scale:200,roaming:false};}}
function layout(reason='layout'){
  if(!win||win.isDestroyed())return;
  const area=display.workArea,cursor=screen.getCursorScreenPoint();
  win.webContents.send('pet:layout',{reason,position:position(settings.position,area,settings.scale),scale:settings.scale,roaming:settings.roaming===true,area:{width:area.width,height:area.height},cursor:{x:cursor.x-area.x,y:cursor.y-area.y},forceThrough});
}
function show(){if(!win)return;win.showInactive();layout('show');}
function reset(){settings.position=null;display=screen.getPrimaryDisplay();settings.displayId=display.id;win.setBounds(display.workArea);layout('reset');persist();show();}
function scale(value){if(![150,200,250,300].includes(value))return;settings.scale=value;settings.position=position(settings.position,display.workArea,value);layout('scale');persist();}
function setPanel(value){panelOpen=value;win.setFocusable(value);if(value){forceThrough=false;win.setIgnoreMouseEvents(false);ignored=false;win.focus();}else{win.blur();}layout('panel');}
function quit(){clearInterval(poll);clearTimeout(saveTimer);try{fs.mkdirSync(app.getPath('userData'),{recursive:true});fs.writeFileSync(settingsFile(),JSON.stringify(settings,null,2));}catch{}app.quit();}
function menu(){return Menu.buildFromTemplate([
  {label:'FinPilot · 鲸鱼娘金融助手',enabled:false},{type:'separator'},
  {label:'显示桌宠 / Show pet',click:show},{label:'隐藏桌宠 / Hide pet',click:()=>win.hide()},
  {label:'打开聊天 / Open chat',click:()=>{show();win.webContents.send('pet:command',{type:'open-panel'});}},
  {label:'恢复位置 / Reset position',click:reset},
  {label:'安静散步 / Gentle roaming',type:'checkbox',checked:settings.roaming===true,click:item=>{settings.roaming=item.checked;layout('roaming');persist();}},
  {label:'休息 / Wake or rest',click:()=>{show();win.webContents.send('pet:command',{type:'toggle-sleep'});}},
  {label:'角色大小 / Size',submenu:[150,200,250,300].map(size=>({label:`${size}px`,type:'radio',checked:settings.scale===size,click:()=>{scale(size);tray.setContextMenu(menu());}}))},
  {label:'全部点击穿透 / Pass all clicks',type:'checkbox',checked:forceThrough,click:item=>{forceThrough=item.checked;setPanel(false);layout('through');tray.setContextMenu(menu());}},
  {type:'separator'},{label:'打开工作台 / Workspace',click:()=>shell.openExternal(base+ROUTES.workspace)},
  {label:'退出桌宠（保留后台） / Quit pet',click:quit}
]);}
function allowedEvent(event){return win&&!win.isDestroyed()&&event.sender===win.webContents&&(()=>{try{return new URL(event.senderFrame.url).origin===base;}catch{return false;}})();}
async function start(){
  readSettings();
  const health=await fetch(base+'/api/health',{signal:AbortSignal.timeout(5000)}).then(r=>r.ok?r.json():Promise.reject(Error('health')));
  if(health.application!=='FinPilot')throw Error('The selected service is not FinPilot.');
  display=screen.getAllDisplays().find(d=>d.id===settings.displayId)||screen.getPrimaryDisplay();
  settings.displayId=display.id;
  win=new BrowserWindow({...display.workArea,show:false,frame:false,transparent:true,backgroundColor:'#00000000',resizable:false,movable:false,skipTaskbar:true,alwaysOnTop:true,hasShadow:false,focusable:false,minimizable:false,maximizable:false,fullscreenable:false,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,sandbox:true,nodeIntegration:false,webSecurity:true,spellcheck:false,backgroundThrottling:true}});
  win.setIgnoreMouseEvents(true);
  win.webContents.setWindowOpenHandler(({url})=>{try{const parsed=new URL(url);if(parsed.protocol==='https:'&&!parsed.username&&!parsed.password)shell.openExternal(parsed.href);}catch{}return {action:'deny'};});
  win.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==base)event.preventDefault();});
  win.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
  win.on('close',event=>{if(!app.isQuitting){event.preventDefault();win.hide();}});
  win.on('show',()=>layout('show'));
  win.webContents.on('did-finish-load',()=>{layout('initial');show();});
  ipcMain.on('pet:ready',event=>{if(allowedEvent(event))layout('initial');});
  ipcMain.on('pet:rects',(event,value)=>{if(!allowedEvent(event)||!Array.isArray(value))return;const a=display.workArea;rects=value.slice(0,64).map(r=>finiteRect(r,a.width,a.height)).filter(Boolean);});
  ipcMain.on('pet:position',(event,value)=>{if(!allowedEvent(event))return;settings.position=position(value,display.workArea,settings.scale);settings.displayId=display.id;persist();});
  ipcMain.on('pet:panel',(event,value)=>{if(allowedEvent(event)&&typeof value==='boolean')setPanel(value);});
  ipcMain.on('pet:drag',(event,value)=>{if(!allowedEvent(event)||typeof value!=='boolean')return;dragging=value;dragLease=Date.now();if(value){forceThrough=false;win.setIgnoreMouseEvents(false);ignored=false;}});
  ipcMain.on('pet:scale',(event,value)=>{if(allowedEvent(event)){scale(value);tray.setContextMenu(menu());}});
  ipcMain.on('pet:roaming',(event,value)=>{if(allowedEvent(event)&&typeof value==='boolean'){settings.roaming=value;layout('roaming');persist();tray.setContextMenu(menu());}});
  ipcMain.on('pet:hide',event=>{if(allowedEvent(event))win.hide();});
  ipcMain.on('pet:reset',event=>{if(allowedEvent(event))reset();});
  ipcMain.on('pet:open',(event,target)=>{if(allowedEvent(event)&&Object.hasOwn(ROUTES,target))shell.openExternal(base+ROUTES[target]);});
  screen.on('display-removed',(_event,removed)=>{if(display.id===removed.id)reset();});
  screen.on('display-metrics-changed',(_event,changed)=>{if(changed.id===display.id){display=changed;win.setBounds(changed.workArea);settings.position=position(settings.position,changed.workArea,settings.scale);layout('display-change');}});
  poll=setInterval(()=>{
    if(!win||win.isDestroyed()||!win.isVisible())return;
    if(dragging&&Date.now()-dragLease>3000){dragging=false;win.webContents.send('pet:command',{type:'end-drag'});}
    const cursor=screen.getCursorScreenPoint();
    if(dragging){const near=screen.getDisplayNearestPoint(cursor);if(near.id!==display.id){display=near;settings.displayId=near.id;win.setBounds(near.workArea);}layout('drag-cursor');}
    const area=display.workArea,x=cursor.x-area.x,y=cursor.y-area.y;
    const next=forceThrough||(!dragging&&!rects.some(r=>contains(r,x,y)));
    if(next!==ignored){win.setIgnoreMouseEvents(next);ignored=next;}
  },40);
  tray=new Tray(nativeImage.createFromPath(path.join(__dirname,'tray.png')));tray.setToolTip('FinPilot · 鲸鱼娘金融助手');tray.setContextMenu(menu());tray.on('double-click',show);tray.on('click',show);
  // No backend process is spawned or terminated by the host; the launcher owns
  // startup and deliberately leaves the shared Python service running.
  await win.loadURL(base+'/pet');
}
app.on('second-instance',()=>{show();if(win)win.webContents.send('pet:command',{type:'notice',text:'桌宠已经在运行 / The companion is already running.'});});
app.on('before-quit',()=>{app.isQuitting=true;clearInterval(poll);clearTimeout(saveTimer);});
app.on('window-all-closed',()=>{});
if(primaryInstance&&base)app.whenReady().then(start).catch(error=>{dialog.showErrorBox('FinPilot 桌宠未启动',`请先运行项目后端或使用 start-desktop.ps1。\n${String(error.message).slice(0,180)}`);app.quit();});
