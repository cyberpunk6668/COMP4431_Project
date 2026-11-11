/*
 * FinPilot original procedural mentor, Three.js + native SVG fallback.
 * No camera, microphone, audio capture, external model asset, or network service.
 * Speaking is an approximate procedural mouth animation, NOT phoneme lip sync.
 */
const SVG_NS = 'http://www.w3.org/2000/svg';
const STATES = new Set(['idle', 'listening', 'thinking', 'speaking', 'error']);
// Same warm metal family as the FinPilot landing page. Colour communicates
// interaction state only; it is never an investment-risk or confidence score.
const STATE_COLORS = Object.freeze({
  idle: 0xe8c88a,
  listening: 0xf5dcaa,
  thinking: 0xdba85a,
  speaking: 0xffe7b4,
  error: 0xdfa28e,
});
let instanceNumber = 0;
let threeModule;

const LABELS = {
  zh: { name:'FinPilot 金融知识教练', idle:'准备就绪', listening:'正在聆听', thinking:'正在思考', speaking:'正在朗读', error:'操作未完成', flat:'二维形象', spatial:'三维形象' },
  en: { name:'FinPilot financial learning mentor', idle:'Ready', listening:'Listening', thinking:'Thinking', speaking:'Reading aloud', error:'Action incomplete', flat:'2D avatar', spatial:'3D avatar' },
};

function svgElement(tag, attrs={}, parent) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,String(value));
  if (parent) parent.append(el);
  return el;
}

function createFlatAvatar(id) {
  const root=svgElement('svg',{viewBox:'0 0 320 320',class:'fp-avatar__flat','aria-hidden':'true',focusable:'false'});
  const defs=svgElement('defs',{},root);
  const pearl=svgElement('linearGradient',{id:`${id}-pearl`,x1:'0%',y1:'0%',x2:'100%',y2:'100%'},defs);
  svgElement('stop',{offset:'0%','stop-color':'#55514a'},pearl);svgElement('stop',{offset:'58%','stop-color':'#2d2c29'},pearl);svgElement('stop',{offset:'100%','stop-color':'#181917'},pearl);
  const porcelain=svgElement('linearGradient',{id:`${id}-porcelain`,x1:'0%',y1:'0%',x2:'100%',y2:'100%'},defs);
  svgElement('stop',{offset:'0%','stop-color':'#eee7da'},porcelain);svgElement('stop',{offset:'100%','stop-color':'#c9bdab'},porcelain);
  const metal=svgElement('linearGradient',{id:`${id}-metal`,x1:'0%',y1:'0%',x2:'100%',y2:'100%'},defs);
  svgElement('stop',{offset:'0%','stop-color':'#f1d59e'},metal);svgElement('stop',{offset:'48%','stop-color':'#dba85a'},metal);svgElement('stop',{offset:'100%','stop-color':'#957040'},metal);
  const visor=svgElement('linearGradient',{id:`${id}-visor`,x1:'0%',y1:'0%',x2:'70%',y2:'100%'},defs);
  svgElement('stop',{offset:'0%','stop-color':'#171917'},visor);svgElement('stop',{offset:'100%','stop-color':'#070908'},visor);
  const halo=svgElement('g',{class:'fp-avatar__halo',fill:'none',stroke:'#b79761','stroke-width':'1'},root);
  svgElement('ellipse',{cx:160,cy:154,rx:132,ry:114,'stroke-opacity':'.23','stroke-dasharray':'2 7',transform:'rotate(-22 160 154)'},halo);
  svgElement('circle',{cx:65,cy:75,r:5,fill:'#dba85a',stroke:'none'},halo);
  svgElement('circle',{cx:267,cy:206,r:4,fill:'#ead2a3',stroke:'none'},halo);
  const coin=svgElement('g',{transform:'translate(253 88) rotate(15)'},halo);
  svgElement('rect',{x:-15,y:-15,width:30,height:30,rx:10,fill:'#171816',stroke:'#9c7c45','stroke-width':1},coin);
  svgElement('path',{d:'M-7 5 -2 0 2 2 8 -5 M3 -5h5v5',stroke:'#dbb06c','stroke-width':1.5,'stroke-linecap':'round','stroke-linejoin':'round'},coin);
  svgElement('ellipse',{cx:160,cy:283,rx:65,ry:9,fill:'#dba85a',opacity:'.09'},root);
  const floating=svgElement('g',{class:'fp-avatar__float'},root);
  svgElement('ellipse',{class:'fp-avatar__status-ring',cx:160,cy:283,rx:80,ry:14,fill:'none',stroke:'#e4bf81','stroke-width':1.5},floating);
  // Floating body, tailored shoulder line and an original FinPilot chest emblem.
  svgElement('rect',{x:98,y:197,width:25,height:55,rx:12,fill:`url(#${id}-pearl)`,transform:'rotate(12 110 225)'},floating);
  svgElement('rect',{x:197,y:197,width:25,height:55,rx:12,fill:`url(#${id}-pearl)`,transform:'rotate(-12 209 225)'},floating);
  svgElement('rect',{x:99,y:239,width:17,height:8,rx:4,fill:`url(#${id}-metal)`,transform:'rotate(12 110 225)'},floating);
  svgElement('rect',{x:204,y:239,width:17,height:8,rx:4,fill:`url(#${id}-metal)`,transform:'rotate(-12 209 225)'},floating);
  svgElement('path',{d:'M124 196 Q160 184 196 196 L194 249 Q190 268 160 271 Q130 268 126 249Z',fill:`url(#${id}-pearl)`,stroke:'#9b7c4b','stroke-opacity':'.6','stroke-width':1},floating);
  svgElement('path',{d:'M138 215 Q160 207 182 215 L181 246 Q179 257 160 259 Q141 257 139 246Z',fill:`url(#${id}-porcelain)`},floating);
  svgElement('path',{d:'M137 198 160 212 183 198',fill:'none',stroke:'#b9975e','stroke-width':1.4},floating);
  svgElement('rect',{x:149,y:224,width:22,height:24,rx:7,fill:'#22231f'},floating);
  svgElement('path',{d:'M155 242v-12h12m-12 6h9m-4 6v-12',stroke:'#dba85a','stroke-width':1.6,fill:'none'},floating);
  const head=svgElement('g',{class:'fp-avatar__head'},floating);
  svgElement('rect',{x:155,y:53,width:10,height:21,rx:5,fill:`url(#${id}-metal)`},head);
  svgElement('circle',{class:'fp-avatar__ear-light',cx:160,cy:51,r:7,fill:'#e8c88a'},head);
  svgElement('rect',{x:73,y:111,width:22,height:45,rx:10,fill:`url(#${id}-metal)`},head);
  svgElement('rect',{x:225,y:111,width:22,height:45,rx:10,fill:`url(#${id}-metal)`},head);
  svgElement('rect',{class:'fp-avatar__ear-light',x:78,y:119,width:6,height:28,rx:3,fill:'#e8c88a'},head);
  svgElement('rect',{class:'fp-avatar__ear-light',x:236,y:119,width:6,height:28,rx:3,fill:'#e8c88a'},head);
  svgElement('rect',{x:84,y:71,width:152,height:118,rx:39,fill:`url(#${id}-pearl)`,stroke:'#ad8b51','stroke-opacity':'.6','stroke-width':1},head);
  svgElement('rect',{x:94,y:83,width:132,height:92,rx:29,fill:`url(#${id}-visor)`,stroke:`url(#${id}-metal)`,'stroke-width':1.4},head);
  svgElement('path',{d:'M111 94Q122 88 153 89',fill:'none',stroke:'#d8c198','stroke-opacity':'.22','stroke-width':2,'stroke-linecap':'round'},head);
  svgElement('rect',{'data-eye':true,class:'fp-avatar__eye',x:120,y:111,width:12,height:21,rx:6},head);
  svgElement('rect',{'data-eye':true,class:'fp-avatar__eye',x:188,y:111,width:12,height:21,rx:6},head);
  svgElement('circle',{class:'fp-avatar__cheek',cx:114,cy:141,r:4,fill:'#e8c88a',opacity:'.18'},head);
  svgElement('circle',{class:'fp-avatar__cheek',cx:206,cy:141,r:4,fill:'#e8c88a',opacity:'.18'},head);
  svgElement('path',{class:'fp-avatar__mouth-smile',d:'M147 145Q160 157 173 145',fill:'none',stroke:'#e8c88a','stroke-width':3.5,'stroke-linecap':'round'},head);
  svgElement('ellipse',{class:'fp-avatar__mouth-open',cx:160,cy:149,rx:10,ry:7,fill:'#e8c88a'},head);
  svgElement('circle',{class:'fp-avatar__ear-light',cx:160,cy:181,r:2,fill:'#e8c88a'},head);
  return root;
}

function roundedShape(THREE,width,height,radius) {
  const x=-width/2,y=-height/2,r=radius,s=new THREE.Shape();
  s.moveTo(x+r,y);s.lineTo(x+width-r,y);s.quadraticCurveTo(x+width,y,x+width,y+r);
  s.lineTo(x+width,y+height-r);s.quadraticCurveTo(x+width,y+height,x+width-r,y+height);
  s.lineTo(x+r,y+height);s.quadraticCurveTo(x,y+height,x,y+height-r);
  s.lineTo(x,y+r);s.quadraticCurveTo(x,y,x+r,y);return s;
}

function buildThreeScene(THREE,canvas) {
  const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.8));
  renderer.setClearColor(0x000000,0);renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.02;
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(34,1,.1,50);camera.position.set(.9,.45,6.1);camera.lookAt(0,.05,0);
  scene.add(new THREE.HemisphereLight(0xf4e9d5,0x292621,1.8));
  const key=new THREE.DirectionalLight(0xffefd7,3);key.position.set(-3,5,5);scene.add(key);
  const edge=new THREE.DirectionalLight(0xe5bc77,2.2);edge.position.set(4,1,-3);scene.add(edge);
  const fill=new THREE.DirectionalLight(0xe8edf5,.95);fill.position.set(3,1,5);scene.add(fill);
  const shell=new THREE.MeshPhysicalMaterial({color:0x373632,metalness:.48,roughness:.34,clearcoat:.35,clearcoatRoughness:.3});
  const porcelain=new THREE.MeshPhysicalMaterial({color:0xddd4c4,metalness:.08,roughness:.42,clearcoat:.2});
  const gold=new THREE.MeshStandardMaterial({color:0xdba85a,metalness:.68,roughness:.36});
  const graphite=new THREE.MeshStandardMaterial({color:0x24251f,metalness:.34,roughness:.4});
  const screen=new THREE.MeshStandardMaterial({color:0x090b0a,metalness:.18,roughness:.25});
  const glow=new THREE.MeshBasicMaterial({color:STATE_COLORS.idle});
  const softGlow=new THREE.MeshBasicMaterial({color:STATE_COLORS.idle});
  const lineMat=new THREE.MeshBasicMaterial({color:0xb89965,transparent:true,opacity:.32});
  const robot=new THREE.Group();scene.add(robot);
  function box(w,h,d,r,material,parent,x=0,y=0,z=0) {
    const geometry=new THREE.ExtrudeGeometry(roundedShape(THREE,w,h,r),{depth:d,bevelEnabled:true,bevelSegments:3,steps:1,bevelSize:.025,bevelThickness:.025,curveSegments:12});
    geometry.translate(0,0,-d/2);
    const mesh=new THREE.Mesh(geometry,material);mesh.position.set(x,y,z);parent.add(mesh);return mesh;
  }
  function sphere(radius,material,parent,x,y,z,sx=1,sy=1,sz=1) {
    const mesh=new THREE.Mesh(new THREE.SphereGeometry(radius,20,14),material);mesh.position.set(x,y,z);mesh.scale.set(sx,sy,sz);parent.add(mesh);return mesh;
  }
  function tube(points,radius,material,parent) {
    const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p)));
    const mesh=new THREE.Mesh(new THREE.TubeGeometry(curve,20,radius,8,false),material);parent.add(mesh);return mesh;
  }
  // Body, subtly angled arms, collar and badge.
  box(.98,.77,.43,.23,shell,robot,0,-.79,0);
  box(.72,.47,.016,.13,porcelain,robot,0,-.79,.24);
  box(.15,.19,.02,.045,graphite,robot,0,-.82,.275);
  tube([[-.034,-.867,.316],[-.034,-.779,.316],[.035,-.779,.316]],.008,gold,robot);
  tube([[-.034,-.82,.316],[.025,-.82,.316]],.008,gold,robot);
  tube([[0,-.867,.316],[0,-.779,.316]],.006,gold,robot);
  tube([[-.31,-.445,.23],[0,-.6,.27],[.31,-.445,.23]],.012,gold,robot);
  const arms=[];
  for (const side of [-1,1]) {
    const arm=new THREE.Group();arm.position.set(side*.67,-.74,0);arm.rotation.z=side*.18;robot.add(arm);
    const upper=new THREE.Mesh(new THREE.CapsuleGeometry(.1,.25,5,14),shell);arm.add(upper);
    const cuff=new THREE.Mesh(new THREE.CylinderGeometry(.105,.105,.07,20),gold);cuff.position.y=-.16;arm.add(cuff);
    sphere(.105,porcelain,arm,0,-.23,0,1,.85,1);arms.push(arm);
  }
  sphere(.18,gold,robot,0,-.31,0,1,.4,1);
  const head=new THREE.Group();head.position.y=.44;robot.add(head);
  box(1.59,1.12,.49,.3,shell,head);
  box(1.42,.92,.015,.255,gold,head,0,.015,.28);
  box(1.37,.87,.03,.24,screen,head,0,.015,.305);
  // Glass highlight is deliberately subtle, not a fake HUD/chart.
  tube([[-.51,.33,.357],[-.35,.37,.36],[-.08,.37,.36]],.008,lineMat,head);
  const eyes=[sphere(.074,glow,head,-.32,.075,.366,.82,1.65,.28),sphere(.074,glow,head,.32,.075,.366,.82,1.65,.28)];
  const mouth=tube([[-.15,-.17,.368],[0,-.235,.368],[.15,-.17,.368]],.014,glow,head);
  const talkingMouth=sphere(.062,glow,head,0,-.195,.372,1.75,.7,.24);talkingMouth.visible=false;
  sphere(.03,softGlow,head,0,-.516,.288,1,1,.4);
  const earLights=[];
  for (const side of [-1,1]) {
    const ear=new THREE.Mesh(new THREE.CylinderGeometry(.18,.18,.12,24),gold);ear.rotation.z=Math.PI/2;ear.position.set(side*.874,.01,0);head.add(ear);
    const light=sphere(.08,softGlow,head,side*.94,.01,0,.23,1.1,1);earLights.push(light);
  }
  const antenna=new THREE.Mesh(new THREE.CylinderGeometry(.035,.035,.18,12),gold);antenna.position.set(0,.65,0);head.add(antenna);
  const antennaTip=sphere(.065,softGlow,head,0,.78,0);
  // Orbiting original chart card and quiet orbital rail.
  const orbit=new THREE.Group();orbit.position.set(0,.2,-.56);scene.add(orbit);
  const ring=new THREE.Mesh(new THREE.TorusGeometry(1.48,.007,6,100),lineMat);ring.rotation.set(.3,.2,-.22);orbit.add(ring);
  const orbitDot=sphere(.032,gold,orbit,-1.25,.75,0);
  const chartCard=new THREE.Group();chartCard.position.set(1.34,.77,.05);chartCard.rotation.set(-.05,-.15,.08);scene.add(chartCard);
  box(.42,.42,.035,.1,graphite,chartCard);
  tube([[-.12,-.07,.05],[-.035,.01,.05],[.03,-.02,.05],[.13,.09,.05]],.009,gold,chartCard);
  tube([[.05,.09,.05],[.13,.09,.05],[.13,.01,.05]],.009,gold,chartCard);
  // Contact shadow is drawn locally, not a downloaded texture or model asset.
  const shadowCanvas=document.createElement('canvas');shadowCanvas.width=128;shadowCanvas.height=64;
  const ctx=shadowCanvas.getContext('2d');
  const shade=ctx.createRadialGradient(64,32,3,64,32,55);shade.addColorStop(0,'rgba(219,168,90,.16)');shade.addColorStop(1,'rgba(219,168,90,0)');ctx.fillStyle=shade;ctx.fillRect(0,0,128,64);
  const shadowTexture=new THREE.CanvasTexture(shadowCanvas);
  const shadow=new THREE.Mesh(new THREE.PlaneGeometry(2.45,.62),new THREE.MeshBasicMaterial({map:shadowTexture,transparent:true,depthWrite:false}));shadow.position.set(0,-1.39,-.1);shadow.rotation.x=-.75;scene.add(shadow);
  const listenMaterial=new THREE.MeshBasicMaterial({color:STATE_COLORS.listening,transparent:true,opacity:.42});
  const listeningRing=new THREE.Mesh(new THREE.TorusGeometry(.93,.012,8,80),listenMaterial);listeningRing.position.set(0,-1.26,0);listeningRing.rotation.x=Math.PI/2;listeningRing.visible=false;scene.add(listeningRing);
  return {THREE,renderer,scene,camera,robot,head,eyes,mouth,talkingMouth,earLights,antennaTip,arms,orbit,orbitDot,chartCard,listeningRing,glow,softGlow,lineMat,listenMaterial,shadowTexture};
}

class Mentor {
  constructor(container,options={}) {
    if (!(container instanceof Element)) throw new TypeError('Avatar mount requires an Element');
    this.container=container;this.language=options.language==='en'?'en':'zh';this.requestedMode=options.mode==='2d'?'2d':'3d';
    this.actualMode='2d';this.state='idle';this.fallbackReason=null;this.scene3d=null;this.destroyed=false;this.frames=0;this.frame=0;this.loading=false;this.visible=true;this.gaze={x:0,y:0};
    this.motionMedia=window.matchMedia('(prefers-reduced-motion: reduce)');this.motionOverride=null;this.reducedMotion=this.motionMedia.matches;
    this.root=document.createElement('div');this.root.className='fp-avatar';this.root.dataset.state='idle';this.root.dataset.actualMode='2d';
    this.root.setAttribute('role','img');this.flat=createFlatAvatar(`fp-mentor-${++instanceNumber}`);this.root.append(this.flat);container.append(this.root);
    this.onMotion=()=>{if(this.motionOverride===null)this.applyMotion(this.motionMedia.matches);};this.motionMedia.addEventListener('change',this.onMotion);
    this.onVisibility=()=>this.syncLoop();document.addEventListener('visibilitychange',this.onVisibility);
    this.onPointer=event=>{const rect=this.root.getBoundingClientRect();this.gaze.x=Math.max(-1,Math.min(1,(event.clientX-rect.left)/rect.width*2-1));this.gaze.y=Math.max(-1,Math.min(1,(event.clientY-rect.top)/rect.height*2-1));};
    this.onPointerLeave=()=>{this.gaze.x=0;this.gaze.y=0;};this.root.addEventListener('pointermove',this.onPointer);this.root.addEventListener('pointerleave',this.onPointerLeave);
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(this.root);
    this.intersectionObserver=new IntersectionObserver(entries=>{this.visible=entries[0]?.isIntersecting!==false;this.syncLoop();},{threshold:0});this.intersectionObserver.observe(this.root);
    this.applyMotion(this.reducedMotion);this.updateLabel();this.setMode(this.requestedMode);
  }

  updateLabel() {
    const words=LABELS[this.language];
    this.root.setAttribute('aria-label',`${words.name} · ${words[this.state]} · ${this.actualMode==='3d'?words.spatial:words.flat}`);
    this.root.dataset.state=this.state;this.root.dataset.actualMode=this.actualMode;this.root.dataset.reducedMotion=String(this.reducedMotion);
  }

  notify() {
    if(!this.destroyed)this.container.dispatchEvent(new CustomEvent('finpilot-avatar-status',{bubbles:true,detail:this.getStatus()}));
  }

  async ensure3D() {
    if(this.destroyed||this.loading||this.scene3d)return;
    this.loading=true;this.fallbackReason=null;
    let canvas;
    try {
      if(!threeModule)threeModule=import('./vendor/three/three.module.js');
      const THREE=await threeModule;
      if(this.destroyed||this.requestedMode!=='3d')return;
      canvas=document.createElement('canvas');canvas.className='fp-avatar__canvas';canvas.setAttribute('aria-hidden','true');
      // Probe explicitly so a non-WebGL2 device gets the useful 2D character.
      const context=canvas.getContext('webgl2',{alpha:true,antialias:true,powerPreference:'low-power'});
      if(!context)throw new Error('webgl2_unavailable');
      this.scene3d=buildThreeScene(THREE,canvas);this.root.append(canvas);
      this.onContextLost=event=>{event.preventDefault();if(this.destroyed)return;this.fallbackReason='webgl_context_lost';this.actualMode='2d';this.stopLoop();this.updateLabel();this.notify();};
      this.onContextRestored=()=>{if(this.destroyed||this.requestedMode!=='3d')return;this.fallbackReason=null;this.actualMode='3d';this.resize();this.updateLabel();this.syncLoop();this.notify();};
      canvas.addEventListener('webglcontextlost',this.onContextLost);canvas.addEventListener('webglcontextrestored',this.onContextRestored);
      this.actualMode='3d';this.resize();this.updateLabel();this.syncLoop();
    } catch(error) {
      if(!this.destroyed){this.fallbackReason=error?.message==='webgl2_unavailable'?'webgl2_unavailable':'renderer_initialization_failed';this.actualMode='2d';this.dispose3D();canvas?.remove();this.updateLabel();}
    } finally {this.loading=false;this.notify();}
  }

  setState(state) {
    if(this.destroyed)return;
    if(!STATES.has(state))throw new TypeError('Unsupported avatar state');
    this.state=state;this.updateLabel();this.render(0);this.syncLoop();this.notify();
  }

  setLanguage(language) {if(this.destroyed)return;this.language=language==='en'?'en':'zh';this.updateLabel();this.notify();}

  setMode(mode) {
    if(this.destroyed)return;
    if(!['2d','3d'].includes(mode))throw new TypeError('Unsupported avatar mode');
    this.requestedMode=mode;
    if(mode==='2d'){this.actualMode='2d';this.fallbackReason=null;this.stopLoop();}
    else if(this.scene3d&&!this.scene3d.renderer.getContext().isContextLost()){this.actualMode='3d';this.fallbackReason=null;this.resize();this.syncLoop();}
    else if(this.scene3d){this.dispose3D();this.ensure3D();}
    else this.ensure3D();
    this.updateLabel();this.syncLoop();this.notify();
  }

  setReducedMotion(value) {if(this.destroyed)return;this.motionOverride=Boolean(value);this.applyMotion(this.motionOverride);}
  applyMotion(value) {this.reducedMotion=Boolean(value);this.updateLabel();this.render(0);this.syncLoop();}

  resize() {
    if(this.destroyed||!this.scene3d)return;
    const width=Math.max(1,this.root.clientWidth),height=Math.max(1,this.root.clientHeight),aspect=width/height;
    this.scene3d.camera.aspect=aspect;this.scene3d.camera.position.z=aspect<.9?6.1*.9/aspect:6.1;this.scene3d.camera.lookAt(0,.05,0);this.scene3d.camera.updateProjectionMatrix();
    this.scene3d.renderer.setSize(width,height,false);this.render(0);
  }

  render(time) {
    if(this.destroyed||!this.scene3d||this.actualMode!=='3d')return;
    const s=this.scene3d,t=this.reducedMotion?0:time*.001,state=this.state;
    s.robot.position.y=this.reducedMotion?0:Math.sin(t*1.35)*.035;
    s.robot.rotation.y=this.reducedMotion?-.08:Math.sin(t*.5)*.035-.08;
    s.head.rotation.z=state==='thinking'?-.08:state==='listening'?.025:0;
    s.head.rotation.y=this.reducedMotion?0:this.gaze.x*.09;
    s.head.rotation.x=this.reducedMotion?0:this.gaze.y*.035;
    const blink=!this.reducedMotion&&t%5.4>5.18?Math.max(.08,Math.abs((t%5.4-5.29)/.11)):1;
    for(const eye of s.eyes)eye.scale.y=1.65*blink;
    s.glow.color.set(STATE_COLORS[state]);s.softGlow.color.set(STATE_COLORS[state]);
    s.lineMat.opacity=state==='thinking'?.5:state==='speaking'?.4:state==='error'?.2:.32;
    s.listenMaterial.color.set(STATE_COLORS[state]);
    s.mouth.visible=state!=='speaking';s.talkingMouth.visible=state==='speaking';
    s.talkingMouth.scale.y=this.reducedMotion?.7:.35+Math.abs(Math.sin(t*12.3)*Math.cos(t*4.7))*.95;
    s.orbit.rotation.z=this.reducedMotion?0:t*(state==='thinking'?.28:.055);
    s.orbit.rotation.y=this.reducedMotion?0:Math.sin(t*.3)*.05;
    s.chartCard.position.y=.77+(this.reducedMotion?0:Math.sin(t*1.05+.9)*.045);
    s.listeningRing.visible=state==='listening';s.listeningRing.scale.setScalar(this.reducedMotion?1:1+Math.sin(t*3)*.035);
    s.antennaTip.scale.setScalar(state==='thinking'&&!this.reducedMotion?1+Math.sin(t*3)*.06:1);
    s.arms[0].rotation.z=state==='listening'?-.28:-.18;s.arms[1].rotation.z=state==='speaking'?.28:.18;
    try {s.renderer.render(s.scene,s.camera);this.frames++;}
    catch {this.fallbackReason='renderer_draw_failed';this.actualMode='2d';this.stopLoop();this.updateLabel();this.notify();}
  }

  stopLoop() {if(this.frame)cancelAnimationFrame(this.frame);this.frame=0;}

  syncLoop() {
    if(this.destroyed)return;
    const paused=document.hidden||!this.visible;this.root.dataset.paused=String(paused);
    const animate=this.actualMode==='3d'&&!this.reducedMotion&&!paused;
    if(!animate){this.stopLoop();return;}
    if(this.frame)return;
    let last=0;
    const tick=time=>{this.frame=0;if(this.destroyed||this.actualMode!=='3d'||this.reducedMotion||document.hidden||!this.visible)return;if(time-last>=32){this.render(time);last=time;}this.frame=requestAnimationFrame(tick);};
    this.frame=requestAnimationFrame(tick);
  }

  getStatus() {return {requestedMode:this.requestedMode,actualMode:this.actualMode,renderer:this.actualMode==='3d'?'webgl2':'svg',state:this.state,reducedMotion:this.reducedMotion,fallbackReason:this.fallbackReason,frames:this.frames,destroyed:this.destroyed,threeRevision:this.scene3d?.THREE.REVISION||null};}

  dispose3D() {
    if(!this.scene3d)return;
    const s=this.scene3d;s.renderer.domElement.removeEventListener('webglcontextlost',this.onContextLost);s.renderer.domElement.removeEventListener('webglcontextrestored',this.onContextRestored);
    const geometries=new Set(),materials=new Set();s.scene.traverse(object=>{if(object.geometry)geometries.add(object.geometry);if(object.material)for(const material of(Array.isArray(object.material)?object.material:[object.material]))materials.add(material);});
    for(const geometry of geometries)geometry.dispose();for(const material of materials)material.dispose();s.shadowTexture.dispose();s.renderer.dispose();s.renderer.forceContextLoss();s.renderer.domElement.remove();this.scene3d=null;
  }

  destroy() {
    if(this.destroyed)return;this.destroyed=true;this.stopLoop();this.resizeObserver.disconnect();this.intersectionObserver.disconnect();this.motionMedia.removeEventListener('change',this.onMotion);document.removeEventListener('visibilitychange',this.onVisibility);this.root.removeEventListener('pointermove',this.onPointer);this.root.removeEventListener('pointerleave',this.onPointerLeave);this.dispose3D();this.root.remove();
  }
}

window.FinPilotAvatar=Object.freeze({version:'1.0.0',mount:(container,options)=>new Mentor(container,options)});
window.dispatchEvent(new CustomEvent('finpilot-avatar-ready'));
export {Mentor};
