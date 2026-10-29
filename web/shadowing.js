(function(){
  'use strict';
  const $=id=>document.getElementById(id),audio=$('shadow-audio'),token=document.querySelector('meta[name="app-token"]').content;
  let result=null,data=null,index=0,page=0,epoch=0,ready=false,preparing=false,mediaUrl='',mediaExpires=0,cnHidden=false,rows=[];
  const size=50;
  let rawStudy=null;
  const annotated=cues=>window.LearningCore?.annotateCues(cues,{known:window.LearningLibrary?.getProfile?.().known||[]})||cues;
  function time(value){const s=Math.max(0,Math.floor(value||0));return (s>=3600?String(Math.floor(s/3600)).padStart(2,'0')+':':'')+String(Math.floor(s/60)%60).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
  function message(text){$('shadow-status').textContent=text;}
  function controls(){const enabled=ready&&!!data;$('shadow-play').disabled=!enabled;$('shadow-pause').disabled=!data||(!ready&&!['loading','playing','following'].includes(player.phase));$('shadow-previous').disabled=!enabled||index===0;$('shadow-next').disabled=!enabled||index>=data.cues.length-1;}
  const player=new window.ShadowCore.ShadowPlayer(audio,{beforePlay:async()=>{
    window.LearningHighlights?.stopPronunciation?.();
    window.WatchSync?.pause?.();
    if(mediaExpires>Date.now()/1000+20)return;
    const current=epoch;if(!data)throw Error('请重新打开跟读区。');
    const status=await api(`/api/jobs/${data.id}/audio`);if(current!==epoch)throw Error('已切换任务。');
    if(!useMedia(status))throw Error('请先准备原音。');
    if(audio.readyState>=1&&Number.isFinite(audio.duration)&&audio.duration>0)return;
    await new Promise((resolve,reject)=>{
      const cleanup=()=>{clearTimeout(timer);audio.removeEventListener('loadedmetadata',done);audio.removeEventListener('error',fail);};
      const done=()=>{cleanup();resolve();},fail=()=>{cleanup();reject(Error('原音播放信息更新失败，请重试。'));};
      const timer=setTimeout(fail,10000);audio.addEventListener('loadedmetadata',done,{once:true});audio.addEventListener('error',fail,{once:true});
    });
  },onState(state){
    if(!data)return;
    $('shadow-play').textContent=state.phase==='playing'?'重听原音':'播放原音';
    if(state.phase==='playing')message('正在播放本段原音，结束后自动停下，轮到你跟读。');
    else if(state.phase==='following')message(player.loop?'原音播完了。请跟读，留白后将重复当前片段。':'原音播完了，轮到你跟读。点“播放原音”可重听，或选择下一段。');
    else if(state.phase==='paused')message('已暂停。再次播放会从本段开头重听。');
    else if(state.phase==='error')message('原音播放失败，请检查网络、音轨或浏览器播放限制。');
    for(const row of rows)row.button.setAttribute('aria-pressed',String(row.index===index));
    controls();
  }});
  async function api(path,options={}){
    const response=await fetch(path,{...options,headers:{'X-App-Token':token,...options.headers}});
    const body=await response.json();if(!response.ok)throw Error(body.error||'原音服务暂时不可用。');return body;
  }
  function reset(){
    rawStudy=null;window.LearningDictionary?.close?.();
    epoch++;result=null;data=null;ready=false;preparing=false;mediaUrl='';mediaExpires=0;rows=[];
    player.reset();audio.removeAttribute('src');audio.load();
    $('shadow-entry').hidden=true;$('shadow-open').hidden=true;$('shadow-open').disabled=false;$('shadowing').hidden=true;
    $('shadow-prepare').disabled=false;$('shadow-prepare').textContent='准备原音';controls();
  }
  function showResult(value){reset();result=value;const show=Boolean(value?.url&&/^[a-f0-9]{32}$/.test(value.id));$('shadow-open').hidden=!show;$('shadow-entry').hidden=!show;}
  function select(selected,play=false){
    if(!data)return;index=Math.max(0,Math.min(data.cues.length-1,selected));player.select(data.cues[index]);
    renderCurrent();
    controls();if(play&&ready)player.play().catch(error=>message(error.message));else message(ready?'已选中片段，点“播放原音”开始。':'已选中片段，请先准备原音。');
  }
  function renderCurrent(){
    const cue=data.cues[index];$('shadow-english').textContent=cue.english;$('shadow-chinese').textContent=cue.chinese||'此任务暂无中文参考；可用“中英字幕 Word”整理双语材料。';
    window.LearningHighlights?.renderPair($('shadow-english'),$('shadow-chinese'),cue);
    if(!cue.chinese)$('shadow-chinese').textContent='此任务暂无中文参考；可用“中英字幕 Word”整理双语材料。';
    $('shadow-range').textContent=time(cue.start)+' → '+time(cue.end)+(cue.fragment?(cue.fragment_reason?.includes('restored_tail_uncertain')?' · 结尾完整性待核对':' · 残句 / 截断片段'):'');$('shadow-counter').textContent=String(index+1).padStart(2,'0')+' / '+data.cues.length;
    $('shadow-source').href=data.url+'&t='+Math.floor(cue.start)+'s';$('shadow-clock').textContent='';
    const target=window.ShadowCore.pageFor(index,size);if(target!==page||!rows.length){page=target;renderList();}
    for(const row of rows)row.button.setAttribute('aria-pressed',String(row.index===index));
  }
  function renderList(){
    rows=[];const fragment=document.createDocumentFragment();
    for(let i=page*size;i<Math.min(data.cues.length,(page+1)*size);i++){
      const cue=data.cues[i],row=document.createElement('div'),button=document.createElement('button');row.className='shadow-learning-row';row.setAttribute('aria-pressed',String(i===index));button.type='button';button.className='shadow-row-jump';button.setAttribute('aria-label',`选择并播放第 ${i+1} 段：${cue.english}`);
      const stamp=document.createElement('span');stamp.className='shadow-row-time';stamp.textContent=time(cue.start);
      const text=document.createElement('span'),en=document.createElement('span'),zh=document.createElement('span');en.className='shadow-row-en';en.lang='en';en.textContent=cue.english;text.append(en);zh.className='shadow-row-zh';zh.lang='zh-CN';zh.textContent=cue.chinese||'';
      if(cue.chinese)text.append(zh);window.LearningHighlights?.renderPair(en,zh,cue);
      const arrow=document.createElement('span');arrow.className='shadow-row-arrow';arrow.textContent='▶';arrow.setAttribute('aria-hidden','true');button.append(stamp);row.append(button,text,arrow);
      button.addEventListener('click',()=>select(i,true));row.addEventListener('click',event=>{if(!event?.target?.closest?.('button'))select(i,true);});fragment.append(row);rows.push({button:row,index:i});
    }
    $('shadow-list').replaceChildren(fragment);const pages=Math.ceil(data.cues.length/size);
    $('shadow-page-info').textContent=(page+1)+' / '+pages;$('shadow-page-previous').disabled=page===0;$('shadow-page-next').disabled=page>=pages-1;
  }
  function useMedia(status){
    if(status.status==='ready'){
      if(typeof status.media_url!=='string'||!status.media_url.startsWith('/media/'))throw Error('原音地址无效。');
      mediaExpires=Number(status.expires_at)||Infinity;
      if(mediaUrl!==status.media_url){ready=false;mediaUrl=status.media_url;audio.src=mediaUrl;audio.load();}
      $('shadow-prepare').textContent='原音已就绪';$('shadow-prepare').disabled=true;
      message('原音已取得，正在读取播放信息；不会自动播放。');controls();return true;
    }
    message(status.message||'准备原音后即可逐段跟读。');return false;
  }
  $('shadow-open').addEventListener('click',async()=>{
    if(!result)return;
    if(data&&data.id===result.id){$('shadowing').scrollIntoView({behavior:'smooth',block:'start'});return;}
    const current=++epoch,job=result.id;$('shadow-open').disabled=true;
    try{
      const loaded=await api(`/api/jobs/${job}/study`);if(current!==epoch)return;
      if(!Array.isArray(loaded.cues)||!loaded.cues.length)throw Error('此任务没有可跟读的时间轴。');
      rawStudy=loaded;data={...loaded,cues:annotated(loaded.cues)};index=0;page=0;rows=[];$('shadowing').hidden=false;
      $('shadow-list-note').textContent=`共 ${data.cues.length} 段，每页 ${size} 段，可翻到全文末尾。${data.chinese_note||'中文仅为对应段落参考。'}`;
      select(0);$('shadowing').scrollIntoView({behavior:'smooth',block:'start'});
      const status=await api(`/api/jobs/${job}/audio`);if(current===epoch)useMedia(status);
    }catch(error){if(current===epoch){$('shadowing').hidden=false;message(error.message);}}
    finally{if(current===epoch)$('shadow-open').disabled=false;}
  });
  $('shadow-prepare').addEventListener('click',async()=>{
    if(!data||preparing)return;const current=epoch,job=data.id;preparing=true;$('shadow-prepare').disabled=true;
    try{
      let status=await api(`/api/jobs/${job}/audio`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      while(current===epoch){
        if(useMedia(status))break;
        if(!['queued','downloading'].includes(status.status))throw Error(status.message||'原音准备失败，可重试。');
        await new Promise(resolve=>setTimeout(resolve,900));if(current!==epoch)return;
        status=await api(`/api/jobs/${job}/audio`);
      }
    }catch(error){if(current===epoch){message(error.message);$('shadow-prepare').textContent='重试准备原音';}}
    finally{if(current===epoch){preparing=false;$('shadow-prepare').disabled=Boolean(mediaUrl);}}
  });
  $('shadow-play').addEventListener('click',()=>{if(ready)player.play().catch(error=>message(error.message));});
  $('shadow-pause').addEventListener('click',()=>player.pause());
  $('shadow-previous').addEventListener('click',()=>select(index-1,true));$('shadow-next').addEventListener('click',()=>select(index+1,true));
  $('shadow-rate').addEventListener('change',()=>{try{player.setRate($('shadow-rate').value);}catch(error){message(error.message);}});
  $('shadow-gap').addEventListener('change',()=>{try{player.setGap($('shadow-gap').value);}catch(error){message(error.message);}});
  $('shadow-loop').addEventListener('change',()=>player.setLoop($('shadow-loop').checked));
  $('shadow-toggle-chinese').addEventListener('click',()=>{cnHidden=!cnHidden;$('shadowing').classList.toggle('cn-hidden',cnHidden);$('shadow-toggle-chinese').textContent=cnHidden?'显示中文':'隐藏中文';$('shadow-toggle-chinese').setAttribute('aria-pressed',String(cnHidden));});
  $('shadow-page-previous').addEventListener('click',()=>{if(data&&page>0){page--;renderList();}});
  $('shadow-page-next').addEventListener('click',()=>{if(data&&(page+1)*size<data.cues.length){page++;renderList();}});
  audio.addEventListener('loadedmetadata',()=>{if(!data||!mediaUrl)return;ready=Number.isFinite(audio.duration)&&audio.duration>0;controls();message(ready?'原音已就绪，点“播放原音”开始；播放完会停下，留给你跟读。':'无法读取原音长度，请在原视频核对。');});
  audio.addEventListener('timeupdate',()=>{if(!data||!player.cue)return;player.tick();$('shadow-clock').textContent='当前原音 '+time(audio.currentTime)+' / 本段结束 '+time(player.cue.end);});
  audio.addEventListener('ended',()=>player.finish());
  audio.addEventListener('timeupdate',()=>{
    if(data&&player.phase==='playing')window.LearningLibrary?.rememberProgress?.(result.id,audio.currentTime)?.catch(()=>{$('library-progress-status').textContent='原音练习进度未能保存，请检查本机连接。';});
  });
  window.LearningLibrary?.subscribe?.(()=>{
    if(!rawStudy||!data)return;
    data={...rawStudy,cues:annotated(rawStudy.cues)};renderList();renderCurrent();
  });
  audio.addEventListener('pause',()=>{if(player.phase==='playing'&&audio.currentTime<player.end()-.02)player.pause();});
  audio.addEventListener('error',()=>{if(!data||!mediaUrl)return;player.pause();ready=false;mediaUrl='';controls();$('shadow-prepare').disabled=false;$('shadow-prepare').textContent='重试准备原音';message('原音无法播放。可能是音轨格式或文件问题；可重试，或在 YouTube 核对原视频。');});
  window.OriginalShadowing={showResult,reset,pause:()=>player.pause()};
})();
