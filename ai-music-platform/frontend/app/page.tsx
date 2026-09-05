import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-6 px-4 text-center">
      <h1 className="text-4xl font-bold">AI 音乐平台</h1>
      <p className="text-neutral-400">输入想法，生成完整带人声歌曲 · 对标 Suno</p>
      <Link
        href="/create"
        className="rounded-full bg-indigo-500 px-6 py-3 font-medium hover:bg-indigo-400"
      >
        开始创作
      </Link>
      <div className="flex items-center gap-4 text-sm">
        <Link href="/explore" className="text-indigo-400 hover:text-indigo-300">
          发现公开作品
        </Link>
        <Link href="/library" className="text-indigo-400 hover:text-indigo-300">
          我的作品
        </Link>
      </div>
    </main>
  );
}
