'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const core=require('../web/watch-core.js');
function harness(learning={}){
  const nodes=new Map(),messages=[],listeners={};let nonce=0;
  function element(id){if(!nodes.has(id))nodes.set(id,{id,hidden:false,disabled:false,checked:true,value:'',textContent:'',content:id==='meta-bridge'?'http://127.0.0.1:1234':'token',dataset:{},attributes:{},children:[],scrollCalls:0,
    contentWindow:{postMessage(data,target){messages.push({data,target});}},classList:{toggle(){}},setAttribute(k,v){this.attributes[k]=v;},getAttribute(k){return this.attributes[k]||'';},removeAttribute(k){delete this[k];},addEventListener(k,f){this[k]=f;},append(...x){this.children.push(...x);},replaceChildren(...x){this.children=x;},scrollIntoView(){this.scrollCalls++;}});return nodes.get(id);}
  const calls=[],study={id:'a'.repeat(32),title:'Example',url:'https://youtu.be/BaW_jenozKc',sentence_version:1,mode:'sentences',cues:[{start:0,end:2,english:'One',chinese:'一'},{start:3,end:5,english:'Two',chinese:'二'}]};
  const window={WatchCore:core,location:{href:'http://127.0.0.1:8765/?design=studio',search:'?design=studio'},history:{replaceState(){}},crypto:{randomUUID:()=>String(++nonce).padStart(32,'0')},addEventListener(k,f){listeners[k]=f;},OriginalShadowing:{pause(){}},};
  Object.assign(window,learning);
  const body={dataset:{}};
  const document={body,getElementById:element,querySelector:s=>element(s.includes('video-bridge')?'meta-bridge':'meta-token'),createElement:tag=>{const node=element('created-'+nodes.size);node.tagName=tag.toUpperCase();return node;},createDocumentFragment:()=>element('frag-'+nodes.size)};
  const context={window,document,URL,URLSearchParams,console,fetch:async url=>{calls.push(url);return {ok:true,json:async()=>study};}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/watch-sync.js'),'utf8'),context);
  function event(data,origin='http://127.0.0.1:1234',source=element('original-video-frame').contentWindow){listeners.message({data,origin,source});}
  return {el:element,api:window.WatchSync,window,body,calls,messages,study,event};
}
test('valid pasted URL mounts original player without play and page switch keeps the same frame',()=>{
  const h=harness();h.api.setVideo('https://youtu.be/BaW_jenozKc');const src=h.el('original-video-frame').src;
  assert.match(src,/127\.0\.0\.1:1234\/player/);h.api.setPage('study');h.api.setPage('watch');
  assert.equal(h.el('original-video-frame').src,src);assert.equal(h.messages.filter(x=>x.data.command==='play').length,0);
});
test('external playback controls send play only after an explicit user click and readiness',()=>{
  const h=harness();h.api.setVideo('https://youtu.be/BaW_jenozKc');
  assert.equal(typeof h.el('watch-play-video').click,'function');
  h.el('watch-play-video').click();assert.equal(h.messages.some(x=>x.data.command==='play'),false);
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');h.event({channel,event:'ready',videoId:'BaW_jenozKc'});
  h.el('watch-play-video').click();assert.equal(h.messages.filter(x=>x.data.command==='play').length,1);
  h.event({channel,event:'blocked',videoId:'BaW_jenozKc',errorCode:'AUTOPLAY_BLOCKED'});
  assert.match(h.el('watch-player-status').textContent,/播放器内/);assert.equal(h.el('watch-play-video').disabled,false);
});

test('playing the original video stops a word demonstration but loading does not',()=>{
  const h=harness();let stops=0;h.window.LearningHighlights={stopPronunciation(){stops++;}};
  h.api.setVideo(h.study.url);assert.equal(stops,0);
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'ready',videoId:'BaW_jenozKc'});assert.equal(stops,0);
  h.el('watch-play-video').click();assert.equal(stops,1);
  h.event({channel,event:'state',videoId:'BaW_jenozKc',state:1});assert.equal(stops,2);
});
test('manual player progress changes local subtitles; gaps clear stale text',async()=>{
  const h=harness();await h.api.result({...h.study,chinese_source:'Chinese',bilingual_count:2});
  const query=new URL(h.el('original-video-frame').src),channel=query.searchParams.get('channel');
  h.event({channel,event:'time',videoId:'BaW_jenozKc',time:3.5});assert.equal(h.el('watch-current-en').textContent,'Two');
  h.event({channel,event:'time',videoId:'BaW_jenozKc',time:2.5});assert.notEqual(h.el('watch-current-en').textContent,'Two');
});

test('late arriving captions use the actual paused video time, including an initial gap',async()=>{
  const h=harness();h.study.cues[0].start=1;h.api.setVideo(h.study.url);
  await h.api.result(h.study);assert.equal(h.el('watch-current-en').textContent,'这一时段暂无字幕。');
  h.api.setVideo('https://youtu.be/na0scpoRBO0');h.api.setVideo(h.study.url);
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'time',videoId:'BaW_jenozKc',time:3.5});await h.api.result(h.study);
  assert.equal(h.el('watch-current-en').textContent,'Two');assert.equal(h.el('watch-clock').textContent,'00:03');
});
test('untrusted messages and stale video identities cannot drive caption sync',async()=>{
  const h=harness();await h.api.result(h.study);const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'time',videoId:'BaW_jenozKc',time:3.5},'https://evil.example');assert.notEqual(h.el('watch-current-en').textContent,'Two');
  h.api.setVideo('https://youtu.be/na0scpoRBO0');h.event({channel,event:'time',videoId:'BaW_jenozKc',time:3.5});assert.notEqual(h.el('watch-current-en').textContent,'Two');
});
test('switching pages and reattaching the same completed result does not re-extract or reload study',async()=>{
  const h=harness();await h.api.result(h.study);h.api.setPage('study');h.api.setPage('watch');await h.api.result(h.study);
  assert.equal(h.calls.filter(x=>x.endsWith('/study')).length,1);
});

test('legacy paragraph references are not displayed as sentence translations',async()=>{
  const h=harness();delete h.study.sentence_version;delete h.study.mode;await h.api.result(h.study);
  assert.equal(h.el('watch-sentences').hidden,false);
  assert.match(h.el('watch-transcript-status').textContent,/完整句/);
  assert.equal(h.el('watch-transcript-list').children.length,0);
  assert.equal(h.api.canExport(h.study.url),false);
});

test('video speed uses a readiness-gated numeric command without starting playback',()=>{
  const h=harness();h.api.setVideo(h.study.url);
  assert.equal(h.el('watch-rate').disabled,true);assert.equal(typeof h.el('watch-rate').change,'function');
  h.el('watch-rate').value='2';h.el('watch-rate').change();assert.equal(h.messages.filter(x=>x.data.command==='rate').length,0);
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'ready',videoId:'BaW_jenozKc'});
  h.event({channel,event:'playback',videoId:'BaW_jenozKc',rate:1,rates:[.75,1,1.25,1.5,2]});
  assert.equal(h.el('watch-rate').disabled,false);
  h.el('watch-rate').value='2';h.el('watch-rate').change();
  assert.equal(h.messages.at(-1).data.command,'rate');assert.equal(h.messages.at(-1).data.rate,2);
  assert.equal(h.messages.filter(x=>x.data.command==='play').length,0);
  h.event({channel,event:'playback',videoId:'BaW_jenozKc',rate:2,rates:[.75,1,1.25,1.5,2]});
  assert.equal(h.el('watch-rate').value,'2');assert.match(h.el('watch-rate-status').textContent,/2×/);
  h.api.setPage('watch');h.api.setPage('study');assert.equal(h.el('watch-rate').value,'2');
});

test('rate messages cannot desynchronize captions and unsupported options stay disabled',async()=>{
  const h=harness();await h.api.result(h.study);const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'ready',videoId:'BaW_jenozKc'});
  h.event({channel,event:'playback',videoId:'BaW_jenozKc',rate:1,rates:[1]});
  assert.equal(h.el('watch-rate').children.find(x=>x.value==='2').disabled,true);
  h.event({channel,event:'playback',videoId:'BaW_jenozKc',rate:2,rates:[1,2]},'https://evil.example');
  assert.equal(h.el('watch-rate').value,'1');
  h.event({channel,event:'time',videoId:'BaW_jenozKc',time:3.5});assert.equal(h.el('watch-current-en').textContent,'Two');
  h.event({channel,event:'rate-error',videoId:'BaW_jenozKc',errorCode:'RATE_UNSUPPORTED'});
  assert.match(h.el('watch-rate-status').textContent,/不支持/);assert.equal(h.el('watch-play-video').disabled,false);
});

test('a new video starts at 1x while same-video page changes keep an explicit chosen rate',()=>{
  const h=harness();h.api.setVideo(h.study.url);
  const firstChannel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel:firstChannel,event:'ready',videoId:'BaW_jenozKc'});
  h.event({channel:firstChannel,event:'playback',videoId:'BaW_jenozKc',rate:2,rates:[.75,1,1.25,1.5,2]});
  h.api.setPage('watch');h.api.setPage('study');h.api.setVideo(h.study.url);
  assert.equal(h.el('watch-rate').value,'2');
  h.el('url').value='https://youtu.be/na0scpoRBO0';h.el('url').input();
  assert.equal(h.el('watch-rate').value,'1');assert.equal(h.el('watch-rate').disabled,true);
  h.event({channel:firstChannel,event:'playback',videoId:'BaW_jenozKc',rate:2,rates:[1,2]});
  assert.equal(h.el('watch-rate').value,'1','old video events cannot restore its speed');
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'ready',videoId:'na0scpoRBO0'});
  h.event({channel,event:'playback',videoId:'na0scpoRBO0',rate:1,rates:[.75,1,1.25,1.5,2]});
  assert.equal(h.el('watch-rate').value,'1');assert.equal(h.el('watch-rate').disabled,false);
  assert.equal(h.messages.filter(x=>x.data.command==='play').length,0);
});

test('current captions and transcript share learning renderer without nesting word buttons in seek buttons',async()=>{
  const h=harness();let annotations=0,renders=0;
  h.window.LearningCore={annotateCues(cues){annotations++;return cues;}};
  h.window.LearningHighlights={renderPair(en,zh,cue){renders++;en.textContent=cue.english;zh.textContent=cue.chinese;const word=h.el('word-'+renders);word.tagName='BUTTON';en.append(word);}};
  await h.api.result(h.study);assert.equal(annotations,1);assert.ok(renders>=3);
  const roots=h.el('watch-transcript-list').children;
  function walk(node,inButton=false){assert.ok(!(inButton&&node.tagName==='BUTTON'),'no nested interactive buttons');for(const child of node.children||[])walk(child,inButton||node.tagName==='BUTTON');}
  roots.forEach(root=>walk(root));
});

test('profile changes reannotate raw full cues without seeking, playing or consuming render quota',async()=>{
  let profile={known:[]},changed;const passes=[];
  const h=harness({LearningLibrary:{getProfile:()=>profile,subscribe(fn){changed=fn;},progressFor:async()=>0},LearningCore:{annotateCues(cues,options){passes.push({cues,options});return cues.map(c=>({...c,learning:[]}));}}});
  h.study.cues=Array.from({length:120},(_,i)=>({start:i,end:i+1,english:'Otherworldly '+i,chinese:''}));
  await h.api.result(h.study);const before=h.messages.length;
  profile={known:['otherworldly']};assert.equal(typeof changed,'function');changed(profile);
  assert.equal(passes.at(-1).cues.length,120);assert.ok(passes.at(-1).cues.every(c=>!c.learning));
  assert.deepEqual(passes.at(-1).options.known,['otherworldly']);assert.equal(h.messages.length,before);
  h.el('watch-page-next').click();assert.equal(passes.length,2);
});
test('restoration waits for saved progress, ignores startup zero, stays paused and never changes 1x',async()=>{
  let resolve;const saved=new Promise(r=>resolve=r),writes=[];
  const h=harness({LearningLibrary:{getProfile:()=>({known:[]}),subscribe(){},progressFor:()=>saved,rememberProgress(...args){writes.push(args);return Promise.resolve();}}});
  const loading=h.api.result(h.study);await new Promise(r=>setImmediate(r));
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'ready',videoId:'BaW_jenozKc'});h.event({channel,event:'time',videoId:'BaW_jenozKc',time:0});
  assert.equal(writes.length,0);resolve(42);await loading;
  assert.equal(h.messages.at(-1).data.command,'seek');assert.equal(h.messages.at(-1).data.seconds,42);
  assert.equal(h.messages.some(x=>x.data.command==='play'||x.data.command==='rate'),false);
  h.event({channel,event:'time',videoId:'BaW_jenozKc',time:0});assert.equal(writes.length,0);
  h.event({channel,event:'state',videoId:'BaW_jenozKc',state:1});h.event({channel,event:'time',videoId:'BaW_jenozKc',time:43});
  assert.equal(writes[0][1],43);
});
test('retained local-caption jobs resume their reading position without any video seek',async()=>{
  const h=harness({LearningLibrary:{getProfile:()=>({known:[]}),subscribe(){},progressFor:async()=>3.5}});
  await h.api.result({...h.study,url:null});
  assert.equal(h.el('watch-current-en').textContent,'Two');assert.equal(h.el('watch-clock').textContent,'00:03');
  assert.equal(h.messages.some(x=>x.data.command==='play'||x.data.command==='seek'),false);
});
test('an explicit user seek wins over an asynchronously arriving saved position',async()=>{
  let resolve;const saved=new Promise(r=>resolve=r);
  const h=harness({LearningLibrary:{getProfile:()=>({known:[]}),subscribe(){},progressFor:()=>saved}});
  const loading=h.api.result(h.study);await new Promise(r=>setImmediate(r));
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');h.event({channel,event:'ready',videoId:'BaW_jenozKc'});
  h.el('watch-transcript-list').children[0].children[0].children[0].click();resolve(42);await loading;
  assert.ok(h.messages.some(x=>x.data.command==='seek'&&x.data.seconds===0));
  assert.equal(h.messages.some(x=>x.data.command==='seek'&&x.data.seconds===42),false);
});

test('a newer same-video URL timestamp wins over delayed saved progress',async()=>{
  let resolveSaved;const saved=new Promise(resolve=>resolveSaved=resolve);
  const h=harness({LearningLibrary:{getProfile:()=>({known:[]}),subscribe(){},progressFor:()=>saved}});
  h.window.WatchSync.setVideo('https://www.youtube.com/watch?v=BaW_jenozKc');
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'ready',videoId:'BaW_jenozKc'});
  const loading=h.window.WatchSync.result({id:'a'.repeat(32),url:'https://www.youtube.com/watch?v=BaW_jenozKc',sentence_version:1});
  await new Promise(resolve=>setImmediate(resolve));
  h.window.WatchSync.setVideo('https://www.youtube.com/watch?v=BaW_jenozKc&t=80s');
  resolveSaved(42);await loading;
  assert.ok(h.messages.some(x=>x.data.command==='seek'&&x.data.seconds===80));
  assert.equal(h.messages.some(x=>x.data.command==='seek'&&x.data.seconds===42),false);
});

test('a newer paused native-player seek wins over delayed saved progress',async()=>{
  let resolveSaved;const saved=new Promise(resolve=>resolveSaved=resolve);
  const h=harness({LearningLibrary:{getProfile:()=>({known:[]}),subscribe(){},progressFor:()=>saved}});
  h.window.WatchSync.setVideo('https://www.youtube.com/watch?v=BaW_jenozKc');
  const channel=new URL(h.el('original-video-frame').src).searchParams.get('channel');
  h.event({channel,event:'ready',videoId:'BaW_jenozKc'});
  const loading=h.window.WatchSync.result({id:'a'.repeat(32),url:'https://www.youtube.com/watch?v=BaW_jenozKc',sentence_version:1});
  await new Promise(resolve=>setImmediate(resolve));
  h.event({channel,event:'state',videoId:'BaW_jenozKc',state:2});h.event({channel,event:'time',videoId:'BaW_jenozKc',time:80});
  resolveSaved(42);await loading;
  assert.equal(h.messages.some(x=>x.data.command==='seek'&&x.data.seconds===42),false);
});
