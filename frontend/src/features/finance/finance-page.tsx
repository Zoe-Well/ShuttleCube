import { useQuery } from "@tanstack/react-query";
import { WalletCards } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { MetricCard, PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { ReceivableDetail } from "./receivable-detail";
import type { ReceivableSummary } from "./types";
import { sourceNames, yuan } from "./types";

export function FinancePage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<"outstanding" | "settled" | "all">("outstanding");
  const query = useQuery({
    queryKey: ["receivables"],
    queryFn: () => api<ReceivableSummary[]>("/receivables"),
  });
  const items = query.data ?? [];
  const outstanding = items.reduce((sum, item) => sum + Number(item.outstanding_amount), 0);
  const received = items.reduce((sum, item) => sum + Number(item.net_received), 0);
  const visibleItems = items.filter((item) => {
    if (view === "outstanding") return item.outstanding_amount > 0;
    if (view === "settled") return item.actual_amount > 0 && item.outstanding_amount === 0;
    return true;
  });
  return (
    <section>
      <PageHeader
        eyebrow="Finance operations"
        title="业务收款"
        description="管理固定班、私教、订场和活动产生的应收、收款与退款"
      />
      <div className="mb-4 grid grid-cols-3 gap-3">
        <MetricCard
          label="业务应收记录"
          value={String(items.filter((item) => item.actual_amount > 0).length)}
          footnote="不含零金额免费业务"
          icon={<WalletCards size={16} />}
        />
        <MetricCard
          label="累计业务净收款"
          value={yuan(received)}
          footnote="有效收款减退款"
          icon={<WalletCards size={16} />}
        />
        <MetricCard
          label="当前待收款"
          value={yuan(outstanding)}
          footnote="仍需跟进的款项"
          icon={<WalletCards size={16} />}
        />
      </div>
      <Panel
        title="业务应收明细"
        description="已有业务的收款请在这里登记；装备、饮料等即时销售请使用日常收支"
      >
        <div className="flex gap-2 border-b border-slate-100 p-4" aria-label="业务收款筛选">
          {([
            ["outstanding", "待收款"],
            ["settled", "已结清"],
            ["all", "全部（含免费）"],
          ] as const).map(([key, label]) => (
            <button
              className={view === key ? "btn btn-primary" : "btn"}
              key={key}
              type="button"
              onClick={() => setView(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {visibleItems.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>业务</th>
                <th>实际应收</th>
                <th>净实收</th>
                <th>退款</th>
                <th>欠费</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((item) => (
                <tr
                  className={item.outstanding_amount > 0 ? "[&_*]:!text-red-600" : ""}
                  key={item.receivable_id}
                >
                  <td className="table-primary">
                    {item.business_name ?? sourceNames[item.source_type] ?? item.source_type}
                  </td>
                  <td>{yuan(item.actual_amount)}</td>
                  <td>{yuan(item.net_received)}</td>
                  <td>{yuan(item.refunded_amount)}</td>
                  <td className={item.outstanding_amount > 0 ? "font-semibold" : ""}>
                    {yuan(item.outstanding_amount)}
                  </td>
                  <td>
                    {item.actual_amount === 0 ? (
                      <span className="text-xs text-slate-500">无需收款</span>
                    ) : (
                      <StatusBadge status={item.payment_status} />
                    )}
                  </td>
                  <td>
                    <button
                      className="text-xs font-semibold text-emerald-700"
                      onClick={() => setSelected(item.receivable_id)}
                    >
                      {item.outstanding_amount > 0 ? "收款/详情" : "查看详情"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="p-5 text-sm text-slate-400">
            {view === "outstanding" ? "当前没有待收款业务" : "该分类下暂无业务应收记录"}
          </p>
        )}
      </Panel>
      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title="业务收款详情"
        description="查看资金流水并登记收退款"
      >
        {selected && <ReceivableDetail receivableId={selected} />}
      </Drawer>
    </section>
  );
}
