(() => {
  'use strict';
  const $=selector=>document.querySelector(selector), bridge=window.FinPilotDesktop;
  const words={
    title:['小鲸 · 金融知识助手','Whale-chan · Financial learning'],ready:['准备就绪','Ready'],thinking:['正在整理回答','Preparing an answer'],listening:['网页正在聆听','Workspace is listening'],speaking:['正在朗读','Reading aloud'],error:['请查看操作提示','Check the operation status'],
    unlinked:['尚未连接会话；发送问题会新建会话，或在工作台选择连接。','No selected conversation. Send to create one, or connect one from the workspace.'],linked:['已共享选定会话；切换网页会话不会自动跟随。','Sharing the selected conversation; changing workspace conversations does not follow automatically.'],
    offline:['本地服务暂未连接；不会自动重新发送问题。','The local service is disconnected. Questions are never automatically resent.'],sending:['正在请求所选模型；可能进行一次受限引用或格式修正…','Requesting the selected model; one bounded citation/schema repair may follow…'],
    placeholder:['问一个问题，或继续解释当前报告…','Ask a question or continue discussing the selected report…'],send:['发送 ↗','Send ↗'],new:['新建会话','New conversation'],disconnect:['断开共享','Disconnect'],explain:['解释本报告','Explain report'],noReport:['先在工作台选择并连接一份报告。','Select and connect a report in the workspace first.'],
    hello:['在呢，想一起弄清哪个问题？','Here to help. What would you like to understand?'],welcome:['先问一个问题，或在工作台点击「连接当前会话到桌宠」。只读取你明确连接的会话。','Ask a question, or connect the selected workspace conversation. Only an explicitly selected conversation is read.'],
    requestFailed:['请求未完成。草稿已保留，请先核对会话记录再决定是否重发。','The request did not finish. Your draft remains. Check saved messages before deciding to resend.'],
    moved:['会话连接已改变；刚才的问题仍保存在原会话中。','The connection changed. The previous question remains in its original conversation.']
  };
  const state={language:'zh',engine:'deepseek',connection:null,session:null,models:[],busy:false,avatar:null,avatarState:'idle',activities:[],reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,open:false,size:200,x:0,y:0,area:{width:innerWidth,height:innerHeight},drag:null,menu:false,toastTimer:null,drafts:new Map(),lastSid:null,roaming:false,sleeping:false};
  let client,dragPing=0,clickTimer=0,syncingControls=false,hitTimer=0,roamFrame=0,roamLast=0,roamDirection=-1,roamActive=false,roamSaved=0,panelObserver;
  const unsubscribers=[];
  const t=key=>words[key]?.[state.language==='en'?1:0]||key;
  const api=async(path,options={})=>{
    const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})},signal:options.signal||AbortSignal.timeout(path==='/api/chat'?90000:15000)});
    if(!response.ok){let code='';try{const value=await response.json();code=typeof value.detail==='string'?value.detail:value.detail?.code||'';}catch{}throw Error(code||`HTTP ${response.status}`);}
    return response.json();
  };
  function toast(message){clearTimeout(state.toastTimer);$('#pet-toast').textContent=message;$('#pet-toast').hidden=false;layout();state.toastTimer=setTimeout(()=>{$('#pet-toast').hidden=true;},4200);}
  function setError(message){$('#pet-error').textContent=message;$('#pet-error').hidden=!message;if(message&&!state.activities.length&&!state.busy)avatarState('error');}
  function avatarState(value){if(value!=='idle'&&state.sleeping){state.sleeping=false;state.avatar?.playAction('wake');}state.avatarState=value;state.avatar?.setState(value);$('#pet-state').textContent=t(value==='idle'?'ready':value);}
  function settle(){const active=state.activities;avatarState(active.some(a=>a.kind==='speech'&&a.phase==='listening')?'listening':active.some(a=>a.kind==='speech'&&a.phase==='speaking')?'speaking':active.length||state.busy?'thinking':!$('#pet-error').hidden?'error':'idle');}
  function setBusy(busy){state.busy=busy;$('#pet-send').disabled=busy;$('#pet-new').disabled=busy;$('#pet-disconnect').disabled=busy;$('#pet-engine').disabled=busy;$('#pet-language').disabled=busy;$('#pet-explain').disabled=busy||!state.session?.active_analysis_id;$('#pet-input').disabled=busy;$('#pet-request-status').hidden=!busy;$('#pet-request-status').textContent=t('sending');settle();}
  function language(){document.documentElement.lang=state.language==='en'?'en':'zh-CN';$('#pet-title').textContent=t('title');$('#pet-input').placeholder=t('placeholder');$('#pet-send').textContent=t('send');$('#pet-new').textContent=t('new');$('#pet-disconnect').textContent=t('disconnect');$('#pet-explain').textContent=t('explain');$('#pet-language').textContent=state.language==='zh'?'EN':'中文';state.avatar?.setLanguage(state.language);avatarState(state.avatarState);renderSession();if(guideView){$('#pet-help-open').textContent=state.language==='en'?'Usage guide':'使用指南';$('.pet-help-header strong').textContent='FinPilot · '+(state.language==='en'?'Usage guide':'使用指南');$('#pet-help-close').textContent=state.language==='en'?'Back to chat':'返回聊天';$('.pet-help-search button').textContent=state.language==='en'?'Search':'搜索';guideInput.placeholder=state.language==='en'?'Search reviewed manual topics…':'搜索已审阅的操作主题…';if(!guideView.hidden)loadGuide();}}
  function renderModels(){const select=$('#pet-engine');select.replaceChildren();for(const model of state.models){const option=document.createElement('option');option.value=model.id;option.textContent=model.label||model.id;option.disabled=!model.available;select.append(option);}select.value=state.engine;}
  function renderSession(){
    const list=$('#pet-messages'),saved=state.session;list.replaceChildren();
    if(!saved?.messages?.length){const welcome=document.createElement('p');welcome.className='pet-welcome';welcome.textContent=t('welcome');list.append(welcome);}
    else for(const message of saved.messages)list.append(window.FinPilotMessages.renderMessage(message,{language:state.language,onOpenAnalysis:()=>openPage('history'),onOpenProjectHelp:openGuideURL}));
    $('#pet-analysis').replaceChildren();
    if(saved?.active_analysis&&window.FinPilotMessages){$('#pet-analysis').append(window.FinPilotMessages.renderAnalysis(saved.active_analysis,{language:state.language}));}
    $('#pet-explain').disabled=state.busy||!saved?.active_analysis_id;
    $('#pet-connection').textContent=saved?`${saved.title||''} · ${t('linked')}`:t('unlinked');
    requestAnimationFrame(()=>{list.scrollTop=list.scrollHeight;layout();});
  }
  function connected(value){
    const sid=value?.session_id||null;
    if(sid!==state.lastSid){if(state.lastSid)state.drafts.set(state.lastSid,$('#pet-input').value);state.session=null;state.lastSid=sid;$('#pet-input').value=state.drafts.get(sid)||'';}
    state.connection=value;state.language=value?.language||state.language;state.engine=value?.engine||state.engine;
    syncingControls=true;renderModels();language();syncingControls=false;
  }
  async function ensureSession(){
    const selected=client.getConnection()?.session_id;if(selected)return selected;
    const saved=await api('/api/sessions',{method:'POST',body:JSON.stringify({title:state.language==='zh'?'鲸鱼娘对话':'Whale-chan conversation'})});
    await client.connect(saved.id,{language:state.language,engine:state.engine});return saved.id;
  }
  async function send(message){
    if(state.busy||!message.trim())return;
    const text=message.trim();if(/\bsk-[A-Za-z0-9_-]{16,}/.test(text)){setError('请先移除密钥或密码 / Remove credentials before sending.');return;}
    setError('');setBusy(true);let sid;
    try{
      sid=await ensureSession();
      // Intentionally omit analysis_id. The server resolves the current binding
      // while holding the existing per-session lock, including remote refreshes.
      await api('/api/chat',{method:'POST',body:JSON.stringify({message:text,session_id:sid,language:state.language,engine:state.engine})});
      if(client.getConnection()?.session_id===sid){$('#pet-input').value='';state.drafts.delete(sid);await client.sync();}
      else toast(t('moved'));
    }catch{setError(t('requestFailed'));if(!$('#pet-input').value)$('#pet-input').value=text;try{await client.sync();}catch{}}
    finally{setBusy(false);}
  }
  function characterHitRects(){
    const canvas=$('#pet-stage canvas');
    if(bridge&&canvas?.width&&canvas.height&&state.avatar?.getStatus().renderer==='canvas2d'){
      try{
        const r=canvas.getBoundingClientRect(),width=canvas.width,height=canvas.height;
        const pixels=canvas.getContext('2d').getImageData(0,0,width,height).data,rectangles=[];
        const step=Math.max(1,Math.floor(width/80)),band=Math.max(1,Math.ceil(height/16));
        for(let top=0;top<height;top+=band){
          const mask=[];
          for(let x=0;x<width;x+=step){let opaque=false;for(let y=top;y<Math.min(top+band,height);y+=step){if(pixels[(y*width+x)*4+3]>36){opaque=true;break;}}mask.push(opaque);}
          for(let i=0;i<mask.length;i++){if(!mask[i])continue;const start=i;while(i+1<mask.length&&mask[i+1])i++;rectangles.push({x:r.x+start*step/width*r.width,y:r.y+top/height*r.height,width:(i-start+1)*step/width*r.width,height:Math.min(band,height-top)/height*r.height});}
        }
        if(rectangles.length)return rectangles.slice(0,58);
      }catch{/* A static fallback still needs a usable keyboard/mouse target. */}
    }
    const r=$('#pet-character').getBoundingClientRect();return [{x:r.x,y:r.y,width:r.width,height:r.height}];
  }
  function hitRects(){const values=[$('#pet-menu-toggle'),!$('#pet-panel').hidden&&$('#pet-panel'),!$('#pet-menu').hidden&&$('#pet-menu')].filter(Boolean).map(el=>{const r=el.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};});values.push(...characterHitRects());bridge?.setInteractiveRects(values);}
  function clamp(){const w=state.size;state.x=Math.max(0,Math.min(state.area.width-w,state.x));state.y=Math.max(0,Math.min(state.area.height-state.size,state.y));}
  function layout(){
    clamp();const el=$('#pet-character'),w=Math.round(state.size);el.style.width=`${w}px`;el.style.height=`${state.size}px`;el.style.left=`${state.x}px`;el.style.top=`${state.y}px`;
    const menu=$('#pet-menu-toggle');menu.style.left=`${Math.min(state.area.width-30,state.x+w-18)}px`;menu.style.top=`${Math.max(2,state.y+10)}px`;
    const panel=$('#pet-panel'),margin=12,gap=16,panelWidth=panel.offsetWidth,panelHeight=panel.offsetHeight;
    const fitX=value=>Math.max(margin,Math.min(state.area.width-panelWidth-margin,value));
    const fitY=value=>Math.max(margin,Math.min(state.area.height-panelHeight-margin,value));
    let panelX,panelY,placement;
    // Choose an actually available side. Clamping an always-left panel to the
    // screen edge can cover the whole character and make it impossible to grab.
    if(state.area.width<480){panelX=fitX((state.area.width-panelWidth)/2);panelY=fitY(state.area.height-panelHeight-margin);placement='sheet';}
    else if(state.area.width-(state.x+w)-margin>=panelWidth+gap){panelX=state.x+w+gap;panelY=fitY(state.y+state.size-panelHeight);placement='right';}
    else if(state.x-margin>=panelWidth+gap){panelX=state.x-gap-panelWidth;panelY=fitY(state.y+state.size-panelHeight);placement='left';}
    else {
      panelX=fitX(state.x+w/2-panelWidth/2);
      const below=state.area.height-(state.y+state.size)-margin;
      if(state.y-margin>=panelHeight+gap||below<panelHeight+gap){panelY=fitY(state.y-panelHeight-gap);placement='above';}
      else{panelY=state.y+state.size+gap;placement='below';}
    }
    panel.dataset.placement=placement;panel.style.left=`${panelX}px`;panel.style.top=`${panelY}px`;
    const popup=$('#pet-menu');popup.style.left=`${Math.max(6,Math.min(state.area.width-221,state.x-90))}px`;popup.style.top=`${Math.max(6,Math.min(state.area.height-popup.offsetHeight-6,state.y-20))}px`;
    const notice=$('#pet-toast');notice.style.left=`${Math.max(12,Math.min(state.area.width-notice.offsetWidth-12,state.x-70))}px`;notice.style.top=`${Math.max(12,state.y-notice.offsetHeight-12)}px`;
    hitRects();
  }
  function openPanel(value=true){state.open=value;$('#pet-panel').hidden=!value;bridge?.setPanelOpen(value);if(value){state.menu=false;$('#pet-menu').hidden=true;$('#pet-menu-toggle').setAttribute('aria-expanded','false');requestAnimationFrame(()=>{layout();$('#pet-input').focus();});}else layout();}
  function openPage(target){if(bridge)bridge.open(target);else{const paths={workspace:'/workspace',history:'/workspace?view=history',calculator:'/workspace?view=calculator'};if(paths[target])window.open(paths[target],'_blank','noopener');}}
  let guideView,guideContent,guideInput,guideStatus,guideController,guideSequence=0,guideTimer=0;
  async function openGuideURL(value='/help'){
    const url=window.FinPilotMessages.projectURL(value);if(!url)return;
    if(url.startsWith('/help')){openGuide(url.split('#')[1]||null);return;}
    if(!bridge){window.open(url,'_blank','noopener');return;}
    if(url.startsWith('/workspace')){openPage(url.includes('view=calculator')||url.includes('?tool=')?'calculator':url.includes('view=history')?'history':'workspace');if(url.includes('view=options'))toast(state.language==='en'?'Choose Options Analysis in the workspace.':'请在打开的工作台点击「期权分析」。');else if(url.includes('view=knowledge'))toast(state.language==='en'?'Choose Knowledge Sources in the workspace.':'请在打开的工作台点击「知识来源」。');else if(url.includes('?tool='))toast(state.language==='en'?'Choose the corresponding calculator tab.':'请在计算器选择对应的复利、贷款或预算标签。');return;}
    // The frozen native bridge cannot open additional local destinations.
    // Show the precise address without navigating the transparent host away.
    await openGuide();guideStatus.textContent=(state.language==='en'?'Open this local address in your browser: ':'请在浏览器打开本地地址：')+location.origin+url;
  }
  function closeGuide(){guideSequence++;guideController?.abort();clearTimeout(guideTimer);if(guideView)guideView.hidden=true;$('#pet-input').focus();layout();}
  function createGuide(){
    if(guideView)return;const make=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;};
    guideView=make('section','pet-help-view');guideView.id='pet-help-view';guideView.setAttribute('aria-label','项目使用指南 / Usage guide');guideView.hidden=true;
    const header=make('header','pet-help-header'),title=make('strong','','FinPilot · '+(state.language==='en'?'Usage guide':'使用指南')),close=make('button','',state.language==='en'?'Back to chat':'返回聊天');close.type='button';close.id='pet-help-close';close.addEventListener('click',closeGuide);header.append(title,close);
    const form=make('form','pet-help-search');guideInput=make('input');guideInput.type='search';guideInput.maxLength=300;guideInput.id='pet-help-search';guideInput.setAttribute('aria-label','搜索手册 / Search manual');guideInput.placeholder=state.language==='en'?'Search reviewed manual topics…':'搜索已审阅的操作主题…';const submit=make('button','',state.language==='en'?'Search':'搜索');submit.type='submit';form.append(guideInput,submit);form.addEventListener('submit',event=>{event.preventDefault();clearTimeout(guideTimer);loadGuide();});guideInput.addEventListener('input',()=>{clearTimeout(guideTimer);guideTimer=setTimeout(()=>loadGuide(),250);});
    guideStatus=make('p','pet-help-status');guideStatus.id='pet-help-status';guideStatus.setAttribute('role','status');guideContent=make('div','pet-help-content');guideContent.id='pet-help-content';
    guideView.append(header,form,guideStatus,guideContent);$('#pet-panel').append(guideView);
    const button=make('button','',state.language==='en'?'Usage guide':'使用指南');button.type='button';button.id='pet-help-open';button.addEventListener('click',()=>openGuide());$('.pet-tools').append(button);
  }
  async function openGuide(topic=null){createGuide();openPanel();guideView.hidden=false;guideInput.value='';await loadGuide(topic);if(!guideView.hidden)guideInput.focus();}
  async function loadGuide(topic=null){
    const current=++guideSequence;guideController?.abort();guideController=new AbortController();const query=guideInput.value.trim();
    if(/\bsk-[A-Za-z0-9_-]{16,}/.test(query)){guideStatus.textContent=state.language==='en'?'Remove credentials first. This text was not sent.':'请先移除密钥；此内容未被发送。';return;}
    guideStatus.textContent=state.language==='en'?'Reading the local manual; no model request.':'正在读取本地手册，不调用模型。';
    const path=topic&&/^help\.[a-z][a-z0-9_-]*$/.test(topic)?`/api/project-help/topics/${encodeURIComponent(topic)}?language=${state.language}`:query?`/api/project-help/search?q=${encodeURIComponent(query)}&language=${state.language}`:`/api/project-help?language=${state.language}`;
    try{const data=await api(path,{signal:guideController.signal}),topics=Array.isArray(data.topics)?data.topics:[data];if(current!==guideSequence||guideView.hidden)return;guideContent.replaceChildren();for(const item of topics)guideContent.append(window.FinPilotMessages.renderProjectHelp({...item,intent:'project_help',manual_version:item.manual_version||data.manual_version},{language:state.language,onOpenProjectHelp:openGuideURL}));guideStatus.textContent=state.language==='en'?`${topics.length} reviewed topics · local manual`:`${topics.length} 个已审阅主题 · 本地手册`;if(!topics.length)guideStatus.textContent=state.language==='en'?'No matching topics. Try another feature name.':'没有匹配主题，请换一个功能名称。';layout();}
    catch(error){if(error.name==='AbortError'||current!==guideSequence)return;guideStatus.textContent=state.language==='en'?'Manual unavailable. Check the local service, then search again.':'暂时无法读取手册。请确认本地服务后重新搜索。';}
  }
  function endDrag(){if(!state.drag)return;const moved=state.drag.moved;state.drag=null;clearInterval(dragPing);bridge?.endDrag();$('#pet-character').dataset.dragging='false';if(moved){clamp();state.y=state.area.height-state.size-12;state.x=Math.max(8,Math.min(state.area.width-state.size-8,state.x));layout();bridge?.savePosition({x:state.x,y:state.y});state.avatar?.playAction('land');}else{clearTimeout(clickTimer);clickTimer=setTimeout(()=>{state.avatar?.playAction('pat');toast(t('hello'));},240);}}
  function toggleSleep(){state.sleeping=!state.sleeping;state.avatar?.playAction(state.sleeping?'sleep':'wake');$('#pet-state').textContent=state.sleeping?(state.language==='zh'?'正在休息':'Resting'):t('ready');}
  function ensureRoam(){if(state.roaming&&!state.reduced&&!document.hidden&&!roamFrame)roamFrame=requestAnimationFrame(roam);}
  function roam(time){
    roamFrame=0;
    if(!state.roaming||state.reduced||document.hidden){if(roamActive){roamActive=false;state.avatar?.playAction('idle');bridge?.savePosition({x:state.x,y:state.y});}roamLast=0;return;}
    ensureRoam();const elapsed=roamLast?Math.min(.08,(time-roamLast)/1000):0;roamLast=time;
    const active=state.roaming&&!state.reduced&&!state.open&&!state.menu&&!state.drag&&!state.busy&&!state.activities.length&&!state.sleeping&&!document.hidden;
    if(!active){if(roamActive){roamActive=false;state.avatar?.playAction('idle');bridge?.savePosition({x:state.x,y:state.y});}return;}
    if(!roamActive){roamActive=true;state.avatar?.playAction(roamDirection<0?'walk-left':'walk-right');}
    const edge=Math.max(8,state.area.width-state.size-8);state.x+=roamDirection*14*elapsed;state.y=state.area.height-state.size-12;
    if(state.x<8||state.x>edge){state.x=Math.max(8,Math.min(edge,state.x));roamDirection*=-1;state.avatar?.playAction(roamDirection<0?'walk-left':'walk-right');}
    layout();if(time-roamSaved>5000){roamSaved=time;bridge?.savePosition({x:state.x,y:state.y});}
  }
  function attachInteractions(){
    const character=$('#pet-character');
    character.addEventListener('pointerdown',event=>{if(event.button!==0)return;character.setPointerCapture(event.pointerId);state.drag={startX:event.clientX,startY:event.clientY,offsetX:event.clientX-state.x,offsetY:event.clientY-state.y,moved:false};});
    character.addEventListener('pointermove',event=>{const d=state.drag;if(!d)return;if(!d.moved&&Math.hypot(event.clientX-d.startX,event.clientY-d.startY)>6){d.moved=true;character.dataset.dragging='true';state.avatar?.playAction('drag');bridge?.beginDrag();dragPing=setInterval(()=>bridge?.beginDrag(),500);}if(d.moved){state.x=event.clientX-d.offsetX;state.y=event.clientY-d.offsetY;layout();}});
    character.addEventListener('pointerup',endDrag);character.addEventListener('pointercancel',endDrag);character.addEventListener('lostpointercapture',()=>{if(state.drag)endDrag();});
    character.addEventListener('dblclick',()=>{clearTimeout(clickTimer);openPanel(!state.open);});character.addEventListener('contextmenu',event=>{event.preventDefault();toggleMenu();});
    character.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();openPanel(!state.open);}else if(event.key===' '){event.preventDefault();state.avatar?.playAction('wave');toast(t('hello'));}else if(event.key.startsWith('Arrow')){event.preventDefault();state.x+=event.key==='ArrowLeft'?-12:event.key==='ArrowRight'?12:0;state.y+=event.key==='ArrowUp'?-12:event.key==='ArrowDown'?12:0;layout();bridge?.savePosition({x:state.x,y:state.y});}});
    $('#pet-menu-toggle').addEventListener('click',toggleMenu);$('#pet-menu-chat').addEventListener('click',()=>openPanel());$('#pet-close-panel').addEventListener('click',()=>openPanel(false));
    $('#pet-reset').addEventListener('click',()=>{if(bridge)bridge.reset();else{state.x=innerWidth-190;state.y=innerHeight-state.size-16;layout();}});$('#pet-hide').addEventListener('click',()=>{if(bridge)bridge.hide();else{openPanel(false);toast('浏览器预览中请关闭此页；原生桌宠可由托盘恢复。');}});
    $('#pet-size').addEventListener('change',event=>{const size=Number(event.target.value);if(bridge)bridge.setScale(size);else{state.size=size;layout();}});
    $('#pet-roam').addEventListener('change',event=>{state.roaming=event.target.checked;bridge?.setRoaming(state.roaming);ensureRoam();});$('#pet-sleep').addEventListener('click',toggleSleep);
    document.querySelectorAll('[data-open]').forEach(button=>button.addEventListener('click',()=>openPage(button.dataset.open)));
    document.addEventListener('keydown',event=>{if(event.key==='Escape'){if(guideView&&!guideView.hidden){closeGuide();return;}openPanel(false);state.menu=false;$('#pet-menu').hidden=true;$('#pet-menu-toggle').setAttribute('aria-expanded','false');layout();}});
    $('#pet-chat-form').addEventListener('submit',event=>{event.preventDefault();send($('#pet-input').value);});$('#pet-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();send(event.currentTarget.value);}});
    $('#pet-explain').addEventListener('click',()=>{if(!state.session?.active_analysis_id)return toast(t('noReport'));send(state.language==='zh'?'请用白话解释当前已绑定的期权报告，标明数据时间和判断依据，并区分可确认与不可比部分。':'Explain the currently attached options report in plain language, retaining data times, evidence and incomparable limitations.');});
    $('#pet-new').addEventListener('click',async()=>{try{setError('');const saved=await api('/api/sessions',{method:'POST',body:JSON.stringify({title:state.language==='zh'?'鲸鱼娘新对话':'New Whale-chan conversation'})});await client.connect(saved.id,{language:state.language,engine:state.engine});}catch{setError(t('offline'));}});
    $('#pet-disconnect').addEventListener('click',()=>client.disconnect().catch(()=>setError(t('offline'))));
    $('#pet-engine').addEventListener('change',event=>{if(syncingControls)return;state.engine=event.target.value;client.setPreferences({language:state.language,engine:state.engine}).catch(()=>setError(t('offline')));});
    $('#pet-language').addEventListener('click',()=>{state.language=state.language==='zh'?'en':'zh';language();client.setPreferences({language:state.language,engine:state.engine}).catch(()=>setError(t('offline')));});
    $('#pet-reduce').checked=state.reduced;$('#pet-reduce').addEventListener('change',event=>{state.reduced=event.target.checked;state.avatar?.setReducedMotion(state.reduced);ensureRoam();});
    panelObserver=new ResizeObserver(layout);panelObserver.observe($('#pet-panel'));window.addEventListener('resize',()=>{state.area={width:innerWidth,height:innerHeight};layout();});
  }
  function toggleMenu(){state.menu=!state.menu;$('#pet-menu').hidden=!state.menu;$('#pet-menu-toggle').setAttribute('aria-expanded',String(state.menu));bridge?.setPanelOpen(state.menu||state.open);layout();if(state.menu)$('#pet-menu-chat').focus();}
  function mount(){if(state.avatar||!window.FinPilotCompanion)return;state.avatar=window.FinPilotCompanion.mount($('#pet-stage'),{language:state.language,reducedMotion:state.reduced});state.avatar.setState(state.avatarState);}
  async function init(){
    attachInteractions();createGuide();mount();window.addEventListener('finpilot-companion-ready',mount);
    state.x=innerWidth-state.size-34;state.y=innerHeight-state.size-16;layout();
    if(bridge)hitTimer=setInterval(()=>{if(!document.hidden)hitRects();},200);
    if(bridge){unsubscribers.push(bridge.onLayout(value=>{state.area=value.area;state.size=value.scale;state.roaming=value.roaming===true;$('#pet-roam').checked=state.roaming;$('#pet-size').value=String(value.scale);if(state.drag?.moved&&value.reason==='drag-cursor'){state.x=value.cursor.x-state.drag.offsetX;state.y=value.cursor.y-state.drag.offsetY;}else if(!state.drag){state.x=value.position.x;state.y=value.position.y;}layout();ensureRoam();}));
      unsubscribers.push(bridge.onCommand(command=>{if(command.type==='open-panel')openPanel();if(command.type==='end-drag')endDrag();if(command.type==='toggle-sleep')toggleSleep();if(command.type==='notice')toast(command.text);}));bridge.ready();}
    client=window.FinPilotCompanionClient.create({surface:bridge?'desktop':'workspace',shouldSync:()=>true,onConnection:connected,onSession:saved=>{state.session=saved;renderSession();},onActivity:activities=>{state.activities=activities;settle();},onStatus:value=>{if(!value.connected)$('#pet-connection').textContent=t('offline');}});
    try{const result=await api('/api/models');state.models=result.models||[];renderModels();}catch{setError(t('offline'));}
    window.finPilotPet={getStatus:()=>({open:state.open,busy:state.busy,sessionId:state.connection?.session_id||null,position:{x:state.x,y:state.y},scale:state.size,avatar:state.avatar?.getStatus(),native:Boolean(bridge)}),openPanel};
    document.addEventListener('visibilitychange',ensureRoam);ensureRoam();
    window.addEventListener('pagehide',()=>{guideController?.abort();clearTimeout(guideTimer);client.destroy();state.avatar?.destroy();panelObserver?.disconnect();for(const unsubscribe of unsubscribers)unsubscribe();document.removeEventListener('visibilitychange',ensureRoam);window.removeEventListener('finpilot-companion-ready',mount);cancelAnimationFrame(roamFrame);clearInterval(dragPing);clearInterval(hitTimer);clearTimeout(clickTimer);clearTimeout(state.toastTimer);},{once:true});
  }
  init().catch(()=>setError('桌宠界面未能初始化；请打开完整工作台。 / Open the workspace to continue.'));
})();
