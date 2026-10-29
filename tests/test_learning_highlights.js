'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function harness(){
  const all=[],ids=new Map(),events={},windowEvents={},timers=new Map();let document,serial=0;
  class Node{
    constructor(tag='span',id=''){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.dataset={};this.attributes={};this.style={};this.hidden=false;this.disabled=false;this.checked=true;this.listeners={};this._text='';this.isConnected=true;this.className='';this.paused=true;this.currentTime=0;this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),toggle:(x,v)=>v?this.classes.add(x):this.classes.delete(x)};all.push(this);}
    set textContent(text){this._text=String(text);this.children=[];}get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
    set innerHTML(_){throw Error('unsafe HTML rendering');}
    append(...nodes){this.children.push(...nodes);nodes.forEach(x=>x.parentElement=this);}
    replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
    setAttribute(k,v){this.attributes[k]=String(v);}getAttribute(k){return this.attributes[k];}
    addEventListener(k,f){this.listeners[k]=f;}
    removeEventListener(k,f){if(this.listeners[k]===f)delete this.listeners[k];}
    removeAttribute(k){delete this.attributes[k];delete this[k];}
    contains(node){return node===this||this.children.some(child=>child.contains?.(node));}
    focus(){document.activeElement=this;this.listeners.focus?.();}
    pause(){this.paused=true;}load(){}play(){this.paused=false;this.playCount=(this.playCount||0)+1;return Promise.resolve();}
  }
  document={body:new Node('body'),activeElement:null,getElementById:id=>{if(!ids.has(id))ids.set(id,new Node('div',id));return ids.get(id);},createElement:tag=>new Node(tag),createTextNode:text=>({textContent:String(text)}),addEventListener:(k,f)=>events[k]=f,querySelectorAll:()=>all.filter(x=>x.className.includes('learning-token'))};
  const window={LearningPronunciations:{otherworldly:{ipa:'/ˌʌð.ɚˈwɝːld.li/',canonical:'otherworldly',spoken:'otherworldly',audio:'/pronunciations/otherworldly.wav'}},WatchSync:{pause(){window.videoPauses=(window.videoPauses||0)+1;}},OriginalShadowing:{pause(){window.shadowPauses=(window.shadowPauses||0)+1;}},setTimeout(fn,ms){timers.set(++serial,{fn,ms});return serial;},clearTimeout(id){timers.delete(id);},addEventListener(k,fn){windowEvents[k]=fn;}};
  const file=path.join(__dirname,'../web/learning-highlights.js');
  if(fs.existsSync(file))vm.runInNewContext(fs.readFileSync(file,'utf8'),{window,document,console});
  const cue={english:'This is otherworldly.',chinese:'这超凡脱俗。',learning:[{id:'otherworldly',kind:'vocab',term:'otherworldly',meaning:'超凡的；异乎寻常的',note:'这里形容突破惊人。',warning:'',english:{start:8,end:20,text:'otherworldly'},chinese:[{start:1,end:5,text:'超凡脱俗'}]}]};
  return {api:window.LearningHighlights,window,document,events,windowEvents,cue,all,node:()=>new Node(),get:id=>document.getElementById(id),tokens:()=>all.filter(x=>x.className.includes('learning-token')),run(ms){for(const [id,t] of [...timers])if(t.ms===ms){timers.delete(id);t.fn();}}};
}

test('gold-card known/saved actions persist the canonical key and exact local sentence without row actions',async()=>{
  const h=harness(),calls=[];let state='neutral';
  h.window.LearningLibrary={termState:()=>state,async setTerm(value){calls.push(value);state=value.state;}};
  h.api.renderPair(h.node(),h.node(),{...h.cue,start:12});h.tokens()[0].listeners.click({preventDefault(){},stopPropagation(){}});
  assert.equal(typeof h.get('learning-save').listeners.click,'function');
  await h.get('learning-save').listeners.click({preventDefault(){},stopPropagation(){}});
  assert.equal(calls[0].key,'otherworldly');assert.equal(calls[0].state,'learn');assert.equal(calls[0].english,h.cue.english);assert.equal(calls[0].start,12);
  assert.equal(h.get('learning-save').getAttribute('aria-pressed'),'true');
  await h.get('learning-known').listeners.click({preventDefault(){},stopPropagation(){}});assert.equal(calls[1].state,'known');
});
test('paired highlights preserve every original character without parsing HTML',()=>{
  const h=harness();assert.ok(h.api,'safe shared learning renderer exists');
  const en=h.node(),zh=h.node();h.api.renderPair(en,zh,h.cue);
  assert.equal(en.textContent,h.cue.english);assert.equal(zh.textContent,h.cue.chinese);
  assert.equal(h.tokens().length,2);assert.equal(h.tokens()[0].dataset.kind,h.tokens()[1].dataset.kind);
  h.api.renderPair(en,zh,{english:'<img src=x onerror=bad()>',chinese:'原文',learning:[]});
  assert.equal(en.textContent,'<img src=x onerror=bad()>');
});
test('term click stops row actions and opens bilingual usage; Escape restores focus',()=>{
  const h=harness();assert.ok(h.api);h.api.renderPair(h.node(),h.node(),h.cue);
  const token=h.tokens()[0];let prevented=0,stopped=0;
  token.listeners.click({preventDefault(){prevented++;},stopPropagation(){stopped++;}});
  assert.equal(prevented,1);assert.equal(stopped,1);assert.equal(h.get('learning-card').hidden,false);
  assert.equal(h.get('learning-term').textContent,'otherworldly');assert.match(h.get('learning-meaning').textContent,/超凡/);
  h.events.keydown({key:'Escape',preventDefault(){}});
  assert.equal(h.get('learning-card').hidden,true);assert.equal(h.document.activeElement,token);
});
test('unmatched Chinese is not marked and translation warnings are explicit',()=>{
  const h=harness();assert.ok(h.api);const item=h.cue.learning[0];item.chinese=[];item.warning='此处不是字面的另一个世界。';
  const en=h.node(),zh=h.node();h.api.renderPair(en,zh,h.cue);assert.equal(h.tokens().length,1);
  h.tokens()[0].listeners.click({preventDefault(){},stopPropagation(){}});
  assert.match(h.get('learning-warning').textContent,/不是字面/);assert.match(h.get('learning-alignment').textContent,/未找到/);
});
test('highlight toggle disables only learning interaction and leaves text intact',()=>{
  const h=harness();assert.ok(h.api);const en=h.node(),zh=h.node();h.api.renderPair(en,zh,h.cue);
  h.api.setEnabled(false);assert.ok(h.tokens().every(x=>x.disabled));assert.equal(h.get('learning-card').hidden,true);
  assert.equal(en.textContent,h.cue.english);h.api.setEnabled(true);assert.ok(h.tokens().every(x=>!x.disabled));
});
test('malformed spans cannot color unrelated original text',()=>{
  const h=harness();assert.ok(h.api);h.cue.learning[0].english.start=0;
  const en=h.node(),zh=h.node();h.api.renderPair(en,zh,h.cue);assert.equal(h.tokens().length,0);assert.equal(en.textContent,h.cue.english);
});

test('all learning categories use one gold treatment and one simple card heading',()=>{
  const h=harness();
  for(const kind of ['idiom','vocab','finance']){
    const cue={...h.cue,learning:[{...h.cue.learning[0],kind}]};
    h.api.renderPair(h.node(),h.node(),cue);
    const token=h.tokens().at(-2);
    assert.ok(token.className.includes('learning-gold'));
    assert.ok(!/learning-(?:idiom|vocab|finance)(?:\s|$)/.test(token.className));
    token.listeners.click({preventDefault(){},stopPropagation(){}});
    assert.equal(h.get('learning-category').textContent,'学习重点 · IELTS 7');
  }
});

test('hover opens meaning and IPA without focus stealing, audio, or video actions',()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const token=h.tokens()[0];
  const focus=h.node();h.document.activeElement=focus;
  assert.equal(typeof token.listeners.pointerenter,'function');token.listeners.pointerenter({pointerType:'mouse'});
  assert.equal(h.get('learning-card').hidden,true);h.run(180);
  assert.equal(h.get('learning-card').hidden,false);assert.match(h.get('learning-ipa').textContent,/wɝ/);
  assert.equal(h.document.activeElement,focus);assert.equal(h.get('learning-audio').playCount||0,0);
  assert.equal(h.window.videoPauses||0,0);assert.equal(h.window.shadowPauses||0,0);
  assert.equal(token.getAttribute('aria-expanded'),'true');
});

test('hover grace lets the mouse enter the card and cancels transient hovers',()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const token=h.tokens()[0];
  token.listeners.pointerenter({pointerType:'mouse'});token.listeners.pointerleave();h.run(180);
  assert.equal(h.get('learning-card').hidden,true);
  token.listeners.pointerenter({pointerType:'mouse'});h.run(180);token.listeners.pointerleave();
  h.get('learning-card').listeners.pointerenter();h.run(300);assert.equal(h.get('learning-card').hidden,false);
  h.get('learning-card').listeners.pointerleave();h.run(300);assert.equal(h.get('learning-card').hidden,true);
});

test('keyboard focus opens without stealing focus and Escape does not reopen it',()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const token=h.tokens()[0];token.focus();
  assert.equal(h.document.activeElement,token);assert.equal(h.get('learning-card').hidden,false);
  h.events.keydown({key:'Escape',preventDefault(){}});h.run(180);h.run(300);
  assert.equal(h.get('learning-card').hidden,true);assert.equal(h.document.activeElement,token);
});

test('click pins hover card and explicit local pronunciation pauses other audio only on demand',async()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const token=h.tokens()[1];
  token.listeners.click({preventDefault(){},stopPropagation(){}});token.listeners.pointerleave();h.run(300);
  assert.equal(h.get('learning-card').hidden,false);assert.equal(h.get('learning-speak').disabled,false);
  await h.get('learning-speak').listeners.click();
  assert.equal(h.get('learning-audio').src,'/pronunciations/otherworldly.wav');
  assert.equal(h.get('learning-audio').playCount,1);assert.equal(h.window.videoPauses,1);assert.equal(h.window.shadowPauses,1);
  h.get('learning-audio').listeners.playing();assert.match(h.get('learning-audio-status').textContent,/正在播放/);
  h.get('learning-audio').listeners.ended();assert.match(h.get('learning-audio-status').textContent,/播完/);
  assert.equal(h.get('learning-stop').hidden,true);
});

test('missing, rejected or failed pronunciation is honest and close cancels stale callbacks',async()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const token=h.tokens()[0];
  token.listeners.click({preventDefault(){},stopPropagation(){}});
  h.get('learning-audio').play=()=>Promise.reject(Error('blocked'));await h.get('learning-speak').listeners.click();
  assert.match(h.get('learning-audio-status').textContent,/未能播放/);
  let resolve;h.get('learning-audio').play=()=>new Promise(r=>resolve=r);
  const pending=h.get('learning-speak').listeners.click();const oldPlaying=h.get('learning-audio').listeners.playing;
  h.api.close(false);resolve();await pending;oldPlaying();
  assert.equal(h.get('learning-card').hidden,true);assert.equal(h.get('learning-audio').paused,true);
  assert.doesNotMatch(h.get('learning-audio-status').textContent,/正在播放/);
  delete h.window.LearningPronunciations.otherworldly;
  token.listeners.click({preventDefault(){},stopPropagation(){}});
  assert.equal(h.get('learning-speak').disabled,true);assert.match(h.get('learning-ipa').textContent,/暂无/);
});

test('same-word hover in either language preserves pronunciation and pinned card',async()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const [en,zh]=h.tokens();
  en.listeners.click({preventDefault(){},stopPropagation(){}});await h.get('learning-speak').listeners.click();
  for(const token of [en,zh]){token.listeners.pointerenter({pointerType:'mouse'});h.run(180);token.listeners.pointerleave();h.run(300);}
  assert.equal(h.get('learning-audio').paused,false);assert.equal(h.get('learning-audio').src,'/pronunciations/otherworldly.wav');
  assert.equal(h.get('learning-card').hidden,false);assert.equal(h.window.videoPauses,1);
});

test('focus-induced scrolling preserves the keyboard glossary while unrelated hover scrolling closes it',()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const token=h.tokens()[0];token.focus();
  h.windowEvents.scroll({target:h.node()});assert.equal(h.get('learning-card').hidden,false);
  h.api.close(false);h.document.activeElement=h.node();token.listeners.pointerenter({pointerType:'mouse'});h.run(180);
  h.windowEvents.scroll({target:h.node()});assert.equal(h.get('learning-card').hidden,true);
});

test('focus can move between paired languages without dismissing the card on scroll',()=>{
  const h=harness();h.api.renderPair(h.node(),h.node(),h.cue);const [en,zh]=h.tokens();en.focus();zh.focus();
  h.windowEvents.scroll({target:h.node()});assert.equal(h.get('learning-card').hidden,false);
  h.events.keydown({key:'Escape',preventDefault(){}});assert.equal(h.document.activeElement,zh);
  assert.equal(h.get('learning-card').hidden,true);
});
