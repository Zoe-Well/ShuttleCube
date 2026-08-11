import { useState } from "react";

import { api } from "@/api/client";

export function BulkCancelBar({
  endpoint,
  ids,
  onDone,
}: {
  endpoint: string;
  ids: string[];
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  if (!ids.length) return null;

  const submit = async () => {
    if (!reason.trim()) {
      setError("请填写批量删除原因");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api(endpoint, { method: "POST", body: JSON.stringify({ ids, reason: reason.trim() }) });
      setOpen(false);
      setReason("");
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "批量删除失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-slate-500">已选 {ids.length} 条</span>
      <button className="btn btn-danger" onClick={() => setOpen(true)} type="button">批量删除</button>
      {open && (
        <div className="fixed inset-0 z-[90] grid place-items-center bg-slate-950/35 p-6">
          <section className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl" role="dialog" aria-modal="true">
            <h2 className="m-0 text-sm font-semibold text-slate-800">永久删除 {ids.length} 条记录</h2>
            <p className="mt-2 text-xs leading-5 text-red-600">业务记录、关联排期和资源占用都会永久删除，无法恢复。</p>
            <textarea className="field mt-3" placeholder="请输入统一删除原因" value={reason} onChange={(event) => setReason(event.target.value)} />
            {error && <div className="mt-3 rounded-md bg-red-50 p-3 text-xs font-medium text-red-700" role="alert">{error}</div>}
            <footer className="mt-4 flex justify-end gap-2 border-t border-slate-100 pt-4">
              <button className="btn" onClick={() => setOpen(false)} type="button">返回</button>
              <button className="btn btn-danger" disabled={saving} onClick={() => void submit()} type="button">确认永久删除</button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}
