'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const file=path.join(__dirname,'../web/learning-library.js');
const moduleApi=fs.existsSync(file)?require(file):{};
const id='a'.repeat(32),profile={known:[],saved:[],progress:{[id]:42}};
function harness(handler=()=>profile){
  assert.equal(typeof moduleApi.createLibrary,'function','learning library client is exported');
  const calls=[],navigations=[];let now=10000;
  const client=moduleApi.createLibrary({token:'test-token',now:()=>now,href:'http://127.0.0.1:8765/?design=studio',navigate:url=>navigations.push(url),fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>handler(url,options)};}});
  return {client,calls,navigations,advance:ms=>now+=ms};
}
test('profile loads asynchronously and term actions use the exact authenticated API contract',async()=>{
  const h=harness((url,options)=>url.endsWith('/term')?{known:['otherworldly'],saved:[],progress:{[id]:42}}:profile);
  await h.client.ready;assert.equal(h.client.getProfile().progress[id],42);
  await h.client.setTerm({key:'otherworldly',term:'otherworldly',state:'known',english:'Otherworldly.',chinese:'非凡',url:'https://youtu.be/BaW_jenozKc',start:5});
  assert.equal(h.client.termState('otherworldly'),'known');
  assert.equal(h.calls[0].url,'/api/learning');assert.equal(h.calls[1].url,'/api/learning/term');
  assert.equal(h.calls[1].options.headers['X-App-Token'],'test-token');
  assert.equal(JSON.parse(h.calls[1].options.body).state,'known');
  assert.equal(h.calls[1].options.headers['Content-Type'],'application/json');
  assert.throws(()=>h.client.api('https://evil.invalid/'),/invalid|无效/i);
});
test('initial zero cannot overwrite saved progress; writes are throttled at least five seconds per retained job',async()=>{
  const h=harness(url=>url.endsWith('/progress')?{ok:true}:profile);await h.client.ready;
  await h.client.rememberProgress(id,0);assert.equal(h.calls.length,1);
  await h.client.rememberProgress(id,43);await h.client.rememberProgress(id,44);
  h.advance(4999);await h.client.rememberProgress(id,45);assert.equal(h.calls.length,2);
  h.advance(1);await h.client.rememberProgress(id,46);assert.equal(h.calls.length,3);
  assert.deepEqual(JSON.parse(h.calls[2].options.body),{job_id:id,time:46});
  await h.client.rememberProgress('../escape',8);await h.client.rememberProgress(id,Infinity);
  assert.equal(h.calls.length,3);
});
test('resume validates a retained job and builds a local navigation without trusting its URL',async()=>{
  const h=harness();await h.client.ready;
  assert.equal(h.client.resume('../bad'),false);assert.equal(h.client.resume('https://evil.invalid/'),false);
  assert.equal(h.navigations.length,0);assert.equal(h.client.resume(id),true);
  const url=new URL(h.navigations[0],'http://127.0.0.1:8765');
  assert.equal(url.origin,'http://127.0.0.1:8765');assert.equal(url.searchParams.get('job'),id);assert.equal(url.searchParams.get('page'),'study');
});
test('profile snapshots cannot mutate the active profile and progress survives an older term response',async()=>{
  const h=harness(url=>url.endsWith('/progress')?{ok:true}:profile);await h.client.ready;
  h.client.getProfile().known.push('otherworldly');assert.equal(h.client.termState('otherworldly'),'neutral');
  await h.client.rememberProgress(id,55);await h.client.setTerm({key:'astounding',term:'astounding',state:'learn'});
  assert.equal(h.client.getProfile().progress[id],55);
});
test('concurrent term actions serialize so a late response cannot revert a newer choice',async()=>{
  let pendingResolve,posts=0;
  const h=harness((url,options)=>{
    if(!url.endsWith('/term'))return profile;
    posts++;const state=JSON.parse(options.body).state;
    if(posts===1)return new Promise(resolve=>pendingResolve=resolve);
    return {known:[],saved:[{key:'otherworldly',term:'otherworldly'}],progress:{}};
  });await h.client.ready;
  const first=h.client.setTerm({key:'otherworldly',term:'otherworldly',state:'known'});
  const second=h.client.setTerm({key:'otherworldly',term:'otherworldly',state:'learn'});
  await new Promise(resolve=>setImmediate(resolve));assert.equal(posts,1);
  pendingResolve({known:['otherworldly'],saved:[],progress:{}});await first;await second;
  assert.equal(h.client.termState('otherworldly'),'learn');
});
test('library drawer renders untrusted titles as text and rejects stale closed requests',async()=>{
  assert.equal(typeof moduleApi.mount,'function','library drawer mount is exported');
  const ui=require('./learning-ui-harness.js')();let resolve;
  const pending=new Promise(r=>resolve=r),h=harness(url=>url==='/api/library'?pending:profile);
  const panel=moduleApi.mount(ui.window,ui.document,h.client);
  const first=panel.open();panel.close();resolve({items:[{id,title:'<img onerror=bad()>',position:42,cue_count:12,url:'javascript:bad()'}]});await first;
  assert.equal(ui.el('library-panel').hidden,true);assert.equal(ui.el('library-recent').textContent,'');
  await panel.open();assert.match(ui.el('library-recent').textContent,/<img onerror=bad\(\)>/);
  assert.ok(ui.all.some(n=>n.tagName==='BUTTON'&&/继续/.test(n.textContent)));
  assert.equal(ui.all.filter(n=>n.tagName==='A'&&n.href==='javascript:bad()').length,0);
});
test('saved expressions can be returned to learning or neutral from the library',async()=>{
  assert.equal(typeof moduleApi.mount,'function');
  const ui=require('./learning-ui-harness.js')(),saved={known:['astounding'],saved:[{key:'otherworldly',term:'<script>word</script>',english:'Exact original.',chinese:'示例'}],progress:{}};
  const h=harness(url=>url==='/api/library'?{items:[]}:saved);await h.client.ready;moduleApi.mount(ui.window,ui.document,h.client);
  assert.match(ui.el('library-saved').textContent,/<script>word<\/script>/);
  const remove=ui.all.find(n=>n.tagName==='BUTTON'&&n.textContent==='移出收藏');assert.ok(remove);await remove.fire('click');
  assert.equal(JSON.parse(h.calls.at(-1).options.body).state,'neutral');
  assert.match(ui.el('library-known').textContent,/astounding/);
});
test('resume respects a pending submission navigation lock',async()=>{
  const navigations=[];let canNavigate=false;
  const client=moduleApi.createLibrary({token:'token',fetch:async()=>({ok:true,json:async()=>profile}),href:'http://127.0.0.1:8765/',navigate:url=>navigations.push(url),canNavigate:()=>canNavigate});
  await client.ready;assert.equal(client.resume(id),false);assert.equal(navigations.length,0);
  canNavigate=true;assert.equal(client.resume(id),true);
});

test('a failed initial profile read can recover when reopening the library',async()=>{
  let reads=0;
  const h=harness(url=>{
    if(url==='/api/learning'&&++reads===1)throw Error('temporary startup failure');
    return profile;
  });
  await assert.rejects(h.client.ready,/startup/);
  await h.client.ready;
  assert.equal(reads,2);
  await h.client.setTerm({key:'bifurcated',term:'bifurcated',state:'known'});
  assert.equal(h.calls.at(-1).url,'/api/learning/term');
});

test('a later save retries a failed startup profile without a reload',async()=>{
  let reads=0;
  const h=harness(url=>{
    if(url==='/api/learning'&&++reads===1)throw Error('temporary startup failure');
    return profile;
  });
  await assert.rejects(h.client.ready,/startup/);
  await h.client.setTerm({key:'bifurcated',term:'bifurcated',state:'known'});
  assert.equal(reads,2);
  assert.equal(h.calls.at(-1).url,'/api/learning/term');
});

test('slow progress writes serialize per job so old requests cannot replace a newer position',async()=>{
  let finishFirst;const positions=[];
  const h=harness((url,options)=>{
    if(!url.endsWith('/progress'))return profile;
    positions.push(JSON.parse(options.body).time);
    if(positions.length===1)return new Promise(resolve=>finishFirst=resolve);
    return {ok:true};
  });
  await h.client.ready;
  const first=h.client.rememberProgress(id,50);
  await new Promise(resolve=>setImmediate(resolve));
  h.advance(6000);
  const second=h.client.rememberProgress(id,70);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(positions,[50],'do not issue the later HTTP write before the earlier one completes');
  finishFirst({ok:true});await first;await second;
  assert.deepEqual(positions,[50,70]);
  assert.equal(await h.client.progressFor(id),70);
});
