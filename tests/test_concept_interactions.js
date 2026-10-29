'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const core=require('../web/concept-core.js');

function harness(){
  const nodes=new Map();
  function node(id){
    if(!nodes.has(id))nodes.set(id,{dataset:{},attrs:{},handlers:{},textContent:'',value:'1',hidden:false,
      classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v;},
      addEventListener(k,fn){this.handlers[k]=fn;},click(){return this.handlers.click?.();}});
    return nodes.get(id);
  }
  const audio=node('lesson-audio');
  Object.assign(audio,{paused:true,ended:false,currentTime:0,duration:5,
    pause(){this.paused=true;this.handlers.pause?.();},
    play(){this.paused=false;this.ended=false;this.handlers.play?.();return Promise.resolve();}});
  const terms=['compelling','bandwagon','priced','perspective'].map(id=>{const n=node('term-'+id);n.dataset.term=id;return n;});
  const rows=Array.from({length:4},(_,i)=>{const n=node('row-'+i);n.dataset.lineIndex=String(i);return n;});
  const selectors={'[data-view]':[],'[data-term]':terms,'[data-line-index]':rows,'[data-select-line]':[],'.chinese':[]};
  const context={window:{StudyPreview:core},document:{getElementById:node,querySelectorAll:s=>selectors[s]||[],body:{dataset:{study:'folio'},classList:{toggle(){}}}},localStorage:{getItem(){return null;},setItem(){}},console};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/concept.js'),'utf8'),context);
  return {node,audio,terms};
}

test('term selection exposes pressed state and announces its meaning',()=>{
  const {node,terms}=harness();
  terms[0].click();
  assert.equal(terms[0].attrs['aria-pressed'],'true');
  assert.equal(terms[2].attrs['aria-pressed'],'false');
  assert.match(node('vocab-feedback').textContent,/compelling/);
});

test('pause updates audio status instead of continuing to report playing',async()=>{
  const {node,audio}=harness();
  await node('play-pause').click();
  audio.currentTime=1;
  node('play-pause').click();
  assert.match(node('audio-message').textContent,/已暂停/);
  assert.equal(audio.paused,true);
});
