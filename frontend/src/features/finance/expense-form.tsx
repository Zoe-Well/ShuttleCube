import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";

import { api } from "@/api/client";
import { beijingDateTimeInputToIso } from "@/lib/beijing-time";

export function ExpenseForm({ onDone }: { onDone?: () => void }) {
  const client = useQueryClient();
  const mutation = useMutation({ mutationFn: (payload: object) => api("/expenses", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(payload) }), onSuccess: () => { void client.invalidateQueries({ queryKey: ["expenses"] }); onDone?.(); } });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); mutation.mutate({ category: String(data.get("category")), spent_at: beijingDateTimeInputToIso(String(data.get("spent_at"))), amount: Number(data.get("amount")), payee: String(data.get("payee")), payment_method: String(data.get("payment_method")), notes: String(data.get("notes") || "") || null }); };
  return <form className="grid gap-3 p-4" onSubmit={submit}><label className="text-xs font-medium">分类<input className="field mt-1" list="expense-categories" name="category" placeholder="选择或输入自定义分类" required /><datalist id="expense-categories"><option value="rent">场租</option><option value="utilities">水电</option><option value="equipment">器材采购</option><option value="supplies">日常物料</option><option value="other">其他</option></datalist></label><label className="text-xs font-medium">支出时间<input className="field mt-1" name="spent_at" type="datetime-local" required /></label><label className="text-xs font-medium">金额<input className="field mt-1" min="0.01" name="amount" step="0.01" type="number" required /></label><label className="text-xs font-medium">收款方<input className="field mt-1" name="payee" required /></label><label className="text-xs font-medium">付款方式<select className="field mt-1" name="payment_method" defaultValue="wechat"><option value="wechat">微信</option><option value="alipay">支付宝</option><option value="cash">现金</option><option value="bank">银行转账</option></select></label><label className="text-xs font-medium">备注<textarea className="field mt-1" name="notes" /></label>{mutation.error && <p className="text-xs text-red-600" role="alert">{mutation.error.message}</p>}<button className="btn btn-primary" disabled={mutation.isPending}>登记支出</button></form>;
}
