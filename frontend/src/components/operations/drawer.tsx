import { X } from "lucide-react";
import type { ReactNode } from "react";

export function Drawer({ open, title, description, onClose, children }: { open: boolean; title: string; description?: string; onClose: () => void; children: ReactNode }) {
  if(!open)return null;
  return <div className="fixed inset-0 z-50"><button aria-label="关闭抽屉" className="absolute inset-0 cursor-default bg-slate-950/25 backdrop-blur-[1px]" onClick={onClose}/><aside className="absolute inset-y-0 right-0 flex w-[520px] flex-col border-l border-slate-200 bg-white shadow-2xl"><header className="flex items-start justify-between border-b border-slate-200 px-6 py-5"><div><h2 className="m-0 text-base font-semibold text-slate-800">{title}</h2>{description&&<p className="mt-1 text-xs text-slate-500">{description}</p>}</div><button className="icon-btn" onClick={onClose}><X size={16}/></button></header><div className="min-h-0 flex-1 overflow-y-auto p-6">{children}</div></aside></div>;
}
