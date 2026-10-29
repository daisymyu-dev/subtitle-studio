(function(root,factory){
  'use strict';
  const exported=factory();
  if(typeof module==='object'&&module.exports)module.exports=exported;
  else {
    root.LearningLibrary=exported.createLibrary({fetch:root.fetch.bind(root),token:document.querySelector('meta[name="app-token"]').content,href:root.location.href,navigate:url=>root.location.assign(url),canNavigate:()=>root.SubtitleApp?.canNavigate?.()!==false});
    exported.mount?.(root,document,root.LearningLibrary);
  }
})(typeof window!=='undefined'?window:this,function(){
  'use strict';
  const jobId=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
  const finiteTime=value=>Number.isFinite(value)&&value>=0&&value<=604800;
  const keyValid=value=>typeof value==='string'&&/^[A-Za-z0-9 -]{1,120}$/.test(value);
  function createLibrary({fetch,token,now=()=>Date.now(),href,navigate,canNavigate=()=>true}){
    let profile={known:[],saved:[],progress:{}},queue=Promise.resolve(),profileLoad=null,profileLoaded=false;
    const listeners=new Set(),lastWrite=new Map(),progressQueues=new Map(),localProgress={};
    const snapshot=()=>({known:[...profile.known],saved:profile.saved.map(item=>({...item})),progress:{...profile.progress}});
    function publish(body){
      profile={known:Array.isArray(body?.known)?body.known.filter(keyValid):[],saved:Array.isArray(body?.saved)?body.saved.filter(item=>keyValid(item?.key)).map(item=>({...item})):[],progress:{}};
      for(const [id,value] of Object.entries(body?.progress||{}))if(jobId(id)&&finiteTime(value))profile.progress[id]=value;
      Object.assign(profile.progress,localProgress);
      for(const fn of listeners)fn(snapshot());return snapshot();
    }
    function api(path,options={}){
      if(!['/api/learning','/api/learning/term','/api/learning/progress','/api/library','/api/dictionary'].includes(path))throw Error('无效的本机 API 地址。');
      return (async()=>{
        const response=await fetch(path,{...options,headers:{...options.headers,'X-App-Token':token},credentials:'same-origin'});
        const body=await response.json();if(!response.ok)throw Error(body.error||'本机学习库暂时不可用，请重试。');return body;
      })();
    }
    const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    function ensureReady(){
      if(profileLoaded)return Promise.resolve(snapshot());
      if(profileLoad)return profileLoad;
      profileLoad=api('/api/learning').then(publish).then(value=>{profileLoaded=true;return value;}).finally(()=>{profileLoad=null;});
      // A failed read is visible to the caller; the next action can retry it.
      profileLoad.catch(()=>{});return profileLoad;
    }
    ensureReady();
    function setTerm(value){
      if(!keyValid(value?.key)||typeof value.term!=='string'||!['known','learn','neutral'].includes(value.state))return Promise.reject(Error('学习表达无效。'));
      const body={key:value.key,term:value.term,state:value.state};
      for(const field of ['english','chinese','url','start'])if(value[field]!==undefined)body[field]=value[field];
      const task=queue.catch(()=>{}).then(ensureReady).then(()=>post('/api/learning/term',body)).then(publish);
      queue=task;return task;
    }
    async function rememberProgress(id,time){
      if(!jobId(id)||!finiteTime(time))return false;
      await ensureReady();
      if(time===0&&(profile.progress[id]||0)>0)return false;
      const clock=now();if(clock-(lastWrite.get(id)??-Infinity)<5000)return false;
      // Reserve the throttle slot at submission, then serialize HTTP writes per job.
      // A slow old request must complete before a newer position is persisted.
      lastWrite.set(id,clock);
      const task=(progressQueues.get(id)||Promise.resolve()).catch(()=>{}).then(async()=>{
        await post('/api/learning/progress',{job_id:id,time});
        localProgress[id]=time;profile.progress[id]=time;return true;
      });
      progressQueues.set(id,task);
      const cleanup=()=>{if(progressQueues.get(id)===task)progressQueues.delete(id);};
      task.then(cleanup,cleanup);return task;
    }
    function resume(id){
      if(!jobId(id)||!canNavigate())return false;
      const url=new URL(href);url.searchParams.set('job',id);url.searchParams.set('page','study');url.hash='';
      navigate(url.pathname+url.search);return true;
    }
    return {get ready(){return ensureReady();},api,getProfile:snapshot,setTerm,rememberProgress,resume,
      termState:key=>profile.known.includes(key)?'known':profile.saved.some(item=>item.key===key)?'learn':'neutral',
      subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},
      async progressFor(id){await ensureReady();return jobId(id)?profile.progress[id]||0:0;}};
  }
  function mount(root,document,client){
    const $=id=>document.getElementById(id),panel=$('library-panel');let epoch=0;
    const text=(tag,value,cls)=>{const node=document.createElement(tag);node.textContent=value||'';if(cls)node.className=cls;return node;};
    const stamp=value=>{const seconds=Math.max(0,Math.floor(value||0));return Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');};
    function action(label,value){
      const button=text('button',label);button.type='button';
      button.addEventListener('click',async()=>{
        button.disabled=true;
        try{await client.setTerm(value);$('library-status').textContent='学习状态已保存在本机。';}
        catch(error){$('library-status').textContent=error.message;}
        finally{button.disabled=false;}
      });return button;
    }
    function renderProfile(profile=client.getProfile()){
      $('library-count').textContent=profile.saved.length+' 收藏 · '+profile.known.length+' 已掌握';
      const saved=profile.saved.map(item=>{
        const row=document.createElement('article');row.className='library-entry';
        row.append(text('h4',item.term),text('p',item.english,'library-english'),text('p',item.chinese,'library-muted'));
        const actions=document.createElement('div');actions.className='library-entry-actions';
        actions.append(action('已掌握',{key:item.key,term:item.term,state:'known'}),action('移出收藏',{key:item.key,term:item.term,state:'neutral'}));row.append(actions);return row;
      });
      $('library-saved').replaceChildren(...(saved.length?saved:[text('p','点金色表达的「收藏」，或选中英文单词后查词。','library-empty')]));
      const known=profile.known.map(key=>{
        const row=document.createElement('div');row.className='library-known-entry';
        row.append(text('span',root.LearningLexicon?.find(item=>item.id===key)?.term||key),action('重新学习',{key,term:key,state:'neutral'}));return row;
      });
      $('library-known').replaceChildren(...(known.length?known:[text('p','已掌握的表达不再自动标注；随时可以重新学习。','library-empty')]));
    }
    function close(){epoch++;panel.hidden=true;$('library-open').setAttribute('aria-expanded','false');}
    async function open(){
      const current=++epoch;panel.hidden=false;$('library-open').setAttribute('aria-expanded','true');
      root.LearningHighlights?.close?.(false);root.LearningDictionary?.close?.();$('library-close').focus();
      $('library-status').textContent='正在读取本机学习库…';
      try{
        const [body]=await Promise.all([client.api('/api/library'),client.ready]);
        if(current!==epoch||panel.hidden)return;
        const profile=client.getProfile();
        const rows=(Array.isArray(body.items)?body.items:[]).filter(item=>jobId(item?.id)).map(item=>{
          const row=document.createElement('article');row.className='library-entry';
          const position=profile.progress[item.id]??item.position??0;
          row.append(text('h4',item.title||'未命名字幕'),text('p',(Number(item.cue_count)||0)+' 句 · 上次 '+stamp(position),'library-muted'));
          const button=text('button','继续学习 · '+stamp(position));button.type='button';button.addEventListener('click',()=>{if(!client.resume(item.id))$('library-status').textContent='当前任务正在处理，请完成后再继续其他任务。';});row.append(button);return row;
        });
        $('library-recent').replaceChildren(...(rows.length?rows:[text('p','还没有保留的任务。生成一次字幕后，即可从这里继续。','library-empty')]));
        renderProfile(profile);$('library-status').textContent='仅保存在此电脑 · 继续学习不会自动播放。';
      }catch(error){if(current===epoch)$('library-status').textContent=error.message;}
    }
    $('library-open').addEventListener('click',()=>panel.hidden?open():close());$('library-close').addEventListener('click',()=>{close();$('library-open').focus();});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!panel.hidden){event.preventDefault();close();$('library-open').focus();}});
    client.subscribe(renderProfile);renderProfile();client.ready.then(()=>renderProfile()).catch(error=>{$('library-status').textContent=error.message;});
    client.closePanel=close;panel.hidden=true;return {open,close};
  }
  return {createLibrary,mount};
});
