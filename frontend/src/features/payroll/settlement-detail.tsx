import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { AttachmentViewer } from "@/features/finance/attachment-viewer";
import { VoidRecordButton } from "@/features/finance/void-record-button";
import type { Settlement } from "./types";

export function SettlementDetail({ settlementId, onVoided }: { settlementId: string; onVoided?: () => void }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["payroll-settlement", settlementId], queryFn: () => api<Settlement>(`/payroll-settlements/${settlementId}`) });
  const item = query.data;
  if (!item) return <p className="p-4 text-sm text-slate-400">正在加载结算详情…</p>;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["coach-fees"] });
    void client.invalidateQueries({ queryKey: ["payroll-settlements"] });
    void client.invalidateQueries({ queryKey: ["expenses"] });
    onVoided?.();
  };
  return <div className="grid gap-3 p-4 text-sm"><div className="grid grid-cols-2 gap-3"><div><span className="text-slate-400">计算金额</span><b className="block">¥{item.calculated_amount.toFixed(2)}</b></div><div><span className="text-slate-400">实际支付</span><b className="block">¥{item.actual_amount.toFixed(2)}</b></div></div><p>期间：{item.period_start} 至 {item.period_end}</p><p>包含 {item.fee_ids.length} 笔费用 · 状态 {item.status === "confirmed" ? "已确认" : "已作废"}</p><AttachmentViewer ownerType="payroll_settlement" ownerId={item.id} />{item.status === "confirmed" ? <div className="flex justify-end"><VoidRecordButton endpoint={`/payroll-settlements/${item.id}/void`} label="作废结算" onVoided={refresh} /></div> : null}</div>;
}
