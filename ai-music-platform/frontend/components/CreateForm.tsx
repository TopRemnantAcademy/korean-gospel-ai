"use client";

import { useEffect, useRef, useState } from "react";
import { api, SongView } from "@/lib/api";
import Player from "./Player";

const POLL_INTERVAL_MS = 5000;
const MAX_POLLS = 40;

export default function CreateForm() {
  const [style, setStyle] = useState("国风 伤感 钢琴");
  const [prompt, setPrompt] = useState("");
  const [lyric, setLyric] = useState("");
  const [title, setTitle] = useState("");
  const [vocal, setVocal] = useState("");
  const [instrumental, setInstrumental] = useState(false);
  const [isPublic, setIsPublic] = useState(false);
  const [song, setSong] = useState<SongView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [timedOut, setTimedOut] = useState(false);
  const canceledRef = useRef(false);

  useEffect(() => {
    return () => {
      canceledRef.current = true;
    };
  }, []);

  async function poll(songId: number): Promise<SongView | null> {
    let s: SongView | null = null;
    for (let i = 0; i < MAX_POLLS; i++) {
      if (canceledRef.current) return null;
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      if (canceledRef.current) return null;
      s = await api.getSong(songId);
      setSong(s);
      if (s.status === "completed" || s.status === "failed") return s;
    }
    return s;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    canceledRef.current = false;
    setLoading(true);
    setError("");
    setSong(null);
    setTimedOut(false);
    try {
      const { song_id } = await api.generate({
        task: instrumental ? "generate" : lyric ? "custom" : "generate",
        style,
        prompt,
        lyric: instrumental ? "" : lyric,
        title: title || undefined,
        vocal_gender: vocal || undefined,
        make_instrumental: instrumental,
        is_public: isPublic,
      });

      const s = await poll(song_id);
      if (s && s.status !== "completed" && s.status !== "failed") {
        setTimedOut(true);
      }
    } catch (err: any) {
      setError(err?.message || "生成失败");
    } finally {
      if (!canceledRef.current) setLoading(false);
    }
  }

  async function onRefresh() {
    if (!song) return;
    canceledRef.current = false;
    setTimedOut(false);
    setLoading(true);
    try {
      const s = await poll(song.id);
      if (s && s.status !== "completed" && s.status !== "failed") {
        setTimedOut(true);
      }
    } catch (err: any) {
      setError(err?.message || "刷新失败");
    } finally {
      if (!canceledRef.current) setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <form
        onSubmit={onSubmit}
        className="space-y-3 rounded-2xl border border-neutral-800 bg-neutral-900 p-4"
      >
        <div>
          <label className="mb-1 block text-sm text-neutral-400">风格标签</label>
          <input
            value={style}
            onChange={(e) => setStyle(e.target.value)}
            className="w-full rounded border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder="国风 伤感 钢琴"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-neutral-400">主题 / 情绪</label>
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="w-full rounded border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder="失恋的雨夜"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-neutral-400">自定义歌词（留空交给 AI）</label>
          <textarea
            value={lyric}
            onChange={(e) => setLyric(e.target.value)}
            disabled={instrumental}
            className="w-full rounded border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500"
            rows={5}
            placeholder="写一段歌词，或留空"
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="rounded border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder="歌名（可选）"
          />
          <select
            value={vocal}
            onChange={(e) => setVocal(e.target.value)}
            className="rounded border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500"
          >
            <option value="">音色不限</option>
            <option value="male">男声</option>
            <option value="female">女声</option>
          </select>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={instrumental}
              onChange={(e) => setInstrumental(e.target.checked)}
            />
            纯音乐
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            公开发布到发现页
          </label>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-full bg-indigo-500 py-2 font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
        >
          {loading ? "生成中…（后台轮询）" : "生成歌曲"}
        </button>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </form>

      {song && (
        <div className="space-y-2">
          <Player song={song} isOwner={song.is_owner ?? false} onSpawn={setSong} />
          {timedOut && (
            <button
              onClick={onRefresh}
              className="rounded-full bg-neutral-700 px-4 py-1.5 text-sm text-white transition hover:bg-neutral-600"
            >
              仍在生成，点此刷新状态
            </button>
          )}
        </div>
      )}
    </div>
  );
}
