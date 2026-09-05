/* ═══════════════════════════════════════════════════════════════════════════
   Player — 全局播放引擎 + Now Playing 迷你栏 + 全屏播放器面板
   • 真实音频（stream_url / 离线 blob）→ <audio> + Web Audio EQ 图
   • 无音频时用 Web Audio 合成器 pad 生成演示音（EQ·媒体控制·下载均真实可用）
   • Media Session API（锁屏/耳机控制）、A-B 段落循环、睡眠定时器
   • 离线下载（IndexedDB）+ 播放列表（队列）管理 + 均衡器 + 音质设置
   与 Espresso Atelier 设计令牌保持一致。
   ═══════════════════════════════════════════════════════════════════════════ */

const Player = (function () {
  const FREQS = [60, 230, 910, 3000, 14000];
  const EQ_PRESETS = {
    flat:     [0, 0, 0, 0, 0],
    pop:      [-1, 2, 4, 2, -1],
    rock:     [4, 2, -1, 2, 4],
    classical:[3, 1, -1, 1, 3],
    vocal:    [-2, 0, 3, 4, 2],
    bass:     [7, 5, 1, 0, 0],
  };

  const state = {
    queue: [], index: -1, current: null,
    isPlaying: false, position: 0, duration: 0,
    repeat: 'all',          // 'all' | 'one'
    shuffle: false,
    ab: { a: null, b: null, active: false },
    sleep: null,            // { endsAt, timerId }
    audio: null, audioSrc: null,
    synth: null, padGain: null,
    ctx: null, eqNodes: [], eqGain: null,
    offlineUrl: null,
    _downloading: false,
  };
  let ticker = null;
  let _artCache = {};
  const listeners = {};

  function emit(evt, val) {
    (listeners[evt] || []).forEach(fn => fn(val));
    (listeners['*'] || []).forEach(fn => fn(evt, val));
  }
  function on(evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); return () => {
    listeners[evt] = (listeners[evt] || []).filter(f => f !== fn);
  }; }

  function durationOf(h) {
    return (h && h.duration) ? h.duration : (h && h.lyrics ? h.lyrics.length * 4 : 20);
  }

  /* ── Web Audio 图（EQ） ─────────────────────────────────────────────── */
  function ensureCtx() {
    if (!state.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      state.ctx = new AC();
      // EQ 链：lowshelf → peaking×3 → highshelf → master gain → destination
      state.eqNodes = FREQS.map((f, i) => {
        const flt = state.ctx.createBiquadFilter();
        flt.type = i === 0 ? 'lowshelf' : (i === FREQS.length - 1 ? 'highshelf' : 'peaking');
        flt.frequency.value = f;
        flt.Q.value = 0.9;
        flt.gain.value = (AppState.get('eqGains') || EQ_PRESETS.flat)[i] || 0;
        return flt;
      });
      for (let i = 0; i < state.eqNodes.length - 1; i++) state.eqNodes[i].connect(state.eqNodes[i + 1]);
      state.eqGain = state.ctx.createGain();
      state.eqGain.gain.value = 1;
      state.eqNodes[state.eqNodes.length - 1].connect(state.eqGain);
      state.eqGain.connect(state.ctx.destination);
      // 合成器 pad 子增益（仅实时）
      state.padGain = state.ctx.createGain();
      state.padGain.gain.value = 1;
      state.padGain.connect(state.eqNodes[0]);
    }
    if (state.ctx.state === 'suspended') state.ctx.resume();
    return state.ctx;
  }

  function applyEq() {
    const gains = AppState.get('eqGains') || EQ_PRESETS.flat;
    state.eqNodes.forEach((n, i) => { if (n) n.gain.value = gains[i] || 0; });
  }

  /* 基于种子的根音——每首歌稳定的 pad 音色 */
  function seedOf(id) {
    const s = String(id); let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return h;
  }
  function rootFreq(id) {
    const semis = seedOf(id) % 12;       // 0..11 半音
    return 174.61 * Math.pow(2, semis / 12); // 约 F3 附近
  }

  /* ── 音频（真实/离线）路径 ──────────────────────────────────────── */
  function _teardownAudio() {
    if (state.audio) {
      try { if (state.audioSrc) state.audioSrc.disconnect(); } catch (_) {}
      try { state.audio.pause(); } catch (_) {}
      state.audio = null; state.audioSrc = null;
    }
    if (state.offlineUrl) { try { URL.revokeObjectURL(state.offlineUrl); } catch (_) {} state.offlineUrl = null; }
  }

  /* ── 合成器 pad（演示用回退） ──────────────────────────────────────────── */
  function stopSynth() {
    if (state.synth) {
      state.synth.forEach(n => { try { n.stop && n.stop(); } catch (_) {} try { n.disconnect(); } catch (_) {} });
      state.synth = null;
    }
  }
  function startSynth() {
    const ctx = ensureCtx();
    if (!ctx) return;
    stopSynth();
    const root = rootFreq(state.current.id);
    const intervals = [0, 4, 7, 11, 12];   // maj7 + 八度 pad
    const nodes = [];
    const t0 = ctx.currentTime;
    intervals.forEach((semi, i) => {
      const osc = ctx.createOscillator();
      osc.type = i === 3 ? 'triangle' : 'sine';
      osc.frequency.value = root * Math.pow(2, semi / 12);
      const g = ctx.createGain();
      g.gain.value = 0;
      osc.connect(g); g.connect(state.padGain);
      const peak = 0.05 / (i * 0.5 + 1);
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(peak, t0 + 1.2);
      g.gain.setValueAtTime(peak, t0 + Math.max(1.4, state.duration - 1.2));
      osc.start(t0);
      osc.stop(t0 + state.duration + 0.1);
      nodes.push(osc, g);
    });
    // breathing LFO
    const lfo = ctx.createOscillator(); lfo.frequency.value = 0.12;
    const lfoGain = ctx.createGain(); lfoGain.gain.value = 0.25;
    lfo.connect(lfoGain); lfoGain.connect(state.padGain.gain);
    lfo.start(t0); lfo.stop(t0 + state.duration + 0.1);
    nodes.push(lfo, lfoGain);
    state.synth = nodes;
  }

  /* ── OfflineAudioContext → WAV（下载用） ──────────────────────────── */
  async function renderSynthWav(track) {
    const dur = durationOf(track);
    const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!OAC) return null;
    const ctx = new OAC(2, Math.ceil(44100 * dur), 44100);
    const root = rootFreq(track.id);
    const intervals = [0, 4, 7, 11, 12];
    const master = ctx.createGain(); master.gain.value = 0.9; master.connect(ctx.destination);
    intervals.forEach((semi, i) => {
      const osc = ctx.createOscillator();
      osc.type = i === 3 ? 'triangle' : 'sine';
      osc.frequency.value = root * Math.pow(2, semi / 12);
      const g = ctx.createGain(); g.gain.value = 0;
      osc.connect(g); g.connect(master);
      const peak = 0.18 / (i * 0.5 + 1);
      g.gain.setValueAtTime(0, 0);
      g.gain.linearRampToValueAtTime(peak, 1.2);
      g.gain.setValueAtTime(peak, Math.max(1.4, dur - 1.2));
      g.gain.linearRampToValueAtTime(0, dur);
      osc.start(0); osc.stop(dur + 0.05);
    });
    const buf = await ctx.startRendering();
    return encodeWav(buf);
  }

  /* ── Media Session（锁屏/耳机） ──────────────────────────────── */
  function makeArtwork(track) {
    const key = track.id + ':' + (track.cover || '');
    if (_artCache[key]) return _artCache[key];
    try {
      const c = document.createElement('canvas'); c.width = c.height = 256;
      const x = c.getContext('2d');
      const grad = x.createLinearGradient(0, 0, 256, 256);
      const isSermon = track.kind === 'sermon';
      grad.addColorStop(0, isSermon ? '#2E7D56' : '#1F3A2C');
      grad.addColorStop(1, isSermon ? '#16382A' : '#122319');
      x.fillStyle = grad; x.fillRect(0, 0, 256, 256);
      x.fillStyle = 'rgba(201,162,75,.9)';
      x.font = '700 96px "Noto Serif SC", serif';
      x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(track.number != null ? String(track.number) : (isSermon ? '✚' : '♪'), 128, 128);
      const url = c.toDataURL('image/png');
      _artCache[key] = url; return url;
    } catch (_) { return ''; }
  }
  // ── 原生 MediaSession 桥接(Capacitor MediaSession 插件) ──
  // PWA/iOS/无插件时自动降级为网页 navigator.mediaSession(已有逻辑)。
  const NativeMS = (function () {
    const cap = (typeof window !== 'undefined' && window.Capacitor && window.Capacitor.Plugins)
      ? window.Capacitor.Plugins.MediaSession : null;
    const ok = !!cap;
    let started = false;
    function start() { if (!ok || started) return; started = true; try { cap.startService({}); } catch (_) {} }
    function stop() { if (!ok) return; started = false; try { cap.stopService({}); } catch (_) {} }
    function sync(playing, pos, dur) {
      if (!ok) return;
      try { cap.notifyState({ playing: !!playing, position: Math.round((pos || 0) * 1000), duration: Math.round((dur || 0) * 1000) }); } catch (_) {}
    }
    function meta(title, artist, album) {
      if (!ok) return;
      try { cap.updateMetadata({ title: title || '', artist: artist || 'FLOW AI', album: album || '' }); } catch (_) {}
    }
    return { ok, start, stop, sync, meta };
  })();

  function updateMediaSession() {
    if (!('mediaSession' in navigator) || !state.current) return;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: state.current.title,
        artist: state.current.subtitle || (state.current.kind === 'sermon' ? '讲道' : '诗歌'),
        album: state.current.kind === 'sermon' ? '讲道' : '诗歌',
        artwork: [{ src: makeArtwork(state.current), sizes: '256x256', type: 'image/png' }],
      });
    } catch (_) {}
    if (state.current) {
      NativeMS.meta(
        state.current.title,
        state.current.subtitle || (state.current.kind === 'sermon' ? '讲道' : '诗歌'),
        state.current.kind === 'sermon' ? '讲道' : '诗歌'
      );
    }
  }
  function updatePositionState() {
    if (!('mediaSession' in navigator) || !('setPositionState' in navigator.mediaSession) || !state.duration) return;
    try { navigator.mediaSession.setPositionState({ duration: state.duration, position: state.position, playbackRate: 1 }); } catch (_) {}
  }

  /* ── 加载 / 播放 ─────────────────────────────────────────────────────── */
  async function load(hymn, queue, startIndex) {
    const sameId = state.current && hymn.id === state.current.id;
    state.current = hymn;
    state.queue = queue && queue.length ? queue : [hymn];
    const i = startIndex != null ? startIndex : state.queue.findIndex(x => x.id === hymn.id);
    state.index = i >= 0 ? i : 0;
    state.duration = durationOf(hymn);
    if (!sameId) state.position = 0;
    autoQualityByNetwork(); // 按网络自适应音质（无 UI）

    _teardownAudio();
    stopSynth();

    // 优先离线 blob，其次 stream_url，再否则合成器回退
    let url = null;
    try {
      const blob = await OfflineStore.getBlob(hymn.id);
      if (blob) { url = URL.createObjectURL(blob); state.offlineUrl = url; }
    } catch (_) {}
    if (!url && hymn.stream_url) url = hymn.stream_url;

    if (url) {
      state.audio = new Audio();
      state.audio.src = url;
      state.audio.preload = 'metadata';
      state.audio.addEventListener('timeupdate', () => {
        state.position = state.audio.currentTime;
        if (state.audio.duration && !isNaN(state.audio.duration)) state.duration = state.audio.duration;
        checkAb(); emit('tick', state); updatePositionState();
      });
      state.audio.addEventListener('loadedmetadata', () => {
        if (state.audio.duration && !isNaN(state.audio.duration)) { state.duration = state.audio.duration; emit('tick', state); }
      });
      state.audio.addEventListener('ended', () => next(true));
      // U-1：音频加载/播放失败时给用户反馈 + 合成器回退
      state.audio.addEventListener('error', () => {
        console.warn('[Player] 音频加载失败：', state.audio && state.audio.error);
        _teardownAudio();
        ensureCtx();
        startSynth();
        state.isPlaying = true;
        startTicker();
        emit('play', state);
        if (typeof showToast === 'function') showToast('无法加载音频，将播放默想音乐');
      });
      try {
        ensureCtx();
        if (state.ctx) { state.audioSrc = state.ctx.createMediaElementSource(state.audio); state.audioSrc.connect(state.eqNodes[0]); }
      } catch (_) {}
    } else {
      // 合成器回退
      ensureCtx();
    }

    /* 方案 A：播放即静默缓存——真歌(stream_url)首次在线播放后自动写入离线，
       完全无感（不弹 toast、不弹提示），仅安静更新收藏/已下载状态。 */
    if (hymn.stream_url && !OfflineStore.has(hymn.id)) {
      cacheSilently(hymn);
    }

    if (hymn.kind === 'sermon') AppState.addSermonRecent(hymn.id);
    else AppState.addHymnRecent(hymn.id);
    updateMediaSession();
    emit('track', state);
  }

  /* 静默缓存：后台拉取真实音频并写入离线存储，不向用户展示任何进度/完成提示 */
  async function cacheSilently(hymn) {
    try {
      const resp = await fetch(hymn.stream_url);
      if (!resp.ok) return;
      const blob = await resp.blob();
      if (!blob || !blob.size) return;
      await OfflineStore.putBlob(hymn.id, blob);
      AppState.setHymnDownloaded(hymn.id, true);
      // 仅安静刷新列表/迷你栏的“离线”徽标，不弹 toast
      emit('download', { id: hymn.id, downloaded: true, silent: true });
    } catch (_) { /* 离线缓存失败不影响播放 */ }
  }

  function startTicker() {
    stopTicker();
    if (state.audio) return; // 音频由 timeupdate 主导
    let last = performance.now();
    ticker = setInterval(() => {
      const now = performance.now();
      const dt = (now - last) / 1000; last = now;
      if (!state.isPlaying) return;
      state.position += dt;
      if (state.position >= state.duration) { state.position = state.duration; emit('tick', state); next(true); return; }
      checkAb(); emit('tick', state); updatePositionState();
    }, 250);
  }
  function stopTicker() { if (ticker) { clearInterval(ticker); ticker = null; } }

  function play(hymn, queue, startIndex) {
    if (!hymn) return;
    if (state.current && hymn.id === state.current.id && !state.isPlaying) { resume(); return; }
    load(hymn, queue, startIndex).then(() => {
      state.isPlaying = true;
      if (state.audio) state.audio.play().catch(() => {});
      else startSynth();
      startTicker();
      NativeMS.start(); NativeMS.sync(true, state.position, state.duration);
      emit('play', state);
    });
  }
  function resume() {
    if (!state.current) return;
    state.isPlaying = true;
    if (state.audio) state.audio.play().catch(() => {});
    else { ensureCtx(); startSynth(); }
    startTicker();
    NativeMS.start(); NativeMS.sync(true, state.position, state.duration);
    emit('play', state);
  }
  function saveLastPlay() {
    // 最小化/退出后 WebView 可能被销毁 → 记录上次播放以便恢复迷你栏
    try {
      const cur = state.queue[state.index];
      if (cur) {
        localStorage.setItem('cx_lastplay', JSON.stringify({
          id: cur.id, title: cur.title, ref: cur.ref,
          position: state.position || 0, duration: state.duration || 0,
          queue: state.queue, index: state.index,
        }));
      }
    } catch (_) {}
  }
  function pause() {
    state.isPlaying = false;
    if (state.audio) state.audio.pause();
    stopSynth();
    stopTicker();
    saveLastPlay();
    NativeMS.sync(false, state.position, state.duration);
    emit('pause', state);
  }
  function toggle() { if (!state.current) return; state.isPlaying ? pause() : resume(); }
  function stop() {
    pause();
    state.current = null;
    state.queue = [];
    state.index = -1;
    state.position = 0;
    state.duration = 0;
    state.ab = { a: null, b: null, active: false };
    NativeMS.stop();
    if (state.audio) { try { state.audio.pause(); state.audio.src = ''; } catch (_) {} state.audio = null; }
    if (state.audioSrc) { try { state.audioSrc.disconnect(); } catch (_) {} state.audioSrc = null; }
    if (state.offlineUrl) { try { URL.revokeObjectURL(state.offlineUrl); } catch (_) {} state.offlineUrl = null; }
    emit('stop', state);
  }

  function next(auto) {
    if (!state.queue.length) return;
    let i;
    if (state.shuffle) i = Math.floor(Math.random() * state.queue.length);
    else if (state.repeat === 'one' && auto) i = state.index;
    else { i = state.index + 1; if (i >= state.queue.length) i = 0; }
    const h = state.queue[i];
    const keepPlaying = state.isPlaying || !!auto;
    load(h, state.queue, i).then(() => {
      state.isPlaying = keepPlaying;
      if (state.audio && keepPlaying) state.audio.play().catch(() => {});
      else if (keepPlaying) startSynth();
      startTicker();
      if (keepPlaying) NativeMS.sync(true, state.position, state.duration);
      emit('track', state);
      emit(keepPlaying ? 'play' : 'pause', state);
    });
  }
  function prev() {
    if (!state.queue.length) return;
    if (state.audio && state.audio.currentTime > 3) { state.audio.currentTime = 0; state.position = 0; emit('tick', state); return; }
    if (!state.audio && state.position > 3) { state.position = 0; emit('tick', state); return; }
    let i;
    if (state.shuffle) i = Math.floor(Math.random() * state.queue.length);
    else { i = state.index - 1; if (i < 0) i = state.queue.length - 1; }
    const h = state.queue[i];
    const keepPlaying = state.isPlaying;
    load(h, state.queue, i).then(() => {
      state.isPlaying = keepPlaying;
      if (state.audio && keepPlaying) state.audio.play().catch(() => {});
      else if (keepPlaying) startSynth();
      startTicker();
      if (keepPlaying) NativeMS.sync(true, state.position, state.duration);
      emit('track', state);
      emit(keepPlaying ? 'play' : 'pause', state);
    });
  }

  function seek(sec) {
    state.position = Math.max(0, Math.min(sec, state.duration));
    if (state.audio) state.audio.currentTime = state.position;
    emit('tick', state); updatePositionState();
  }
  function cycleRepeat() {
    state.repeat = state.repeat === 'all' ? 'one' : 'all';
    emit('mode', state); return state.repeat;
  }
  function toggleShuffle() {
    state.shuffle = !state.shuffle;
    emit('mode', state); return state.shuffle;
  }

  /* ── A-B 段落循环 ──────────────────────────────────────────────────── */
  function setAbA() { state.ab.a = state.position; state.ab.b = null; state.ab.active = false; emit('ab', state); }
  function setAbB() {
    if (state.ab.a == null) { state.ab.a = 0; }
    state.ab.b = state.position;
    if (state.ab.b <= state.ab.a) state.ab.b = state.ab.a + 3;
    state.ab.active = true; emit('ab', state);
  }
  function clearAb() { state.ab = { a: null, b: null, active: false }; emit('ab', state); }
  function checkAb() {
    if (state.ab.active && state.ab.a != null && state.ab.b != null && state.position >= state.ab.b) {
      seek(state.ab.a);
    }
  }

  /* ── 睡眠定时器 ────────────────────────────────────────────────────── */
  function setSleep(min) {
    clearSleep();
    if (!min) { emit('sleep', state); return; }
    state.sleep = { endsAt: Date.now() + min * 60000, timerId: null };
    state.sleep.timerId = setInterval(() => {
      if (Date.now() >= state.sleep.endsAt) { clearSleep(); pause(); emit('sleep', state); showToast && showToast(uiT('toast.sleepEnd')); }
      else emit('sleep', state);
    }, 1000);
    emit('sleep', state);
  }
  function clearSleep() {
    if (state.sleep && state.sleep.timerId) clearInterval(state.sleep.timerId);
    state.sleep = null; emit('sleep', state);
  }
  function sleepRemaining() {
    if (!state.sleep) return 0;
    return Math.max(0, Math.round((state.sleep.endsAt - Date.now()) / 1000));
  }

  /* ── 均衡器 / 音质 ─────────────────────────────────────────────── */
  function setEq(preset, gains) {
    AppState.setEq(preset, gains);
    applyEq();
    emit('eq', state);
  }
  function setQuality(q) { AppState.setAudioQuality(q); emit('quality', state); }

  /* ── 下载（离线） ─────────────────────────────────────────────── */
  async function download(track) {
    if (state._downloading) return false;
    state._downloading = true; emit('download', { id: track.id, busy: true });
    try {
      let blob;
      if (track.stream_url) {
        const resp = await fetch(track.stream_url);
        if (!resp.ok) throw new Error('fetch');
        blob = await resp.blob();
      } else {
        blob = await renderSynthWav(track);
      }
      if (blob) await OfflineStore.putBlob(track.id, blob);
      AppState.setHymnDownloaded(track.id, true);
      emit('download', { id: track.id, downloaded: true });
      return true;
    } catch (e) {
      emit('download', { id: track.id, error: true });
      return false;
    } finally {
      state._downloading = false;
    }
  }
  async function removeDownload(id) {
    await OfflineStore.removeBlob(id);
    AppState.setHymnDownloaded(id, false);
    emit('download', { id, downloaded: false });
  }
  function isDownloaded(id) { return AppState.isHymnDownloaded(id); }

  /* ── 队列（播放列表）管理 ──────────────────────────────────────────────── */
  function queueAddNext(track) {
    if (!state.queue.length) { play(track, [track], 0); return; }
    const at = state.index + 1;
    state.queue.splice(at, 0, track);
    emit('track', state); emit('queue', state);
  }
  function queueRemoveAt(idx) {
    if (idx < 0 || idx >= state.queue.length) return;
    state.queue.splice(idx, 1);
    if (idx < state.index) state.index--;
    if (state.index >= state.queue.length) state.index = state.queue.length - 1;
    emit('queue', state);
  }
  function queueJump(idx) {
    if (idx < 0 || idx >= state.queue.length) return;
    const h = state.queue[idx];
    load(h, state.queue, idx).then(() => {
      state.isPlaying = true;
      if (state.audio) state.audio.play().catch(() => {}); else startSynth();
      startTicker(); emit('track', state); emit('play', state);
    });
  }

  function currentLyricIndex() {
    if (!state.current || !state.current.lyrics) return -1;
    const n = state.current.lyrics.length;
    const per = state.duration / n;
    if (per <= 0) return -1;
    return Math.max(0, Math.min(n - 1, Math.floor(state.position / per)));
  }

  return {
    on, play, pause, resume, toggle, stop, next, prev, seek,
    cycleRepeat, toggleShuffle,
    setAbA, setAbB, clearAb,
    setSleep, clearSleep, sleepRemaining,
    setEq, setQuality,
    download, removeDownload, isDownloaded,
    queueAddNext, queueRemoveAt, queueJump,
    getState: () => state, currentLyricIndex,
    isCurrent: (id) => !!(state.current && state.current.id === id),
    getQueue: () => state.queue, getIndex: () => state.index,
    EQ_PRESETS, FREQS,
    // 原生 MediaSession 控制回调(安卓 MediaSessionPlugin.evaluateJavascript 호출)
    _nativePlay: () => resume(),
    _nativePause: () => pause(),
    _nativeSeekTo: (ms) => seek((ms || 0) / 1000),
    _nativeNext: () => next(false),
    _nativePrev: () => prev(),
    _nativeSeekRelative: (deltaMs) => seek(state.position + (deltaMs || 0) / 1000),
  };
})();

/* ═══════════════════════════════════════════════════════════════════════════
   UI — 迷你栏 + 全屏面板 + EQ 面板 + 队列面板 + 通用底部操作表
   ═══════════════════════════════════════════════════════════════════════════ */
let _mini, _sheet, _queueSheet, _actionSheet, _eqPanel;
let _sheetBar, _lyricEls = [], _sheetLyrics, _abMarkA, _abMarkB;

function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(sec / 60), s = sec % 60;
  return m + ':' + String(s).padStart(2, '0');
}

/* ── 通用底部操作表（曲目菜单 / 定时器 / 音质等） ──────────────────── */
function showActionSheet(title, items) {
  if (_actionSheet) _actionSheet.remove();
  const sheet = h('div', { className: 'action-sheet', onClick: (e) => { if (e.target === sheet) closeActionSheet(); } },
    h('div', { className: 'action-backdrop', onClick: closeActionSheet }),
    h('div', { className: 'action-panel' },
      h('div', { className: 'action-grab' }),
      title ? h('div', { className: 'action-title', textContent: title }) : null,
      h('div', { className: 'action-list' },
        ...items.map(it => h('button', {
          className: 'action-item' + (it.active ? ' active' : '') + (it.danger ? ' danger' : ''),
          onClick: () => { if (it.onClick) it.onClick(); if (!it.keepOpen) closeActionSheet(); },
        },
          it.icon ? h('span', { className: 'action-ico', textContent: it.icon }) : null,
          h('span', { className: 'action-label' }, it.label, it.sub ? h('span', { className: 'action-sub', textContent: it.sub }) : null),
          it.active ? h('span', { className: 'action-check', textContent: '✓' }) : null,
        )),
      ),
      h('button', { className: 'action-cancel', textContent: uiT('common.cancel'), onClick: closeActionSheet }),
    ),
  );
  document.body.append(sheet);
  _actionSheet = sheet;
  sheet.style.willChange = 'transform, opacity';
  requestAnimationFrame(() => sheet.classList.add('open'));
  return closeActionSheet;
}
function closeActionSheet() {
  if (!_actionSheet) return;
  const s = _actionSheet; _actionSheet = null;
  s.classList.remove('open');
  const onEnd = (e) => {
    if (e.target !== s || e.propertyName !== 'transform') return;
    s.style.willChange = 'auto';
    s.removeEventListener('transitionend', onEnd);
    s.remove();
  };
  s.addEventListener('transitionend', onEnd);
  setTimeout(() => { if (document.body.contains(s)) s.remove(); }, 260);
}

function initPlayer() {
  const app = $('#app');
  if (!app) return;

  /* ── 迷你播放器 ── */
  _mini = h('div', { id: 'mini-player', className: 'mini-player hidden', onClick: () => openSheet() },
    h('div', { className: 'mini-art', id: 'mini-art', textContent: '♪' }),
    h('div', { className: 'mini-meta' },
      h('div', { className: 'mini-title', id: 'mini-title', textContent: '' }),
      h('div', { className: 'mini-sub', id: 'mini-sub', textContent: '' }),
    ),
    h('button', { className: 'mini-play', id: 'mini-play', textContent: '▶',
      onClick: (e) => { e.stopPropagation(); Player.toggle(); } }),
    h('button', { className: 'mini-close', id: 'mini-close', textContent: '✕',
      onClick: (e) => { e.stopPropagation(); Player.stop(); } }),
    h('div', { className: 'mini-progress', id: 'mini-progress' }),
  );
  _miniBar = _mini.querySelector('#mini-progress');
  app.append(_mini);

  /* ── 全屏播放器面板 ── */
  _sheet = h('div', { id: 'player-sheet', className: 'player-sheet hidden' },
    h('div', { className: 'player-backdrop', onClick: () => closeSheet() }),
    h('div', { className: 'player-panel', onClick: (e) => e.stopPropagation() },
      h('div', { className: 'player-grab' }),
      h('div', { className: 'player-toprow' },
        h('button', { className: 'player-close', textContent: '✕', onClick: () => closeSheet() }),
        h('span', { className: 'player-now', textContent: uiT('player.nowPlaying') }),
        h('button', { className: 'player-queue-btn', id: 'pc-queue', textContent: '☰', title: uiT('player.queue'),
          onClick: () => openQueue() }),
      ),
      h('div', { className: 'player-disc', id: 'player-disc' },
        h('div', { className: 'disc-num', id: 'disc-num', textContent: '♪' }),
        h('div', { className: 'disc-hole' }),
      ),
      h('div', { className: 'player-info' },
        h('div', { className: 'player-title', id: 'player-title', textContent: '' }),
        h('div', { className: 'player-sub', id: 'player-sub', textContent: '' }),
        h('div', { className: 'player-chips' },
          h('span', { className: 'chip', id: 'player-cat', textContent: '' }),
          h('button', { className: 'player-fav', id: 'player-fav', textContent: '☆',
            onClick: () => {
              const s = Player.getState(); if (!s.current) return;
              if (s.current.kind === 'sermon') AppState.toggleSermonFav(s.current.id);
              else AppState.toggleHymnFav(s.current.id);
              renderSheet(); renderMini();
            } }),
        ),
      ),
      h('div', { className: 'player-lyrics', id: 'player-lyrics' }),
      h('div', { className: 'player-seek' },
        h('span', { className: 'seek-cur', id: 'seek-cur', textContent: '0:00' }),
        h('div', { className: 'seek-track', id: 'seek-track' },
          h('div', { className: 'seek-fill', id: 'seek-fill' }),
          h('div', { className: 'seek-knob', id: 'seek-knob' }),
          h('div', { className: 'ab-mark ab-a', id: 'ab-a' }),
          h('div', { className: 'ab-mark ab-b', id: 'ab-b' }),
        ),
        h('span', { className: 'seek-dur', id: 'seek-dur', textContent: '0:00' }),
      ),
      h('div', { className: 'player-controls' },
        h('button', { className: 'pc-btn', id: 'pc-shuffle', textContent: '🔀', title: uiT('player.shuffle'),
          onClick: () => { Player.toggleShuffle(); renderSheet(); } }),
        h('button', { className: 'pc-btn', textContent: '⏮', onClick: () => Player.prev() }),
        h('button', { className: 'pc-play', id: 'pc-play', textContent: '▶', onClick: () => Player.toggle() }),
        h('button', { className: 'pc-btn', textContent: '⏭', onClick: () => Player.next() }),
        h('button', { className: 'pc-btn', id: 'pc-repeat', textContent: '🔁', title: uiT('player.repeat'),
          onClick: () => { Player.cycleRepeat(); renderSheet(); } }),
      ),
      /* 辅助工具行（方案 A：隐藏下载/音质，突出睡眠定时器） */
      h('div', { className: 'player-tools' },
        h('button', { className: 'tool-btn', id: 'pc-ab', textContent: 'A–B', title: uiT('player.abLoop'),
          onClick: () => onAbClick() }),
        h('button', { className: 'tool-btn', id: 'pc-eq', textContent: '🎚', title: uiT('player.eq'),
          onClick: () => toggleEqPanel() }),
        h('button', { className: 'tool-btn tool-btn--sleep', id: 'pc-sleep', textContent: '⏲', title: uiT('player.sleep'),
          onClick: () => openSleepMenu() }),
      ),
      /* 均衡器面板（可折叠） */
      buildEqPanel(),
    ),
  );
  document.body.append(_sheet);
  _sheetBar = _sheet.querySelector('#seek-fill');
  _sheetLyrics = _sheet.querySelector('#player-lyrics');
  _abMarkA = _sheet.querySelector('#ab-a');
  _abMarkB = _sheet.querySelector('#ab-b');
  _eqPanel = _sheet.querySelector('#eq-panel');

  /* seek 交互 — T-1：增加触摸拖拽支持
     注：不在闭包里缓存 track，改为在事件中实时查询，避免 _sheet 重建后引用失效为 null。 */
  function seekFromEvent(e) {
    const track = _sheet && _sheet.querySelector('#seek-track');
    if (!track) return;
    const rect = track.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
    const ratio = Math.max(0, Math.min(1, x / rect.width));
    const s = Player.getState();
    Player.seek(ratio * s.duration);
  }
  const seekTrackEl = _sheet.querySelector('#seek-track');
  if (seekTrackEl) {
    seekTrackEl.addEventListener('click', seekFromEvent);
    // T-1：移动端拖拽 seek
    let _seekDragging = false;
    seekTrackEl.addEventListener('touchstart', (e) => { _seekDragging = true; seekFromEvent(e); }, { passive: true });
    seekTrackEl.addEventListener('touchmove', (e) => { if (_seekDragging) seekFromEvent(e); }, { passive: true });
    seekTrackEl.addEventListener('touchend', () => { _seekDragging = false; });
  }

  /* subscriptions */
  Player.on('track', () => { renderMini(); renderSheet(); syncPlaylistUI(); });
  Player.on('play', () => { renderMini(); renderSheet(); syncPlaylistUI(); });
  Player.on('pause', () => { renderMini(); renderSheet(); syncPlaylistUI(); });
  Player.on('tick', () => updateProgress());
  Player.on('mode', () => renderSheet());
  Player.on('ab', () => renderSheet());
  Player.on('eq', () => renderEqPanel());
  Player.on('sleep', () => renderSheet());
  Player.on('download', () => renderSheet());
  Player.on('quality', () => renderSheet());

  renderMini();
  buildQueueSheet();
  wireMediaHandlersSafe();

  // 恢复上次播放（WebView 被系统销毁后切回前台时）：仅还原迷你栏元信息，不自动出声
  try {
    const raw = localStorage.getItem('cx_lastplay');
    if (raw) {
      const lp = JSON.parse(raw);
      if (lp && lp.id) {
        state.queue = lp.queue && lp.queue.length ? lp.queue : [lp];
        state.index = lp.index != null ? lp.index : 0;
        state.position = lp.position || 0;
        state.duration = lp.duration || 0;
        state.current = { id: lp.id, title: lp.title, ref: lp.ref };
        renderMini();
      }
    }
  } catch (_) {}
}

function wireMediaHandlersSafe() {
  // Media Session 动作处理器只注册一次（播放/暂停/上一首/下一首）
  if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
    const set = (a, fn) => { try { navigator.mediaSession.setActionHandler(a, fn); } catch (_) {} };
    set('play', () => Player.resume());
    set('pause', () => Player.pause());
    set('previoustrack', () => Player.prev());
    set('nexttrack', () => Player.next());
    // T-11：锁屏/耳机进度条拖拽 seek
    set('seekto', (details) => {
      if (details && details.seekTime != null) Player.seek(details.seekTime);
    });
  }
}

/* ── EQ 面板构建 ──────────────────────────────────────────────────────── */
function buildEqPanel() {
  const presets = Player.EQ_PRESETS;
  const gains = AppState.get('eqGains') || presets.flat;
  const presetChips = h('div', { className: 'eq-presets' });
  Object.keys(presets).forEach(p => {
    presetChips.append(h('button', {
      className: 'eq-preset' + (AppState.get('eqPreset') === p ? ' active' : ''),
      'data-preset': p, textContent: eqPresetName(p),
      onClick: () => {
        const g = [...presets[p]];
        Player.setEq(p, g);
        presetChips.querySelectorAll('.eq-preset').forEach(b => b.classList.toggle('active', b.dataset.preset === p));
        _eqPanel.querySelectorAll('.eq-slider').forEach((sl, i) => { sl.value = g[i]; sl.nextElementSibling.textContent = (g[i] > 0 ? '+' : '') + g[i]; });
      },
    }));
  });
  const sliders = h('div', { className: 'eq-sliders' });
  Player.FREQS.forEach((f, i) => {
    const wrap = h('div', { className: 'eq-band' },
      h('input', { type: 'range', min: -12, max: 12, step: 1, value: gains[i] || 0, className: 'eq-slider',
        onInput: (e) => {
          const v = parseInt(e.target.value);
          e.target.nextElementSibling.textContent = (v > 0 ? '+' : '') + v;
          const cur = [...(AppState.get('eqGains') || presets.flat)]; cur[i] = v;
          Player.setEq(null, cur);
        } }),
      h('span', { className: 'eq-val', textContent: (gains[i] > 0 ? '+' : '') + (gains[i] || 0) }),
      h('span', { className: 'eq-freq', textContent: f >= 1000 ? (f / 1000) + 'k' : f }),
    );
    sliders.append(wrap);
  });
  return       h('div', { id: 'eq-panel', className: 'eq-panel hidden' },
        h('div', { className: 'eq-head' }, h('span', { textContent: uiT('player.eq') }), h('button', { className: 'eq-close', textContent: '✕', onClick: () => toggleEqPanel() })),
    sliders,
    presetChips,
  );
}
function eqPresetName(p) {
  return { flat: uiT('eq.flat'), pop: uiT('eq.pop'), rock: uiT('eq.rock'), classical: uiT('eq.classical'), vocal: uiT('eq.vocal'), bass: uiT('eq.bass') }[p] || p;
}
function toggleEqPanel() { if (_eqPanel) { _eqPanel.classList.toggle('hidden'); renderEqPanel(); } }
function renderEqPanel() {
  if (!_eqPanel) return;
  const preset = AppState.get('eqPreset');
  _eqPanel.querySelectorAll('.eq-preset').forEach(b => b.classList.toggle('active', b.dataset.preset === preset));
}

/* ── A-B / 下载 / 定时器 / 音质 点击处理器 ───────────────────────── */
function onAbClick() {
  const s = Player.getState();
  if (!s.current) return;
  if (!s.ab.active && s.ab.a == null) { Player.setAbA(); showToast(uiT('toast.abSetA')); }
  else if (!s.ab.active && s.ab.a != null) { Player.setAbB(); showToast(uiT('toast.abOn')); }
  else { Player.clearAb(); showToast(uiT('toast.abOff')); }
  renderSheet();
}
function openSleepMenu() {
  const items = [
    { label: uiT('sleep.15'), sub: uiT('sleep.sub', { m: 15 }), onClick: () => Player.setSleep(15) },
    { label: uiT('sleep.30'), sub: uiT('sleep.sub', { m: 30 }), onClick: () => Player.setSleep(30) },
    { label: uiT('sleep.45'), sub: uiT('sleep.sub', { m: 45 }), onClick: () => Player.setSleep(45) },
    { label: uiT('sleep.60'), sub: uiT('sleep.sub', { m: 60 }), onClick: () => Player.setSleep(60) },
    { label: uiT('sleep.90'), sub: uiT('sleep.sub', { m: 90 }), onClick: () => Player.setSleep(90) },
    { label: uiT('sleep.off'), danger: true, onClick: () => Player.clearSleep() },
  ];
  showActionSheet(uiT('player.sleep'), items);
}
/* 方案 A：音质不再暴露给用户，按网络状态自适应（仅内部调用，无 UI） */
function autoQualityByNetwork() {
  let q = 'standard';
  try {
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (c) {
      const eff = c.effectiveType || c.type || '';
      if (eff === '4g' || eff === 'wifi' || c.saveData === false) q = 'hifi';
      else if (eff === '2g' || eff === 'slow-2g' || c.saveData) q = 'saver';
    }
  } catch (_) {}
  AppState.setAudioQuality(q);
  return q;
}

/* ── 队列（播放列表）面板 ─────────────────────────────────────────────────── */
function buildQueueSheet() {
  _queueSheet = h('div', { id: 'queue-sheet', className: 'queue-sheet hidden' },
    h('div', { className: 'player-backdrop', onClick: () => closeQueue() }),
    h('div', { className: 'queue-panel' },
      h('div', { className: 'queue-head' },
        h('span', { textContent: uiT('player.queue') }),
        h('button', { className: 'queue-close', textContent: '✕', onClick: () => closeQueue() }),
      ),
      h('div', { className: 'queue-list', id: 'queue-list' }),
    ),
  );
  document.body.append(_queueSheet);
}
function openQueue() { if (_queueSheet) { _queueSheet.classList.remove('hidden'); renderQueue(); } }
function closeQueue() { if (_queueSheet) _queueSheet.classList.add('hidden'); }
function renderQueue() {
  if (!_queueSheet) return;
  const list = _queueSheet.querySelector('#queue-list');
  empty(list);
  const queue = Player.getQueue();
  const idx = Player.getIndex();
  if (!queue.length) { list.append(h('p', { className: 'empty-text', textContent: uiT('player.queueEmpty') })); return; }
  queue.forEach((t, i) => {
    const row = h('div', { className: 'queue-row' + (i === idx ? ' current' : ''),
        onClick: () => { Player.queueJump(i); renderQueue(); renderSheet(); } },
      h('span', { className: 'queue-idx', textContent: i === idx ? '♪' : (i + 1) }),
      h('div', { className: 'queue-meta' },
        h('div', { className: 'queue-title', textContent: t.title }),
        h('div', { className: 'queue-sub', textContent: t.subtitle || '' }),
      ),
      h('button', { className: 'queue-del', textContent: '✕',
        onClick: (e) => { e.stopPropagation(); Player.queueRemoveAt(i); renderQueue(); } }),
    );
    list.append(row);
  });
}

/* ── 面板开合 + 渲染 ─────────────────────────────────────────────────── */
function openSheet() {
  if (!_sheet || !Player.getState().current) return;
  _sheet.classList.remove('hidden');
  renderSheet();
}
function closeSheet() {
  if (_sheet) _sheet.classList.add('hidden');
  if (_eqPanel) _eqPanel.classList.add('hidden');
}

function renderMini() {
  const s = Player.getState();
  const app = $('#app');
  if (!s.current) { _mini.classList.add('hidden'); if (app) app.classList.remove('has-mini'); return; }
  _mini.classList.remove('hidden');
  if (app) app.classList.add('has-mini');
  _mini.querySelector('#mini-art').textContent = s.current.number != null ? s.current.number : '♪';
  _mini.querySelector('#mini-title').textContent = s.current.title;
  _mini.querySelector('#mini-sub').textContent = s.current.subtitle || '';
  _mini.querySelector('#mini-play').textContent = s.isPlaying ? '⏸' : '▶';
  updateProgress();
}

function renderSheet() {
  const s = Player.getState();
  if (!s.current) return;
  const fav = s.current.kind === 'sermon' ? AppState.get('sermonFavorites') : AppState.get('hymnFavorites');
  _sheet.querySelector('#disc-num').textContent = s.current.number != null ? s.current.number : '♪';
  _sheet.querySelector('#player-title').textContent = s.current.title;
  _sheet.querySelector('#player-sub').textContent = s.current.subtitle || '';
  _sheet.querySelector('#player-cat').textContent = s.current.category || (s.current.kind === 'sermon' ? '讲道' : '诗歌');
  const favBtn = _sheet.querySelector('#player-fav');
  favBtn.textContent = fav.includes(s.current.id) ? '⭐' : '☆';
  favBtn.classList.toggle('active', fav.includes(s.current.id));

  _sheet.querySelector('#pc-play').textContent = s.isPlaying ? '⏸' : '▶';
  const rep = _sheet.querySelector('#pc-repeat');
  rep.textContent = s.repeat === 'one' ? '🔂' : '🔁';
  rep.classList.toggle('active', s.repeat === 'one');
  _sheet.querySelector('#pc-shuffle').classList.toggle('active', s.shuffle);

  /* A-B 显示 */
  const abBtn = _sheet.querySelector('#pc-ab');
  abBtn.classList.toggle('active', s.ab.active);
  if (_abMarkA) _abMarkA.style.left = (s.ab.a != null && s.duration ? (s.ab.a / s.duration * 100) : -5) + '%';
  if (_abMarkB) _abMarkB.style.left = (s.ab.b != null && s.duration ? (s.ab.b / s.duration * 100) : -5) + '%';
  if (_abMarkA) _abMarkA.style.display = s.ab.a != null ? 'block' : 'none';
  if (_abMarkB) _abMarkB.style.display = s.ab.b != null ? 'block' : 'none';

  /* 睡眠定时器徽标 */
  const sleepBtn = _sheet.querySelector('#pc-sleep');
  const rem = Player.sleepRemaining();
  sleepBtn.classList.toggle('active', rem > 0);
  sleepBtn.textContent = rem > 0 ? '⏲' + Math.ceil(rem / 60) + 'm' : '⏲';

  /* 歌词 / 摘要 */
  _sheetLyrics.textContent = '';
  _lyricEls = [];
  if (s.current.lyrics && s.current.lyrics.length) {
    s.current.lyrics.forEach(line => {
      const el = h('p', { className: 'lyric-line', textContent: line });
      _lyricEls.push(el);
      _sheetLyrics.append(el);
    });
  } else if (s.current.summary) {
    const wrap = h('div', { className: 'lyric-summary' });
    String(s.current.summary).split('\n').forEach(para => {
      wrap.append(h('p', { className: 'lyric-line', textContent: para }));
    });
    if (s.current.transcript && s.current.transcript.length) {
      wrap.append(h('div', { className: 'lyric-divider', textContent: uiT('player.sermonScripture') }));
      s.current.transcript.forEach(para => {
        wrap.append(h('p', { className: 'lyric-line muted', textContent: para }));
      });
    }
    _sheetLyrics.append(wrap);
  } else {
    _sheetLyrics.append(h('p', { className: 'lyric-line muted', textContent: uiT('player.noContent') }));
  }
  updateProgress();
  if (_queueSheet && !_queueSheet.classList.contains('hidden')) renderQueue();
}

function updateProgress() {
  const s = Player.getState();
  const pct = s.duration ? Math.min(100, (s.position / s.duration) * 100) : 0;
  if (_miniBar) _miniBar.style.width = pct + '%';
  if (_sheetBar) {
    _sheetBar.style.width = pct + '%';
    const knob = _sheet.querySelector('#seek-knob');
    if (knob) knob.style.left = pct + '%';
  }
  const cur = _sheet.querySelector('#seek-cur'), dur = _sheet.querySelector('#seek-dur');
  if (cur) cur.textContent = fmtTime(s.position);
  if (dur) dur.textContent = fmtTime(s.duration);
  const disc = _sheet.querySelector('#player-disc');
  if (disc) disc.classList.toggle('spinning', s.isPlaying);

  const rem = Player.sleepRemaining();
  const sleepBtn = _sheet.querySelector('#pc-sleep');
  if (sleepBtn && rem > 0) sleepBtn.textContent = '⏲' + Math.ceil(rem / 60) + 'm';

  const li = Player.currentLyricIndex();
  if (_lyricEls.length && li >= 0) {
    _lyricEls.forEach((el, i) => el.classList.toggle('active', i === li));
    const act = _lyricEls[li];
    if (act && _sheetLyrics) {
      const target = act.offsetTop - _sheetLyrics.clientHeight / 2 + act.clientHeight / 2;
      if (Math.abs(_sheetLyrics.scrollTop - target) > 30) _sheetLyrics.scrollTo({ top: target, behavior: 'smooth' });
    }
  }
}

/* toast（screens/index.js 也有定义，这里为播放器单独调用做准备） */
function showToast(msg) {
  let t = document.getElementById('app-toast');
  if (!t) {
    t = h('div', { id: 'app-toast', className: 'app-toast' });
    document.body.append(t);
  }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 1800);
}
