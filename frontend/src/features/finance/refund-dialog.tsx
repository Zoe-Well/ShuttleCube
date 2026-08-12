import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import { beijingDateTimeInputToIso } from "@/lib/beijing-time";

export function RefundDialog({ receivableId, disabled, maxAmount, lessonBalance, onRecorded }: { receivableId: string; disabled?: boolean; maxAmount?: number; lessonBalance?: number | null; onRecorded?: () => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: (payload: object) =>
      api(`/receivables/${receivableId}/refunds`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["receivables"] });
      void queryClient.invalidateQueries({ queryKey: ["receivable", receivableId] });
      onRecorded?.();
      setOpen(false);
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    mutation.mutate({
      refunded_at: beijingDateTimeInputToIso(String(data.get("refunded_at"))),
      actual_amount: Number(data.get("actual_amount")),
      suggested_amount: Number(data.get("actual_amount")),
      lesson_units_to_remove: Number(data.get("lesson_units_to_remove") || 0),
      reason: String(data.get("reason")),
    });
  };
  return (
    <>
      <button className="btn" disabled={disabled} type="button" onClick={() => setOpen(true)}>登记退款</button>
      {open && <div aria-label="登记退款" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/30" role="dialog"><form className="panel w-[420px] p-5" onSubmit={submit}><h3 className="text-base font-semibold">登记实际退款</h3><p className="mt-1 text-xs text-slate-500">退款会减少实际应收；如同时退回未使用课时，请填写对应节数。</p><label className="mt-4 block text-xs font-medium">退款时间<input className="field mt-1" name="refunded_at" type="datetime-local" required /></label><label className="mt-3 block text-xs font-medium">退款金额<input className="field mt-1" max={maxAmount} min="0.01" name="actual_amount" step="0.01" type="number" required /><span className="field-hint">当前最多可退 ¥{Number(maxAmount ?? 0).toFixed(2)}</span></label>{lessonBalance !== null && lessonBalance !== undefined ? <label className="mt-3 block text-xs font-medium">退回未使用课时<input className="field mt-1" max={lessonBalance} min="0" name="lesson_units_to_remove" type="number" defaultValue="0" /><span className="field-hint">当前剩余 {lessonBalance} 节；填写 0 表示只退款、不改变课时。</span></label> : <input name="lesson_units_to_remove" type="hidden" value="0" />}<label className="mt-3 block text-xs font-medium">退款原因<textarea className="field mt-1" name="reason" required /></label>{mutation.error && <p className="mt-3 text-xs text-red-600" role="alert">{mutation.error.message}</p>}<div className="mt-5 flex justify-end gap-2"><button className="btn" type="button" onClick={() => setOpen(false)}>取消</button><button className="btn btn-primary" disabled={mutation.isPending}>确认退款</button></div></form></div>}
    </>
  );
}
