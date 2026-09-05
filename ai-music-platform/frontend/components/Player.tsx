"use client";

import { useEffect, useRef, useState } from "react";
import { api, SongView } from "@/lib/api";

const POLL_INTERVAL_MS = 5000;
const MAX_POLLS = 40;

export default function Player({
  song,
  onSpawn,
  isOwner = false,
}: {
  song: SongView;
  onSpawn?: (s: SongView) => void;
  isOwner?: boolean;
}) {
  const [local, setLocal] = useState<SongView>(song);
  const [syncState, setSyncState] = useState<"idle" | "syncing" | "synced" | "failed">("idle");
  const [msg, setMsg] = useState("");
  const [spawning, setSpawning] = useState<"" | "extend" | "cover" | "remix">("");
  const [downloading, setDownloading] = useState(false);
  // 需鉴权的试听端点（对象存储未配置时的回退）→ 取 blob 再播，见下方 useEffect
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);
  const canceledRef = useRef(false);

  useEffect(() => {
    setLocal(song);
  }, [song]);

  useEffect(() => {
    return () => {
      canceledRef.current = true;
    };
  }, []);

  // 未订阅者的 audio_url 有两种形态：
  //   · 对象存储直链（http…）        → <audio src> 可直接播
  //   · /api/songs/{id}/preview      → 需鉴权，<audio> 无法带 token，故取 blob 播放
  // blob 获取失败即视为「试听片段不可用」（后端 fail-closed，绝不回退完整音频）。
  useEffect(() => {
    const url = local.audio_url || "";
    if (!url.startsWith("/api/")) {
      setPreviewSrc(null);
      setPreviewFailed(false);
      return;
    }
    let revoked = false;
    let objUrl: string | null = null;
    setPreviewFailed(false);
    api
      .previewObjectUrl(local.id)
      .then((u) => {
        objUrl = u;
        if (revoked) {
          if (u) URL.revokeObjectURL(u);
          return;
        }
        setPreviewSrc(u);
        setPreviewFailed(!u);
      })
      .catch(() => {
        if (!revoked) setPreviewFailed(true);
      });
    return () => {
      revoked = true;
      if (objUrl) URL.revokeObjectURL(objUrl);
    };
  }, [local.audio_url, local.id]);

  async function onPlay() {
    try {
      const updated = await api.play(local.id);
      setLocal((p) => ({ ...p, play_count: updated.play_count ?? p.play_count }));
    } catch (e: any) {
      if (e?.status === 401) setMsg("请先登录后再播放（右上角）");
      else setMsg(e?.message || "播放失败");
    }
  }

  async function onSync() {
    if (!local.id) return;
    setSyncState("syncing");
    setMsg("");
    try {
      await api.syncFlow(local.id);
      setSyncState("synced");
      setMsg("已同步到 FLOW APP（APK 歌单可刷新拉取）");
    } catch (e: any) {
      setSyncState("failed");
      setMsg(e?.message || "同步失败");
    }
  }

  async function handleSpawn(task: "extend" | "cover" | "remix") {
    if (!local.id) return;
    setSpawning(task);
    setMsg("");
    try {
      const fn =
        task === "extend" ? api.extendSong : task === "cover" ? api.coverSong : api.remixSong;
      const { song_id } = await fn(local.id, {});
      let s: SongView | null = null;
      for (let i = 0; i < MAX_POLLS; i++) {
        if (canceledRef.current) break;
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (canceledRef.current) break;
        s = await api.getSong(song_id);
        if (s.status === "completed" || s.status === "failed") break;
      }
      if (s && s.status === "completed") {
        setLocal(s);
        onSpawn?.(s);
        setMsg(`已生成${task === "extend" ? "续写" : task === "cover" ? "翻唱" : "Remix"}，已载入播放器`);
      } else if (s && s.status === "failed") {
        setMsg("生成失败，请稍后重试");
      } else {
        setMsg("生成超时，请稍后在我的作品查看");
      }
    } catch (e: any) {
      setMsg(e?.message || "生成失败");
    } finally {
      setSpawning("");
    }
  }

  async function handleDownload() {
    if (!local.id) return;
    setDownloading(true);
    setMsg("");
    try {
      await api.downloadSong(local.id);
      setMsg("已开始下载完整音频");
    } catch (e: any) {
      if (e?.status === 403) setMsg("订阅后可下载完整音频");
      else setMsg(e?.message || "下载失败");
    } finally {
      setDownloading(false);
    }
  }

  const completed = local.status === "completed";
  const generating = !local.audio_url && !completed;
  // 已完成但无音频 = 试听片段生成失败（后端 fail-closed，不会回退完整链接）
  const audioMissing = completed && (!local.audio_url || previewFailed);
  const playSrc = previewSrc ?? (local.audio_url ?? undefined);

  return (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
      {local.status && local.status !== "completed" && (
        <p className="mb-2 text-sm text-neutral-400">状态：{local.status}</p>
      )}

      {generating ? (
        <p className="text-sm text-neutral-400">生成中…（状态：{local.status || "pending"}）</p>
      ) : audioMissing ? (
        <p className="text-sm text-amber-400">试听片段暂不可用，请稍后重试或订阅后收听完整版。</p>
      ) : (
        <>
          {local.cover_url && (
            <img
              src={local.cover_url}
              alt={local.title || ""}
              loading="lazy"
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = "none";
              }}
              className="mb-3 h-40 w-40 rounded-xl object-cover"
            />
          )}
          <h3 className="mb-2 font-semibold">{local.title || "未命名"}</h3>
          <audio src={playSrc} controls className="w-full" />
          {local.can_play_full === false && (
            <p className="mt-1 text-xs text-amber-400">
              试听前 {local.preview_seconds ?? 60} 秒 · 订阅后可收听并下载完整版
            </p>
          )}
          {local.lyric && (
            <pre className="mt-3 whitespace-pre-wrap text-sm text-neutral-400">{local.lyric}</pre>
          )}
        </>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {!generating && (
          <button
            onClick={onPlay}
            className="rounded-full bg-indigo-500 px-4 py-1.5 text-sm text-white transition hover:bg-indigo-400"
          >
            播放 +1（{local.play_count || 0}）
          </button>
        )}
        {local.id != null && !generating && (
          <>
            {isOwner && (
              <>
                <button
                  onClick={onSync}
                  disabled={syncState === "syncing" || syncState === "synced"}
                  className="rounded-full bg-emerald-600 px-4 py-1.5 text-sm text-white transition hover:bg-emerald-500 disabled:opacity-60"
                >
                  {syncState === "synced"
                    ? "已同步到 FLOW ✓"
                    : syncState === "syncing"
                    ? "同步中…"
                    : "同步到 FLOW APP"}
                </button>
                <button
                  onClick={() => handleSpawn("extend")}
                  disabled={spawning !== ""}
                  className="rounded-full bg-neutral-700 px-4 py-1.5 text-sm text-white transition hover:bg-neutral-600 disabled:opacity-60"
                >
                  {spawning === "extend" ? "续写中…" : "续写 Extend"}
                </button>
              </>
            )}
            <button
              onClick={() => handleSpawn("cover")}
              disabled={spawning !== ""}
              className="rounded-full bg-neutral-700 px-4 py-1.5 text-sm text-white transition hover:bg-neutral-600 disabled:opacity-60"
            >
              {spawning === "cover" ? "翻唱中…" : "翻唱 Cover"}
            </button>
            <button
              onClick={() => handleSpawn("remix")}
              disabled={spawning !== ""}
              className="rounded-full bg-neutral-700 px-4 py-1.5 text-sm text-white transition hover:bg-neutral-600 disabled:opacity-60"
            >
              {spawning === "remix" ? "Remix 中…" : "Remix"}
            </button>
            {local.can_download && (
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="rounded-full bg-sky-600 px-4 py-1.5 text-sm text-white transition hover:bg-sky-500 disabled:opacity-60"
              >
                {downloading ? "下载中…" : "下载完整版"}
              </button>
            )}
          </>
        )}
      </div>
      {msg && <p className="mt-1 text-xs text-neutral-400">{msg}</p>}
    </div>
  );
}
