'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const file=path.join(__dirname,'../web/learning-dictionary.js'),api=fs.existsSync(file)?require(file):{};
function harness(handler){
  assert.equal(typeof api.createDictionary,'function','explicit dictionary UI is exported');
  const h=require('./learning-ui-harness.js')(),calls=[];
  const client={api:async(url,options)=>{calls.push({url,options});return handler?handler(url,options):{word:'serendipity',phonetic:'/ˌsɛrənˈdɪpɪti/',definitions:[{part_of_speech:'noun',definition:'A happy discovery.',example:'An example.'}],source_url:'https://en.wiktionary.org/wiki/serendipity',license:{name:'CC BY-SA 3.0',url:'https://creativecommons.org/licenses/by-sa/3.0/'}};},termState:()=> 'neutral',setTerm:async()=>{},subscribe(){}};
  h.window.LearningLibrary=client;h.dictionary=api.createDictionary(h.window,h.document,client);h.calls=calls;
  h.en=h.node('p');h.en.textContent='A moment of serendipity.';h.dictionary.bindEnglish(h.en,{english:h.en.textContent,chinese:'意外之喜',start:12});
  h.select=(word='serendipity',inside=true)=>{const node=inside?h.en:h.node('p');h.window.getSelection=()=>({isCollapsed:false,rangeCount:1,toString:()=>word,getRangeAt:()=>({startContainer:node,endContainer:node,getBoundingClientRect:()=>({left:100,bottom:150,top:130})})});h.en.fire('pointerup');};
  return h;
}
test('arbitrary selected English word is private until an explicit disclosed lookup; only the word is posted',async()=>{
  const h=harness();h.select();assert.equal(h.calls.length,0);assert.equal(h.el('dictionary-selection').hidden,false);
  assert.match(h.el('dictionary-privacy').textContent,/dictionaryapi\.dev/);assert.match(h.el('dictionary-privacy').textContent,/不发送整句/);
  await h.el('dictionary-lookup').fire('click');assert.equal(h.calls[0].url,'/api/dictionary');
  assert.deepEqual(JSON.parse(h.calls[0].options.body),{word:'serendipity'});
  assert.match(h.el('dictionary-definitions').textContent,/happy discovery/);assert.match(h.el('dictionary-ipa').textContent,/dɪp/);
  assert.match(h.el('dictionary-license').textContent,/CC BY-SA/);assert.equal(h.el('dictionary-source').href,'https://en.wiktionary.org/wiki/serendipity');
});
test('sentences, Chinese, oversized and selections crossing subtitle boundaries never offer lookup',()=>{
  const h=harness();for(const word of ['two words','学习','x'.repeat(65),'<img>']){h.select(word);assert.equal(h.el('dictionary-selection').hidden,true);}
  h.select('serendipity',false);assert.equal(h.el('dictionary-selection').hidden,true);assert.equal(h.calls.length,0);
});
test('changing a selection or job ignores a stale dictionary response and unsafe source links',async()=>{
  let resolve;const h=harness(()=>new Promise(r=>resolve=r));h.select();const pending=h.el('dictionary-lookup').fire('click');
  h.dictionary.close();resolve({word:'serendipity',definitions:[],source_url:'javascript:alert(1)',license:'unknown'});await pending;
  assert.equal(h.el('dictionary-card').hidden,true);assert.equal(h.el('dictionary-source').href,undefined);
});
test('dictionary pronunciation uses only a local English voice on explicit click; never a remote fallback',async()=>{
  const h=harness(),spoken=[];h.window.speechSynthesis={getVoices:()=>[{lang:'en-US',localService:false}],speak:u=>spoken.push(u),cancel(){}};
  h.window.SpeechSynthesisUtterance=function(text){this.text=text;};h.select();await h.el('dictionary-lookup').fire('click');
  assert.equal(spoken.length,0);h.el('dictionary-speak').fire('click');assert.equal(spoken.length,0);assert.match(h.el('dictionary-voice-status').textContent,/没有可用的本机英文/);
  const local={lang:'en-GB',localService:true};h.window.speechSynthesis.getVoices=()=>[{lang:'zh-CN',localService:true},local];
  h.el('dictionary-speak').fire('click');assert.equal(spoken.length,1);assert.equal(spoken[0].voice,local);assert.equal(spoken[0].text,'serendipity');
  assert.match(h.el('dictionary-voice-status').textContent,/非视频原声/);h.dictionary.close();
});
test('selected text clicks do not propagate to subtitle seek actions and hover never requests',()=>{
  const h=harness();let stopped=0;h.select();h.en.fire('click',{stopPropagation(){stopped++;}});
  h.en.fire('pointerenter');assert.equal(stopped,1);assert.equal(h.calls.length,0);
});
test('keyboard and mobile users can explicitly submit an arbitrary word from the visible library input',async()=>{
  const h=harness();h.el('dictionary-input').value=' resilience ';
  assert.equal(typeof h.el('dictionary-form').listeners.submit?.[0],'function');
  assert.match(h.el('dictionary-input-privacy').textContent,/dictionaryapi\.dev/);
  await h.el('dictionary-form').fire('submit');assert.equal(h.calls.length,1);
  assert.deepEqual(JSON.parse(h.calls[0].options.body),{word:'resilience'});assert.equal(h.el('dictionary-word').textContent,'resilience');
});
test('manual dictionary input rejects phrases without any lookup or focus trap',async()=>{
  const h=harness();h.el('dictionary-input').value='whole sentence';
  assert.equal(typeof h.el('dictionary-form').listeners.submit?.[0],'function');
  await h.el('dictionary-form').fire('submit');assert.equal(h.calls.length,0);
  assert.match(h.el('dictionary-input-status').textContent,/单个英文/);
});
test('dictionary safely renders markup-looking definitions and rejects unsafe attribution URLs',async()=>{
  const h=harness(()=>({definitions:[{definition:'<img src=x onerror=bad()>',example:'<script>bad</script>'}],source_url:'javascript:bad()',license:{name:'<license>',url:'http://unsafe.invalid/'}}));
  h.select();await h.el('dictionary-lookup').fire('click');assert.match(h.el('dictionary-definitions').textContent,/<img/);
  assert.equal(h.el('dictionary-source').hidden,true);assert.equal(h.all.some(n=>n.tagName==='IMG'),false);
  assert.equal(h.all.some(n=>n.tagName==='A'&&n.href==='http://unsafe.invalid/'),false);
});
