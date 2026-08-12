import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import { beijingDateTimeInputToIso } from "@/lib/beijing-time";
import type { ReceivableSummary } from "./types";

export function PaymentDialog({
  receivableId,
  defaultAmount,
  disabled,
  onRecorded,
}: {
  receivableId: string;
  defaultAmount?: number;
  disabled?: boolean;
  onRecorded?: () => void;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: (payload: object) =>
      api<ReceivableSummary>(`/receivables/${receivableId}/payments`, {
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
      paid_at: beijingDateTimeInputToIso(String(data.get("paid_at"))),
      amount: Number(data.get("amount")),
      method: String(data.get("method")),
      payer_name: String(data.get("payer_name") || "") || null,
      notes: String(data.get("notes") || "") || null,
    });
  };
  return (
    <>
      <button className="btn btn-primary" disabled={disabled} type="button" onClick={() => setOpen(true)}>
        登记收款
      </button>
      {open && (
        <div aria-label="登记收款" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/30" role="dialog">
          <form className="panel w-[420px] p-5" onSubmit={submit}>
            <h3 className="text-base font-semibold">登记实际收款</h3>
            <label className="mt-4 block text-xs font-medium">收款时间<input className="field mt-1" name="paid_at" type="datetime-local" required /></label>
            <label className="mt-3 block text-xs font-medium">金额<input className="field mt-1" defaultValue={defaultAmount} max={defaultAmount} min="0.01" name="amount" step="0.01" type="number" required /></label>
            <label className="mt-3 block text-xs font-medium">方式<select className="field mt-1" name="method" defaultValue="wechat"><option value="wechat">微信</option><option value="alipay">支付宝</option><option value="cash">现金</option><option value="bank">银行转账</option></select></label>
            <label className="mt-3 block text-xs font-medium">付款人<input className="field mt-1" name="payer_name" /></label>
            <label className="mt-3 block text-xs font-medium">备注<textarea className="field mt-1" name="notes" /></label>
            {mutation.error && <p className="mt-3 text-xs text-red-600" role="alert">{mutation.error.message}</p>}
            <div className="mt-5 flex justify-end gap-2"><button className="btn" type="button" onClick={() => setOpen(false)}>取消</button><button className="btn btn-primary" disabled={mutation.isPending}>确认收款</button></div>
          </form>
        </div>
      )}
    </>
  );
}
