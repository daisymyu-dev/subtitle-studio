'use strict';
const token = document.querySelector('meta[name="app-token"]').content;
const $ = id => document.getElementById(id);
let source = 'youtube';
let currentJob = null;
let youtubeResult = null;
let busy = false;
let stopped = false;
let navigationLocked = false;
const navigationLinks = Array.from(document.querySelectorAll('a[href]')).filter(link => !link.getAttribute('href').startsWith('#'));
const sources = {uploaded_caption:'上传字幕',platform_auto:'YouTube 自动字幕',local_asr:'本地语音识别',local_caption:'本地字幕文件'};
const translationConsentVersion='public-beta-v1';
const translationConsent=$('translation-consent');
if(translationConsent&&'checked' in translationConsent){
  try{translationConsent.checked=sessionStorage.getItem('subtitle-translation-consent')===translationConsentVersion;}catch{}
  translationConsent.addEventListener('change',()=>{
    try{sessionStorage.setItem('subtitle-translation-consent',translationConsent.checked?translationConsentVersion:'');}catch{}
  });
}
function requireTranslationConsent(){
  // Legacy/embed pages with no bilingual consent control keep their existing workflow.
  if(!translationConsent||!('checked' in translationConsent))return true;
  if(!translationConsent.checked){
    showError('请先确认素材处理权限及 Google 公共网页翻译的文字发送说明。');
    translationConsent.scrollIntoView({block:'center'});translationConsent.focus();return false;
  }
  try{sessionStorage.setItem('subtitle-translation-consent',translationConsentVersion);}catch{}
  return true;
}

function lockNavigation(value) {
  navigationLocked = value;
  for (const link of navigationLinks) link.setAttribute('aria-disabled',String(value));
}
for (const link of navigationLinks) link.addEventListener('click',event => {
  if (navigationLocked) {
    event.preventDefault();
    showError('素材正在导入或提交，请稍候再切换版本。任务建立后可以切换，进度会自动恢复。');
  }
});

async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers:{'X-App-Token':token,...options.headers}});
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {message = (await response.json()).error || message;} catch {}
    throw new Error(message);
  }
  return response;
}
function showError(message) {$('form-error').textContent = message; $('form-error').hidden = !message;}
function rememberJob(id) {
  currentJob=id;sessionStorage.setItem('subtitle-job',id);
  if(typeof window!=='undefined'&&window.history?.replaceState){
    const url=new URL(window.location.href);url.searchParams.set('job',id);
    window.history.replaceState(null,'',url.pathname+url.search+url.hash);
  }
}
function formatTime(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  const hours = Math.floor(seconds / 3600);
  return (hours ? String(hours).padStart(2,'0') + ':' : '') + String(Math.floor(seconds / 60) % 60).padStart(2,'0') + ':' + String(seconds % 60).padStart(2,'0');
}
function switchTab(value) {
  if (busy) return;
  source = value;
  for (const type of ['youtube','file']) {
    const selected = type === source;
    const tab = $('tab-' + type);
    tab.classList.toggle('active',selected);
    tab.setAttribute('aria-selected',String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(type + '-pane').hidden = !selected;
  }
  $('mode').disabled = true;
  $('language').disabled = true;
  $('asr-language').disabled = source === 'youtube';
  if(typeof window!=='undefined'&&source==='file')window.WatchSync?.setVideo('');
  if(typeof window!=='undefined'&&source==='youtube') {
    window.WatchSync?.setVideo($('url').value);
    if(youtubeResult&&window.WatchSync?.accepts?.(youtubeResult)!==false){rememberJob(youtubeResult.id);resultView(youtubeResult);}
  }
  showError('');
}
for (const type of ['youtube','file']) $('tab-' + type).addEventListener('click', () => switchTab(type));
document.querySelector('.tabs').addEventListener('keydown', event => {
  if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
    event.preventDefault(); switchTab(source === 'youtube' ? 'file' : 'youtube'); $('tab-' + source).focus();
  }
});
$('file').addEventListener('change', () => {$('file-label').textContent = $('file').files[0]?.name || '选择音视频或字幕文件';});

function setBusy(value) {
  if(value&&typeof window!=='undefined')window.OriginalShadowing?.reset();
  busy = value;
  for (const id of ['start','word-start','watch-sentences','url','file','mode','language','model','asr-language','tab-youtube','tab-file']) $(id).disabled = value || ['mode','language'].includes(id) || (source==='youtube'&&id==='asr-language');
  $('start').firstElementChild.textContent = value ? '正在整理，请稍候…' : '生成字幕，进入学习页';
  $('word-start').setAttribute('aria-busy',String(value));
}
function status(job) {
  $('status-card').classList.toggle('busy',['queued','running'].includes(job.status));
  $('status-card').classList.toggle('error',job.status === 'error');
  $('status-title').textContent = ({queued:'已加入队列',running:'正在处理',done:'整理完成',error:'需要处理'})[job.status] || '准备就绪';
  $('status-message').textContent = job.message;
  const phase = job.stage === 'done' ? 3 : ['exporting','chinese','translating','word','desktop'].includes(job.stage) ? 2 : ['captions','audio','model','recognizing'].includes(job.stage) ? 1 : 0;
  ['step-input','step-captions','step-export'].forEach((id,index) => {
    $(id).classList.toggle('active',index === phase && job.status !== 'error');
    $(id).classList.toggle('complete',index < phase);
  });
  $('recognition-progress').hidden = !(job.stage === 'recognizing' && job.duration) && !(job.stage === 'translating' && job.translation_total);
  if (job.stage === 'recognizing' && job.duration) $('recognition-progress').textContent = `已识别 ${formatTime(job.processed)} / ${formatTime(job.duration)}`;
  if (job.stage === 'translating' && job.translation_total) $('recognition-progress').textContent = `已翻译 ${job.translated} / ${job.translation_total} 段`;
}
function resultView(result) {
  if(typeof window!=='undefined'&&window.WatchSync?.accepts?.(result)===false)return;
  if(result.url)youtubeResult=result;
  if(typeof window!=='undefined')window.WatchSync?.result(result);
  if(typeof window!=='undefined') {
    if(result.url&&result.sentence_version!==1)window.OriginalShadowing?.reset();
    else window.OriginalShadowing?.showResult(result);
  }
  $('result-title').textContent = result.title;
  const items = [sources[result.source] || result.source, `${result.count} 原字幕片段`, result.sentence_count?`${result.sentence_count} 句中英对照`:'',result.language ? `语言：${result.language}` : '', result.model ? `模型：${result.model}` : ''];
  $('result-meta').replaceChildren(...items.filter(Boolean).map(text => {const span = document.createElement('span');span.textContent = text;return span;}));
  $('result-warning').textContent = result.warning;
  $('output-path').textContent = result.output_dir;
  $('desktop-result').hidden = !result.desktop_path;
  $('desktop-result').textContent = result.desktop_path ? `已保存桌面：${result.desktop_path}（完整中英对照，无需再点下载）` : '';
  $('word-download').hidden = !result.files?.docx;
  const fragment = document.createDocumentFragment();
  for (const cue of result.url&&result.sentence_version!==1 ? [] : result.bilingual_preview || result.preview) {
    const row = document.createElement('div'); row.className = 'cue-row';
    const time = document.createElement('span'); time.className = 'cue-time'; time.textContent = formatTime(cue.start) + ' → ' + formatTime(cue.end);
    const text = document.createElement('span'); text.className = 'cue-text'; text.textContent = cue.english || cue.text;
    if (cue.chinese) {const chinese = document.createElement('span');chinese.className='cue-chinese';chinese.textContent=cue.chinese;text.append(chinese);}
    row.append(time,text); fragment.append(row);
  }
  $('preview').replaceChildren(fragment);
  const total = result.bilingual_count || result.count;
  $('preview-note').textContent = result.desktop_path ? `Word 包含全部 ${total} 组中英对照；此处最多显示前 200 组。中文来源：${result.chinese_source}。` : result.count > 200 ? `这里预览前 200 段；完整 ${result.count} 段原文已保存在下方的本机文件夹中。` : '完整原文已保存在下方的本机文件夹中。';
  $('results').hidden = false;
  $('results').scrollIntoView({behavior:'smooth',block:'start'});
}
async function prepareSentenceResult() {
  if(!requireTranslationConsent())throw Error('尚未确认 Google 公共网页翻译的文字发送说明。');
  const id=window.WatchSync?.resultId();if(!id)throw Error('请先生成或恢复当前视频字幕。');
  window.WatchSync?.pause();window.OriginalShadowing?.reset();
  let job=await(await api(`/api/jobs/${id}/sentences`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
  while(['queued','running'].includes(job.status)) {
    status({status:'running',stage:job.stage||'sentences',message:job.message,translated:job.translated,translation_total:job.translation_total});
    await new Promise(resolve=>setTimeout(resolve,900));
    job=await(await api(`/api/jobs/${id}/sentences`)).json();
  }
  if(job.status!=='done')throw Error(job.message||'逐句整理尚未完成。');
  rememberJob(id);resultView(job.result);return job.result;
}
$('watch-sentences').addEventListener('click',async()=>{
  if(busy||!requireTranslationConsent())return;showError('');setBusy(true);lockNavigation(true);
  try{await prepareSentenceResult();status({status:'done',stage:'done',message:'逐句中英对照已完成，每句配对应译文。'});}
  catch(error){showError(error.message);status({status:'error',message:error.message});}
  finally{setBusy(false);lockNavigation(false);}
});
async function poll(jobId) {
  let failures = 0;
  while (!stopped) {
    try {
      const response = await api('/api/jobs/' + jobId);
      const job = await response.json(); failures = 0; status(job);
      if (job.status === 'done') {resultView(job.result); return;}
      if (job.status === 'error') throw Object.assign(new Error(job.message),{terminal:true});
    } catch (error) {
      if (error.terminal || ++failures >= 3) throw error;
      $('status-message').textContent = '与本地工具的连接暂时中断，正在重试…';
    }
    await new Promise(resolve => setTimeout(resolve,900));
  }
}
$('word-start').addEventListener('click',async () => {
  if (busy) return;
  const url = $('url').value.trim();
  if (!url) return showError('请先粘贴一条英文 YouTube 视频链接。');
  const cached=typeof window!=='undefined'&&window.WatchSync?.canExport?.(url)&&window.WatchSync?.isSentence?.()!==false;
  if(!cached&&!requireTranslationConsent())return;
  showError('');setBusy(true);lockNavigation(true);$('results').hidden=true;
  status({status:'running',stage:'metadata',message:'正在创建中英 Word 任务；完成后自动保存到桌面。'});
  try {
    if(typeof window!=='undefined'&&window.WatchSync?.isSentence?.()===false&&window.WatchSync.resultId())await prepareSentenceResult();
    const cachedId=typeof window!=='undefined'&&window.WatchSync?.canExport(url)?window.WatchSync.resultId():null;
    if(cachedId){
      const result=await(await api(`/api/jobs/${cachedId}/word`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
      rememberJob(result.id);lockNavigation(false);resultView(result);status({status:'done',stage:'done',message:'中英 Word 已保存桌面；使用已有全文，没有重复提取或翻译。'});return;
    }
    if(typeof window!=='undefined')window.WatchSync?.beginTask(url);
    const job = await (await api('/api/word-jobs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url,model:$('model').value})})).json();
    rememberJob(job.id);lockNavigation(false);
    await poll(job.id);
  } catch(error) {
    showError(error.message || 'Word 任务失败，请检查本地工具是否仍在运行。');
    status({status:'error',stage:'error',message:error.message || '本地连接中断。'});
  } finally {lockNavigation(false);setBusy(false);}
});
$('task-form').addEventListener('submit',async event => {
  event.preventDefault(); if (busy) return;
  showError('');
  let data = {source,options:{mode:source === 'file' ? 'auto' : $('mode').value,language:$('language').value,asr_language:$('asr-language').value,model:$('model').value}};
  const file = $('file').files[0];
  if (source === 'youtube') {data.url = $('url').value.trim(); if (!data.url) return showError('请先粘贴一条视频链接。');}
  else if (!file) return showError('请先选择一个本地文件。');
  else if (file.size > 500 * 1024 * 1024) return showError('文件超过 500 MiB，请先缩小或截取。');
  if(source==='youtube'&&!requireTranslationConsent())return;
  setBusy(true); lockNavigation(true); $('results').hidden = true;
  if(typeof window!=='undefined')window.WatchSync?.beginTask(source==='youtube'?data.url:'');
  status({status:'running',stage:'upload',message:source === 'file' ? '正在将文件导入本机工作区，不会上传到互联网。' : '正在创建任务。'});
  try {
    if (source === 'file') {
      const upload = await (await api('/api/uploads',{method:'POST',body:file,headers:{'X-File-Name':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'}})).json();
      data.upload_id = upload.upload_id;
    }
    const endpoint=source==='youtube'?'/api/study-jobs':'/api/jobs';
    const payload=source==='youtube'?{url:data.url,model:$('model').value}:data;
    const job = await (await api(endpoint,{method:'POST',body:JSON.stringify(payload),headers:{'Content-Type':'application/json'}})).json();
    rememberJob(job.id);
    lockNavigation(false);
    await poll(job.id);
  } catch (error) {
    showError(error.message || '连接失败，请确认工具仍在运行。');
    status({status:'error',stage:'error',message:error.message || '本地连接中断。'});
  } finally {lockNavigation(false);setBusy(false);}
});
document.querySelectorAll('[data-format]').forEach(button => button.addEventListener('click',async () => {
  if (!currentJob) return;
  const format = button.dataset.format;
  button.disabled = true;
  try {
    const response = await api(`/api/jobs/${currentJob}/files/${format}`);
    const disposition = response.headers.get('Content-Disposition') || '';
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/)?.[1];
    const blob = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');link.href = blob;link.download = encoded ? decodeURIComponent(encoded) : `subtitles.${format}`;document.body.append(link);link.click();link.remove();setTimeout(() => URL.revokeObjectURL(blob),30000);
  } catch(error) {showError(error.message);}
  finally {button.disabled = false;}
}));
$('shutdown').addEventListener('click',async () => {
  if (busy) return showError('当前任务尚未完成，请完成后再关闭。');
  if (!confirm('关闭本地字幕工具？已导出的文件会保留。')) return;
  try {const result = await (await api('/api/shutdown',{method:'POST'})).json(); stopped = true;showError('');status({status:'done',stage:'done',message:result.message});setBusy(true);$('shutdown').disabled = true;} catch(error) {showError(error.message);}
});
const linkedJob = typeof window!=='undefined' ? new URLSearchParams(window.location.search).get('job') : null;
if(typeof window!=='undefined')window.SubtitleApp={canNavigate:()=>!busy&&!navigationLocked};
const previousJob = linkedJob && /^[a-f0-9]{32}$/.test(linkedJob) ? linkedJob : sessionStorage.getItem('subtitle-job');
if (previousJob && /^[a-f0-9]{32}$/.test(previousJob)) {
  setBusy(true);
  (async () => {
    try {
      const job = await (await api('/api/jobs/' + previousJob)).json();currentJob = previousJob;status(job);
      if (job.status === 'done') resultView(job.result);
      else if (['queued','running'].includes(job.status)) {setBusy(true);await poll(previousJob);}
    } catch {} finally {setBusy(false);}
  })();
}
