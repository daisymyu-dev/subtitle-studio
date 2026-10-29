(function(root,factory){
  const exported=factory();
  if(typeof module==='object'&&module.exports)module.exports=exported;
  else root.LearningDictionary=exported.createDictionary(root,document,root.LearningLibrary);
})(typeof window!=='undefined'?window:this,function(){
  'use strict';
  function createDictionary(root,document,library){
    const $=id=>document.getElementById(id),bindings=new WeakMap();
    let selection=null,entry=null,epoch=0,utterance=null,voiceEpoch=0;
    const wordValid=word=>typeof word==='string'&&/^[A-Za-z][A-Za-z'-]{0,63}$/.test(word);
    const safeLink=value=>{try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password?url.href:'';}catch{return '';}};
    const text=(tag,value)=>{const node=document.createElement(tag);node.textContent=typeof value==='string'?value:'';return node;};
    function stop(){voiceEpoch++;if(utterance)root.speechSynthesis?.cancel();utterance=null;$('dictionary-stop').hidden=true;}
    function close(){epoch++;stop();selection=null;entry=null;$('dictionary-selection').hidden=true;$('dictionary-card').hidden=true;$('dictionary-voice-status').textContent='';}
    function place(node,rect){
      if(!rect)return;
      const width=node.getBoundingClientRect().width||320,height=node.getBoundingClientRect().height||150;
      node.style.left=Math.max(12,Math.min(rect.left,root.innerWidth-width-12))+'px';
      node.style.top=Math.max(12,Math.min(rect.bottom+8,root.innerHeight-height-12))+'px';
    }
    function selectedIn(node){
      const selected=root.getSelection?.();if(!selected||selected.isCollapsed||selected.rangeCount!==1)return null;
      const word=selected.toString().trim(),range=selected.getRangeAt(0);
      if(!wordValid(word)||!node.contains(range.startContainer)||!node.contains(range.endContainer))return null;
      return {word:word.toLowerCase(),range};
    }
    function offer(node,event){
      const selected=selectedIn(node);
      if(!selected){close();return;}
      event?.stopPropagation?.();if(event?.type==='contextmenu')event.preventDefault();
      close();selection={word:selected.word,node,cue:bindings.get(node),rect:selected.range.getBoundingClientRect()};
      $('dictionary-selection-word').textContent=selection.word;
      $('dictionary-privacy').textContent='点击「查词」即同意仅将此单词发送至 dictionaryapi.dev；不发送整句，不上传音视频。';
      $('dictionary-selection').hidden=false;place($('dictionary-selection'),selection.rect);
    }
    function bindEnglish(node,cue){
      if(!bindings.has(node)){
        node.addEventListener('pointerup',event=>offer(node,event));
        node.addEventListener('contextmenu',event=>offer(node,event));
        node.addEventListener('keyup',event=>{if(event.key==='Shift'||event.key.startsWith('Arrow'))offer(node,event);});
        node.addEventListener('click',event=>{if(selectedIn(node))event.stopPropagation();});
      }
      bindings.set(node,cue);
    }
    function termButtons(){
      const key=entry?.word,state=key?library.termState(key):'neutral',valid=!!key&&/^[a-z-]{1,64}$/.test(key);
      $('dictionary-save').disabled=!valid;$('dictionary-known').disabled=!valid;
      $('dictionary-save').textContent=state==='learn'?'已收藏 · 移出':'收藏';$('dictionary-save').setAttribute('aria-pressed',String(state==='learn'));
      $('dictionary-known').textContent=state==='known'?'已掌握 · 撤销':'已掌握';$('dictionary-known').setAttribute('aria-pressed',String(state==='known'));
    }
    async function lookup(event){
      event?.preventDefault?.();event?.stopPropagation?.();
      if(!selection||selection.node.isConnected===false)return;
      const chosen=selection,current=++epoch;stop();root.LearningHighlights?.close?.(false);
      library.closePanel?.();
      entry=null;$('dictionary-selection').hidden=true;$('dictionary-card').hidden=false;
      $('dictionary-word').textContent=chosen.word;$('dictionary-status').textContent='正在查询英文词典…';$('dictionary-ipa').textContent='';
      $('dictionary-definitions').replaceChildren();$('dictionary-source').hidden=true;$('dictionary-license').replaceChildren();$('dictionary-voice-status').textContent='';
      $('dictionary-speak').disabled=true;termButtons();place($('dictionary-card'),chosen.rect);$('dictionary-close').focus();
      try{
        const body=await library.api('/api/dictionary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({word:chosen.word})});
        if(current!==epoch||chosen.node.isConnected===false)return;
        const definitions=(Array.isArray(body.definitions)?body.definitions:[]).filter(d=>typeof d?.definition==='string').slice(0,6);
        if(!definitions.length)throw Error('词典暂未收录此词，或没有可用释义。');
        entry={word:chosen.word,cue:chosen.cue};
        $('dictionary-ipa').textContent=typeof body.phonetic==='string'&&body.phonetic?body.phonetic:'词典未提供音标';
        $('dictionary-definitions').replaceChildren(...definitions.map(d=>{
          const li=document.createElement('li');li.append(text('small',d.part_of_speech),text('p',d.definition));
          if(d.example){const example=text('p',d.example);example.className='dictionary-example';li.append(example);}return li;
        }));
        const source=safeLink(body.source_url);$('dictionary-source').hidden=!source;if(source)$('dictionary-source').href=source;
        const license=body.license;
        $('dictionary-license').append(text('span','许可：'+(typeof license==='string'?license:license?.name||'来源未提供许可信息')));
        const licenseUrl=safeLink(license?.url);if(licenseUrl){const link=text('a','查看许可 ↗');link.href=licenseUrl;link.target='_blank';link.rel='noopener noreferrer';$('dictionary-license').append(link);}
        $('dictionary-status').textContent='英文词典释义 · 非本句语境翻译';$('dictionary-speak').disabled=false;termButtons();place($('dictionary-card'),chosen.rect);
      }catch(error){if(current===epoch)$('dictionary-status').textContent=error.message||'查词暂时不可用，请重试。';}
    }
    function speak(){
      if(!entry||$('dictionary-card').hidden)return;
      stop();const synth=root.speechSynthesis,voice=synth?.getVoices().find(v=>v.localService===true&&/^en(?:[-_]|$)/i.test(v.lang));
      if(!voice||!root.SpeechSynthesisUtterance){$('dictionary-voice-status').textContent='没有可用的本机英文语音；此浏览器暂不支持离线发音，不会改用云端语音。';return;}
      root.LearningHighlights?.stopPronunciation?.();root.WatchSync?.pause?.();root.OriginalShadowing?.pause?.();
      const current=voiceEpoch,u=new root.SpeechSynthesisUtterance(entry.word);utterance=u;u.voice=voice;u.lang=voice.lang;u.rate=1;
      $('dictionary-voice-status').textContent='本机英文合成示范 · 非视频原声，非词典录音。';$('dictionary-stop').hidden=false;
      u.onend=()=>{if(current===voiceEpoch){stop();$('dictionary-voice-status').textContent='本机示范已播完。';}};
      u.onerror=()=>{if(current===voiceEpoch){stop();$('dictionary-voice-status').textContent='本机语音未能播放，不会改用远程语音。';}};
      try{synth.speak(u);}catch{u.onerror();}
    }
    async function setState(state,event){
      event?.preventDefault?.();event?.stopPropagation?.();if(!entry)return;
      const chosen=entry,current=epoch;
      $('dictionary-save').disabled=true;$('dictionary-known').disabled=true;
      const context=root.WatchSync?.context?.();
      try{
        await library.setTerm({key:chosen.word,term:chosen.word,state:library.termState(chosen.word)===state?'neutral':state,english:chosen.cue?.english||'',chinese:chosen.cue?.chinese||'',start:chosen.cue?.start||0,url:context?.url||''});
        if(current===epoch)$('dictionary-status').textContent='学习状态已保存在本机。';
      }catch(error){if(current===epoch)$('dictionary-status').textContent=error.message;}
      finally{if(current===epoch)termButtons();}
    }
    $('dictionary-lookup').addEventListener('click',lookup);
    $('dictionary-input-privacy').textContent='点击「同意并查词」即同意仅发送此单词至 dictionaryapi.dev；不发送整句，不上传音视频。';
    $('dictionary-form').addEventListener('submit',event=>{
      event.preventDefault();event.stopPropagation();const input=$('dictionary-input'),word=input.value.trim();
      if(!wordValid(word)){$('dictionary-input-status').textContent='请输入单个英文单词（最多 64 个字母或词内连字符、撇号），不要输入整句。';input.focus();return;}
      close();selection={word:word.toLowerCase(),node:input,cue:null,rect:input.getBoundingClientRect()};$('dictionary-input-status').textContent='';return lookup(event);
    });
    $('dictionary-lookup').addEventListener('pointerdown',event=>event.preventDefault());
    $('dictionary-dismiss').addEventListener('click',close);$('dictionary-close').addEventListener('click',close);
    $('dictionary-speak').addEventListener('click',speak);$('dictionary-stop').addEventListener('click',()=>{stop();$('dictionary-voice-status').textContent='已停止本机示范。';});
    $('dictionary-save').addEventListener('click',event=>setState('learn',event));$('dictionary-known').addEventListener('click',event=>setState('known',event));
    library.subscribe?.(termButtons);
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&(!$('dictionary-card').hidden||!$('dictionary-selection').hidden)){event.preventDefault();close();}});
    root.addEventListener('pagehide',close);root.addEventListener('resize',close);
    root.addEventListener('scroll',event=>{if(!$('dictionary-card').contains(event.target))close();},{capture:true,passive:true});
    close();return {bindEnglish,close,stop};
  }
  return {createDictionary};
});
