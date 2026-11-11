'use strict';
const ROUTES = Object.freeze({workspace:'/workspace', history:'/workspace?view=history', calculator:'/workspace?view=calculator', demo:'/demo'});
function localBase(value='http://127.0.0.1:8000') {
  const url=new URL(value);
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.username||url.password||url.pathname!=='/'||url.search||url.hash)throw Error('Only the configured loopback FinPilot origin is allowed');
  return url.origin;
}
function finiteRect(value,width,height) {
  if(!value||!['x','y','width','height'].every(k=>Number.isFinite(value[k])))return null;
  if(value.width<0||value.height<0)return null;
  const x=Math.max(0,Math.min(width,value.x)),y=Math.max(0,Math.min(height,value.y));
  return {x,y,width:Math.max(0,Math.min(value.width,width-x)),height:Math.max(0,Math.min(value.height,height-y))};
}
function contains(r,x,y) {return x>=r.x&&y>=r.y&&x<=r.x+r.width&&y<=r.y+r.height;}
function position(value,area,size=200) {
  const h=Math.max(150,Math.min(300,size)),w=h;
  const x=Number.isFinite(value?.x)?value.x:area.width-w-34;
  const y=Number.isFinite(value?.y)?value.y:area.height-h-16;
  return {x:Math.max(0,Math.min(area.width-w,x)),y:Math.max(0,Math.min(area.height-h,y)),width:w,height:h};
}
module.exports={ROUTES,localBase,finiteRect,contains,position};
