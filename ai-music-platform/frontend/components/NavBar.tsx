"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import AuthBar from "@/components/AuthBar";

const LINKS = [
  { href: "/create", label: "创作" },
  { href: "/explore", label: "发现" },
  { href: "/library", label: "我的作品" },
  { href: "/account", label: "账户" },
  { href: "/admin", label: "审核后台" },
  { href: "/admin/music-config", label: "平台设置" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-20 border-b border-neutral-800 bg-neutral-950/90 backdrop-blur">
      <nav className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3">
        <Link
          href="/"
          className="text-lg font-bold text-neutral-100 transition hover:text-white"
        >
          AI 音乐平台
        </Link>
        <div className="flex flex-wrap items-center gap-1 text-sm">
          {LINKS.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-full px-3 py-1.5 transition ${
                  active
                    ? "bg-indigo-500 text-white"
                    : "text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
          <div className="ml-2">
            <AuthBar />
          </div>
        </div>
      </nav>
    </header>
  );
}
