import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { PageHeader, Panel } from "@/components/operations/page";
import { AttachmentViewer } from "./attachment-viewer";
import { ExpenseForm } from "./expense-form";
import { OtherIncomeForm } from "./other-income-form";
import { paymentMethodName, yuan } from "./types";

type Expense = { id: string; category: string; spent_at: string; amount: number; payee: string; payment_method: string; source_type?: string | null; source_id?: string | null; status: string; notes?: string | null; void_reason?: string | null };
type OtherIncome = { id: string; category: string; received_at: string; amount: number; payer: string; payment_method: string; status: string };
type CashRow = { id: string; kind: "income" | "expense"; occurredAt: string; category: string; party: string; paymentMethod: string; amount: number; status: string; sourceType?: string | null; sourceId?: string | null; notes?: string | null; voidReason?: string | null };

const categoryNames: Record<string, string> = {
  equipment_sale: "装备售卖",
  drinks: "饮料和水",
  rent: "场租",
  utilities: "水电",
  equipment: "器材采购",
  supplies: "日常物料",
  other: "其他",
  coach_payroll: "教练工资",
};

export function ExpensesPage() {
  const client = useQueryClient();
  const [incomeOpen, setIncomeOpen] = useState(false);
  const [expenseOpen, setExpenseOpen] = useState(false);
  const [voiding, setVoiding] = useState<CashRow | null>(null);
  const [selectedExpense, setSelectedExpense] = useState<CashRow | null>(null);
  const expenses = useQuery({ queryKey: ["expenses"], queryFn: () => api<Expense[]>("/expenses") });
  const incomes = useQuery({ queryKey: ["other-incomes"], queryFn: () => api<OtherIncome[]>("/other-incomes") });
  const rows = useMemo<CashRow[]>(() => [
    ...(incomes.data ?? []).map((item) => ({ id: item.id, kind: "income" as const, occurredAt: item.received_at, category: item.category, party: item.payer, paymentMethod: item.payment_method, amount: Number(item.amount), status: item.status })),
    ...(expenses.data ?? []).map((item) => ({ id: item.id, kind: "expense" as const, occurredAt: item.spent_at, category: item.category, party: item.payee, paymentMethod: item.payment_method, amount: Number(item.amount), status: item.status, sourceType: item.source_type, sourceId: item.source_id, notes: item.notes, voidReason: item.void_reason })),
  ].sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)), [expenses.data, incomes.data]);
  const voidMutation = useMutation({
    mutationFn: ({ item, reason }: { item: CashRow; reason: string }) => api(
      item.kind === "income" ? `/other-incomes/${item.id}/void` : `/expenses/${item.id}/void`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
    onSuccess: () => {
      setVoiding(null);
      void client.invalidateQueries({ queryKey: ["expenses"] });
      void client.invalidateQueries({ queryKey: ["other-incomes"] });
    },
  });
  const submitVoid = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!voiding) return;
    const data = new FormData(event.currentTarget);
    voidMutation.mutate({ item: voiding, reason: String(data.get("reason")) });
  };

  return (
    <section>
      <PageHeader
        eyebrow="Other cash flow"
        title="日常收支"
        description="登记装备、饮料、水等即时收入和日常经营成本；课程、订场及活动收款请使用业务收款"
        actions={<><button className="btn" onClick={() => setExpenseOpen(true)}>记支出</button><button className="btn btn-primary" onClick={() => setIncomeOpen(true)}>记收入</button></>}
      />
      <Panel title="日常收支流水" description="教练工资由教练结算自动生成，只能回到结算单处理；其他错误记录请填写原因后作废">
        {rows.length ? (
          <table className="data-table">
            <thead><tr><th>日期</th><th>收支</th><th>分类</th><th>往来方</th><th>方式</th><th>金额</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>{rows.map((item) => (
              <tr key={`${item.kind}-${item.id}`}>
                <td>{new Date(item.occurredAt).toLocaleString("zh-CN")}</td>
                <td>{item.kind === "income" ? "收入" : "支出"}</td>
                <td>{categoryNames[item.category] ?? item.category}</td>
                <td className="table-primary">{item.party}</td>
                <td>{paymentMethodName(item.paymentMethod)}</td>
                <td className={item.kind === "income" ? "font-semibold text-emerald-700" : "font-semibold text-red-600"}>{item.kind === "income" ? "+" : "−"}{yuan(item.amount)}</td>
                <td>{item.status === "effective" ? "有效" : "已作废"}</td>
                <td>
                  <div className="flex items-center gap-2">
                    {item.kind === "expense" ? <button className="text-xs font-semibold text-emerald-700" onClick={() => setSelectedExpense(item)}>详情</button> : null}
                    {item.sourceType === "payroll_settlement" ? <Link className="text-xs font-semibold text-emerald-700" to="/payroll">查看结算</Link> : item.status === "effective" ? <button className="text-xs font-semibold text-red-600" onClick={() => setVoiding(item)}>作废</button> : null}
                  </div>
                </td>
              </tr>
            ))}</tbody>
          </table>
        ) : <p className="p-5 text-sm text-slate-400">暂无日常收支记录</p>}
      </Panel>
      <Drawer open={incomeOpen} onClose={() => setIncomeOpen(false)} title="登记其他收入" description="适用于即时收款的装备、饮料、水和其他营收"><OtherIncomeForm onDone={() => setIncomeOpen(false)} /></Drawer>
      <Drawer open={expenseOpen} onClose={() => setExpenseOpen(false)} title="登记经营支出" description="登记实际发生的经营成本"><ExpenseForm onDone={() => setExpenseOpen(false)} /></Drawer>
      <Drawer open={voiding !== null} onClose={() => setVoiding(null)} title="作废收支记录" description="作废后报表不再统计，原记录和原因仍会保留">
        <form className="grid gap-4" onSubmit={submitVoid}><label className="field-label">作废原因<textarea className="field" name="reason" required /></label>{voidMutation.error ? <p className="text-xs text-red-600">{voidMutation.error.message}</p> : null}<button className="btn btn-primary" disabled={voidMutation.isPending}>确认作废</button></form>
      </Drawer>
      <Drawer open={selectedExpense !== null} onClose={() => setSelectedExpense(null)} title="支出详情" description="查看支出来源、备注与付款凭证">
        {selectedExpense ? <div className="grid gap-3 p-4 text-sm"><div className="grid grid-cols-2 gap-3"><div><span className="text-slate-400">分类</span><b className="block">{categoryNames[selectedExpense.category] ?? selectedExpense.category}</b></div><div><span className="text-slate-400">金额</span><b className="block">{yuan(selectedExpense.amount)}</b></div><div><span className="text-slate-400">收款方</span><b className="block">{selectedExpense.party}</b></div><div><span className="text-slate-400">付款方式</span><b className="block">{paymentMethodName(selectedExpense.paymentMethod)}</b></div></div>{selectedExpense.sourceType === "payroll_settlement" ? <p className="rounded-md bg-amber-50 p-3 text-amber-800">该支出由教练结算自动生成。如需纠错，请前往教练结算作废结算单。</p> : null}{selectedExpense.notes ? <p>备注：{selectedExpense.notes}</p> : null}{selectedExpense.voidReason ? <p className="text-red-600">作废原因：{selectedExpense.voidReason}</p> : null}<AttachmentViewer ownerType="expense" ownerId={selectedExpense.id} /></div> : null}
      </Drawer>
    </section>
  );
}
