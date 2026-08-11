import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";

import { api } from "@/api/client";

export function OtherIncomeForm({ onDone }: { onDone?: () => void }) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (payload: object) => api("/other-incomes", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(payload) }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["other-incomes"] }); onDone?.(); },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    mutation.mutate({ category: String(data.get("category")), received_at: new Date(String(data.get("received_at"))).toISOString(), amount: Number(data.get("amount")), payer: String(data.get("payer")), payment_method: String(data.get("payment_method")), notes: String(data.get("notes") || "") || null });
  };
  return <form className="grid gap-3 p-4" onSubmit={submit}><p className="rounded-md bg-amber-50 p-3 text-xs text-amber-800">仅登记装备、饮料、水等没有对应课程、订场或活动订单的即时收入；已有业务的收款请前往“业务收款”。</p><label className="text-xs font-medium">分类<input className="field mt-1" list="income-categories" name="category" placeholder="选择或输入自定义分类" required /><datalist id="income-categories"><option value="equipment_sale">装备售卖</option><option value="drinks">饮料和水</option><option value="other">其他</option></datalist></label><label className="text-xs font-medium">收入时间<input className="field mt-1" name="received_at" type="datetime-local" required /></label><label className="text-xs font-medium">金额<input className="field mt-1" min="0.01" name="amount" step="0.01" type="number" required /></label><label className="text-xs font-medium">付款方<input className="field mt-1" name="payer" placeholder="例如：散客、某学员家长" required /></label><label className="text-xs font-medium">收款方式<select className="field mt-1" name="payment_method" defaultValue="wechat"><option value="wechat">微信</option><option value="alipay">支付宝</option><option value="cash">现金</option><option value="bank">银行转账</option></select></label><label className="text-xs font-medium">备注<textarea className="field mt-1" name="notes" /></label>{mutation.error && <p className="text-xs text-red-600" role="alert">{mutation.error.message}</p>}<button className="btn btn-primary" disabled={mutation.isPending}>登记收入</button></form>;
}
