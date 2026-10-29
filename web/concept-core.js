(function(root){
  'use strict';
  const core = {
    moveIndex(index,delta,length){return Math.max(0,Math.min(Math.max(0,length-1),index+delta));},
    formatTime(value){const seconds=Number.isFinite(value)?Math.max(0,Math.floor(value)):0;return String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');},
    progress(current,duration){return Number.isFinite(duration)&&duration>0?Math.max(0,Math.min(1000,Math.round(current/duration*1000))):0;},
    toggleSaved(saved,id,allowed){const clean=[...new Set(saved.filter(item=>allowed.includes(item)))];return !allowed.includes(id)?clean:clean.includes(id)?clean.filter(item=>item!==id):[...clean,id];}
  };
  if(typeof module==='object'&&module.exports)module.exports=core;
  else root.StudyPreview=core;
})(typeof window==='object'?window:globalThis);
