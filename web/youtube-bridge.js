/* Runs only in the separate, unprivileged VideoBridge origin. */
(function () {
  'use strict';
  const win = window;
  const doc = document;
  const status = doc.getElementById('bridge-status');
  const meta = name => doc.querySelector('meta[name="' + name + '"]')?.content;
  const appOrigin = meta('bridge-app-origin');
  const videoId = meta('bridge-video-id');
  const channel = meta('bridge-channel');
  const exactMatch = (pattern, value) => typeof value === 'string' && pattern.exec(value)?.[0] === value;
  const originMatch = typeof appOrigin === 'string' && /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})$/.exec(appOrigin);
  if (!originMatch || originMatch[0] !== appOrigin || Number(originMatch[1]) > 65535 ||
      appOrigin === win.location.origin || win.parent === win ||
      !exactMatch(/^[A-Za-z0-9_-]{11}$/, videoId) ||
      !exactMatch(/^[A-Za-z0-9_-]{16,}$/, channel)) {
    status.textContent = 'Invalid player configuration.';
    return;
  }

  let player = null;
  let ready = false;
  let failed = false;
  let disposed = false;
  let sampleTimer = null;
  let startupTimer = null;
  let sdkStarted = false;
  const selectableRates=[.75,1,1.25,1.5,2],publicRates=[.25,.5,.75,1,1.25,1.5,1.75,2];
  let preferredRate=1,requestedRate=null,restoreRate=null,beforeStartRate=null,rateTimer=null,playbackKey='';

  // Do not forward SDK event objects, DOM nodes, URLs or exception messages.
  function publish(event, fields = {}) {
    if (!disposed) win.parent.postMessage({channel, event, videoId, ...fields}, appOrigin);
  }

  function stopStartupTimer() {
    if (startupTimer !== null) win.clearTimeout(startupTimer);
    startupTimer = null;
  }

  function stopSampling() {
    if (sampleTimer !== null) win.clearInterval(sampleTimer);
    sampleTimer = null;
  }

  function clearRateRequest(){
    if(rateTimer!==null)win.clearTimeout(rateTimer);
    rateTimer=null;requestedRate=null;
  }

  function playback(force=false){
    try{
      const rate=player.getPlaybackRate(),available=player.getAvailablePlaybackRates();
      if(!publicRates.includes(rate)||!Array.isArray(available))return null;
      const rates=publicRates.filter(value=>available.includes(value)),key=JSON.stringify([rate,rates]);
      if(requestedRate===rate)clearRateRequest();
      if(requestedRate===null&&restoreRate===null&&beforeStartRate===null)preferredRate=rate;
      if(force||key!==playbackKey){playbackKey=key;publish('playback',{rate,rates});}
      return {rate,rates};
    }catch{return null;}
  }

  function changeRate(rate){
    try{
      const snapshot=playback();
      if(!snapshot||!snapshot.rates.includes(rate)){
        playback(true);publish('rate-error',{errorCode:snapshot?'RATE_UNSUPPORTED':'RATE_UNAVAILABLE'});return;
      }
      clearRateRequest();preferredRate=rate;requestedRate=rate;
      if(beforeStartRate!==null||[-1,0,5].includes(player.getPlayerState()))beforeStartRate=rate;
      if(restoreRate!==null)restoreRate=rate;
      rateTimer=win.setTimeout(()=>{
        const expected=requestedRate;
        rateTimer=null;requestedRate=null;const snapshot=playback(true);
        if(snapshot?.rate!==expected)publish('rate-error',{errorCode:'RATE_UNCONFIRMED'});
      },2000);
      player.setPlaybackRate(rate);playback(true);
    }catch{
      clearRateRequest();playback(true);publish('rate-error',{errorCode:'RATE_UNAVAILABLE'});
    }
  }

  function fail(errorCode) {
    if (disposed || failed) return;
    failed = true;
    ready = false;
    stopStartupTimer();
    stopSampling();
    clearRateRequest();
    status.textContent = typeof errorCode === 'number'
      ? 'YouTube could not play this video (error ' + errorCode + ').'
      : errorCode.endsWith('TIMEOUT') ? 'YouTube player timed out (' + errorCode + ').'
        : 'YouTube player failed (' + errorCode + ').';
    publish('error', {errorCode});
  }

  function armStartupTimeout(code) {
    stopStartupTimer();
    startupTimer = win.setTimeout(() => fail(code), 15000);
  }

  function sample() {
    if (!ready || failed || disposed) return;
    try {
      const time = player.getCurrentTime();
      if (Number.isFinite(time) && time >= 0) publish('time', {time});
      playback();
    } catch (_) {
      fail('PLAYER_ERROR');
    }
  }

  function onMessage(event) {
    const data = event.data;
    if (disposed || failed || !ready || event.source !== win.parent || event.origin !== appOrigin ||
        !data || typeof data !== 'object' || Array.isArray(data) || data.channel !== channel ||
        !['seek', 'pause', 'play','rate'].includes(data.command)) return;
    if(data.command==='rate'){
      if(selectableRates.includes(data.rate))changeRate(data.rate);
      return;
    }
    try {
      if (data.command === 'play') {
        if(player.getPlayerState()!==1)restoreRate=preferredRate;
        player.playVideo();
      } else if (data.command === 'pause') {
        player.pauseVideo();
      } else {
        const seconds = data.seconds;
        if (!Number.isFinite(seconds) || seconds < 0 || seconds > 604800) return;
        const state = player.getPlayerState();
        if (state === -1 || state === 5 || state === 0) {
          // seekTo on an unstarted player may start playback. Cue instead.
          restoreRate=preferredRate;
          player.cueVideoById({videoId, startSeconds: seconds});
        } else {
          player.seekTo(seconds, true);
          if (state !== 1 && state !== 3) player.pauseVideo();
        }
        sample();
      }
    } catch (_) {
      fail('PLAYER_ERROR');
    }
  }

  function startPlayer() {
    if (sdkStarted || failed || disposed) return;
    if (!win.YT || typeof win.YT.Player !== 'function') {
      fail('SDK_LOAD_ERROR');
      return;
    }
    sdkStarted = true;
    armStartupTimeout('PLAYER_TIMEOUT');
    try {
      player = new win.YT.Player('player', {
        host: 'https://www.youtube-nocookie.com',
        width: '100%', height: '100%', videoId,
        playerVars: {autoplay: 0, controls: 1, playsinline: 1, origin: win.location.origin},
        events: {
          onReady(event) {
            if (ready || failed || disposed) return;
            player = event.target;
            stopStartupTimer();
            const iframe = player.getIframe();
            iframe.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
            iframe.setAttribute('title', 'YouTube video player');
            ready = true;
            status.textContent = '';
            publish('ready');
            // A new video starts at 1x, not the SDK's remembered speed.
            // Keep this through first play; later explicit rate choices replace it.
            beforeStartRate=1;
            const initialPlayback=playback(true);
            if(initialPlayback&&initialPlayback.rate!==1)changeRate(1);
            sampleTimer = win.setInterval(sample, 150);
          },
          onStateChange(event) {
            if (!ready || failed || disposed || ![-1, 0, 1, 2, 3, 5].includes(event.data)) return;
            // Leave the actual player and its controls unobstructed.
            if (event.data === 1) status.textContent = '';
            if(event.data===1){if(restoreRate===null)restoreRate=beforeStartRate;beforeStartRate=null;}
            if((event.data===5||event.data===1)&&restoreRate!==null){const rate=restoreRate;restoreRate=null;changeRate(rate);}
            publish('state', {state: event.data});
            sample();
          },
          onError(event) {
            fail(Number.isInteger(event.data) ? event.data : 'PLAYER_ERROR');
          },
          onPlaybackRateChange(){
            if(!ready||failed||disposed)return;
            if(requestedRate===null&&restoreRate===null&&[-1,0,5].includes(player.getPlayerState())){
              const rate=player.getPlaybackRate();
              if(publicRates.includes(rate)){preferredRate=rate;beforeStartRate=rate;}
            }
            playback(true);
          },
          onAutoplayBlocked() {
            // A browser gesture restriction is recoverable via native controls.
            if (ready && !failed && !disposed) publish('blocked', {errorCode:'AUTOPLAY_BLOCKED'});
          }
        }
      });
    } catch (_) {
      fail('PLAYER_ERROR');
    }
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    ready = false;
    stopStartupTimer();
    stopSampling();
    clearRateRequest();
    win.removeEventListener('message', onMessage);
    win.removeEventListener('pagehide', dispose);
    win.onYouTubeIframeAPIReady = null;
    try { if (player) player.destroy(); } catch (_) { /* Already removed by the browser. */ }
  }

  win.addEventListener('message', onMessage);
  win.addEventListener('pagehide', dispose);
  win.onYouTubeIframeAPIReady = startPlayer;
  if (win.YT && typeof win.YT.Player === 'function') {
    startPlayer();
  } else {
    armStartupTimeout('SDK_TIMEOUT');
    const script = doc.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    script.referrerPolicy = 'strict-origin-when-cross-origin';
    script.onerror = () => fail('SDK_LOAD_ERROR');
    doc.head.appendChild(script);
  }
})();
