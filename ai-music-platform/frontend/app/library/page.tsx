"use client";

import { useEffect, useState } from "react";
import { api, SongView } from "@/lib/api";
import Player from "@/components/Player";
import ConfirmDialog from "@/components/ConfirmDialog";

const PAGE = 20;

export default function LibraryPage() {
  const [songs, setSongs] = useState<SongView[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SongView | null>(null);

  async function load(initial = false) {
    if (initial) setLoading(true);
    else setLoadingMore(true);
    setError("");
    try {
      const next = initial ? 0 : offset;
      const data = await api.listSongs(PAGE, next);
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
  }, []);

  async function onTogglePublic(s: SongView) {
    try {
      const updated = await api.updateVisibility(s.id, !s.is_public);
      setSongs((prev) => prev.map((x) => (x.id === s.id ? updated : x)));
    } catch (e: any) {
      setError(e?.message || "更新失败");
    }
  }

  async function confirmDelete() {
    const s = pendingDelete;
    if (!s) return;
    setPendingDelete(null);
    try {
      await api.deleteSong(s.id);
      await load(true);
    } catch (e: any) {
      setError(e?.message || "删除失败");
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">我的作品</h1>

      {loading && <p className="text-neutral-400">加载中…</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {!loading && songs.length === 0 && (
        <p className="text-neutral-400">还没有作品，去创作一首吧。</p>
      )}

      <div className="space-y-4">
        {songs.map((s) => (
          <div key={s.id} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="mb-2 flex items-start justify-between gap-3">
              <h3 className="font-semibold">{s.title || "未命名"}</h3>
              <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">
                {s.status}
              </span>
            </div>
            <Player
              song={s}
              isOwner={s.is_owner ?? false}
              onSpawn={(u) => setSongs((prev) => prev.map((x) => (x.id === s.id ? u : x)))}
            />
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-neutral-400">
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={!!s.is_public}
                  onChange={() => onTogglePublic(s)}
                />
                公开发布到发现页
              </label>
              <button
                onClick={() => setPendingDelete(s)}
                className="rounded-full border border-red-500/50 px-4 py-1.5 text-red-400 transition hover:bg-red-500/10"
              >
                删除
              </button>
            </div>
          </div>
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

      <ConfirmDialog
        open={!!pendingDelete}
        title="删除作品"
        message={
          pendingDelete
            ? `确定删除《${pendingDelete.title || "未命名"}》？此操作不可恢复。`
            : ""
        }
        confirmText="删除"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </main>
  );
}
