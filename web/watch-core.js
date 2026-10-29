(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.WatchCore=api;})(typeof window!=='undefined'?window:this,function(){
  'use strict';
  function videoInfo(value){
    try{
      const url=new URL(String(value).trim());if(!['http:','https:'].includes(url.protocol)||url.username||url.password||(url.port&&!['80','443'].includes(url.port)))return null;
      const host=url.hostname.toLowerCase(),parts=url.pathname.split('/').filter(Boolean);let id;
      if(['youtu.be','www.youtu.be'].includes(host)&&parts.length===1)id=parts[0];
      else if(['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(host)){
        if(url.pathname==='/watch')id=url.searchParams.get('v');else if(parts.length===2&&['shorts','live','embed'].includes(parts[0]))id=parts[1];
      }
      if(!id||! /^[\w-]{11}$/.test(id))return null;
      let start=0;const raw=url.searchParams.get('t')||url.searchParams.get('start')||'';
      if(/^\d+(?:\.\d+)?s?$/.test(raw))start=parseFloat(raw);else if(/^(?:\d+h)?(?:\d+m)?(?:\d+s)?$/.test(raw))start=(Number(raw.match(/(\d+)h/)?.[1])||0)*3600+(Number(raw.match(/(\d+)m/)?.[1])||0)*60+(Number(raw.match(/(\d+)s/)?.[1])||0);
      return {id,url:'https://www.youtube.com/watch?v='+id,start:Math.min(604800,start)};
    }catch{return null;}
  }
  function frameURL(origin,id,channel){
    const url=new URL(origin);if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!url.port||url.username||url.password||url.pathname!=='/'||url.search||url.hash||! /^[\w-]{11}$/.test(id)||! /^[a-f0-9]{32}$/.test(channel))throw Error('播放器地址无效。');
    return url.origin+'/player?v='+encodeURIComponent(id)+'&channel='+channel;
  }
  function makeTimeline(cues){
    if(!Array.isArray(cues)||!cues.length)throw Error('没有完整字幕时间轴。');
    const sorted=cues.map(cue=>{if(!cue||!Number.isFinite(cue.start)||!Number.isFinite(cue.end)||cue.start<0||cue.end<=cue.start||typeof cue.english!=='string'||!cue.english.trim())throw Error('字幕时间轴无效。');return {...cue,chinese:typeof cue.chinese==='string'?cue.chinese:''};}).sort((a,b)=>a.start-b.start||a.end-b.end);
    let max=-1;return {cues:sorted,ends:sorted.map(c=>max=Math.max(max,c.end))};
  }
  function activeIndex(timeline,time){
    if(!timeline||!Number.isFinite(time)||time<0)return -1;
    let low=0,high=timeline.cues.length;
    while(low<high){const mid=(low+high)>>1;if(timeline.cues[mid].start<=time)low=mid+1;else high=mid;}
    for(let i=low-1;i>=0&&timeline.ends[i]>time;i--)if(timeline.cues[i].end>time)return i;
    return -1;
  }
  function canExportCached(result,url){const a=videoInfo(result?.url),b=videoInfo(url);return Boolean(a&&b&&a.id===b.id&&/^[a-f0-9]{32}$/.test(result?.id)&&result.chinese_source&&Number.isInteger(result.bilingual_count)&&result.bilingual_count>0);}
  return {videoInfo,frameURL,makeTimeline,activeIndex,canExportCached};
});
