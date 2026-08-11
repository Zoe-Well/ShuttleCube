import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { PageHeader, Panel } from "@/components/operations/page";
import { AuditDrawer, type AuditEntry } from "./audit-drawer";

export function AuditTimeline() {
  const [entityType, setEntityType] = useState("");
  const [selected, setSelected] = useState<AuditEntry[] | null>(null);
  const query = useQuery({
    queryKey: ["audit", entityType],
    queryFn: () =>
      api<AuditEntry[]>(
        `/audit${entityType ? `?entity_type=${encodeURIComponent(entityType)}` : ""}`,
      ),
  });
  const groups = useMemo(() => {
    const byRequest = new Map<string, AuditEntry[]>();
    for (const item of query.data ?? []) {
      if (item.is_noop) continue;
      const group = byRequest.get(item.request_id) ?? [];
      group.push(item);
      byRequest.set(item.request_id, group);
    }
    return [...byRequest.values()];
  }, [query.data]);
  return (
    <section>
      <PageHeader
        eyebrow="Audit trail"
        title="操作审计"
        description="按操作人、业务实体和请求追查关键数据变化"
      />
      <Panel>
        <div className="flex items-center gap-2 border-b border-slate-200 p-4">
          <Search size={14} className="text-slate-400" />
          <select
            aria-label="业务类型筛选"
            className="field max-w-72"
            value={entityType}
            onChange={(event) => setEntityType(event.target.value)}
          >
            <option value="">全部关键业务</option>
            <option value="receivable">应收与收退款</option>
            <option value="fixed_class">固定班</option>
            <option value="enrollment">固定班学员权益</option>
            <option value="class_session">固定班课次</option>
            <option value="coach_fee">教练费用</option>
            <option value="payroll_settlement">教练结算</option>
            <option value="expense">经营支出</option>
            <option value="schedule_entry">排期</option>
            <option value="coach">教练资料</option>
            <option value="court">场地</option>
          </select>
          <span className="text-xs text-slate-400">同一次操作的关联记录已合并展示</span>
        </div>
        <div className="divide-y divide-slate-100">
          {groups.map((entries) => {
            const item = entries[0];
            return (
            <button
              className="grid w-full grid-cols-[160px_1fr_160px] gap-4 p-4 text-left text-sm hover:bg-slate-50"
              key={item.request_id}
              onClick={() => setSelected(entries)}
            >
              <span className="text-slate-500">
                {new Date(item.occurred_at).toLocaleString("zh-CN")}
              </span>
              <span>
                <b>{item.action_label}</b>
                 <small className="mt-1 block text-slate-400">
                   {item.entity_label} · {item.entity_name}
                   {entries.length > 1 ? ` · 包含 ${entries.length} 项关联变更` : ""}
                 </small>
                 <small className="mt-1 block text-slate-500">{item.business_summary}</small>
              </span>
              <span className="text-right">{item.actor_name}</span>
            </button>
            );
          })}
          {groups.length === 0 && <p className="p-5 text-sm text-slate-400">暂无关键业务操作</p>}
        </div>
      </Panel>
      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title="审计详情"
        description="查看操作前后摘要与原因"
      >
        {selected && <AuditDrawer entries={selected} />}
      </Drawer>
    </section>
  );
}
