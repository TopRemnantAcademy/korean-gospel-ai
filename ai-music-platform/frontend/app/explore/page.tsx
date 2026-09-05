"use client";

import { useEffect, useState } from "react";
import { api, SongView } from "@/lib/api";
import Player from "@/components/Player";

const PAGE = 20;

export default function ExplorePage() {
  const [songs, setSongs] = useState<SongView[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState("");
  const [q, setQ] = useState(""); // 防抖后实际用于请求的关键字

  // 输入停止 300ms 后再触发搜索，避免逐字符请求
  useEffect(() => {
    const t = setTimeout(() => setQ(query.trim()), 300);
    return () => clearTimeout(t);
  }, [query]);

  async function load(initial = false) {
    if (initial) setLoading(true);
    else setLoadingMore(true);
    setError("");
    try {
      const next = initial ? 0 : offset;
      const data = await api.explore(PAGE, next, q);
      setSongs((prev) => (initial ? data : [...prev, ...data]));
      setOffset(next + data.length);
      setHasMore(data.length === PAGE);
    } catch (e: any) {
      if (e?.status === 401) setError("登录已过期或无效，请重新登录（右上角）。");
      else setError(e?.message || "加载失败");
    } finally {
      if (initial) setLoading(false);
      else setLoadingMore(false);
    }
  }

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-4 text-2xl font-bold">发现</h1>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="搜索标题或歌词…"
        className="mb-4 w-full rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-indigo-500"
      />

      {loading && <p className="text-neutral-400">加载中…</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {!loading && songs.length === 0 && (
        <p className="text-neutral-400">{q ? "没有匹配的作品。" : "暂无公开作品。"}</p>
      )}

      <div className="space-y-4">
        {songs.map((s) => (
          <Player
            key={s.id}
            song={s}
            isOwner={s.is_owner ?? false}
            onSpawn={(u) => setSongs((prev) => prev.map((x) => (x.id === s.id ? u : x)))}
          />
        ))}
      </div>

      {hasMore && (
        <button
          onClick={() => load(false)}
          disabled={loadingMore}
          className="mt-4 w-full rounded-full bg-neutral-800 py-2 text-sm text-neutral-200 transition hover:bg-neutral-700 disabled:opacity-50"
        >
          {loadingMore ? "加载中…" : "加载更多"}
        </button>
      )}
    </main>
  );
}
