import type { OperationCase } from "./api";
import { buildCaseEvidenceItems } from "./case-evidence";

export function CaseEvidenceSummary({ item }: { item: OperationCase }) {
  const entries = buildCaseEvidenceItems(item);
  return (
    <section className="panel p-5">
      <h2 className="font-semibold">业务情况</h2>
      <p className="mt-1 text-xs text-slate-500">根据现有业务记录自动汇总，内部记录编号已隐藏。</p>
      {entries.length ? (
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {entries.map((entry) => (
            <div className="rounded-lg bg-slate-50 p-3" key={entry.label}>
              <dt className="text-xs text-slate-500">{entry.label}</dt>
              <dd className="mt-1 break-words text-sm font-medium">{entry.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-4 text-sm text-slate-600">
          暂无可展示的业务摘要，请通过业务记录查看详情。
        </p>
      )}
    </section>
  );
}
