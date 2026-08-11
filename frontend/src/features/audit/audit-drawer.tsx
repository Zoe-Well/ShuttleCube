import { Panel } from "@/components/operations/page";

export type AuditEntry = {
  id: string;
  actor_name: string;
  action_type: string;
  action_label: string;
  entity_type: string;
  entity_id: string;
  entity_label: string;
  entity_name: string;
  occurred_at: string;
  before_summary?: Record<string, unknown> | null;
  after_summary?: Record<string, unknown> | null;
  reason?: string | null;
  request_id: string;
  business_summary: string;
  changes: Array<{ field: string; before: string; after: string }>;
  is_noop: boolean;
};

export function AuditDrawer({ entries }: { entries: AuditEntry[] }) {
  const entry = entries[0];
  return (
    <div className="grid gap-4 p-1">
      <Panel title="操作信息">
        <dl className="grid grid-cols-2 gap-3 p-4 text-sm">
          <div>
            <dt className="text-slate-400">操作人</dt>
            <dd>{entry.actor_name}</dd>
          </div>
          <div>
            <dt className="text-slate-400">时间</dt>
            <dd>{new Date(entry.occurred_at).toLocaleString("zh-CN")}</dd>
          </div>
          <div>
            <dt className="text-slate-400">业务操作</dt>
            <dd>{entry.action_label}</dd>
          </div>
          <div>
            <dt className="text-slate-400">业务对象</dt>
            <dd>{entry.entity_name}</dd>
          </div>
          <div><dt className="text-slate-400">关联变更</dt><dd>{entries.length} 项</dd></div>
        </dl>
      </Panel>
      {entries.map((item) => (
        <Panel key={item.id} title={item.action_label} description={`${item.entity_label} · ${item.entity_name}`}>
          <div className="grid gap-3 p-4 text-sm">
            <p className="m-0 text-slate-700">{item.business_summary}</p>
            {item.changes.length ? (
              <div className="overflow-hidden rounded-md border border-slate-200">
                {item.changes.map((change) => (
                  <div className="grid grid-cols-[140px_1fr_24px_1fr] gap-2 border-b border-slate-100 px-3 py-2 last:border-b-0" key={`${item.id}-${change.field}`}>
                    <span className="text-slate-500">{change.field}</span>
                    <span>{change.before}</span><span className="text-slate-300">→</span><b>{change.after}</b>
                  </div>
                ))}
              </div>
            ) : null}
            {item.reason ? <p className="m-0 rounded-md bg-amber-50 p-3 text-amber-800">原因：{item.reason}</p> : null}
          </div>
        </Panel>
      ))}
      <details className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
        <summary className="cursor-pointer font-medium">查看技术记录</summary>
        <p className="break-all">请求编号：{entry.request_id}</p>
        <pre className="overflow-auto">{JSON.stringify(entries.map((item) => ({ action: item.action_type, before: item.before_summary, after: item.after_summary })), null, 2)}</pre>
      </details>
    </div>
  );
}
