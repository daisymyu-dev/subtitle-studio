'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function harness(previousJob, fetch, search='',watchSync=null) {
  const elements = new Map();
  const urlChanges=[];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      disabled:false, hidden:false, value:'auto', files:[], textContent:'', content:'session',
      firstElementChild:{textContent:''}, classList:{toggle(){}},
      attributes:{},addEventListener(name, fn){this[name] = fn;},
      setAttribute(key,value){this.attributes[key] = value;},
      getAttribute(key){return this.attributes[key] || '';},focus(){},
      replaceChildren(){},scrollIntoView(){},append(){},
    });
    return elements.get(id);
  }
  const navigation = [element('nav-signal'),element('nav-comparison')];
  navigation[0].attributes.href = '/?design=signal';
  navigation[1].attributes.href = '/designs';
  const context = {
    document:{getElementById:element,querySelector:element,querySelectorAll:(selector)=>selector === 'a[href]' ? navigation : [],createElement:()=>element('created-'+elements.size),createDocumentFragment:()=>element('fragment-'+elements.size)},
    sessionStorage:{getItem:()=>previousJob,setItem(){}},
    fetch,setTimeout,console,
  };
  if(search||watchSync){context.window={WatchSync:watchSync,location:{search,href:'http://127.0.0.1:8765/'+search},history:{replaceState(_a,_b,url){urlChanges.push(String(url));}}};context.URLSearchParams=URLSearchParams;context.URL=URL;}
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'), context);
  return {element,navigation,urlChanges,context};
}

test('restoring a previous task locks submission until its response arrives', async () => {
  let resolveFetch;
  const calls = [];
  const pending = new Promise(resolve => {resolveFetch = resolve;});
  const {element} = harness('a'.repeat(32),(url)=>{calls.push(url);return pending;});
  assert.equal(element('start').disabled, true);
  await element('task-form').submit({preventDefault(){}});
  assert.equal(calls.length, 1);
  resolveFetch({ok:true,json:async()=>({status:'error',stage:'error',message:'Old task'})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(element('start').disabled, false);
});

test('new bilingual study requires explicit translation opt-in before creating any job',async()=>{
  const calls=[],h=harness(null,async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url==='/api/study-jobs'?{id:'a'.repeat(32)}:{status:'error',stage:'error',message:'Fixture'}};});
  h.element('translation-consent').checked=false;h.element('url').value='https://youtu.be/BaW_jenozKc';
  await h.element('task-form').submit({preventDefault(){}});assert.equal(calls.length,0);assert.match(h.element('form-error').textContent,/Google/);
  h.element('translation-consent').checked=true;await h.element('task-form').submit({preventDefault(){}});assert.equal(calls[0].url,'/api/study-jobs');
});
test('new Word or retained-text translation requires opt-in but cached local Word does not',async()=>{
  const calls=[],id='a'.repeat(32),result={id,title:'Example',count:0,preview:[],files:{}};
  let cached=false;
  const h=harness(null,async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.endsWith('/word')?result:url==='/api/word-jobs'?{id}:{status:'error',stage:'error',message:'Fixture'}};},'',{canExport:()=>cached,resultId:()=>id,result(){},beginTask(){}});
  h.element('translation-consent').checked=false;h.element('url').value='https://youtu.be/BaW_jenozKc';
  await h.element('word-start').click();assert.equal(calls.length,0);
  cached=true;await h.element('word-start').click();assert.equal(calls[0].url,`/api/jobs/${id}/word`);
});
test('public UI discloses Beta scope, starter library, dictionary consent and the privacy page',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  assert.match(html,/PUBLIC BETA/);assert.match(html,/English → Chinese/);assert.match(html,/24 条/);assert.match(html,/非.*AI/);
  assert.match(html,/id="translation-consent"/);assert.match(html,/href="\/privacy.html"/);assert.match(html,/dictionary-privacy/);
});
test('source controls disclose optional ASR and the Windows Core limitation without disabling caption tools',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  assert.match(html,/本地听写需安装可选 ASR 依赖/);assert.match(html,/Windows Core 便携包不含听写/);
  assert.match(html,/字幕提取与补标点不受影响/);
});
test('routine local result paths are inside a closed disclosure, not exposed in screenshots by default',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  const disclosure=html.match(/<details\b[^>]*class="output-location"[^>]*>[\s\S]*?<\/details>/);
  assert.ok(disclosure,'local file location is a native disclosure');
  assert.match(disclosure[0],/<summary>本机文件位置<\/summary>/);assert.match(disclosure[0],/id="output-path"/);
  assert.doesNotMatch(disclosure[0].split('>')[0],/\bopen\b/);
});

test('a validated retained-job link restores the complete local result',async()=>{
  const calls=[],id='f'.repeat(32);
  harness(null,async url=>{calls.push(url);return {ok:true,json:async()=>({status:'error',stage:'error',message:'Fixture'})};},'?job='+id);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls[0],'/api/jobs/'+id);
});
test('starting another job updates the retained-job link instead of restoring the old one on reload',async()=>{
  const old='a'.repeat(32),next='b'.repeat(32);
  const h=harness(null,async url=>({ok:true,json:async()=>url==='/api/word-jobs'?{id:next}:{status:'error',stage:'error',message:'Fixture'}}),'?job='+old);
  await new Promise(resolve=>setImmediate(resolve));h.element('url').value='https://youtu.be/BaW_jenozKc';await h.element('word-start').click();
  assert.match(h.urlChanges.at(-1)||'',new RegExp('job='+next));
});

test('one-click bilingual Word creates an explicit job and prevents duplicate submits', async () => {
  const calls = [];
  let resolveSubmit;
  const pending = new Promise(resolve => {resolveSubmit=resolve;});
  const {element} = harness(null, (url, options) => {
    calls.push({url,options});
    return url === '/api/word-jobs' ? pending : Promise.resolve({ok:true,json:async()=>({status:'error',stage:'error',message:'Test stop'})});
  });
  element('url').value = 'https://youtu.be/BaW_jenozKc';
  assert.equal(typeof element('word-start').click,'function');
  const first = element('word-start').click();
  await element('word-start').click();
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,'/api/word-jobs');
  assert.equal(JSON.parse(calls[0].options.body).url,'https://youtu.be/BaW_jenozKc');
  assert.equal(element('word-start').disabled,true);
  resolveSubmit({ok:true,json:async()=>({id:'d'.repeat(32)})});
  await first;
  assert.equal(element('word-start').disabled,false);
});

test('design navigation waits until a submitted job ID is safely saved', async () => {
  let resolveSubmit, resolvePoll;
  const submit = new Promise(resolve=>{resolveSubmit=resolve;});
  const polling = new Promise(resolve=>{resolvePoll=resolve;});
  const {element,navigation} = harness(null,url=>['/api/jobs','/api/study-jobs'].includes(url) ? submit : polling);
  element('url').value = 'https://www.youtube.com/watch?v=na0scpoRBO0';
  const processing = element('task-form').submit({preventDefault(){}});
  let prevented = false;
  const click = {preventDefault(){prevented=true;}};
  if (navigation[0].click) navigation[0].click(click);
  assert.equal(prevented, true);
  assert.equal(navigation[0].getAttribute('aria-disabled'), 'true');
  resolveSubmit({ok:true,json:async()=>({id:'b'.repeat(32)})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(navigation[0].getAttribute('aria-disabled'), 'false');
  prevented = false;
  navigation[0].click(click);
  assert.equal(prevented, false);
  resolvePoll({ok:true,json:async()=>({status:'error',stage:'error',message:'Test complete'})});
  await processing;
});

test('YouTube generate action creates bilingual study without automatic Word saving',async()=>{
  const calls=[];
  const h=harness(null,async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.startsWith('/api/jobs/')?{status:'error',stage:'error',message:'Fixture'}:{id:'a'.repeat(32)}};});
  h.element('url').value='https://youtu.be/BaW_jenozKc';h.element('model').value='base';await h.element('task-form').submit({preventDefault(){}});
  assert.equal(calls[0].url,'/api/study-jobs');assert.deepEqual(JSON.parse(calls[0].options.body),{url:'https://youtu.be/BaW_jenozKc',model:'base'});
});
test('Word export reuses a completed bilingual job without extracting or polling again',async()=>{
  const id='a'.repeat(32),calls=[];
  const result={id,title:'Example',source:'platform_auto',count:1,preview:[],files:{docx:'Example.docx'},output_dir:'results',desktop_path:'Desktop/Example.docx'};
  const h=harness(null,async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.endsWith('/word')?result:url==='/api/word-jobs'?{id}:{status:'error',stage:'error',message:'Unexpected extraction'}};},'',{canExport:()=>true,resultId:()=>id,result(){}});
  h.element('url').value='https://youtu.be/BaW_jenozKc';await h.element('word-start').click();
  assert.equal(calls.length,1);assert.equal(calls[0].url,`/api/jobs/${id}/word`);assert.equal(h.element('desktop-result').hidden,false);
});

test('source switch restores a completed YouTube result for cached Word export',async()=>{
  const calls=[],id='e'.repeat(32),result={id,url:'https://youtu.be/BaW_jenozKc',title:'Cached',source:'platform_auto',count:1,preview:[],files:{},bilingual_count:1};
  let cached=false;
  const watch={result(){cached=true;},setVideo(url){if(!url)cached=false;},canExport:()=>cached,resultId:()=>id};
  const h=harness(null,async(url)=>{calls.push(url);return {ok:true,json:async()=>result};},'',watch);
  h.element('url').value=result.url;h.context.resultView(result);
  h.element('tab-file').click();h.element('tab-youtube').click();await h.element('word-start').click();
  assert.deepEqual(calls,[`/api/jobs/${id}/word`]);assert.equal(h.element('result-title').textContent,'Cached');
});

test('a rejected video identity cannot populate any result UI or original audio',()=>{
  let audioCalls=0;
  const h=harness(null,async()=>{throw Error('no request');},'',{accepts:()=>false,result(){throw Error('rejected result must not attach');}});
  h.context.window.OriginalShadowing={showResult(){audioCalls++;}};
  h.context.resultView({id:'a'.repeat(32),url:'https://youtu.be/BaW_jenozKc',title:'Wrong video',source:'platform_auto',count:1,preview:[]});
  assert.equal(audioCalls,0);assert.notEqual(h.element('result-title').textContent,'Wrong video');
});

test('legacy sentence upgrade translates retained text instead of extracting the URL again',async()=>{
  const id='d'.repeat(32),calls=[];
  const result={id,url:'https://youtu.be/BaW_jenozKc',title:'Sentence study',source:'platform_auto',count:2,preview:[],files:{},sentence_version:1};
  const watch={result(){},pause(){},accepts:()=>true,resultId:()=>id,isSentence:()=>false};
  const h=harness(null,async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({id,status:'done',result})};},'',watch);
  h.element('url').value=result.url;await h.element('watch-sentences').click();
  assert.equal(calls.length,1);assert.equal(calls[0].url,`/api/jobs/${id}/sentences`);assert.equal(calls[0].options.method,'POST');
  assert.equal(h.element('result-title').textContent,'Sentence study');
});
