'use strict';
// Public Node Playwright Electron API from the installed Python distribution.
// Python Playwright does not expose _electron. No production host file is edited.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),port=8018,base=`http://127.0.0.1:${port}`;
const {_electron}=require(path.join(root,'.venv/Lib/site-packages/playwright/driver/package'));
const stamp=new Date().toISOString().replace(/[^0-9TZ]/g,''),scratch=path.join(root,'tmp/native-instrumentation-v15',stamp),profile=path.join(scratch,'profile');
fs.mkdirSync(profile,{recursive:true});
const canonical=path.join(root,'reports/native_instrumentation_v15.json');
const target=fs.existsSync(canonical)?canonical.replace('.json',`-${stamp}.json`):canonical;
const executable=path.join(root,'desktop/artifacts/win-unpacked/FinPilotPet.exe');
const report={checked_at:new Date().toISOString(),status:'running',phase:'preflight',api:'Public Node Playwright _electron; Python API does not expose Electron',
  scope:'Actual packaged Electron main-process and owned renderer instrumentation with an isolated controlled-provider backend. Cursor/drag are simulated; no physical mouse or desktop-screen capture.',
  executable:'desktop/artifacts/win-unpacked/FinPilotPet.exe',fixture_port:port,external_model_requests:0,new_broker_requests:0,
  user_profile_or_other_windows_read:false,physical_mouse_tested:false,checks:[],screenshots:[],
  limitations:['Main-process and renderer instrumentation, not physical mouse or OS click-through proof.',
    'Focus/blur are suppressed in this test process; windows auto-hide immediately after show events to avoid interrupting the user.',
    'Cursor and poll visibility are simulated while the actual window is hidden. Drag uses injected renderer events with pointer capture stubbed.',
    'Screenshots capture only owned webContents with a transparent background, not the desktop or other apps.']};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const portOpen=()=>new Promise(resolve=>{const s=net.connect(port,'127.0.0.1');s.once('connect',()=>{s.destroy();resolve(true);});s.once('error',()=>resolve(false));});
async function request(route,body){const r=await fetch(base+route,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error(`Fixture HTTP ${r.status}`);return r.json();}
const assert=(value,message)=>{if(!value)throw Error(message);};
let server,app,duplicate,log;const began=Date.now();
async function launch(){return _electron.launch({executablePath:executable,args:[`--base-url=${base}`,`--pet-data-dir=${profile}`],cwd:root,
  env:{...process.env,DEEPSEEK_API_KEY:'',IBKR_ENABLED:'false'},timeout:10000});}
async function instrument(app){return app.evaluate(({BrowserWindow,Tray,screen,app})=>{
  const w=BrowserWindow.getAllWindows()[0];if(!w)throw Error('No owned BrowserWindow');
  const initial={visible:w.isVisible(),alwaysOnTop:w.isAlwaysOnTop(),focusable:w.isFocusable(),bounds:w.getBounds(),backgroundColor:w.getBackgroundColor(),
    preferences:w.webContents.getLastWebPreferences(),version:app.getVersion(),displays:screen.getAllDisplays().map(d=>({id:d.id,workArea:d.workArea,scaleFactor:d.scaleFactor}))};
  const realVisible=w.isVisible.bind(w),realIgnore=w.setIgnoreMouseEvents.bind(w),realCursor=screen.getCursorScreenPoint.bind(screen);
  const probe=globalThis.__nativeProbe={w,shown:initial.visible?1:0,shownVisible:initial.visible,shownTopmost:initial.visible&&w.isAlwaysOnTop(),hideDelay:60,ignoreCalls:[],cursor:null,simulatePoll:true,focusSuppressed:0,visibleInputSafetyOverrides:0,realVisible};
  w.on('show',()=>{probe.shown++;probe.shownVisible=probe.shownVisible||realVisible();realIgnore(true);setTimeout(()=>{probe.shownTopmost=probe.shownTopmost||w.isAlwaysOnTop();w.hide();},probe.hideDelay);});w.hide();
  w.focus=()=>{probe.focusSuppressed++;};w.blur=()=>{};
  w.isVisible=()=>realVisible()||probe.simulatePoll;
  w.setIgnoreMouseEvents=(value,options)=>{probe.ignoreCalls.push(Boolean(value));if(realVisible()&&!value){probe.visibleInputSafetyOverrides++;return realIgnore(true,options);}return realIgnore(value,options);};
  screen.getCursorScreenPoint=()=>probe.cursor||realCursor();
  const contextMenu=Tray.prototype.setContextMenu;
  Tray.prototype.setContextMenu=function(menu){probe.tray=this;probe.menu=menu;return contextMenu.call(this,menu);};
  return {...initial,preferences:{sandbox:initial.preferences.sandbox,contextIsolation:initial.preferences.contextIsolation,nodeIntegration:initial.preferences.nodeIntegration,webSecurity:initial.preferences.webSecurity}};
});}
(async()=>{
try{
  assert(fs.existsSync(executable),'Packaged executable missing');
  report.packaged_host_asar_sha256=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'desktop/artifacts/win-unpacked/resources/app.asar'))).digest('hex');
  assert(!await portOpen(),'Fixture port occupied; no existing process was touched');
  log=fs.openSync(path.join(scratch,'fixture.log'),'w');
  server=spawn(path.join(root,'.venv/Scripts/python.exe'),['-m','uvicorn','scripts.companion_fixture_v15:create_fixture_app','--factory','--host','127.0.0.1','--port',String(port)],
    {cwd:root,env:{...process.env,FINPILOT_COMPANION_TEST_DB:path.join(scratch,'fixture.sqlite3'),IBKR_ENABLED:'false',DEEPSEEK_API_KEY:'fixture-provider-only',FINPILOT_OPTIONS_MODEL_DIAGNOSTICS:'0'},stdio:['ignore',log,log],windowsHide:true});
  let ready;for(let i=0;i<40;i++){try{ready=await request('/__fixture/state');break;}catch{await sleep(100);}}
  assert(ready?.fixture_only,'Owned fixture failed to start');
  report.phase='electron_launch';app=await launch();const page=await app.firstWindow();
  report.native=await instrument(app);
  await page.waitForFunction(()=>window.finPilotPet?.getStatus().avatar?.renderer==='canvas2d',null,{polling:100,timeout:10000});
  report.native.renderer=await page.evaluate(()=>({status:window.finPilotPet.getStatus(),nodeRequire:typeof require,nodeProcess:typeof process,bridgeKeys:Object.keys(window.FinPilotDesktop)}));
  await sleep(100);
  report.phase='native_properties_after_first_show';
  report.native.after_first_show=await app.evaluate(()=>({showEvents:globalThis.__nativeProbe.shown,visibleDuringShow:globalThis.__nativeProbe.shownVisible,topmostDuringShow:globalThis.__nativeProbe.shownTopmost,actuallyHiddenForHarness:!globalThis.__nativeProbe.realVisible()}));
  assert(report.native.after_first_show.showEvents>0&&report.native.after_first_show.visibleDuringShow,'Native showInactive did not produce a visible show event');
  assert(report.native.focusable===false,'Native focusable default differs');
  assert(report.native.preferences.sandbox&&report.native.preferences.contextIsolation&&report.native.preferences.nodeIntegration===false&&report.native.preferences.webSecurity,'Native sandbox preferences differ');
  assert(report.native.renderer.nodeRequire==='undefined'&&report.native.renderer.nodeProcess==='undefined','Node globals exposed in renderer');
  report.checks.push('actual_packaged_window_show_sandbox_and_renderer_node_isolation');
  report.topmost_explicit_setter_probe=await app.evaluate(async()=>{const p=globalThis.__nativeProbe,w=p.w;p.hideDelay=160;const before=w.isAlwaysOnTop();w.showInactive();const shownBeforeSetter=w.isAlwaysOnTop();w.setAlwaysOnTop(true);const immediately=w.isAlwaysOnTop();await new Promise(resolve=>setTimeout(resolve,60));const settled=w.isAlwaysOnTop(),visible=p.realVisible();w.hide();p.hideDelay=60;return {test_intervention:true,before,shownBeforeSetter,immediately,after60ms:settled,visibleAt60ms:visible};});
  report.checks.push('explicit_topmost_setter_probe_is_recorded_as_test_intervention');

  report.phase='tray_scale_visibility';await page.evaluate(()=>window.FinPilotDesktop.setScale(250));
  await page.waitForFunction(()=>window.finPilotPet.getStatus().scale===250,null,{polling:100});
  report.tray=await app.evaluate(()=>{const p=globalThis.__nativeProbe;return {captured:Boolean(p.tray),destroyed:p.tray?.isDestroyed(),bounds:p.tray?.getBounds(),labels:p.menu?.items.map(i=>i.label)};});
  assert(report.tray.captured&&!report.tray.destroyed,'Actual tray object was not captured');
  const visibility=await app.evaluate(()=>{const p=globalThis.__nativeProbe,old=p.shown;const show=p.menu.items.find(i=>i.label.startsWith('显示桌宠'));show.click(show);const hide=p.menu.items.find(i=>i.label.startsWith('隐藏桌宠'));hide.click(hide);return {showEvents:p.shown-old,visibleDuringShow:p.shownVisible,actuallyHiddenAfter:p.realVisible()===false};});
  assert(visibility.showEvents>0&&visibility.visibleDuringShow&&visibility.actuallyHiddenAfter,'Tray visibility callbacks not observed');
  report.visibility=visibility;report.checks.push('actual_tray_object_and_callbacks_show_then_harness_hide_without_focus');
  await page.evaluate(()=>window.FinPilotDesktop.setScale(999));await sleep(80);
  assert(await page.evaluate(()=>window.finPilotPet.getStatus().scale)===250,'Invalid scale accepted');
  report.checks.push('allowed_scale_ipc_updates_renderer_and_invalid_scale_is_rejected');

  report.phase='hidden_cursor_and_panel_instrumentation';
  const opaque=await page.evaluate(()=>{const c=document.querySelector('#pet-stage canvas'),r=c.getBoundingClientRect(),pixels=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
    let best=null;for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){if(pixels[(y*c.width+x)*4+3]<180)continue;const score=(x-c.width/2)**2+(y-c.height*.35)**2;if(!best||score<best.score)best={x,y,score};}if(!best)throw Error('No opaque sprite pixel');return {x:r.x+best.x/c.width*r.width,y:r.y+best.y/c.height*r.height};});
  const origin=report.native.bounds;
  await app.evaluate((_e,point)=>{globalThis.__nativeProbe.cursor=point;}, {x:origin.x+opaque.x,y:origin.y+opaque.y});await sleep(260);
  const hit=await app.evaluate(()=>globalThis.__nativeProbe.ignoreCalls.includes(false));assert(hit,'Opaque sprite did not request native input');
  await app.evaluate((_e,point)=>{globalThis.__nativeProbe.cursor=point;}, {x:origin.x+2,y:origin.y+2});await sleep(100);
  const away=await app.evaluate(()=>globalThis.__nativeProbe.ignoreCalls.at(-1));assert(away===true,'Transparent area did not request click-through');
  await page.evaluate(()=>window.FinPilotDesktop.setPanelOpen(true));await sleep(80);
  assert(await app.evaluate(()=>globalThis.__nativeProbe.w.isFocusable()),'Panel did not enable keyboard focusability');
  await page.evaluate(()=>window.FinPilotDesktop.setPanelOpen(false));await sleep(80);
  assert(await app.evaluate(()=>!globalThis.__nativeProbe.w.isFocusable()),'Closed panel stayed focusable');
  report.cursor_simulation=await app.evaluate(()=>({ignoreSetterCalls:globalThis.__nativeProbe.ignoreCalls.slice(-12),actualWindowHidden:!globalThis.__nativeProbe.realVisible(),focusCallsSuppressed:globalThis.__nativeProbe.focusSuppressed}));
  report.checks.push('simulated_cursor_drives_real_ignore_setter_while_os_window_hidden');
  report.checks.push('real_panel_ipc_toggles_focusability_with_actual_focus_suppressed');

  report.phase='renderer_drag_injection';
  const drag=await page.evaluate(()=>{const el=document.querySelector('#pet-character'),r=el.getBoundingClientRect(),before=window.finPilotPet.getStatus().position;
    el.setPointerCapture=()=>{};const emit=(type,x,y)=>el.dispatchEvent(new PointerEvent(type,{bubbles:true,pointerId:12345,pointerType:'mouse',button:0,buttons:type==='pointerup'?0:1,clientX:x,clientY:y}));
    emit('pointerdown',r.x+r.width/2,r.y+r.height/2);emit('pointermove',r.x+r.width/2-120,r.y+r.height/2-50);
    const during={position:window.finPilotPet.getStatus().position,dragging:el.dataset.dragging,clip:window.finPilotPet.getStatus().avatar.activeClip};emit('pointerup',r.x+r.width/2-120,r.y+r.height/2-50);
    return {before,during,after:window.finPilotPet.getStatus().position};});
  assert(drag.during.dragging==='true'&&drag.during.position.x!==drag.before.x,'Injected drag did not move renderer');
  assert(drag.after.x>=0&&drag.after.y>=0,'Drop left viewport');report.renderer_drag=drag;report.checks.push('renderer_pointer_event_drag_and_drop_with_capture_stub_not_physical_input');
  await sleep(250);
  const shot=path.join(root,'reports/screenshots/native-instrumentation-v15',stamp,'owned-renderer.png');fs.mkdirSync(path.dirname(shot),{recursive:true});
  try{await page.screenshot({path:shot,omitBackground:true,timeout:1500});report.screenshots.push(path.relative(root,shot).replaceAll('\\','/'));}
  catch(error){report.screenshot_unavailable='Owned hidden webContents screenshot timed out; no desktop capture fallback was attempted.';}

  report.phase='duplicate_same_profile';
  duplicate=spawn(executable,[`--base-url=${base}`,`--pet-data-dir=${profile}`],{cwd:root,env:{...process.env,DEEPSEEK_API_KEY:'',IBKR_ENABLED:'false'},stdio:'ignore',windowsHide:false});
  const duplicateCode=await Promise.race([new Promise(resolve=>duplicate.once('exit',resolve)),sleep(7000).then(()=>{throw Error('Duplicate instance did not exit promptly');})]);
  assert(duplicateCode===0,'Duplicate process exit was not clean');
  assert(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().length)===1,'Duplicate created another owned window');
  await sleep(100);report.topmost_after_normal_second_instance=await app.evaluate(()=>globalThis.__nativeProbe.shownTopmost);
  report.duplicate={exit_code:duplicateCode,only_same_test_profile:true};report.checks.push('same_profile_second_process_exits_and_keeps_single_window');
  report.phase='persist_restart';await app.close();app=null;
  app=await launch();const restarted=await app.firstWindow();await instrument(app);
  await restarted.waitForFunction(()=>window.finPilotPet?.getStatus().avatar?.renderer==='canvas2d',null,{polling:100,timeout:10000});
  report.restart=await restarted.evaluate(()=>window.finPilotPet.getStatus());assert(report.restart.scale===250,'Saved size did not survive restart');
  assert(report.restart.position.x>=0&&report.restart.position.y>=0,'Saved position escaped work area');report.checks.push('owned_profile_restart_restores_scale_and_clamped_position');
  const final=await request('/__fixture/state');assert(final.counters.external_model_requests===0&&final.counters.broker_requests===0&&final.counters.controlled_provider_generations===0,'Native controls unexpectedly generated data/model work');
  report.fixture_counters=final.counters;report.phase='complete';
  report.topmost_after_normal_second_instance_has_prior_test_intervention=true;
  report.status=report.native.after_first_show.topmostDuringShow?'passed_instrumented':'limited_instrumented';
  if(report.status==='limited_instrumented')report.limitations.push('isAlwaysOnTop remained false during short shown samples; auto-hiding may affect native state. Native stable topmost remains unverified by this run.');
}catch(error){report.status='failed';report.error=String(error.stack||error).slice(0,2200);}
finally{
  if(duplicate&&duplicate.exitCode===null)duplicate.kill();
  if(app){try{await app.close();}catch{}}
  if(server){try{await request('/__fixture/control',{action:'shutdown'});}catch{}await sleep(250);if(server.exitCode===null)server.kill();await sleep(100);report.owned_fixture_port_released=!await portOpen();}
  if(log!==undefined){try{fs.closeSync(log);}catch{}}
  report.elapsed_seconds=Number(((Date.now()-began)/1000).toFixed(3));
  fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,JSON.stringify(report,null,2));
  console.log(JSON.stringify({status:report.status,phase:report.phase,checks:report.checks.length,report:path.relative(root,target).replaceAll('\\','/')}));
}
process.exitCode=report.status==='passed_instrumented'?0:1;
})();
