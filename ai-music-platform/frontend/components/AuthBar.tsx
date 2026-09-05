"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AuthBar() {
  const { isAuthed, email, login, logout } = useAuth();
  const [emailInput, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    try {
      const r =
        mode === "login"
          ? await api.login(emailInput, password)
          : await api.register(emailInput, password);
      login(r.access_token);
      setOpen(false);
      setEmail("");
      setPassword("");
    } catch (err: any) {
      setMsg(err?.message || "失败");
    }
  }

  if (isAuthed) {
    const name = email ? email.split("@")[0] : "已登录";
    return (
      <div className="flex items-center gap-2">
        <span
          className="max-w-[10rem] truncate text-sm text-neutral-300"
          title={email ?? ""}
        >
          {name}
        </span>
        <button
          onClick={logout}
          className="rounded-full px-3 py-1.5 text-sm text-neutral-400 transition hover:bg-neutral-800 hover:text-neutral-100"
        >
          退出
        </button>
      </div>
    );
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="rounded-full bg-indigo-500 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-400"
      >
        {open ? "关闭" : mode === "login" ? "登录" : "注册"}
      </button>
      {open && (
        <form
          onSubmit={submit}
          className="absolute right-0 z-10 mt-2 w-64 space-y-2 rounded-xl border border-neutral-800 bg-neutral-900 p-3 shadow-lg"
        >
          <input
            value={emailInput}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            placeholder="邮箱"
            aria-label="邮箱"
            className="w-full rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-indigo-500"
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="密码"
            aria-label="密码"
            className="w-full rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-indigo-500"
          />
          <button
            type="submit"
            className="w-full rounded-full bg-indigo-500 py-2 text-sm font-medium text-white transition hover:bg-indigo-400"
          >
            {mode === "login" ? "登录" : "注册"}
          </button>
          <button
            type="button"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
            className="w-full text-xs text-neutral-400 underline"
          >
            {mode === "login" ? "去注册" : "去登录"}
          </button>
          {msg && <p className="text-xs text-red-400">{msg}</p>}
        </form>
      )}
    </div>
  );
}
