/* ═══════════════════════════════════════════════════════════════════════════
   OfflineStore — 基于 IndexedDB 的音频 Blob 缓存（离线播放用）
   键：'audio:<trackId>' → Blob(MP3/WAV)。与 localStorage 不同，可存储大体积二进制。
   ═══════════════════════════════════════════════════════════════════════════ */

const OfflineStore = (function () {
  const DB = 'gospel_offline';
  const STORE = 'audio';
  let _dbPromise = null;

  function open() {
    if (_dbPromise) return _dbPromise;
    _dbPromise = new Promise((resolve, reject) => {
      if (!('indexedDB' in window)) { reject(new Error('no-idb')); return; }
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return _dbPromise;
  }

  function key(id) { return 'audio:' + id; }

  async function putBlob(id, blob) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(blob, key(id));
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error);
    });
  }

  async function getBlob(id) {
    try {
      const db = await open();
      return await new Promise((resolve) => {
        const tx = db.transaction(STORE, 'readonly');
        const rq = tx.objectStore(STORE).get(key(id));
        rq.onsuccess = () => resolve(rq.result || null);
        rq.onerror = () => resolve(null);
      });
    } catch (_) { return null; }
  }

  async function removeBlob(id) {
    try {
      const db = await open();
      return await new Promise((resolve) => {
        const tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).delete(key(id));
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => resolve(false);
      });
    } catch (_) { return false; }
  }

  async function has(id) { return !!(await getBlob(id)); }

  return { putBlob, getBlob, removeBlob, has };
})();

/* ── WAV 编码器（OfflineAudioContext 渲染结果 → PCM16 Blob）─────────────── */
function encodeWav(audioBuffer) {
  const numCh = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const len = audioBuffer.length;
  const bytesPerSample = 2;
  const blockAlign = numCh * bytesPerSample;
  const dataSize = len * blockAlign;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  function writeStr(off, str) { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); }

  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);               // PCM
  view.setUint16(22, numCh, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeStr(36, 'data');
  view.setUint32(40, dataSize, true);

  let off = 44;
  const channels = [];
  for (let c = 0; c < numCh; c++) channels.push(audioBuffer.getChannelData(c));
  for (let i = 0; i < len; i++) {
    for (let c = 0; c < numCh; c++) {
      let s = Math.max(-1, Math.min(1, channels[c][i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      off += 2;
    }
  }
  return new Blob([buffer], { type: 'audio/wav' });
}
