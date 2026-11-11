/* FinPilot 2D companion. Existing attributed artwork; no model/broker access.
 * State labels describe operations, never market sentiment or confidence.
 * Speaking uses existing gestures, NOT phoneme lip synchronization. */
(() => {
  'use strict';
  const base = new URL('./', document.currentScript.src);
  const STATES = new Set(['idle','listening','thinking','speaking','error']);
  const ACTIONS = new Set(['idle','wave','pat','walk-left','walk-right','drag','fall','land','sleep','wake']);
  const words = {
    zh:{name:'鲸鱼娘 · 金融学习助手',idle:'准备就绪',listening:'正在聆听',thinking:'正在处理',speaking:'正在朗读',error:'操作未完成'},
    en:{name:'Whale-chan · financial learning companion',idle:'Ready',listening:'Listening',thinking:'Working',speaking:'Reading aloud',error:'Action incomplete'},
  };
  let manifestPromise;
  const images = new Map();
  function localURL(path) {
    if (!/^assets\/[a-z0-9-]+\.webp$/.test(path)) throw new Error('invalid_asset_path');
    return new URL(path,base).href;
  }
  function loadImage(url) {
    if (!images.has(url)) images.set(url,new Promise((resolve,reject) => {
      const image = new Image(); image.decoding='async';
      image.onload=()=>resolve(image); image.onerror=()=>{images.delete(url);reject(new Error('image_load_failed'));};
      image.src=url;
    }));
    return images.get(url);
  }
  function manifest() {
    if (!manifestPromise) manifestPromise=fetch(new URL('manifest.json',base),{credentials:'same-origin'})
      .then(r=>{if(!r.ok)throw new Error('manifest_load_failed');return r.json();})
      .then(m=>{if(m.version!==1||!m.clips?.idle||!m.atlases?.['idle-front'])throw new Error('invalid_manifest');return m;})
      .catch(error=>{manifestPromise=null;throw error;});
    return manifestPromise;
  }
  function chooseFrame(clip,elapsed,reduced) {
    let time=Math.max(0,Number.isFinite(elapsed)?elapsed:0);
    const duration=clip.frames.reduce((sum,frame)=>sum+frame.duration_ms,0);
    if(reduced)time=0;else if(clip.loop)time%=duration;else time=Math.min(time,duration-.001);
    let index=0;
    while(index<clip.frames.length-1&&time>=clip.frames[index].duration_ms){time-=clip.frames[index].duration_ms;index++;}
    return {frame:clip.frames[index],index,duration};
  }
  class Companion {
    constructor(container,options={}) {
      if(!(container instanceof Element))throw new TypeError('Companion mount requires an Element');
      this.container=container;this.language=options.language==='en'?'en':'zh';this.state='idle';this.action=null;
      this.destroyed=false;this.visible=true;this.frame=0;this.frames=0;this.spriteChanges=0;this.activeClip='idle';
      this.loading=true;this.failed=false;this.renderer='unavailable';this.fallbackReason=null;this.assetRevision=null;
      this.atlases=new Map();this.pending=new Set();this.started=performance.now();this.lastDraw='';this.lastTick=0;
      this.motionMedia=matchMedia('(prefers-reduced-motion: reduce)');
      this.motionOverride=typeof options.reducedMotion==='boolean'?options.reducedMotion:null;
      this.reducedMotion=this.motionOverride??this.motionMedia.matches;
      this.root=document.createElement('div');this.root.className='fp-companion';this.root.setAttribute('role','img');
      this.canvas=document.createElement('canvas');this.canvas.className='fp-companion__canvas';this.canvas.setAttribute('aria-hidden','true');
      this.image=document.createElement('img');this.image.className='fp-companion__portrait';this.image.alt='';this.image.setAttribute('aria-hidden','true');
      this.notice=document.createElement('span');this.notice.className='fp-companion__notice';
      this.root.append(this.canvas,this.image,this.notice);container.append(this.root);
      this.context=this.canvas.getContext('2d',{alpha:true});
      this.onMotion=()=>{if(this.motionOverride===null){this.reducedMotion=this.motionMedia.matches;this.resetMotion();}};
      this.onVisibility=()=>this.syncLoop();this.motionMedia.addEventListener('change',this.onMotion);
      document.addEventListener('visibilitychange',this.onVisibility);
      this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(this.root);
      this.intersectionObserver=new IntersectionObserver(entries=>{this.visible=entries[0]?.isIntersecting!==false;this.syncLoop();},{threshold:0});
      this.intersectionObserver.observe(this.root);this.updateLabel();this.showPortrait(null);this.initialize();
    }
    async initialize() {
      try {
        if(!this.context)throw new Error('canvas2d_unavailable');
        const data=await manifest();if(this.destroyed)return;
        this.data=data;this.assetRevision=data.asset_revision;
        await this.ensureAtlas('idle-front');if(this.destroyed||this.failed)return;
        this.loading=false;this.resize();this.draw(performance.now(),true);this.syncLoop();this.notify();
      } catch(error) {this.fallback(error?.message==='canvas2d_unavailable'?'canvas2d_unavailable':'manifest_load_failed');}
    }
    updateLabel() {
      const text=words[this.language];this.root.setAttribute('aria-label',`${text.name} · ${text[this.state]} · 2D`);
      this.root.dataset.state=this.state;this.root.dataset.renderer=this.renderer;
      this.root.dataset.reducedMotion=String(this.reducedMotion);this.root.dataset.actualMode='2d';
      this.root.dataset.loading=String(this.loading);
      this.notice.textContent=this.language==='en'?'The character is unavailable. Text chat is still available.':'形象暂不可用，文字聊天仍可使用。';
    }
    notify() {
      if(!this.destroyed)this.container.dispatchEvent(new CustomEvent('finpilot-companion-status',{bubbles:true,detail:this.getStatus()}));
    }
    async showPortrait(reason) {
      try {
        const portrait=await loadImage(localURL('assets/portrait.webp'));
        if(this.destroyed||this.renderer==='canvas2d'&&!this.failed)return;
        this.image.src=portrait.src;this.renderer='static-image';this.fallbackReason=reason;
        this.updateLabel();this.notify();
      } catch {
        if(this.destroyed||this.renderer==='canvas2d'&&!this.failed)return;
        this.renderer='unavailable';this.fallbackReason=reason||'portrait_load_failed';this.updateLabel();this.notify();
      }
    }
    fallback(reason) {
      if(this.destroyed)return;this.failed=true;this.loading=false;this.stopLoop();this.fallbackReason=reason;
      this.renderer=this.image.complete&&this.image.naturalWidth?'static-image':'unavailable';this.updateLabel();this.notify();this.showPortrait(reason);
    }
    ensureAtlas(name) {
      if(this.destroyed||this.failed)return Promise.resolve(null);
      if(this.atlases.has(name))return Promise.resolve(this.atlases.get(name));
      const meta=this.data?.atlases[name];if(!meta){this.fallback('atlas_missing');return Promise.resolve(null);}
      const url=localURL(meta.url);this.pending.add(name);
      return loadImage(url).then(image=>{
        this.pending.delete(name);if(this.destroyed||this.failed)return null;
        this.atlases.set(name,image);this.lastDraw='';this.draw(performance.now(),true);this.syncLoop();return image;
      }).catch(()=>{this.pending.delete(name);this.fallback('atlas_load_failed');return null;});
    }
    resize() {
      if(this.destroyed)return;
      const width=Math.max(1,this.root.clientWidth),height=Math.max(1,this.root.clientHeight),ratio=Math.min(devicePixelRatio||1,1.8);
      this.canvas.width=Math.round(width*ratio);this.canvas.height=Math.round(height*ratio);this.lastDraw='';this.draw(performance.now(),true);
    }
    current(now) {
      const elapsed=now-this.started;let name=this.action||this.state;
      if(!this.data.clips[name])name='idle';let clip=this.data.clips[name];
      const duration=clip.frames.reduce((sum,frame)=>sum+frame.duration_ms,0);
      if(this.action&&!clip.loop&&!clip.hold&&elapsed>=duration&&!this.reducedMotion){
        const finished=this.action;this.action=null;this.started=now;name=this.state;clip=this.data.clips[name];
        this.container.dispatchEvent(new CustomEvent('finpilot-companion-action-end',{bubbles:true,detail:{action:finished}}));
      }
      let timing=now-this.started;
      // Existing HQ blink cells and a short authored shift; no generated faces.
      if(name==='idle'&&!this.reducedMotion){
        const cycle=timing%12500;
        if(cycle>=7600&&cycle<8200){name='shift';clip=this.data.clips.shift;timing=cycle-7600;}
      }
      const selected=chooseFrame(clip,timing,this.reducedMotion);
      let sprite=selected.frame;
      if(name==='idle'&&!this.reducedMotion&&timing%6100>5900)sprite={...sprite,source_index:1};
      return {name,clip,sprite,index:selected.index};
    }
    draw(now,force=false) {
      if(this.destroyed||this.failed||!this.data||!this.context)return;
      const {name,clip,sprite,index}=this.current(now);this.activeClip=name;
      const image=this.atlases.get(sprite.atlas);
      if(!image){if(!this.pending.has(sprite.atlas))this.ensureAtlas(sprite.atlas);return;}
      const bounds=this.data.atlases[sprite.atlas].frames[String(sprite.source_index)];
      if(!bounds){this.fallback('frame_missing');return;}
      const key=`${sprite.atlas}:${sprite.source_index}:${clip.flip}`;
      if(!force&&key===this.lastDraw)return;
      const c=this.context,w=this.canvas.width,h=this.canvas.height,size=Math.min(w,h);
      c.clearRect(0,0,w,h);c.save();c.imageSmoothingEnabled=true;c.imageSmoothingQuality='high';
      c.translate(w/2,h/2);if(clip.flip)c.scale(-1,1);
      c.drawImage(image,bounds.x,bounds.y,bounds.w,bounds.h,-size/2,-size/2,size,size);c.restore();
      if(this.lastDraw!==key)this.spriteChanges++;this.lastDraw=key;this.frames++;
      const changed=this.renderer!=='canvas2d';this.renderer='canvas2d';this.fallbackReason=null;this.updateLabel();
      this.root.dataset.clip=name;this.root.dataset.frame=String(index);if(changed)this.notify();
    }
    stopLoop(){if(this.frame)cancelAnimationFrame(this.frame);this.frame=0;}
    syncLoop() {
      if(this.destroyed)return;
      const paused=document.hidden||!this.visible;const before=this.root.dataset.paused;
      this.root.dataset.paused=String(paused);
      if(this.failed||this.loading||this.reducedMotion||paused){this.stopLoop();if(before!==String(paused))this.notify();return;}
      if(this.frame)return;
      const tick=now=>{
        this.frame=0;if(this.destroyed||this.failed||this.loading||this.reducedMotion||document.hidden||!this.visible)return;
        if(now-this.lastTick>=32){this.lastTick=now;this.draw(now);}
        this.frame=requestAnimationFrame(tick);
      };
      this.frame=requestAnimationFrame(tick);if(before!==String(paused))this.notify();
    }
    setState(state) {
      if(this.destroyed)return;if(!STATES.has(state))throw new TypeError('Unsupported companion state');
      if(state===this.state)return;
      this.state=state;if(!['drag','fall','land'].includes(this.action))this.action=null;
      this.started=performance.now();this.lastDraw='';this.updateLabel();this.draw(this.started,true);this.syncLoop();this.notify();
    }
    setLanguage(language){if(this.destroyed)return;this.language=language==='en'?'en':'zh';this.updateLabel();this.notify();}
    resetMotion(){this.started=performance.now();this.lastDraw='';this.updateLabel();this.draw(this.started,true);this.syncLoop();this.notify();}
    setReducedMotion(value){if(this.destroyed)return;this.motionOverride=Boolean(value);this.reducedMotion=this.motionOverride;this.resetMotion();}
    playAction(action) {
      if(this.destroyed)return null;if(!ACTIONS.has(action))throw new TypeError('Unsupported companion action');
      this.action=action==='idle'?null:action;this.started=performance.now();this.lastDraw='';
      if(this.data){this.draw(this.started,true);this.syncLoop();}
      this.notify();const clip=this.data?.clips[this.action||this.state];
      return {durationMs:clip?.frames.reduce((sum,frame)=>sum+frame.duration_ms,0)||0,loop:Boolean(clip?.loop),hold:Boolean(clip?.hold)};
    }
    getStatus(){return {renderer:this.renderer,actualMode:'2d',requestedMode:'2d',state:this.state,language:this.language,
      activeClip:this.activeClip,frames:this.frames,spriteChanges:this.spriteChanges,paused:document.hidden||!this.visible,
      reducedMotion:this.reducedMotion,fallbackReason:this.fallbackReason,assetRevision:this.assetRevision,
      loading:this.loading,destroyed:this.destroyed};}
    destroy(){if(this.destroyed)return;this.destroyed=true;this.stopLoop();this.resizeObserver.disconnect();this.intersectionObserver.disconnect();
      document.removeEventListener('visibilitychange',this.onVisibility);this.motionMedia.removeEventListener('change',this.onMotion);
      this.atlases.clear();this.root.remove();}
  }
  window.FinPilotCompanion=Object.freeze({version:'15.0.0',mount:(container,options)=>new Companion(container,options)});
  window.dispatchEvent(new CustomEvent('finpilot-companion-ready'));
})();
