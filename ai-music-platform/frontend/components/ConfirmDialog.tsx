"use client";

import { useEffect } from "react";

export default function ConfirmDialog({
  open,
  title = "确认操作",
  message,
  confirmText = "确定",
  cancelText = "取消",
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-neutral-800 bg-neutral-900 p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-2 text-base font-semibold text-neutral-100">{title}</h3>
        <p className="mb-4 text-sm text-neutral-400">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-full border border-neutral-700 px-4 py-1.5 text-sm text-neutral-300 transition hover:bg-neutral-800"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={
              danger
                ? "rounded-full bg-red-500 px-4 py-1.5 text-sm text-white transition hover:bg-red-400"
                : "rounded-full bg-indigo-500 px-4 py-1.5 text-sm text-white transition hover:bg-indigo-400"
            }
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
