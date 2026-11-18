'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {ROUTES,localBase,finiteRect,contains,position}=require('../geometry.cjs');
test('only canonical loopback backend origins are accepted',()=>{
  assert.equal(localBase('http://127.0.0.1:8123'),'http://127.0.0.1:8123');
  for(const url of ['https://example.com','http://user:password@127.0.0.1:8000','file:///pet','http://127.0.0.1:8000/other','http://127.0.0.1:8000/?token=bad'])assert.throws(()=>localBase(url));
});
test('interactive regions cannot exceed the work area or inject nonfinite positions',()=>{
  assert.equal(finiteRect({x:NaN,y:0,width:50,height:50},100,100),null);
  assert.equal(finiteRect({x:0,y:0,width:-3,height:50},100,100),null);
  assert.deepEqual(finiteRect({x:90,y:95,width:99,height:99},100,100),{x:90,y:95,width:10,height:5});
  assert.deepEqual(finiteRect({x:-20,y:-30,width:50,height:60},100,100),{x:0,y:0,width:30,height:30});
  const offscreen=finiteRect({x:-60,y:-70,width:50,height:60},100,100);
  assert.deepEqual(offscreen,{x:0,y:0,width:0,height:0});
  assert(!contains(offscreen,0,0));
  assert(!contains({x:20,y:20,width:10,height:10},30,25));
  assert(contains({x:20,y:20,width:10,height:10},25,25));assert(!contains({x:20,y:20,width:10,height:10},10,10));
});
test('restored pet coordinates remain visible after a screen or size change',()=>{
  assert.deepEqual(position({x:4000,y:-500},{width:800,height:600},250),{x:550,y:0,width:250,height:250});
  const initial=position(null,{width:1920,height:1080},200);assert.equal(initial.x,1686);assert.equal(initial.y,864);
});
test('preload exposes only window controls, not node or a general command bridge',()=>{
  const preload=fs.readFileSync(path.join(__dirname,'../preload.cjs'),'utf8');
  assert(!/require\(['"](?:node:)?(?:fs|child_process|process)['"]\)/.test(preload));
  assert(!/executeJavaScript|ipcRenderer\.invoke|readFile|spawn\(/.test(preload));
  assert(Object.hasOwn(ROUTES,'history'));assert(!Object.hasOwn(ROUTES,'terminal'));
});
