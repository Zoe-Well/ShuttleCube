import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";

import { api } from "@/api/client";
import { beijingDateTimeInputToIso } from "@/lib/beijing-time";
import type { CoachFee, Settlement } from "./types";

export function SettlementDialog({ coachId, fees, month, onClose }: { coachId: string; fees: CoachFee[]; month: string; onClose: () => void }) {
  const client = useQueryClient();
  const calculated = fees.reduce((sum, item) => sum + Number(item.amount), 0);
  const mutation = useMutation({ mutationFn: (payload: object) => api<Settlement>("/payroll-settlements", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(payload) }), onSuccess: () => { void client.invalidateQueries({ queryKey: ["coach-fees"] }); void client.invalidateQueries({ queryKey: ["payroll-settlements"] }); onClose(); } });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); mutation.mutate({ coach_id: coachId, period_month: `${month}-01`, actual_amount: Number(data.get("actual_amount")), adjustment_reason: String(data.get("adjustment_reason") || "") || null, paid_at: beijingDateTimeInputToIso(String(data.get("paid_at"))) }); };
  return <div aria-label="确认教练月结" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/30" role="dialog"><form className="panel w-[460px] p-5" onSubmit={submit}><h3 className="text-base font-semibold">确认 {month} 教练月结</h3><p className="mt-1 text-xs text-slate-500">系统将自动锁定本月全部 {fees.length} 笔待结费用，计算金额 ¥{calculated.toFixed(2)}</p><label className="mt-4 block text-xs font-medium">支付时间<input className="field mt-1" name="paid_at" type="datetime-local" required /></label><label className="mt-3 block text-xs font-medium">实际支付<input className="field mt-1" defaultValue={calculated.toFixed(2)} min="0" name="actual_amount" step="0.01" type="number" required /></label><label className="mt-3 block text-xs font-medium">调整原因<textarea className="field mt-1" name="adjustment_reason" /></label>{mutation.error && <p className="mt-3 text-xs text-red-600" role="alert">{mutation.error.message}</p>}<div className="mt-5 flex justify-end gap-2"><button className="btn" type="button" onClick={onClose}>取消</button><button className="btn btn-primary" disabled={mutation.isPending}>确认支付并结算</button></div></form></div>;
}
