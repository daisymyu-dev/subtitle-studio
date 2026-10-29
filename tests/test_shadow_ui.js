'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const core=require('../web/shadow-core.js');
function harness(fetcher,learning={}){
  const nodes=new Map();
  function el(id){if(!nodes.has(id))nodes.set(id,{id,hidden:false,disabled:false,value:'1',checked:false,textContent:'',content:'session',children:[],dataset:{},attributes:{},paused:true,currentTime:0,duration:10,
    classList:{toggle(){}},setAttribute(k,v){this.attributes[k]=v;},getAttribute(k){return this.attributes[k]||'';},
    listeners:{},addEventListener(k,f){(this.listeners[k]||=[]).push(f);this[k==='pause'?'emitPause':k]=(...args)=>{let result;for(const fn of [...this.listeners[k]])result=fn(...args);return result;};},removeEventListener(k,f){this.listeners[k]=(this.listeners[k]||[]).filter(x=>x!==f);},append(...x){this.children.push(...x);},replaceChildren(...x){this.children=x;},scrollIntoView(){},
    pause(){this.paused=true;},async play(){this.paused=false;this.playCount=(this.playCount||0)+1;},load(){this.readyState=0;},removeAttribute(k){delete this[k];}});return nodes.get(id);}
  const context={window:{ShadowCore:core,...learning},document:{getElementById:el,querySelector:()=>el('meta'),createElement:tag=>el('created-'+nodes.size),createDocumentFragment:()=>el('fragment-'+nodes.size)},
    fetch:fetcher,setTimeout,clearTimeout,console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/shadowing.js'),'utf8'),context);
  return {el,api:context.window.OriginalShadowing};
}
function response(data){return {ok:true,json:async()=>data};}
const study={id:'a'.repeat(32),url:'https://youtu.be/BaW_jenozKc',title:'Example',cues:[{start:0,end:2,english:'Original words',chinese:'中文参考'}],chinese_note:'段落参考'};
test('local-file result hides entry; valid result shows entry without downloading',()=>{
  const calls=[];const h=harness(async url=>{calls.push(url);return response({});});
  h.api.showResult({id:study.id,url:null});assert.equal(h.el('shadow-open').hidden,true);
  h.api.showResult({id:study.id,url:study.url});assert.equal(h.el('shadow-open').hidden,false);assert.equal(calls.length,0);
});
test('opening loads full study, preparing never autoplays',async()=>{
  const calls=[];const h=harness(async(url,options)=>{calls.push({url,options});return response(url.endsWith('/study')?study:{status:'ready',message:'Ready',media_url:'/media/test'});});
  h.api.showResult({id:study.id,url:study.url});await h.el('shadow-open').click();
  assert.equal(h.el('shadowing').hidden,false);assert.equal(h.el('shadow-english').textContent,'Original words');
  await h.el('shadow-prepare').click();assert.equal(h.el('shadow-audio').playCount||0,0);
  assert.equal(calls.filter(x=>x.options?.method==='POST').length,1);
  h.api.reset();
});
test('changing jobs ignores stale study responses and clears old audio',async()=>{
  let resolve;const pending=new Promise(r=>{resolve=r;});
  const h=harness(()=>pending);h.api.showResult({id:study.id,url:study.url});const opened=h.el('shadow-open').click();
  h.api.showResult({id:'b'.repeat(32),url:study.url});assert.equal(h.el('shadow-open').disabled,false);resolve(response(study));await opened;
  assert.equal(h.el('shadowing').hidden,true);assert.equal(h.el('shadow-audio').paused,true);
});
test('reopening while preparation is pending does not abandon its polling state',async()=>{
  let resolve;const pending=new Promise(r=>{resolve=r;});let loads=0;
  const h=harness(async(url,options)=>{if(url.endsWith('/study')){loads++;return response(study);}if(options?.method==='POST')return pending;return response({status:'idle',message:'Prepare'});});
  h.api.showResult({id:study.id,url:study.url});await h.el('shadow-open').click();
  const preparation=h.el('shadow-prepare').click();await h.el('shadow-open').click();
  resolve(response({status:'ready',message:'Ready',media_url:'/media/test'}));await preparation;
  assert.equal(loads,1);assert.equal(h.el('shadow-audio').src,'/media/test');h.api.reset();
});
test('pause remains usable while an expired media ticket is renewing',async()=>{
  let statuses=0;
  const h=harness(async url=>response(url.endsWith('/study')?study:{status:'ready',message:'Ready',media_url:'/media/'+(++statuses),expires_at:statuses===1?1:Date.now()/1000+1800}));
  h.api.showResult({id:study.id,url:study.url});await h.el('shadow-open').click();
  const audio=h.el('shadow-audio');audio.readyState=1;audio.loadedmetadata();h.el('shadow-play').click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.el('shadow-pause').disabled,false);
  h.el('shadow-pause').click();audio.readyState=1;audio.loadedmetadata();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(audio.playCount||0,0);assert.equal(audio.paused,true);h.api.reset();
});
test('full-text paging reaches and selects fragments after 200',async()=>{
  const full={...study,cues:Array.from({length:251},(_,i)=>({start:i,end:i+1,english:'Line '+i,chinese:''}))};
  const h=harness(async url=>response(url.endsWith('/study')?full:{status:'idle',message:'Prepare'}));
  h.api.showResult({id:study.id,url:study.url});await h.el('shadow-open').click();
  for(let i=0;i<4;i++)h.el('shadow-page-next').click();
  assert.equal(h.el('shadow-page-info').textContent,'5 / 6');
  const first=h.el('shadow-list').children[0].children[0];first.click();
  assert.equal(h.el('shadow-counter').textContent,'201 / 251');assert.equal(h.el('shadow-english').textContent,'Line 200');h.api.reset();
});

test('English-only current practice renders learning terms and keeps the Chinese placeholder',async()=>{
  const englishOnly={...study,cues:[{start:0,end:2,english:'An otherworldly rally',chinese:''}]},rendered=[];
  const h=harness(async url=>response(url.endsWith('/study')?englishOnly:{status:'idle',message:'Prepare'}),{
    LearningHighlights:{renderPair(en,zh,cue){rendered.push({id:en.id,cue});en.textContent=cue.english;zh.textContent=cue.chinese||'';}}
  });
  h.api.showResult({id:study.id,url:study.url});await h.el('shadow-open').click();
  assert.ok(rendered.some(item=>item.id==='shadow-english'),'current English-only sentence must use the shared renderer');
  assert.equal(h.el('shadow-english').textContent,'An otherworldly rally');
  assert.match(h.el('shadow-chinese').textContent,/暂无中文参考/);
  assert.equal(h.el('shadow-audio').playCount||0,0);h.api.reset();
});

test('starting original-audio practice stops pronunciation without changing idle preparation',async()=>{
  let stops=0;
  const h=harness(async url=>response(url.endsWith('/study')?study:{status:'ready',message:'Ready',media_url:'/media/test'}),{
    LearningHighlights:{renderPair(){},stopPronunciation(){stops++;}}
  });
  h.api.showResult({id:study.id,url:study.url});await h.el('shadow-open').click();assert.equal(stops,0);
  const audio=h.el('shadow-audio');audio.readyState=1;audio.loadedmetadata();h.el('shadow-play').click();
  await new Promise(resolve=>setImmediate(resolve));assert.equal(stops,1);h.api.reset();
});

test('shadow profile changes reuse full raw cues without resetting current audio or selecting again',async()=>{
  let changed,profile={known:[]};const passes=[];
  const full={...study,cues:Array.from({length:120},(_,i)=>({start:i,end:i+1,english:'Otherworldly '+i,chinese:''}))};
  const h=harness(async url=>response(url.endsWith('/study')?full:{status:'idle'}),{
    LearningLibrary:{getProfile:()=>profile,subscribe(fn){changed=fn;}},
    LearningCore:{annotateCues(cues,options){passes.push({cues,options});return cues.map(c=>({...c,learning:[]}));}}
  });
  h.api.showResult(study);await h.el('shadow-open').click();h.el('shadow-audio').currentTime=.5;
  profile={known:['otherworldly']};assert.equal(typeof changed,'function');changed(profile);
  assert.equal(passes.at(-1).cues.length,120);assert.ok(passes.at(-1).cues.every(c=>!c.learning));
  assert.deepEqual(passes.at(-1).options.known,['otherworldly']);assert.equal(h.el('shadow-audio').currentTime,.5);
  assert.equal(h.el('shadow-audio').playCount||0,0);h.api.reset();
});
