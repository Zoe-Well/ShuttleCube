import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { WalletCards } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { MetricCard, PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { localDateKey } from "@/lib/utils";
import { formatBeijingDate } from "@/lib/beijing-time";
import { SettlementDialog } from "./settlement-dialog";
import { SettlementDetail } from "./settlement-detail";
import type { CoachFee, Settlement } from "./types";

type FeeResult = { calculated_amount: number; items: CoachFee[] };
type Coach = { id: string; name: string };

const currentMonth = localDateKey(new Date()).slice(0, 7);
const monthBounds = (month: string) => {
  const [year, index] = month.split("-").map(Number);
  const last = new Date(Date.UTC(year, index, 0)).getUTCDate();
  return [`${month}-01`, `${month}-${String(last).padStart(2, "0")}`];
};

export function CoachFeesPage() {
  const client = useQueryClient();
  const [coachId, setCoachId] = useState("");
  const [month, setMonth] = useState(currentMonth);
  const [settling, setSettling] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState<CoachFee | null>(null);
  const [adjustmentAmount, setAdjustmentAmount] = useState(0);
  const [adjustmentReason, setAdjustmentReason] = useState("");
  const coaches = useQuery({ queryKey: ["coaches"], queryFn: () => api<Coach[]>("/coaches") });
  const effectiveCoach = coachId || coaches.data?.[0]?.id || "";
  const [from, to] = useMemo(() => monthBounds(month), [month]);
  const feesQuery = useQuery({
    queryKey: ["coach-fees", effectiveCoach, month],
    queryFn: () => api<FeeResult>(`/coach-fees?coach_id=${effectiveCoach}&from=${from}&to=${to}`),
    enabled: Boolean(effectiveCoach),
  });
  const settlements = useQuery({
    queryKey: ["payroll-settlements", effectiveCoach, month],
    queryFn: () => api<Settlement[]>(`/payroll-settlements?coach_id=${effectiveCoach}&period_month=${month}-01`),
    enabled: Boolean(effectiveCoach),
  });
  const adjust = useMutation({
    mutationFn: () =>
      api<CoachFee>(`/coach-fees/${adjusting?.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          adjustment_amount: adjustmentAmount,
          reason: adjustmentReason,
          version: adjusting?.version,
        }),
      }),
    onSuccess: () => {
      setAdjusting(null);
      setAdjustmentAmount(0);
      setAdjustmentReason("");
      void client.invalidateQueries({ queryKey: ["coach-fees"] });
    },
  });
  const fees = feesQuery.data?.items ?? [];
  const pending = fees.filter((item) => item.status === "pending");
  const pendingAmount = pending.reduce((sum, item) => sum + Number(item.amount), 0);
  const coachName = (id: string) => coaches.data?.find((item) => item.id === id)?.name ?? id;
  const beginAdjustment = (fee: CoachFee) => {
    setAdjusting(fee);
    setAdjustmentAmount(Number(fee.adjustment_amount));
    setAdjustmentReason(fee.adjustment_reason ?? "");
  };

  return (
    <section>
      <PageHeader
        eyebrow="Coach payroll"
        title="教练费用与月度结算"
        description="每次履约生成独立费用；每位教练按自然月一次性全量结算"
        actions={
          <button className="btn btn-primary" disabled={!pending.length || !effectiveCoach} onClick={() => setSettling(true)}>
            结算本月全部费用
          </button>
        }
      />
      <Panel className="mb-4" title="月度查询" description="选择教练和月份，系统自动汇总当月全部费用，不能手工漏选">
        <div className="grid grid-cols-2 gap-4 p-4">
          <label className="field-label">教练<select className="field" value={effectiveCoach} onChange={(event) => setCoachId(event.target.value)}>{coaches.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label className="field-label">月份<input className="field" type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label>
        </div>
      </Panel>
      <div className="mb-4 grid grid-cols-3 gap-3">
        <MetricCard label="本月待结费用" value={`¥${pendingAmount.toFixed(2)}`} footnote="来自当月全部已完成授课" icon={<WalletCards size={16} />} />
        <MetricCard label="本月待结笔数" value={String(pending.length)} footnote="包含零金额履约，每笔对应一次授课" icon={<WalletCards size={16} />} />
        <MetricCard label="本月结算记录" value={String(settlements.data?.length ?? 0)} footnote="同月仅允许一份有效结算" icon={<WalletCards size={16} />} />
      </div>
      <Panel title="费用明细" description="基础金额、调整和最终应付均可追溯到具体业务">
        {fees.length ? (
          <table className="data-table">
            <thead><tr><th>业务来源</th><th>发生时间</th><th>基础金额</th><th>调整</th><th>最终应付</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {fees.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.business_path ? <Link className="table-primary hover:text-emerald-700" to={item.business_path}>{item.business_name}</Link> : <span className="table-primary">{item.business_name}</span>}
                    <div className="table-secondary">{item.coach_name ?? coachName(item.coach_id)}</div>
                  </td>
                  <td>{formatBeijingDate(item.occurred_at)}</td>
                  <td>¥{Number(item.base_amount).toFixed(2)}</td>
                  <td className={item.adjustment_amount ? "text-amber-700" : "text-slate-400"}>{item.adjustment_amount ? `${item.adjustment_amount > 0 ? "+" : ""}¥${Number(item.adjustment_amount).toFixed(2)}` : "—"}</td>
                  <td className="font-semibold">¥{Number(item.amount).toFixed(2)}</td>
                  <td><StatusBadge status={item.status} label={item.status === "pending" ? "待结算" : item.status === "settled" ? "已结算" : undefined} /></td>
                  <td>{item.status === "pending" ? <button className="text-xs font-semibold text-emerald-700" onClick={() => beginAdjustment(item)}>调整</button> : <span className="text-xs text-slate-400">已锁定</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="p-5 text-sm text-slate-400">该教练本月暂无费用明细。</p>}
      </Panel>
      <Panel className="mt-4" title="月度结算历史">
        <div className="divide-y divide-slate-100">{settlements.data?.map((item) => <button className="flex w-full justify-between p-4 text-left text-sm" key={item.id} onClick={() => setDetail(item.id)}><span>{coachName(item.coach_id)} · {item.period_start.slice(0, 7)}</span><b>¥{item.actual_amount.toFixed(2)}</b></button>)}</div>
      </Panel>
      {settling && <SettlementDialog coachId={effectiveCoach} fees={pending} month={month} onClose={() => setSettling(false)} />}
      <Drawer open={detail !== null} onClose={() => setDetail(null)} title="结算详情" description="费用、工资支出与凭证">{detail && <SettlementDetail settlementId={detail} onVoided={() => setDetail(null)} />}</Drawer>
      <Drawer open={adjusting !== null} onClose={() => setAdjusting(null)} title="调整待结教练费用" description={adjusting?.business_name ?? "仅待结费用允许调整"}>
        {adjusting && <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); adjust.mutate(); }}>
          <div className="rounded-md bg-slate-50 p-3 text-sm">基础金额：¥{adjusting.base_amount.toFixed(2)} / 调整后应付：¥{Math.max(adjusting.base_amount + adjustmentAmount, 0).toFixed(2)}</div>
          <label className="field-label">调增/调减金额<input className="field" step="0.01" type="number" value={adjustmentAmount} onChange={(event) => setAdjustmentAmount(Number(event.target.value))} /><span className="field-hint">调减请输入负数，例如 -20</span></label>
          <label className="field-label">调整原因<textarea className="field" required value={adjustmentReason} onChange={(event) => setAdjustmentReason(event.target.value)} /></label>
          {adjust.error ? <p className="text-xs text-red-600" role="alert">{adjust.error.message}</p> : null}
          <div className="flex justify-end"><button className="btn btn-primary" disabled={adjust.isPending || !adjustmentReason.trim()}>保存调整</button></div>
        </form>}
      </Drawer>
    </section>
  );
}
