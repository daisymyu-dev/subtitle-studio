'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {ShadowPlayer, pageFor} = require('../web/shadow-core.js');

function fixture(options={}) {
  const tasks = new Map();let next=0;
  const audio={currentTime:0,duration:200,playbackRate:1,paused:true,playCalls:0,
    async play(){this.paused=false;this.playCalls++;},pause(){this.paused=true;}};
  const messages=[];
  const player=new ShadowPlayer(audio,{setTimer:(fn,ms)=>{tasks.set(++next,{fn,ms});return next;},clearTimer:id=>tasks.delete(id),onState:s=>messages.push(s),...options});
  return {audio,player,tasks,messages,run(){const [id,t]=tasks.entries().next().value;tasks.delete(id);t.fn();}};
}
test('selecting a fragment never autoplays; play seeks to original timestamp',async()=>{
  const f=fixture();f.player.select({start:10,end:12});assert.equal(f.audio.playCalls,0);
  await f.player.play();assert.equal(f.audio.currentTime,10);assert.equal(f.audio.paused,false);
});
test('fragment end pauses original audio for following, not the rest of video',async()=>{
  const f=fixture();f.player.select({start:10,end:12});await f.player.play();
  f.audio.currentTime=12.01;f.player.tick();assert.equal(f.audio.paused,true);assert.equal(f.player.phase,'following');assert.equal(f.tasks.size,0);
});
test('loop waits a following gap; explicit pause cancels pending repetition',async()=>{
  const f=fixture();f.player.select({start:10,end:12});f.player.setLoop(true);f.player.setGap(4);await f.player.play();
  f.audio.currentTime=12;f.player.tick();assert.equal(f.tasks.size,1);assert.equal([...f.tasks.values()][0].ms,4000);
  f.player.pause();assert.equal(f.tasks.size,0);assert.equal(f.audio.paused,true);
});
test('loop can replay the same original fragment after the gap',async()=>{
  const f=fixture();f.player.select({start:10,end:12});f.player.setLoop(true);await f.player.play();
  f.audio.currentTime=12;f.player.tick();f.run();await new Promise(r=>setImmediate(r));
  assert.equal(f.audio.playCalls,2);assert.equal(f.audio.currentTime,10);
});
test('changing fragment/job clears old timers and never leaks old playback',async()=>{
  const f=fixture();f.player.select({start:10,end:12});f.player.setLoop(true);await f.player.play();
  f.audio.currentTime=12;f.player.tick();f.player.select({start:30,end:34});
  assert.equal(f.tasks.size,0);assert.equal(f.audio.paused,true);assert.equal(f.player.cue.start,30);
});
test('slow playback preserves pitch and adjusts the end timer',async()=>{
  const f=fixture();f.player.select({start:10,end:12});f.player.setRate(.5);await f.player.play();
  assert.equal(f.audio.playbackRate,.5);assert.equal(f.audio.preservesPitch,true);
  assert.equal([...f.tasks.values()][0].ms,4000);
});
test('invalid range, unknown speed and audio beyond end are rejected',async()=>{
  const f=fixture();assert.throws(()=>f.player.select({start:2,end:1}));assert.throws(()=>f.player.setRate(100));
  f.player.select({start:201,end:205});await assert.rejects(()=>f.player.play());assert.equal(f.audio.playCalls,0);
});
test('play rejection stops all timers and exposes an error',async()=>{
  const f=fixture();f.audio.play=async()=>{throw Error('blocked');};f.player.select({start:1,end:3});
  await assert.rejects(()=>f.player.play());assert.equal(f.tasks.size,0);assert.equal(f.player.phase,'error');
});
test('turning off loop while waiting prevents delayed autoplay',async()=>{
  const f=fixture();f.player.select({start:1,end:3});f.player.setLoop(true);await f.player.play();f.audio.currentTime=3;f.player.tick();
  f.player.setLoop(false);assert.equal(f.tasks.size,0);
});
test('page selection can reach full text beyond the first 200 fragments',()=>{
  assert.equal(pageFor(249,50),4);assert.equal(pageFor(0,50),0);
});
test('browser timer functions are not invoked with the player as their receiver',async()=>{
  const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
  const context={module:{exports:{}},setTimeout:function(){if(this&&this.audio)throw TypeError('Illegal invocation');return 1;},clearTimeout:function(){if(this&&this.audio)throw TypeError('Illegal invocation');}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/shadow-core.js'),'utf8'),context);
  const a={currentTime:0,duration:4,pause(){},async play(){}};
  const p=new context.module.exports.ShadowPlayer(a);p.select({start:0,end:2});
  await assert.doesNotReject(()=>p.play());assert.doesNotThrow(()=>p.pause());
});
test('playback waits for authenticated media renewal and a pause cancels late renewal',async()=>{
  let resolve;const pending=new Promise(r=>{resolve=r;});const f=fixture({beforePlay:()=>pending});
  f.player.select({start:2,end:4});const playing=f.player.play();assert.equal(f.audio.playCalls,0);
  f.player.pause();resolve();await playing;assert.equal(f.audio.playCalls,0);assert.equal(f.tasks.size,0);
});
