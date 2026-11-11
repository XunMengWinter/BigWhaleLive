import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../static/js/pet-renderer.js',import.meta.url),'utf8');
const {PetRenderer}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
class Events {
  listeners=new Map();
  addEventListener(type,fn){if(!this.listeners.has(type))this.listeners.set(type,new Set());this.listeners.get(type).add(fn);}
  removeEventListener(type,fn){this.listeners.get(type)?.delete(fn);}
  dispatch(type){for(const fn of this.listeners.get(type)||[])fn();}
}
class Classes {
  values=new Set();
  add(name){this.values.add(name);}
  remove(name){this.values.delete(name);}
  toggle(name,on){on?this.values.add(name):this.values.delete(name);}
}
class Video extends Events {
  constructor(clip){super();this.dataset={clip};this.classList=new Classes();this.readyState=4;this.currentTime=0;this.paused=true;this.ended=false;this.error=null;this.playCalls=0;this.loadCalls=0;this.fail=0;}
  async play(){this.playCalls++;if(this.fail-->0){const error=new Error('interrupted');error.name='AbortError';throw error;}this.paused=false;if(this.deferred)return this.deferred;}
  pause(){this.paused=true;}
  load(){this.loadCalls++;this.error=null;this.ended=false;this.currentTime=0;}
}
async function flush(){for(let i=0;i<6;i++)await Promise.resolve();}
function harness(t,{reduced=false,fail=0}={}){
  const doc=new Events(),win=new Events(),media=new Events(),timers=new Map(),clock={time:0};
  doc.hidden=false;media.matches=reduced;
  globalThis.document=doc;globalThis.window=win;globalThis.matchMedia=()=>media;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{userAgent:'Chrome',platform:'MacIntel',maxTouchPoints:0}});
  globalThis.HTMLMediaElement={HAVE_METADATA:1};
  globalThis.setInterval=fn=>{const id=Symbol();timers.set(id,fn);return id;};
  globalThis.clearInterval=id=>timers.delete(id);
  const videos=['idle','speaking','thinking'].map(clip=>new Video(clip));videos[0].fail=fail;
  const root={dataset:{},classList:new Classes(),querySelectorAll:()=>videos};
  const label={textContent:''};const renderer=new PetRenderer(root,label,{now:()=>clock.time});
  t.after(()=>renderer.dispose());
  return {renderer,videos,root,label,doc,win,media,timers,clock};
}
test('same-state paused animation resumes instead of being skipped',async t=>{
  const h=harness(t);await flush();h.videos[0].pause();await h.renderer.setState('idle');
  assert.equal(h.videos[0].paused,false);assert.equal(h.root.dataset.motion,'idle');
});
test('transient play rejection does not permanently disable animation',async t=>{
  const h=harness(t,{fail:1});await flush();h.clock.time=2000;await h.renderer.setState('idle');await flush();
  assert.equal(h.renderer.failed,false);assert.equal(h.videos[0].paused,false);assert.equal(h.root.dataset.motion,'idle');
});
test('stalled frame clock is reloaded and restarted',async t=>{
  const h=harness(t);await flush();h.clock.time=5000;h.renderer.checkPlayback();await flush();
  assert.equal(h.videos[0].loadCalls,1);assert.equal(h.videos[0].paused,false);assert.equal(h.root.dataset.motion,'idle');
});
test('superseded play rejection cannot replace the newest animation',async t=>{
  const h=harness(t);await flush();let reject;
  h.videos[1].deferred=new Promise((_,r)=>{reject=r;});
  const old=h.renderer.setState('speaking');await h.renderer.setState('thinking');
  const error=new Error('old play interrupted');error.name='AbortError';reject(error);await old;await flush();
  assert.equal(h.root.dataset.motion,'thinking');assert.equal(h.renderer.failed,false);assert.equal(h.videos[2].paused,false);
});
test('background tabs do not retry and foreground return resumes playback',async t=>{
  const h=harness(t);await flush();h.doc.hidden=true;h.videos[0].pause();const before=h.videos[0].playCalls;
  h.clock.time=10000;h.renderer.checkPlayback();await flush();assert.equal(h.videos[0].playCalls,before);
  h.doc.hidden=false;h.doc.dispatch('visibilitychange');await flush();assert.equal(h.videos[0].paused,false);
});
test('reduced motion remains a static poster',async t=>{
  const h=harness(t,{reduced:true});await flush();h.clock.time=10000;h.renderer.checkPlayback();await flush();
  assert.equal(h.videos[0].playCalls,0);assert.equal(h.root.dataset.motion,'static');
});
test('automatic recovery is bounded when media remains unavailable',async t=>{
  const h=harness(t,{fail:100});await flush();
  for(let i=0;i<10;i++){h.clock.time+=10000;h.renderer.checkPlayback();await flush();}
  assert.ok(h.videos[0].loadCalls<=3);assert.ok(h.videos[0].playCalls<=4);assert.equal(h.root.dataset.motion,'static');
});
test('dispose removes timers and wake listeners',async t=>{
  const h=harness(t);await flush();h.renderer.dispose();assert.equal(h.timers.size,0);
  const before=h.videos[0].playCalls;h.doc.dispatch('visibilitychange');h.win.dispatch('focus');await flush();
  assert.equal(h.videos[0].playCalls,before);
});
