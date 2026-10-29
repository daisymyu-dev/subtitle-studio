'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {videoInfo,frameURL,makeTimeline,activeIndex,canExportCached}=require('../web/watch-core.js');
test('only single authorized YouTube URLs become canonical video identities',()=>{
  assert.deepEqual(videoInfo('https://youtu.be/BaW_jenozKc?t=1m2s'),{id:'BaW_jenozKc',url:'https://www.youtube.com/watch?v=BaW_jenozKc',start:62});
  assert.equal(videoInfo('https://www.youtube.com/shorts/BaW_jenozKc').id,'BaW_jenozKc');
  for(const url of ['javascript:alert(1)','https://youtube.com.evil.test/watch?v=BaW_jenozKc','https://user:pass@youtube.com/watch?v=BaW_jenozKc','https://youtube.com:99/watch?v=BaW_jenozKc','https://youtube.com/playlist?list=xxx','https://youtu.be/short'])assert.equal(videoInfo(url),null);
});
test('the player URL is limited to the isolated loopback bridge',()=>{
  const url=frameURL('http://127.0.0.1:1234','BaW_jenozKc','a'.repeat(32));
  assert.match(url,/^http:\/\/127\.0\.0\.1:1234\/player\?/);assert.ok(!url.includes('app-token'));
  assert.throws(()=>frameURL('https://evil.example','BaW_jenozKc','a'.repeat(32)));
});
test('caption following is chronological, supports overlaps, gaps and backward seek',()=>{
  const cues=[{start:10,end:15,english:'Later'},{start:0,end:5,english:'First'},{start:3,end:4,english:'Overlap'}];
  const timeline=makeTimeline(cues);
  assert.equal(timeline.cues[0].english,'First');assert.equal(activeIndex(timeline,3.5),1);
  assert.equal(activeIndex(timeline,4.5),0);assert.equal(activeIndex(timeline,5),-1);
  assert.equal(activeIndex(timeline,11),2);assert.equal(activeIndex(timeline,1),0);assert.equal(activeIndex(timeline,99),-1);
  assert.equal(cues[0].english,'Later');
});
test('sync retains full captions beyond 200 and rejects malformed input',()=>{
  const timeline=makeTimeline(Array.from({length:301},(_,i)=>({start:i,end:i+1,english:'Line '+i})));
  assert.equal(activeIndex(timeline,250.2),250);assert.equal(timeline.cues.length,301);
  assert.throws(()=>makeTimeline([{start:1,end:0,english:'Bad'}]));
});
test('Word export can reuse only complete bilingual results for the same video',()=>{
  const result={id:'a'.repeat(32),url:'https://youtu.be/BaW_jenozKc',chinese_source:'Chinese',bilingual_count:301};
  assert.equal(canExportCached(result,'https://www.youtube.com/watch?v=BaW_jenozKc&t=1'),true);
  assert.equal(canExportCached(result,'https://youtu.be/na0scpoRBO0'),false);
  assert.equal(canExportCached({...result,chinese_source:''},result.url),false);
});
