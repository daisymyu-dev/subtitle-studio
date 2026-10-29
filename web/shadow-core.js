(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ShadowCore=api;})(typeof window!=='undefined'?window:this,function(){
  'use strict';
  const pageFor=(index,size=50)=>Math.max(0,Math.floor(index/size));
  class ShadowPlayer {
    constructor(audio,options={}) {
      this.audio=audio;this.setTimer=options.setTimer||((fn,ms)=>setTimeout(fn,ms));this.clearTimer=options.clearTimer||(id=>clearTimeout(id));
      this.beforePlay=options.beforePlay;
      this.onState=options.onState||(()=>{});this.cue=null;this.phase='idle';this.loop=false;this.gap='auto';this.rate=1;
      this.timer=null;this.epoch=0;this.audio.preservesPitch=true;
    }
    emit(){this.onState({phase:this.phase,loop:this.loop,rate:this.rate,cue:this.cue});}
    clear(){if(this.timer!==null)this.clearTimer(this.timer);this.timer=null;}
    pause(){this.epoch++;this.clear();this.audio.pause();this.phase='paused';this.emit();}
    reset(){this.pause();this.cue=null;this.phase='idle';this.emit();}
    select(cue){
      if(!cue||!Number.isFinite(cue.start)||!Number.isFinite(cue.end)||cue.start<0||cue.end<=cue.start)throw Error('字幕时间轴无效。');
      this.pause();this.cue=cue;this.phase='idle';this.emit();
    }
    setLoop(value){this.loop=Boolean(value);if(!this.loop&&this.phase==='following')this.clear();this.emit();}
    setGap(value){if(value!=='auto'&&![0,2,4,6].includes(Number(value)))throw Error('无效跟读间隔。');this.gap=value==='auto'?'auto':Number(value);}
    setRate(value){value=Number(value);if(![.5,.75,1,1.25].includes(value))throw Error('无效播放速度。');this.rate=value;this.audio.playbackRate=value;this.audio.preservesPitch=true;if(this.phase==='playing')this.scheduleEnd();this.emit();}
    end(){return Math.min(this.cue.end,Number.isFinite(this.audio.duration)?this.audio.duration:this.cue.end);}
    scheduleEnd(){
      this.clear();const epoch=this.epoch;
      const remaining=Math.max(0,(this.end()-this.audio.currentTime)/this.rate*1000);
      this.timer=this.setTimer(()=>{this.timer=null;if(epoch!==this.epoch||this.phase!=='playing')return;this.tick();if(this.phase==='playing')this.scheduleEnd();},Math.max(20,remaining));
    }
    async play(){
      if(!this.cue)throw Error('请先选择字幕片段。');
      this.pause();
      const epoch=this.epoch;this.phase='loading';this.emit();
      try {
        if(this.beforePlay)await this.beforePlay();if(epoch!==this.epoch)return;
        if(this.cue.start>=this.end())throw Error('此字幕片段超出了原音长度，请核对时间轴。');
        this.audio.currentTime=this.cue.start;this.audio.playbackRate=this.rate;
        await this.audio.play();if(epoch!==this.epoch)return;
        this.phase='playing';this.emit();this.scheduleEnd();
      } catch(error) {
        if(epoch!==this.epoch)return;
        this.clear();this.audio.pause();this.phase='error';this.emit();throw error;
      }
    }
    tick(){if(this.phase==='playing'&&this.audio.currentTime>=this.end()-.015)this.finish();}
    finish(){
      if(this.phase!=='playing')return;
      this.clear();this.audio.pause();this.phase='following';this.emit();
      if(this.loop){
        const gap=this.gap==='auto'?Math.min(30,Math.max(2,(this.end()-this.cue.start)/this.rate)):this.gap;
        const epoch=this.epoch;
        this.timer=this.setTimer(()=>{this.timer=null;if(this.loop&&this.phase==='following'&&epoch===this.epoch)this.play().catch(()=>{});},gap*1000);
      }
    }
  }
  return {ShadowPlayer,pageFor};
});
