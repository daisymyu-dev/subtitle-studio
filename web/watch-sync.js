(function(){
  'use strict';
  const $=id=>document.getElementById(id),core=window.WatchCore,frame=$('original-video-frame');
  const bridge=document.querySelector('meta[name="video-bridge"]').content,token=document.querySelector('meta[name="app-token"]').content;
  let video=null,channel='',playerReady=false,timeline=null,current=-2,lastTime=0,page=0,rows=[],lastResult=null,loadedId='',loadEpoch=0,pending=null,pendingId='',pendingSeek=null;
  const size=50;
  const rateChoices=[.75,1,1.25,1.5,2],publicRates=[.25,.5,.75,1,1.25,1.5,1.75,2];
  let actualRate=1,availableRates=[];
  let rawCues=null,progressReady=false,playing=false,restoreTarget=0,seekRevision=0;
  const profile=()=>window.LearningLibrary?.getProfile?.()||{known:[]};
  function annotate(){return window.LearningCore?.annotateCues(rawCues,{known:profile().known})||rawCues;}
  function stamp(value){const s=Math.max(0,Math.floor(value||0));return(s>=3600?String(Math.floor(s/3600)).padStart(2,'0')+':':'')+String(Math.floor(s/60)%60).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
  function status(text){$('watch-player-status').textContent=text;}
  function send(command,value){if(!video||!channel||!frame.contentWindow)return;frame.contentWindow.postMessage({channel,command,...(value===undefined?{}:command==='rate'?{rate:value}:{seconds:value})},bridge);}
  function rateView(rate,rates){
    actualRate=rate;availableRates=rates;
    const choices=rateChoices.includes(rate)?rateChoices:[...rateChoices,rate].sort((a,b)=>a-b);
    $('watch-rate').replaceChildren(...choices.map(value=>{const option=document.createElement('option');option.value=String(value);option.textContent=value+'×'+(rates.includes(value)?'':'（不支持）');option.disabled=!rates.includes(value);return option;}));
    $('watch-rate').value=String(rate);$('watch-rate').disabled=!playerReady||!rates.length;
    $('watch-rate-status').textContent='当前 '+rate+'×';
  }
  function clearText(){rawCues=null;progressReady=false;playing=false;restoreTarget=0;seekRevision++;timeline=null;current=-2;loadedId='';rows=[];page=0;loadEpoch++;pendingId='';pending=null;document.body.dataset.transcriptReady='false';$('watch-transcript-list').replaceChildren();$('watch-current-en').textContent='生成字幕后，手动播放视频，字幕会跟随进度切换。';$('watch-current-zh').textContent='';$('watch-transcript-count').textContent='当前视频尚未生成字幕。';$('watch-page-info').textContent='—';$('watch-page-previous').disabled=true;$('watch-page-next').disabled=true;window.LearningDictionary?.close?.();}
  function setVideo(url){
    const next=core.videoInfo(url);
    if(video&&next&&video.id===next.id){if(next.start!==video.start&&next.start>0){seekRevision++;restoreTarget=0;pendingSeek=next.start;if(playerReady){send('seek',pendingSeek);pendingSeek=null;}}video=next;return;}
    send('pause');window.LearningHighlights?.close?.(false);window.OriginalShadowing?.reset?.();clearText();lastResult=null;playerReady=false;lastTime=0;$('watch-clock').textContent=stamp(0);$('watch-play-video').disabled=true;$('watch-pause-video').disabled=true;pendingSeek=next?.start||null;video=next;channel='';
    rateView(1,[]);$('watch-rate-status').textContent='播放器就绪后可调倍速';
    $('results').hidden=true;frame.hidden=!next;$('watch-video-empty').hidden=Boolean(next);$('watch-source').hidden=!next;
    if(!next){frame.removeAttribute('src');status('请输入单个有效的 YouTube 视频链接。');return;}
    try{
      channel=window.crypto.randomUUID().replace(/-/g,'');frame.src=core.frameURL(bridge,next.id,channel);
      $('watch-source').href=next.url;status('正在载入原视频。不会自动播放，请手动点击播放器。');
    }catch{frame.hidden=true;$('watch-video-empty').hidden=false;status('播放器配置不可用，请刷新页面或重启本机工具。');}
  }
  function setPage(value){
    const selected=value==='study'?'study':'watch';document.body.dataset.page=selected;
    $('watch-input').hidden=selected!=='watch';$('study-pane').hidden=selected!=='study';
    $('page-watch').setAttribute('aria-selected',String(selected==='watch'));$('page-study').setAttribute('aria-selected',String(selected==='study'));
    if(selected==='watch')window.OriginalShadowing?.pause?.();
    if(window.history?.replaceState){const url=new URL(window.location.href);url.searchParams.set('page',selected);window.history.replaceState(null,'',url.pathname+url.search+url.hash);}
    if(selected==='study'&&timeline&&current>=0&&$('watch-follow').checked)focusCurrent();
  }
  function renderList(){
    rows=[];const fragment=document.createDocumentFragment();
    if(!timeline){$('watch-transcript-list').replaceChildren();return;}
    for(let i=page*size;i<Math.min((page+1)*size,timeline.cues.length);i++){
      const cue=timeline.cues[i],row=document.createElement('div'),button=document.createElement('button');row.className='watch-transcript-row';row.setAttribute('aria-current',String(i===current));button.type='button';button.className='watch-row-jump';button.setAttribute('aria-label',`跳转到第 ${i+1} 段，${stamp(cue.start)}：${cue.english}`);
      const time=document.createElement('span');time.className='watch-row-time';time.textContent=stamp(cue.start);
      const text=document.createElement('span'),en=document.createElement('span'),zh=document.createElement('span');text.className='watch-row-copy';en.className='watch-row-en';en.lang='en';en.textContent=cue.english;zh.className='watch-row-zh';zh.lang='zh-CN';zh.textContent=cue.chinese||'';
      if(cue.fragment){const badge=document.createElement('span');badge.className='sentence-badge';badge.textContent=cue.fragment_reason?.includes('restored_tail_uncertain')?'结尾完整性待核对':'残句 / 截断片段';text.append(badge);}
      text.append(en);
      if(cue.chinese)text.append(zh);
      window.LearningHighlights?.renderPair(en,zh,cue);
      const arrow=document.createElement('span');arrow.className='watch-row-arrow';arrow.textContent='↗';arrow.setAttribute('aria-hidden','true');
      button.append(time);row.append(button,text,arrow);button.addEventListener('click',()=>seek(cue.start));
      row.addEventListener('click',event=>{if(!event?.target?.closest?.('button'))seek(cue.start);});fragment.append(row);rows.push({index:i,button:row});
    }
    $('watch-transcript-list').replaceChildren(fragment);const pages=Math.ceil(timeline.cues.length/size);
    $('watch-page-info').textContent=(page+1)+' / '+pages;$('watch-page-previous').disabled=page===0;$('watch-page-next').disabled=page>=pages-1;
  }
  function focusCurrent(){
    const target=Math.floor(current/size);if(target!==page){page=target;renderList();}
    const row=rows.find(item=>item.index===current);if(row)row.button.scrollIntoView({block:'nearest',behavior:'smooth'});
  }
  function updateTime(time,follow=true){
    lastTime=time;$('watch-clock').textContent=stamp(time);if(!timeline)return;
    const index=core.activeIndex(timeline,time);if(index===current)return;current=index;
    const cue=timeline.cues[index];$('watch-current-en').textContent=cue?cue.english:'这一时段暂无字幕。';$('watch-current-zh').textContent=cue?.chinese||'';
    if(cue)window.LearningHighlights?.renderPair($('watch-current-en'),$('watch-current-zh'),cue);
    if(cue)$('watch-current-note').textContent=(cue.fragment?(cue.fragment_reason?.includes('restored_tail_uncertain')?'结尾完整性待核对。':'残句 / 截断片段。'):'')+'逐句对应中文；'+(cue.restored?'含本地模型补标点；':'')+(cue.timing_estimated?'句内时间为估算，非逐词对齐。':'时间来自原字幕。');
    if(follow&&index>=0&&$('watch-follow').checked&&document.body.dataset.page==='study')focusCurrent();
    for(const row of rows)row.button.setAttribute('aria-current',String(row.index===index));
  }
  function seek(time){
    seekRevision++;restoreTarget=0;
    if(!video){$('watch-transcript-status').textContent='本地文件暂无在线视频播放器，可使用原音跟读或阅读全文。';return;}
    if(!playerReady){pendingSeek=time;status('已记住跳转位置，等待播放器加载；不会自动播放。');}
    else send('seek',time);
    updateTime(time);
  }
  function accepts(value){
    const incoming=core.videoInfo(value.url),entered=core.videoInfo($('url').value);
    return !(entered&&incoming&&entered.id!==incoming.id);
  }
  async function result(value){
    if(!accepts(value)||! /^[a-f0-9]{32}$/.test(value.id))return;
    if(value.url){if(!$('url').value)$('url').value=value.url;setVideo($('url').value||value.url);}else{setVideo('');setPage('study');}
    lastResult=value;$('word-start').hidden=!value.url;$('watch-sentences').hidden=!value.url||value.sentence_version===1;
    if(value.url&&value.sentence_version!==1){
      clearText();$('watch-current-en').textContent='请在学习页点击“整理成完整句子”，生成逐句中英对照。';
      $('watch-transcript-status').textContent='这是旧版碎片字幕。整理成完整句子后，每句只配自己的中文译文，不沿用整段中文。';
      $('watch-transcript-count').textContent='原字幕已保留，可直接按完整句整理，无需重新提取视频。';return;
    }
    if(loadedId===value.id&&timeline)return;
    if(pendingId===value.id&&pending)return pending;
    if(loadedId&&loadedId!==value.id){clearText();window.LearningHighlights?.close?.(false);}
    const epoch=++loadEpoch,revision=seekRevision;pendingId=value.id;
    $('watch-transcript-status').textContent='正在读取完整字幕，不是网页预览片段。';
    pending=(async()=>{
      try{
        const response=await fetch(`/api/jobs/${value.id}/study`,{headers:{'X-App-Token':token}}),body=await response.json();
        if(epoch!==loadEpoch)return;if(!response.ok)throw Error(body.error||'完整字幕暂时不可用。');
        rawCues=body.cues;timeline=core.makeTimeline(annotate());loadedId=value.id;page=0;current=-2;document.body.dataset.transcriptReady='true';
        $('watch-current-note').textContent=body.mode==='sentences'?'逐句对应中文；补标点与句内时间为估算。残句单独标记，不改原话。':'中文为对应段落参考；非逐句精确翻译。';
        $('watch-transcript-count').textContent=`全文 ${timeline.cues.length} ${body.mode==='sentences'?'句':'段'}，每页 ${size} ${body.mode==='sentences'?'句':'段'}。${body.chinese_note||'中文为对应段落参考。'}`;
        $('watch-transcript-status').textContent='播放视频后同步高亮；点击片段可跳转，暂停状态下不会自动播放。';renderList();updateTime(lastTime);
        if(window.LearningLibrary?.progressFor){
          try{
            const saved=await window.LearningLibrary.progressFor(value.id);if(epoch!==loadEpoch)return;
            if(revision===seekRevision&&Number.isFinite(saved)&&saved>0&&saved<=604800){
              if(video){seek(saved);restoreTarget=saved;}else updateTime(saved);
            }
            progressReady=true;
          }catch{if(epoch===loadEpoch)$('watch-transcript-status').textContent='学习进度暂时无法读取；字幕仍可使用，请在学习库重试。';}
        }
      }catch(error){if(epoch===loadEpoch)$('watch-transcript-status').textContent=error.message;}
      finally{if(epoch===loadEpoch){pending=null;pendingId='';}}
    })();return pending;
  }
  window.addEventListener('message',event=>{
    const data=event.data;if(!video||event.origin!==bridge||event.source!==frame.contentWindow||!data||data.channel!==channel||data.videoId!==video.id)return;
    if(data.event==='ready'){playerReady=true;$('watch-play-video').disabled=false;$('watch-pause-video').disabled=false;status('原视频已就绪，不自动播放。点击播放原视频开始观看。');if(pendingSeek!==null){send('seek',pendingSeek);pendingSeek=null;}}
    else if(data.event==='playback'&&publicRates.includes(data.rate)&&Array.isArray(data.rates)&&data.rates.length<=publicRates.length&&data.rates.every(rate=>publicRates.includes(rate))){
      rateView(data.rate,[...new Set(data.rates)]);
    }
    else if(data.event==='rate-error'){
      $('watch-rate').value=String(actualRate);
      $('watch-rate-status').textContent=(data.errorCode==='RATE_UNSUPPORTED'?'此视频不支持该倍速':data.errorCode==='RATE_UNCONFIRMED'?'播放器未确认变速':'倍速暂时不可用')+'，当前 '+actualRate+'×';
    }
    else if(data.event==='time'&&Number.isFinite(data.time)&&data.time>=0&&data.time<=604800){
      // While paused, a changed native-player position is newer user intent too.
      // Startup zero is unchanged; ignore tiny decoder/time-reporting jitter.
      if(!playing&&!restoreTarget&&Math.abs(data.time-lastTime)>.5)seekRevision++;
      updateTime(data.time);
      if(restoreTarget&&data.time>=restoreTarget-.5)restoreTarget=0;
      if(progressReady&&playing&&!restoreTarget&&loadedId)window.LearningLibrary?.rememberProgress?.(loadedId,data.time)?.catch(()=>{$('library-progress-status').textContent='进度保存失败，可在学习库检查本机连接。';});
    }
    else if(data.event==='state'&&[-1,0,1,2,3,5].includes(data.state)){
      playing=data.state===1;if(playing)seekRevision++;
      if(data.state===1){window.LearningHighlights?.stopPronunciation?.();window.OriginalShadowing?.pause?.();status('正在播放原视频，字幕随进度切换。');}
      else if(data.state===2)status('原视频已暂停，字幕保留在当前进度。');
      else if(data.state===0)status('原视频播放结束。');
    }else if(data.event==='blocked'){
      status('浏览器拦截了外部播放操作。请点击播放器内的播放键，字幕仍会同步。');
    }else if(data.event==='error'){
      playerReady=false;$('watch-play-video').disabled=true;$('watch-pause-video').disabled=true;$('watch-rate').disabled=true;const code=String(data.errorCode||'');
      status(['101','150'].includes(code)?'视频作者不允许嵌入播放。请在 YouTube 打开原片，字幕和 Word 仍可使用。':code==='153'?'YouTube 未接受播放器来源标识。可先在 YouTube 打开原片；不会绕过限制。':'播放器暂时不可用，可能是网络或视频访问限制。可在 YouTube 打开原片，字幕仍保留。');
    }
  });
  $('url').addEventListener('input',()=>setVideo($('url').value));
  $('watch-play-video').addEventListener('click',()=>{if(!playerReady)return;window.LearningHighlights?.stopPronunciation?.();window.OriginalShadowing?.pause?.();send('play');});
  $('watch-pause-video').addEventListener('click',()=>send('pause'));
  $('watch-rate').addEventListener('change',()=>{
    const rate=Number($('watch-rate').value);
    if(!playerReady||!rateChoices.includes(rate)||!availableRates.includes(rate)){$('watch-rate').value=String(actualRate);return;}
    $('watch-rate-status').textContent='正在切换至 '+rate+'×…';send('rate',rate);
  });
  rateView(1,[]);
  window.LearningLibrary?.subscribe?.(()=>{
    if(!rawCues||!timeline)return;
    timeline=core.makeTimeline(annotate());current=-2;renderList();updateTime(lastTime,false);
  });
  $('page-watch').addEventListener('click',()=>setPage('watch'));$('page-study').addEventListener('click',()=>setPage('study'));
  $('watch-page-previous').addEventListener('click',()=>{if(timeline&&page>0){$('watch-follow').checked=false;page--;renderList();}});
  $('watch-page-next').addEventListener('click',()=>{if(timeline&&(page+1)*size<timeline.cues.length){$('watch-follow').checked=false;page++;renderList();}});
  $('watch-follow').addEventListener('change',()=>{if($('watch-follow').checked&&current>=0)focusCurrent();});
  $('watch-reload').addEventListener('click',()=>{if(lastResult){loadedId='';result(lastResult);}});
  setPage(new URLSearchParams(window.location.search).get('page'));
  window.WatchSync={setVideo,setPage,result,accepts,pause:()=>send('pause'),context:()=>({id:loadedId,url:lastResult?.url||'',time:lastTime}),beginTask(url){setVideo(url);clearText();lastResult=null;setPage('study');},canExport(url){return lastResult?.sentence_version===1&&core.canExportCached(lastResult,url);},isSentence(){return lastResult?.sentence_version===1;},resultId(){return lastResult?.id||null;}};
})();
