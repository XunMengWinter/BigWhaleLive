import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../static/js/lip-sync.js',import.meta.url),'utf8');
const {buildEnvelope,envelopeAt,LipSyncDriver}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const buffer=samples=>({duration:samples.length/1000,sampleRate:1000,length:samples.length,numberOfChannels:1,getChannelData:()=>Float32Array.from(samples)});

test('audio envelope preserves silence and follows actual media time, including seeking',()=>{
 const envelope=buildEnvelope(buffer([...Array(40).fill(0),...Array(60).fill(.2),...Array(40).fill(0)]));
 assert.equal(envelopeAt(envelope,.01),0);assert(envelopeAt(envelope,.07)>.9);
 assert.equal(envelopeAt(envelope,.12),0);assert.equal(envelopeAt(envelope,999),0);
 assert.equal(envelopeAt(envelope,-1),0);assert.equal(envelopeAt(envelope,NaN),0);
 assert.equal(envelopeAt(envelope,.01),0);
});
test('silent and overlong clips do not generate a fake talking envelope',()=>{
 assert(buildEnvelope(buffer(Array(100).fill(0))).values.every(x=>x===0));
 assert.throws(()=>buildEnvelope({...buffer([0]),duration:121}),/audio_duration/);
});

function harness(t,{deferred=false,fail=false}={}) {
 const originals={window:globalThis.window,fetch:globalThis.fetch,requestAnimationFrame:globalThis.requestAnimationFrame,cancelAnimationFrame:globalThis.cancelAnimationFrame};
 const raf=new Map();let id=0,resolveDecode;
 class Audio extends EventTarget {src='/audio/11111111-1111-4111-8111-111111111111.mp3';paused=false;ended=false;readyState=4;currentTime=.05;volume=.8;muted=false;getAttribute(){return this.src}}
 class Context {async decodeAudioData(){if(fail)throw new Error('decode');if(deferred)return new Promise(resolve=>{resolveDecode=resolve});return buffer(Array(200).fill(.2))}async close(){}}
 globalThis.window={AudioContext:Context};globalThis.fetch=async()=>({ok:true,headers:{get:()=>100},arrayBuffer:async()=>new ArrayBuffer(100)});
 globalThis.requestAnimationFrame=fn=>{raf.set(++id,fn);return id};globalThis.cancelAnimationFrame=i=>raf.delete(i);
 const audio=new Audio(),levels=[],statuses=[];
 const driver=new LipSyncDriver(audio,v=>levels.push(v),s=>statuses.push(s));
 t.after(()=>{driver.dispose();for(const [key,value]of Object.entries(originals)){if(value===undefined)delete globalThis[key];else globalThis[key]=value}});
 return {audio,driver,levels,statuses,raf,resolve:()=>resolveDecode(buffer(Array(200).fill(.2)))};
}
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};

test('playing follows audio time; waiting and pause close immediately without changing audio',async t=>{
 const h=harness(t);await h.driver.prepare();assert.equal(h.levels.at(-1),0);
 h.audio.dispatchEvent(new Event('playing'));h.driver.lastTick=performance.now()-50;h.driver.tick();assert(h.levels.at(-1)>.8);
 h.audio.dispatchEvent(new Event('waiting'));assert.equal(h.levels.at(-1),0);assert.equal(h.raf.size,0);
 h.audio.dispatchEvent(new Event('playing'));h.driver.lastTick=performance.now()-50;h.driver.tick();assert(h.levels.at(-1)>.8);
 h.audio.paused=true;h.audio.dispatchEvent(new Event('pause'));assert.equal(h.levels.at(-1),0);
 assert.equal(h.audio.volume,.8);assert.equal(h.audio.muted,false);assert.match(h.audio.src,/\.mp3$/);
});
test('late decoding after cancellation cannot revive an old utterance',async t=>{
 const h=harness(t,{deferred:true});const pending=h.driver.prepare();await flush();
 h.driver.reset();h.resolve();await pending;
 assert.equal(h.driver.envelope,null);assert.equal(h.levels.at(-1),0);assert.equal(h.statuses.at(-1),'idle');
});
test('decode failure is explicit and does not alter speech playback',async t=>{
 const h=harness(t,{fail:true});await h.driver.prepare();assert.equal(h.statuses.at(-1),'unavailable');
 assert.equal(h.audio.paused,false);assert.equal(h.audio.volume,.8);assert.equal(h.levels.at(-1),0);
});
test('dispose stops frames and removes media listeners',async t=>{
 const h=harness(t);await h.driver.prepare();h.audio.dispatchEvent(new Event('playing'));h.driver.dispose();
 h.audio.dispatchEvent(new Event('playing'));assert.equal(h.raf.size,0);assert.equal(h.levels.at(-1),0);
});

test('mouth tracking rounds millisecond WebM timestamps to the presented frame',async()=>{
 const code=await readFile(new URL('../static/js/mouth-renderer.js',import.meta.url),'utf8');
 const {trackingFrame}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
 assert.equal(trackingFrame(.042,241),1);
 assert.equal(trackingFrame(.083,241),2);
 assert.equal(trackingFrame(.167,241),4);
 assert.equal(trackingFrame(10.042,241),240);
 assert.equal(trackingFrame(0,241),0);
});
