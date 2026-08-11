import { Inbox } from "lucide-react";

export function EmptyState({ title="暂无数据", description="创建第一条记录后，数据会显示在这里。" }: { title?: string; description?: string }) {
  return <div className="grid min-h-48 place-items-center px-6 py-10 text-center"><div><span className="mx-auto grid size-10 place-items-center rounded-full bg-slate-100 text-slate-500"><Inbox size={18}/></span><h3 className="mb-1 mt-3 text-sm font-semibold text-slate-700">{title}</h3><p className="m-0 text-xs text-slate-500">{description}</p></div></div>;
}
