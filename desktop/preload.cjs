'use strict';
const {contextBridge,ipcRenderer}=require('electron');
const subscribe=(channel,callback)=>{if(typeof callback!=='function')return()=>{};const listener=(_event,value)=>callback(value);ipcRenderer.on(channel,listener);return()=>ipcRenderer.removeListener(channel,listener);};
contextBridge.exposeInMainWorld('FinPilotDesktop',Object.freeze({
  version:'15.0.0',
  ready:()=>ipcRenderer.send('pet:ready'),
  setInteractiveRects:rects=>ipcRenderer.send('pet:rects',rects),
  savePosition:value=>ipcRenderer.send('pet:position',value),
  setPanelOpen:open=>ipcRenderer.send('pet:panel',open===true),
  beginDrag:()=>ipcRenderer.send('pet:drag',true),
  endDrag:()=>ipcRenderer.send('pet:drag',false),
  setScale:size=>ipcRenderer.send('pet:scale',size),
  setRoaming:value=>ipcRenderer.send('pet:roaming',value===true),
  hide:()=>ipcRenderer.send('pet:hide'),
  reset:()=>ipcRenderer.send('pet:reset'),
  open:target=>ipcRenderer.send('pet:open',target),
  onLayout:callback=>subscribe('pet:layout',callback),
  onCommand:callback=>subscribe('pet:command',callback)
}));
