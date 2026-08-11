export type ScheduleConflict = { resource_type: string; resource_id: string; title?: string };

export function ConflictAlert({ conflicts }: { conflicts: ScheduleConflict[] }) {
  if (!conflicts.length) return <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">当前资源与时间可用</p>;
  return <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700"><b>发现资源冲突</b><ul className="mt-2 list-disc pl-5">{conflicts.map((item,index)=><li key={`${item.resource_type}-${item.resource_id}-${index}`}>{item.resource_type}：{item.title ?? item.resource_id}</li>)}</ul><p className="mt-2">请调整时间或更换场地、教练、学员。</p></div>;
}
