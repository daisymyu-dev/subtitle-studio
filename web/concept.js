'use strict';
const previewCore=window.StudyPreview;
const byId=id=>document.getElementById(id);
const audio=byId('lesson-audio');
const terms={
  compelling:{line:0,title:'compelling',category:'表达升级',meaning:'有说服力的；让人愿意相信或继续关注的。',note:'修饰 story 时，强调它吸引人、令人信服；不等同于这个故事已经得到事实证实。',pattern:'a compelling story / argument'},
  bandwagon:{line:2,title:'jump on the bandwagon',category:'地道词块',meaning:'看到一件事流行起来后，也跟着加入。',note:'常带“随大流、跟风”的意味，不只是普通的参加。',pattern:'jump on the bandwagon'},
  priced:{line:2,title:'price in',category:'金融语境',meaning:'将某个因素或预期，提前反映在价格中。',note:'这里 priced in 是过去分词，意思不是“定价进去”。重点是价格已经反映了什么。',pattern:'be already priced in'},
  perspective:{line:3,title:'put … into perspective',category:'语境表达',meaning:'放在更大的背景中看，理解其相对重要性。',note:'把一个细节放回整体，判断它到底有多重要；不是字面上的“放进视角”。',pattern:'put something into perspective'}
};
let currentLine=2;
let currentTerm='priced';
let chineseVisible=true;
let saved=[];
try{const stored=JSON.parse(localStorage.getItem('study-design-demo-saved')||'[]');if(Array.isArray(stored))saved=[...new Set(stored.filter(id=>Object.hasOwn(terms,id)))];}catch{}

for(const link of document.querySelectorAll('[data-view]')){
  if(link.dataset.view===document.body.dataset.study)link.setAttribute('aria-current','page');
}
function updatePlayState(){
  const playing=!audio.paused&&!audio.ended;
  byId('play-symbol').textContent=playing?'Ⅱ':'▶';
  byId('play-pause').setAttribute('aria-label',playing?'暂停示范音频':'播放示范音频');
}
function updateTime(){
  byId('current-time').textContent=previewCore.formatTime(audio.currentTime);
  byId('total-time').textContent=Number.isFinite(audio.duration)?previewCore.formatTime(audio.duration):'--:--';
  byId('audio-progress').value=previewCore.progress(audio.currentTime,audio.duration);
}
function selectLine(index,resume=false){
  currentLine=previewCore.moveIndex(index,0,4);
  audio.pause();
  audio.src=`/demo/audio/${String(currentLine).padStart(2,'0')}.wav`;
  audio.playbackRate=Number(byId('playback-rate').value);
  for(const row of document.querySelectorAll('[data-line-index]'))row.classList.toggle('active',Number(row.dataset.lineIndex)===currentLine);
  for(const button of document.querySelectorAll('[data-select-line]')){
    const active=Number(button.dataset.selectLine)===currentLine;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',String(active));
  }
  byId('line-counter').textContent=`${String(currentLine+1).padStart(2,'0')} / 04`;
  byId('previous-line').disabled=currentLine===0;
  byId('next-line').disabled=currentLine===3;
  byId('audio-message').textContent='点播放，听当前句的合成示范。';
  updateTime();
  if(resume)playAudio();
}
async function playAudio(){
  try{await audio.play();byId('audio-message').textContent='正在播放合成示范，非视频原声。';}
  catch{byId('audio-message').textContent='音频暂时无法播放，请稍后重试。';}
}
function updateSaved(){
  const active=saved.includes(currentTerm);
  byId('save-word').textContent=active?'✓ 已收藏':'＋ 收藏表达';
  byId('save-word').setAttribute('aria-pressed',String(active));
  byId('saved-count').textContent=String(saved.length);
}
function selectTerm(id){
  if(!Object.hasOwn(terms,id))return;
  const term=terms[id];
  currentTerm=id;
  if(term.line!==currentLine)selectLine(term.line);
  byId('vocab-title').textContent=term.title;
  byId('vocab-category').textContent=term.category;
  byId('vocab-meaning').textContent=term.meaning;
  byId('vocab-note').textContent=term.note;
  byId('vocab-pattern').textContent=term.pattern;
  for(const button of document.querySelectorAll('[data-term]')){
    const selected=button.dataset.term===id;
    button.classList.toggle('selected',selected);
    button.setAttribute('aria-pressed',String(selected));
  }
  byId('vocab-feedback').textContent=term.title+'：'+term.meaning;
  updateSaved();
}
for(const button of document.querySelectorAll('[data-select-line]'))button.addEventListener('click',()=>selectLine(Number(button.dataset.selectLine)));
for(const button of document.querySelectorAll('[data-term]'))button.addEventListener('click',()=>selectTerm(button.dataset.term));
byId('play-pause').addEventListener('click',()=>audio.paused||audio.ended?playAudio():audio.pause());
byId('previous-line').addEventListener('click',()=>selectLine(previewCore.moveIndex(currentLine,-1,4)));
byId('next-line').addEventListener('click',()=>selectLine(previewCore.moveIndex(currentLine,1,4)));
byId('playback-rate').addEventListener('change',()=>{audio.playbackRate=Number(byId('playback-rate').value);});
byId('audio-progress').addEventListener('input',()=>{if(Number.isFinite(audio.duration))audio.currentTime=audio.duration*Number(byId('audio-progress').value)/1000;});
byId('translation-toggle').addEventListener('click',()=>{
  chineseVisible=!chineseVisible;
  for(const translation of document.querySelectorAll('.chinese'))translation.hidden=!chineseVisible;
  byId('translation-toggle').textContent=chineseVisible?'隐藏中文 ◐':'显示中文 ◑';
  byId('translation-toggle').setAttribute('aria-pressed',String(chineseVisible));
  document.body.classList.toggle('english-only',!chineseVisible);
});
byId('replay-phrase').addEventListener('click',()=>{selectLine(terms[currentTerm].line);playAudio();});
byId('save-word').addEventListener('click',()=>{saved=previewCore.toggleSaved(saved,currentTerm,Object.keys(terms));try{localStorage.setItem('study-design-demo-saved',JSON.stringify(saved));}catch{}updateSaved();});
audio.addEventListener('loadedmetadata',updateTime);
audio.addEventListener('timeupdate',updateTime);
audio.addEventListener('play',updatePlayState);
audio.addEventListener('pause',()=>{updatePlayState();if(!audio.ended&&audio.currentTime>0)byId('audio-message').textContent='示范音频已暂停。';});
audio.addEventListener('ended',()=>{updatePlayState();byId('audio-message').textContent='当前句播放结束，可以再听一次。';});
audio.addEventListener('error',()=>{byId('audio-message').textContent='示范音频暂时不可用。文字和版式仍可预览。';updatePlayState();});
selectLine(currentLine);
selectTerm(currentTerm);
