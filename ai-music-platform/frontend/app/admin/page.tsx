"use client";

import { useEffect, useState } from "react";
import { api, AdminSongView, AdminStats } from "@/lib/api";

type Filter = "" | "pending" | "approved" | "rejected";

const MOD_LABEL: Record<string, string> = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已驳回",
};
function modLabel(s: string) {
  return MOD_LABEL[s] || s;
}
function modColor(s: string) {
  if (s === "approved") return "bg-emerald-900 text-emerald-300";
  if (s === "rejected") return "bg-red-900 text-red-300";
  return "bg-amber-900 text-amber-300";
}

function isAbsUrl(u?: string | null) {
  return typeof u === "string" && /^https?:\/\//i.test(u);
}

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [filter, setFilter] = useState<Filter>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [songs, setSongs] = useState<AdminSongView[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<number | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const PAGE_SIZE = 50;
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setToken(localStorage.getItem("admin_token") || "");
  }, []);

  async function load(reset = true) {
    setError("");
    setLoading(true);
    const off = reset ? 0 : songs.length;
    try {
      const [s, st] = await Promise.all([
        api.adminSongs(filter || undefined, statusFilter || undefined, PAGE_SIZE, off),
        api.adminStats(),
      ]);
      setSongs(reset ? s : [...songs, ...s]);
      setStats(st);
      setHasMore(s.length >= PAGE_SIZE);
    } catch (e: any) {
      setError(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function refreshStats() {
    try {
      setStats(await api.adminStats());
    } catch {
      // 统计刷新失败不影响主流程
    }
  }

  function patchModeration(id: number, status: string, note: string) {
    setSongs((prev) => {
      if (filter && filter !== status) {
        // 当前按审核状态筛选时，处置后该条不再属于此筛选，移除以反映最新视图
        return prev.filter((s) => s.id !== id);
      }
      return prev.map((s) =>
        s.id === id ? { ...s, moderation_status: status, moderation_note: note } : s,
      );
    });
  }

  function loadMore() {
    load(false);
  }

  useEffect(() => {
    if (token) load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filter, statusFilter]);

  function saveToken() {
    localStorage.setItem("admin_token", token);
    load();
  }

  async function approve(id: number) {
    setBusy(true);
    try {
      await api.adminApprove(id);
      patchModeration(id, "approved", "");
      refreshStats();
    } catch (e: any) {
      setError(e?.message || "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function confirmReject() {
    if (rejectTarget == null) return;
    const note = rejectNote;
    setBusy(true);
    try {
      await api.adminReject(rejectTarget, note);
      patchModeration(rejectTarget, "rejected", note);
      setRejectTarget(null);
      setRejectNote("");
      refreshStats();
    } catch (e: any) {
      setError(e?.message || "操作失败");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div className="mx-auto max-w-md p-8">
        <h1 className="mb-4 text-2xl font-semibold">内容审核</h1>
        <p className="mb-4 text-base text-neutral-400">
          请输入管理密码（后台密钥），即可审核用户上传的歌曲。
        </p>
        <input
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="管理密码"
          className="mb-4 w-full rounded-xl border border-neutral-700 bg-neutral-900 px-4 py-3 text-base"
        />
        <button
          onClick={saveToken}
          className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-base font-medium hover:bg-emerald-500"
        >
          进入
        </button>
      </div>
    );
  }

  const FILTERS: { key: Filter; label: string }[] = [
    { key: "", label: "全部" },
    { key: "pending", label: "待审核" },
    { key: "approved", label: "已通过" },
    { key: "rejected", label: "已驳回" },
  ];

  const STATUS_FILTERS: { key: string; label: string }[] = [
    { key: "", label: "全部状态" },
    { key: "completed", label: "已完成" },
    { key: "processing", label: "生成中" },
    { key: "failed", label: "失败" },
  ];

  const pending = stats?.by_moderation?.pending || 0;
  const handled =
    (stats?.by_moderation?.approved || 0) + (stats?.by_moderation?.rejected || 0);

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">内容审核</h1>
        <button
          onClick={() => {
            localStorage.removeItem("admin_token");
            setToken("");
          }}
          className="text-sm text-neutral-400 hover:text-neutral-200"
        >
          退出
        </button>
      </div>

      {error && (
        <p className="mb-4 rounded-xl bg-red-950 px-4 py-3 text-base text-red-300">{error}</p>
      )}

      <div className="mb-5 grid grid-cols-3 gap-3">
        <BigCard emoji="🎵" title="歌曲总数" value={stats ? String(stats.total) : "-"} sub="平台全部歌曲" />
        <BigCard emoji="⏳" title="待审核" value={String(pending)} sub="需要你过目" />
        <BigCard emoji="✅" title="已处理" value={String(handled)} sub="通过 + 驳回" />
      </div>

      <div className="mb-5 flex flex-wrap gap-2 text-base">
        {FILTERS.map((f) => (
          <button
            key={f.key || "all"}
            onClick={() => setFilter(f.key)}
            className={`rounded-full px-4 py-2 ${
              filter === f.key ? "bg-indigo-500 text-white" : "bg-neutral-800"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="mb-5 flex flex-wrap gap-2 text-base">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.key || "all"}
            onClick={() => setStatusFilter(f.key)}
            className={`rounded-full px-4 py-2 ${
              statusFilter === f.key ? "bg-indigo-500 text-white" : "bg-neutral-800"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {songs.map((s) => {
          const ms = s.moderation_status || "pending";
          return (
            <div key={s.id} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold">{s.title}</div>
                  <div className="mt-1 text-sm text-neutral-400">
                    {s.user_email || "未知用户"}
                    {s.duration ? ` · ${Math.floor(s.duration / 60)}分${s.duration % 60}秒` : ""}
                    {s.status ? ` · 生成：${s.status}` : ""}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-neutral-500">
                    {s.content_category ? <span>分类：{s.content_category}</span> : null}
                    {s.engine_name ? <span>引擎：{s.engine_name}</span> : null}
                    {s.tier_key ? <span>套餐：{s.tier_key}</span> : null}
                    {s.cost_cny != null ? <span>成本：¥{s.cost_cny.toFixed(2)}</span> : null}
                    {s.price_cny != null ? <span>营收：¥{s.price_cny.toFixed(2)}</span> : null}
                    {s.margin_cny != null ? (
                      <span className={s.margin_cny >= 0 ? "text-emerald-400" : "text-red-400"}>
                        毛利：¥{s.margin_cny.toFixed(2)}
                      </span>
                    ) : null}
                  </div>
                </div>
                <span className={`shrink-0 rounded-full px-3 py-1 text-sm ${modColor(ms)}`}>
                  {modLabel(ms)}
                </span>
              </div>

              {s.cover_url && isAbsUrl(s.cover_url) ? (
                <img src={s.cover_url} alt="封面" className="mt-3 max-h-40 rounded-xl" />
              ) : null}

              {s.audio_url && isAbsUrl(s.audio_url) ? (
                <audio controls src={s.audio_url} className="mt-3 w-full">
                  你的浏览器不支持音频播放
                </audio>
              ) : null}

              {(s.lyric || s.prompt || s.style) && (
                <details className="mt-3 rounded-lg border border-neutral-800 p-2">
                  <summary className="cursor-pointer text-sm text-neutral-300">查看内容（歌词 / 提示词 / 风格）</summary>
                  <div className="mt-2 space-y-2 text-sm text-neutral-300">
                    {s.style ? <div><b>风格：</b>{s.style}</div> : null}
                    {s.prompt ? <div><b>提示词：</b>{s.prompt}</div> : null}
                    {s.lyric ? <div className="whitespace-pre-wrap"><b>歌词：</b>{s.lyric}</div> : null}
                  </div>
                </details>
              )}

              {ms === "rejected" && s.moderation_note ? (
                <p className="mt-3 rounded-lg bg-red-950 px-3 py-2 text-sm text-red-300">
                  驳回原因：{s.moderation_note}
                </p>
              ) : null}

              <div className="mt-3 flex gap-2">
                {ms !== "approved" && (
                  <button
                    onClick={() => approve(s.id)}
                    disabled={busy}
                    className="rounded-xl bg-emerald-600 px-4 py-2 text-base font-medium hover:bg-emerald-500 disabled:opacity-60"
                  >
                    通过
                  </button>
                )}
                {ms !== "rejected" && (
                  <button
                    onClick={() => setRejectTarget(s.id)}
                    disabled={busy}
                    className="rounded-xl bg-red-800 px-4 py-2 text-base font-medium hover:bg-red-700 disabled:opacity-60"
                  >
                    驳回
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {songs.length === 0 && (
          <p className="rounded-2xl border border-neutral-800 bg-neutral-900 p-6 text-center text-neutral-500">
            这里没有歌曲
          </p>
        )}
      </div>

      {hasMore && (
        <button
          onClick={loadMore}
          disabled={busy || loading}
          className="mt-4 w-full rounded-xl border border-neutral-700 px-4 py-3 text-base hover:bg-neutral-800 disabled:opacity-60"
        >
          {loading ? "加载中…" : "加载更多"}
        </button>
      )}

      {rejectTarget != null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-neutral-800 bg-neutral-900 p-5">
            <h3 className="mb-3 text-lg font-semibold">驳回原因（可选）</h3>
            <textarea
              value={rejectNote}
              onChange={(e) => setRejectNote(e.target.value)}
              rows={4}
              placeholder="如不填将记录为「管理员驳回」"
              className="mb-4 w-full rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2 text-base"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setRejectTarget(null);
                  setRejectNote("");
                }}
                className="rounded-xl px-4 py-2 text-base text-neutral-400 hover:text-neutral-200"
              >
                取消
              </button>
              <button
                onClick={confirmReject}
                disabled={busy}
                className="rounded-xl bg-red-700 px-5 py-2 text-base font-medium hover:bg-red-600 disabled:opacity-60"
              >
                确认驳回
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BigCard({ emoji, title, value, sub }: { emoji: string; title: string; value: string; sub: string }) {
  return (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
      <div className="text-2xl">{emoji}</div>
      <div className="mt-1 text-xs text-neutral-400">{title}</div>
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-neutral-500">{sub}</div>
    </div>
  );
}
