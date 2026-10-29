(function(){
  'use strict';
  const $=id=>document.getElementById(id),categories={idiom:'地道表达',vocab:'进阶词汇',finance:'财经 / 专业搭配'};
  const card=$('learning-card'),audio=$('learning-audio');
  let enabled=true,pairNumber=0,origin=null,active=[],openTimer=null,closeTimer=null,cardHovered=false,pinned=false,closing=false,pronunciation=null,audioEpoch=0,audioCleanup=null;
  let currentTerm=null,termEpoch=0;
  function termButtons(){
    const state=currentTerm?window.LearningLibrary?.termState?.(currentTerm.id):'neutral';
    for(const [id,value] of [['learning-save','learn'],['learning-known','known']]){
      const button=$(id);if(!button)continue;
      button.disabled=!currentTerm||!window.LearningLibrary;
      button.setAttribute('aria-pressed',String(state===value));
      button.textContent=value==='learn'?(state==='learn'?'已收藏 · 移出':'收藏'):(state==='known'?'已掌握 · 撤销':'已掌握');
    }
  }
  async function setTermState(state,event){
    event?.preventDefault?.();event?.stopPropagation?.();if(!currentTerm||!window.LearningLibrary)return;
    const selected=currentTerm,current=termEpoch,library=window.LearningLibrary;
    $('learning-save').disabled=true;$('learning-known').disabled=true;
    try{
      await library.setTerm({key:selected.id,term:selected.term,state:library.termState(selected.id)===state?'neutral':state,...selected.context});
      if(current===termEpoch)$('learning-term-status').textContent='已保存在本机学习库。';
    }catch(error){if(current===termEpoch)$('learning-term-status').textContent=error.message;}
    finally{if(current===termEpoch)termButtons();}
  }
  function clearTimers(){window.clearTimeout(openTimer);window.clearTimeout(closeTimer);openTimer=closeTimer=null;}
  function clearActive(){for(const token of active){token.classList.remove('learning-active');token.setAttribute('aria-expanded','false');}active=[];}
  function stopPronunciation(message=''){
    window.LearningDictionary?.stop?.();
    audioEpoch++;audioCleanup?.();audioCleanup=null;audio.pause();audio.removeAttribute('src');audio.load();
    $('learning-stop').hidden=true;$('learning-audio-status').textContent=message;
  }
  function close(restore=true){
    currentTerm=null;termEpoch++;if($('learning-term-status'))$('learning-term-status').textContent='';
    clearTimers();cardHovered=false;pinned=false;stopPronunciation();pronunciation=null;
    card.hidden=true;clearActive();const previous=origin;origin=null;closing=true;
    if(restore&&previous?.isConnected!==false)previous?.focus({preventScroll:true});closing=false;
  }
  function positionCard(){
    const rect=origin?.getBoundingClientRect?.(),box=card.getBoundingClientRect?.();
    if(!rect||!box)return;
    const width=document.documentElement?.clientWidth||window.innerWidth,height=document.documentElement?.clientHeight||window.innerHeight;
    if(!Number.isFinite(width)||!Number.isFinite(height))return;
    const left=Math.max(12,Math.min(rect.left,width-box.width-12));
    let top=rect.bottom+10;
    if(top+box.height>height-12)top=rect.top-box.height-10;
    top=Math.max(12,Math.min(top,height-box.height-12));
    card.style.left=left+'px';card.style.top=top+'px';card.style.right='auto';card.style.bottom='auto';
  }
  function open(token,item,pairId,mode='click'){
    if(!enabled)return;
    if(!card.hidden&&origin?.dataset.pair===pairId&&origin?.dataset.term===item.id){
      clearTimers();if(mode!=='hover')origin=token;
      if(mode==='click'){pinned=true;$('learning-close').focus({preventScroll:true});}return;
    }
    window.LearningDictionary?.close?.();currentTerm=item;termEpoch++;if($('learning-term-status'))$('learning-term-status').textContent='';termButtons();
    clearTimers();stopPronunciation();clearActive();origin=token;cardHovered=false;pinned=mode==='click';
    for(const candidate of document.querySelectorAll('.learning-token')){
      if(candidate.dataset.pair===pairId&&candidate.dataset.term===item.id){candidate.classList.add('learning-active');candidate.setAttribute('aria-expanded','true');active.push(candidate);}
    }
    $('learning-card').dataset.kind=item.kind;
    $('learning-category').textContent='学习重点 · IELTS 7';
    $('learning-term').textContent=item.english.text;
    const dictionary=window.LearningPronunciations;
    const reference=dictionary&&Object.hasOwn(dictionary,item.id)?dictionary[item.id]:null;
    pronunciation=reference&&reference.audio==='/pronunciations/'+item.id+'.wav'&&typeof reference.ipa==='string'&&typeof reference.canonical==='string'?reference:null;
    const canonical=pronunciation?.canonical||item.term;
    $('learning-canonical').textContent=canonical===item.english.text?'':'词典形式：'+canonical;
    $('learning-ipa').textContent=pronunciation?'美式参考音标 '+pronunciation.ipa:'暂无参考音标';
    $('learning-speak').disabled=!pronunciation;
    $('learning-meaning').textContent=item.meaning;
    $('learning-note').textContent=item.note||'';
    $('learning-warning').textContent=item.warning?'译文提醒：'+item.warning:'';
    $('learning-warning').hidden=!item.warning;
    $('learning-alignment').textContent=item.chinese.length?'英文与本句中文中可靠对应的部分使用同色；释义以上下文为准。':'本句中文未找到可靠的直接对应，只提供语境释义，不强行标注。';
    card.hidden=false;positionCard();if(mode==='click')$('learning-close').focus({preventScroll:true});
  }
  function scheduleClose(){
    window.clearTimeout(openTimer);openTimer=null;window.clearTimeout(closeTimer);
    closeTimer=window.setTimeout(()=>{
      closeTimer=null;
      if(!pinned&&!cardHovered&&!card.contains(document.activeElement)&&document.activeElement!==origin)close(false);
    },300);
  }
  async function speak(){
    if(!enabled||card.hidden||!pronunciation)return;
    const selected=pronunciation;stopPronunciation();const epoch=audioEpoch;pinned=true;
    window.WatchSync?.pause?.();window.OriginalShadowing?.pause?.();
    const playing=()=>{if(epoch===audioEpoch){$('learning-audio-status').textContent='正在播放本机示范发音…';$('learning-stop').hidden=false;}};
    const ended=()=>{if(epoch===audioEpoch)stopPronunciation('示范发音已播完。');};
    const failed=()=>{if(epoch===audioEpoch)stopPronunciation('未能播放示范发音，请再点一次或检查本机音量。');};
    audio.addEventListener('playing',playing);audio.addEventListener('ended',ended);audio.addEventListener('error',failed);
    audioCleanup=()=>{audio.removeEventListener('playing',playing);audio.removeEventListener('ended',ended);audio.removeEventListener('error',failed);};
    audio.src=selected.audio;audio.currentTime=0;$('learning-stop').hidden=false;$('learning-audio-status').textContent='正在加载本机示范发音…';
    try{await audio.play();}catch{failed();}
  }
  function span(value,text){return value&&Number.isInteger(value.start)&&Number.isInteger(value.end)&&value.start>=0&&value.end>value.start&&value.end<=text.length&&value.text===text.slice(value.start,value.end);}
  function overlaps(a,b){return a.start<b.end&&b.start<a.end;}
  function accepted(items,en,zh){
    const found=[],english=[],chinese=[];
    for(const item of Array.isArray(items)?items.slice(0,3):[]){
      if(!item||!Object.hasOwn(categories,item.kind)||!/^[-a-z0-9]{1,80}$/.test(item.id||'')||typeof item.term!=='string'||typeof item.meaning!=='string'||!item.meaning||!span(item.english,en)||english.some(x=>overlaps(x,item.english)))continue;
      const ranges=[];
      for(const candidate of Array.isArray(item.chinese)?item.chinese.slice(0,3):[]){
        if(span(candidate,zh)&&!chinese.some(x=>overlaps(x,candidate))&&!ranges.some(x=>overlaps(x,candidate)))ranges.push(candidate);
      }
      found.push({...item,note:typeof item.note==='string'?item.note:'',warning:typeof item.warning==='string'?item.warning:'',chinese:ranges});english.push(item.english);chinese.push(...ranges);
    }
    return found;
  }
  function renderText(node,text,pieces,pairId){
    let cursor=0;const nodes=[];
    for(const {range,item} of pieces.sort((a,b)=>a.range.start-b.range.start)){
      if(range.start>cursor)nodes.push(document.createTextNode(text.slice(cursor,range.start)));
      const token=document.createElement('button');token.type='button';token.className='learning-token learning-gold';
      token.dataset.kind=item.kind;token.dataset.term=item.id;token.dataset.pair=pairId;
      token.textContent=text.slice(range.start,range.end);token.disabled=!enabled;
      token.setAttribute('aria-label',token.textContent+'，学习重点：'+item.meaning+'，查看用法');
      token.setAttribute('aria-controls','learning-card');token.setAttribute('aria-haspopup','dialog');token.setAttribute('aria-expanded','false');
      token.addEventListener('pointerenter',event=>{
        if(!enabled||event?.pointerType==='touch')return;
        clearTimers();openTimer=window.setTimeout(()=>{openTimer=null;if(token.isConnected!==false)open(token,item,pairId,'hover');},180);
      });
      token.addEventListener('pointerleave',scheduleClose);
      token.addEventListener('focus',()=>{if(!closing)open(token,item,pairId,'focus');});
      token.addEventListener('blur',scheduleClose);
      token.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();open(token,item,pairId);});
      nodes.push(token);cursor=range.end;
    }
    if(cursor<text.length)nodes.push(document.createTextNode(text.slice(cursor)));
    node.replaceChildren(...nodes);
  }
  function renderPair(enNode,zhNode,cue){
    const english=typeof cue?.english==='string'?cue.english:'',chinese=typeof cue?.chinese==='string'?cue.chinese:'';
    const context={english,chinese,start:Number.isFinite(cue?.start)?cue.start:0,url:window.WatchSync?.context?.().url||''};
    const items=accepted(cue?.learning||window.LearningCore?.analyzePair(english,chinese)||[],english,chinese).map(item=>({...item,context})),pairId=String(++pairNumber);
    renderText(enNode,english,items.map(item=>({range:item.english,item})),pairId);
    renderText(zhNode,chinese,items.flatMap(item=>item.chinese.map(range=>({range,item}))),pairId);
    window.LearningDictionary?.bindEnglish?.(enNode,cue);
  }
  function setEnabled(value){
    enabled=Boolean(value);document.body.dataset.learning=enabled?'on':'off';$('learning-toggle').checked=enabled;
    for(const token of document.querySelectorAll('.learning-token'))token.disabled=!enabled;
    if(!enabled)close(false);
  }
  $('learning-toggle').addEventListener('change',()=>setEnabled($('learning-toggle').checked));
  $('learning-close').addEventListener('click',()=>close());
  card.addEventListener('pointerenter',()=>{cardHovered=true;window.clearTimeout(closeTimer);closeTimer=null;});
  card.addEventListener('pointerleave',()=>{cardHovered=false;scheduleClose();});
  card.addEventListener('focusin',()=>{window.clearTimeout(closeTimer);closeTimer=null;});
  card.addEventListener('focusout',scheduleClose);
  $('learning-speak').addEventListener('click',speak);
  $('learning-save')?.addEventListener('click',event=>setTermState('learn',event));
  $('learning-known')?.addEventListener('click',event=>setTermState('known',event));
  window.LearningLibrary?.subscribe?.(termButtons);
  $('learning-stop').addEventListener('click',()=>stopPronunciation('已停止示范发音。'));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!card.hidden){event.preventDefault();close(pinned||card.contains(document.activeElement)||document.activeElement===origin);}});
  window.addEventListener('resize',()=>{if(!card.hidden)positionCard();});
  window.addEventListener('scroll',event=>{
    if(card.hidden||card.contains(event.target))return;
    if(pinned||document.activeElement===origin||card.contains(document.activeElement))positionCard();else close(false);
  },{capture:true,passive:true});
  window.addEventListener('pagehide',()=>close(false));
  $('learning-card').hidden=true;setEnabled(true);
  window.LearningHighlights={renderPair,setEnabled,close,stopPronunciation};
})();
