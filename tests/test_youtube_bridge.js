'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const scriptPath = path.join(__dirname, '../web/youtube-bridge.js');
const implemented = fs.existsSync(scriptPath);
const VIDEO = 'BaW_jenozKc';
const CHANNEL = '9b02f4a31de248218f7c739fd063be18';
const APP = 'http://127.0.0.1:8765';
const ORIGIN = 'http://127.0.0.1:31337';

test('Task A has an isolated child player script', () => {
  assert.ok(implemented, 'youtube-bridge.js must implement the child boundary');
});

function fixture(overrides = {}, prepare = () => {}) {
  const metas = {'bridge-app-origin': APP, 'bridge-video-id': VIDEO,
    'bridge-channel': CHANNEL, ...overrides};
  const messages = [], scripts = [], calls = [], listeners = new Map(), timers = new Map();
  let serial = 0, player, options;
  const status = {textContent: ''};
  const iframe = {setAttribute(name, value) {this[name] = value;}};
  const parent = {postMessage(data, origin) {messages.push({data: JSON.parse(JSON.stringify(data)), origin});}};
  const win = {parent, location: {origin: ORIGIN},
    addEventListener(name, fn) {listeners.set(name, fn);},
    removeEventListener(name, fn) {if (listeners.get(name) === fn) listeners.delete(name);},
    setTimeout(fn, ms) {timers.set(++serial, {fn, ms, repeat: false}); return serial;},
    clearTimeout(id) {timers.delete(id);},
    setInterval(fn, ms) {timers.set(++serial, {fn, ms, repeat: true}); return serial;},
    clearInterval(id) {timers.delete(id);}};
  const doc = {
    querySelector(selector) {const name = selector.match(/name=["']([^"']+)/)?.[1];
      return name in metas ? {content: metas[name]} : null;},
    getElementById(id) {return id === 'bridge-status' ? status : {};},
    createElement() {return {setAttribute(name, value) {this[name] = value;}};},
    head: {appendChild(element) {scripts.push(element);}}};
  const f = {win, doc, messages, scripts, calls, status, listeners, timers, iframe,
    installYT() {
      win.YT = {PlayerState: {UNSTARTED: -1, ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3, CUED: 5},
        Player: function(id, config) {
          options = config;
          calls.push(['construct', id]);
          player = {state: -1, time: 0, rate:1, rates:[.25,.5,.75,1,1.25,1.5,1.75,2],
            getPlayerState() {return this.state;}, getCurrentTime() {return this.time;},
            getPlaybackRate(){return this.rate;},getAvailablePlaybackRates(){return this.rates;},
            setPlaybackRate(rate){calls.push(['setPlaybackRate',rate]);this.rate=rate;},
            getIframe() {return iframe;},
            seekTo(seconds, allowSeekAhead) {calls.push(['seekTo', seconds, allowSeekAhead]); this.time = seconds;},
            cueVideoById(spec) {calls.push(['cueVideoById', spec]); this.time = spec.startSeconds; this.state = 5;this.rate=1;},
            pauseVideo() {calls.push(['pauseVideo']); this.state = 2;},
            playVideo() {calls.push(['playVideo']); this.state = 1;},
            destroy() {calls.push(['destroy']);}};
          return player;
        }};
    },
    sdkReady() {f.installYT(); win.onYouTubeIframeAPIReady();},
    ready() {options.events.onReady({target: player});},
    state(value) {player.state = value; options.events.onStateChange({target: player, data: value});},
    error(code) {options.events.onError({target: player, data: code});},
    send(data, other = {}) {listeners.get('message')?.({source: parent, origin: APP,
      data: {channel: CHANNEL, ...data}, ...other});},
    runTimers(ms) {for (const [id, timer] of [...timers]) {
      if (timer.ms !== ms || !timers.has(id)) continue;
      if (!timer.repeat) timers.delete(id); timer.fn();
    }},
    get player() {return player;}, get options() {return options;}};
  prepare(f);
  vm.runInNewContext(fs.readFileSync(scriptPath, 'utf8'), {window: win, document: doc, URL, Number, Object});
  return f;
}

const bridgeTest = (name, fn) => test(name, {skip: !implemented}, fn);

bridgeTest('only the official SDK is loaded in the isolated document', () => {
  const f = fixture();
  assert.equal(f.scripts.length, 1);
  assert.equal(f.scripts[0].src, 'https://www.youtube.com/iframe_api');
  assert.equal(f.scripts[0].referrerPolicy, 'strict-origin-when-cross-origin');
  assert.deepEqual(f.messages, []);
  f.sdkReady();
  assert.equal(f.options.host, 'https://www.youtube-nocookie.com');
  assert.equal(f.options.videoId, VIDEO);
  assert.equal(f.options.playerVars.origin, ORIGIN);
  assert.equal(f.options.playerVars.autoplay, 0);
  assert.equal(f.options.playerVars.controls, 1);
  f.ready();
  assert.equal(f.calls.filter(c => c[0] === 'playVideo').length, 0);
  assert.equal(f.iframe.referrerpolicy, 'strict-origin-when-cross-origin');
  assert.equal(f.status.textContent, '');
  assert.deepEqual(f.messages[0], {data: {channel: CHANNEL, event: 'ready', videoId: VIDEO}, origin: APP});
});

bridgeTest('commands require the exact parent source, configured origin and channel', () => {
  const f = fixture(); f.sdkReady(); f.ready();
  const before = f.calls.length;
  for (const other of [{source: {}}, {origin: ORIGIN}, {origin: 'https://evil.example'},
    {data: null}, {data: 'play'}, {data: []}, {data: {command: 'play'}},
    {data: {channel: 'wrong', command: 'play'}}]) f.send({command: 'play'}, other);
  for (const command of ['loadVideoById', 'cueVideoById', 'constructor', 'destroy', '__proto__', 'PLAY'])
    f.send({command});
  assert.equal(f.calls.length, before);
  f.send({command: 'play'}); assert.equal(f.player.state, 1);
  f.send({command: 'pause'}); assert.equal(f.player.state, 2);
});

bridgeTest('only finite numeric seek seconds in the supported range are accepted', () => {
  const f = fixture(); f.sdkReady(); f.ready(); f.state(1);
  const before = f.calls.length;
  for (const seconds of [-1, 604801, NaN, Infinity, -Infinity, '10', null, true, {}, undefined])
    f.send({command: 'seek', seconds});
  assert.equal(f.calls.length, before);
  for (const seconds of [0, .125, 604800]) f.send({command: 'seek', seconds});
  assert.equal(f.player.time, 604800);
  assert.equal(f.calls.filter(c => c[0] === 'seekTo').length, 3);
  assert.equal(f.calls.filter(c => c[0] === 'playVideo').length, 0);
});

bridgeTest('seek while paused never plays and seek while playing remains playing', () => {
  const f = fixture(); f.sdkReady(); f.ready(); f.state(2);
  f.send({command: 'seek', seconds: 42.75});
  assert.equal(f.player.time, 42.75); assert.notEqual(f.player.state, 1);
  assert.equal(f.calls.filter(c => c[0] === 'playVideo').length, 0);
  f.state(1); f.send({command: 'seek', seconds: 80});
  assert.equal(f.player.state, 1); assert.equal(f.player.time, 80);
});

bridgeTest('unstarted cued and ended seeks cue without starting playback', () => {
  for (const state of [-1, 5, 0]) {
    const f = fixture(); f.sdkReady(); f.ready(); f.state(state);
    f.send({command: 'seek', seconds: 12});
    assert.equal(f.player.time, 12); assert.notEqual(f.player.state, 1);
    assert.equal(f.calls.filter(c => c[0] === 'seekTo' || c[0] === 'playVideo').length, 0);
  }
});

bridgeTest('commands sent before ready are not queued for later autoplay', () => {
  const f = fixture(); f.send({command: 'play'}); f.sdkReady();
  f.send({command: 'play'}); f.ready();
  assert.equal(f.calls.filter(c => c[0] === 'playVideo').length, 0);
});

bridgeTest('time samples every 150ms and messages disclose public fields only', () => {
  const f = fixture(); f.sdkReady(); f.ready();
  assert.ok([...f.timers.values()].some(t => t.repeat && t.ms === 150));
  f.state(1); f.player.time = 17.25; f.runTimers(150);
  assert.deepEqual(f.messages.at(-1), {origin: APP,
    data: {channel: CHANNEL, event: 'time', videoId: VIDEO, time: 17.25}});
  assert.ok(f.messages.some(m => m.data.event === 'state' && m.data.state === 1));
  for (const message of f.messages) {
    assert.equal(message.origin, APP);
    assert.equal(message.data.channel, CHANNEL);
    assert.equal(message.data.videoId, VIDEO);
    assert.ok(Object.keys(message.data).every(k =>
      ['channel', 'event', 'videoId', 'time', 'state', 'errorCode','rate','rates'].includes(k)));
  }
  const before = f.messages.length;
  f.player.time = NaN; f.runTimers(150);
  f.player.time = Infinity; f.runTimers(150);
  f.player.time = -1; f.runTimers(150);
  assert.equal(f.messages.length, before);
});

bridgeTest('embedding errors keep their actual codes and stop sampling', () => {
  for (const code of [2, 5, 100, 101, 150, 153]) {
    const f = fixture(); f.sdkReady(); f.ready(); f.error(code);
    assert.equal(f.messages.at(-1).data.errorCode, code);
    assert.equal(f.messages.at(-1).data.event, 'error');
    assert.match(f.status.textContent, new RegExp(String(code)));
    assert.equal([...f.timers.values()].filter(t => t.repeat).length, 0);
  }
});

bridgeTest('SDK load failure and timeout are errors, never a false ready status', () => {
  for (const kind of ['load', 'timeout', 'player']) {
    const f = fixture();
    if (kind === 'load') f.scripts[0].onerror();
    else if (kind === 'player') {f.sdkReady(); f.runTimers(15000);}
    else f.runTimers(15000);
    assert.equal(f.messages.at(-1).data.event, 'error');
    assert.equal(f.messages.at(-1).data.errorCode,
      kind === 'load' ? 'SDK_LOAD_ERROR' : kind === 'player' ? 'PLAYER_TIMEOUT' : 'SDK_TIMEOUT');
    assert.ok(!f.messages.some(m => m.data.event === 'ready'));
    assert.match(f.status.textContent, /failed|timed out/i);
  }
});

bridgeTest('a ready SDK is reused and duplicate callbacks cannot create more players or samplers', () => {
  const f = fixture({}, f => f.installYT());
  assert.equal(f.scripts.length, 0);
  f.win.onYouTubeIframeAPIReady(); f.ready(); f.ready();
  assert.equal(f.calls.filter(c => c[0] === 'construct').length, 1);
  assert.equal(f.messages.filter(m => m.data.event === 'ready').length, 1);
  assert.equal([...f.timers.values()].filter(t => t.repeat).length, 1);
  assert.equal([...f.timers.values()].filter(t => !t.repeat).length, 0);
});

bridgeTest('late readiness after failure cannot report success or accept commands', () => {
  const f = fixture(); f.sdkReady(); f.runTimers(15000);
  const before = f.calls.length;
  f.ready(); f.win.onYouTubeIframeAPIReady(); f.send({command: 'play'});
  assert.equal(f.calls.length, before);
  assert.ok(!f.messages.some(m => m.data.event === 'ready'));
  assert.equal(f.timers.size, 0);
});

bridgeTest('unknown SDK error payloads and exceptions never leak data to the parent', () => {
  const f = fixture(); f.sdkReady(); f.ready(); f.error({private: 'do not forward'});
  assert.equal(f.messages.at(-1).data.errorCode, 'PLAYER_ERROR');
  assert.ok(!JSON.stringify(f.messages).includes('do not forward'));
  const g = fixture(); g.sdkReady(); g.ready();
  g.player.getCurrentTime = () => {throw Error('private file path');};
  g.runTimers(150);
  assert.equal(g.messages.at(-1).data.errorCode, 'PLAYER_ERROR');
  assert.ok(!JSON.stringify(g.messages).includes('private file path'));
});

bridgeTest('unknown player states are ignored and browser-blocked play is reported honestly', () => {
  const f = fixture(); f.sdkReady(); f.ready();
  const before = f.messages.length;
  for (const state of ['1', NaN, 99, {}, null]) f.state(state);
  assert.equal(f.messages.length, before);
  f.options.events.onAutoplayBlocked();
  assert.equal(f.messages.at(-1).data.errorCode, 'AUTOPLAY_BLOCKED');
  assert.equal(f.messages.at(-1).data.event, 'blocked');
  assert.ok(f.timers.size > 0);
  f.send({command:'play'});
  assert.equal(f.calls.at(-1)[0], 'playVideo');
});

bridgeTest('ready player leaves all available height for native controls', () => {
  const f=fixture();f.sdkReady();f.ready();assert.equal(f.status.textContent,'');
});

bridgeTest('invalid public metadata never loads the SDK or publishes to an unsafe origin', () => {
  for (const overrides of [{'bridge-app-origin': '*'}, {'bridge-app-origin': 'null'},
    {'bridge-app-origin': 'https://evil.example'}, {'bridge-app-origin': APP + '/path'},
    {'bridge-video-id': VIDEO + '\n'}, {'bridge-video-id': 'bad'},
    {'bridge-channel': 'short'}, {'bridge-channel': CHANNEL + '\n'}]) {
    const f = fixture(overrides);
    assert.equal(f.scripts.length, 0); assert.equal(f.messages.length, 0);
    assert.match(f.status.textContent, /invalid/i);
  }
});

bridgeTest('leaving the child clears timers listeners and the player', () => {
  const f = fixture(); f.sdkReady(); f.ready();
  f.listeners.get('pagehide')();
  assert.equal(f.timers.size, 0); assert.equal(f.listeners.has('message'), false);
  assert.equal(f.calls.filter(c => c[0] === 'destroy').length, 1);
  const before = f.calls.length; f.send({command: 'play'}); f.runTimers(150);
  assert.equal(f.calls.length, before);
});

bridgeTest('each requested rate changes only speed while paused and reports actual speed',()=>{
  const f=fixture();f.sdkReady();f.ready();f.state(2);f.player.time=12;
  for(const rate of [.75,1,1.25,1.5,2]){
    f.send({command:'rate',rate});f.runTimers(150);
    assert.equal(f.player.rate,rate);assert.equal(f.player.state,2);assert.equal(f.player.time,12);
    const snapshot=f.messages.filter(x=>x.data.event==='playback').at(-1);
    assert.equal(snapshot?.data.rate,rate);
  }
  assert.equal(f.calls.filter(x=>x[0]==='playVideo'||x[0]==='seekTo').length,0);
});

bridgeTest('invalid unready and untrusted rate commands never reach the SDK',()=>{
  const f=fixture();f.send({command:'rate',rate:2});f.sdkReady();f.ready();
  for(const rate of ['2',null,NaN,Infinity,0,-1,1.75,3,{}])f.send({command:'rate',rate});
  f.send({command:'rate',rate:2},{origin:'https://evil.example'});
  f.send({command:'rate',rate:2},{source:{}});
  assert.equal(f.calls.filter(x=>x[0]==='setPlaybackRate').length,0);
});

bridgeTest('unsupported or rejected speed does not disable video or falsely confirm success',()=>{
  const f=fixture();f.sdkReady();f.ready();f.player.rates=[1];f.send({command:'rate',rate:2});
  assert.equal(f.calls.filter(x=>x[0]==='setPlaybackRate').length,0);
  assert.equal(f.messages.filter(x=>x.data.event==='rate-error').at(-1)?.data.errorCode,'RATE_UNSUPPORTED');
  f.player.rates=[1,2];f.player.setPlaybackRate=()=>{};f.send({command:'rate',rate:2});f.runTimers(2000);
  assert.equal(f.messages.filter(x=>x.data.event==='playback').at(-1)?.data.rate,1);
  assert.equal(f.messages.filter(x=>x.data.event==='rate-error').at(-1)?.data.errorCode,'RATE_UNCONFIRMED');
  f.send({command:'play'});assert.equal(f.player.state,1);
});

bridgeTest('native rate changes are reflected and paused cue restores the selected speed',()=>{
  const f=fixture();f.sdkReady();f.ready();f.player.rate=1.5;
  assert.equal(typeof f.options.events.onPlaybackRateChange,'function');
  f.options.events.onPlaybackRateChange({data:1.5});
  assert.equal(f.messages.filter(x=>x.data.event==='playback').at(-1)?.data.rate,1.5);
  f.state(5);f.send({command:'seek',seconds:30});f.state(5);f.runTimers(150);
  assert.equal(f.player.rate,1.5);assert.notEqual(f.player.state,1);
  assert.equal(f.calls.filter(x=>x[0]==='playVideo').length,0);
});

bridgeTest('late confirmation at the deadline is not reported as failed',()=>{
  const f=fixture();f.sdkReady();f.ready();f.player.setPlaybackRate=()=>{};
  f.send({command:'rate',rate:2});f.player.rate=2;f.runTimers(2000);
  assert.equal(f.messages.filter(x=>x.data.event==='playback').at(-1)?.data.rate,2);
  assert.equal(f.messages.filter(x=>x.data.event==='rate-error').length,0);
});

bridgeTest('first playback can reset the SDK rate but retains the user-selected speed',()=>{
  const f=fixture();f.sdkReady();f.ready();f.send({command:'rate',rate:2});
  f.player.playVideo=()=>{f.player.rate=1;f.state(3);f.state(1);};
  f.send({command:'play'});f.runTimers(150);
  assert.equal(f.player.rate,2);
});

bridgeTest('native first play also retains a pre-play selection across the SDK reset',()=>{
  const f=fixture();f.sdkReady();f.ready();f.send({command:'rate',rate:2});
  f.player.rate=1;f.state(3);f.state(1);f.runTimers(150);
  assert.equal(f.player.rate,2);
});

bridgeTest('intentional native settings before and after first play are not overridden',()=>{
  const f=fixture();f.sdkReady();f.ready();f.send({command:'rate',rate:2});
  f.player.rate=.75;f.options.events.onPlaybackRateChange({data:.75});
  f.player.rate=1;f.state(3);f.state(1);f.runTimers(150);assert.equal(f.player.rate,.75);
  f.player.rate=1.25;f.options.events.onPlaybackRateChange({data:1.25});f.runTimers(150);
  assert.equal(f.player.rate,1.25);
});

bridgeTest('a new video resets an inherited SDK speed to actual 1x without play or seek',()=>{
  for(const inherited of [.75,1.5,2]){
    const f=fixture();f.sdkReady();f.player.rate=inherited;f.player.time=0;f.ready();
    assert.equal(f.player.rate,1,'reset inherited '+inherited+'x');
    assert.equal(f.messages.filter(x=>x.data.event==='playback').at(-1)?.data.rate,1);
    assert.equal(f.player.time,0);assert.equal(f.player.state,-1);
    assert.equal(f.calls.filter(x=>['playVideo','seekTo','cueVideoById'].includes(x[0])).length,0);
    f.player.rate=2;f.state(3);f.state(1);f.runTimers(150);
    assert.equal(f.player.rate,1,'first native play must retain the new-video default');
  }
});

bridgeTest('first native play keeps 1x even if YouTube reapplies a remembered speed after readiness',()=>{
  const f=fixture();f.sdkReady();f.ready();
  assert.equal(f.calls.filter(x=>x[0]==='playVideo').length,0);
  f.player.rate=2;f.state(3);f.state(1);f.runTimers(150);
  assert.equal(f.player.rate,1);
  f.player.rate=1.5;f.options.events.onPlaybackRateChange({data:1.5});f.runTimers(150);
  assert.equal(f.player.rate,1.5,'later intentional speed choices must still work');
});

bridgeTest('explicit app choices during first buffering replace the default and any pending restore',()=>{
  for(const rate of [.75,1.25,1.5,2]){
    for(const externalPlay of [false,true]){
      const f=fixture();f.sdkReady();f.ready();
      if(externalPlay)f.send({command:'play'});
      f.state(3);f.send({command:'rate',rate});f.state(1);f.runTimers(150);
      assert.equal(f.player.rate,rate,rate+'x while buffering, externalPlay='+externalPlay);
    }
  }
});

bridgeTest('SDK remembered-speed events during initial buffering do not override default 1x',()=>{
  const f=fixture();f.sdkReady();f.ready();f.state(3);
  f.player.rate=2;f.options.events.onPlaybackRateChange({data:2});f.state(1);
  assert.equal(f.player.rate,1);
  const g=fixture();g.sdkReady();g.ready();g.send({command:'rate',rate:2});g.state(3);
  g.player.rate=1;g.options.events.onPlaybackRateChange({data:1});g.state(1);
  assert.equal(g.player.rate,2);
});
