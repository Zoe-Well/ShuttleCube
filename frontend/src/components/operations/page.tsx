import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="mb-5 flex items-start justify-between gap-6"><div>{eyebrow&&<p className="eyebrow">{eyebrow}</p>}<h1 className="page-title">{title}</h1><p className="page-subtitle">{description}</p></div>{actions&&<div className="flex shrink-0 items-center gap-2">{actions}</div>}</header>;
}

export function Panel({ title, description, actions, children, className="" }: { title?: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel overflow-hidden ${className}`}>{(title||actions)&&<div className="panel-header"><div><h2 className="panel-title">{title}</h2>{description&&<p className="panel-description">{description}</p>}</div>{actions}</div>}{children}</section>;
}

export function MetricCard({ label, value, footnote, icon }: { label: string; value: string; footnote: string; icon: ReactNode }) {
  return <div className="metric-card"><div className="flex items-center justify-between"><span className="metric-label">{label}</span><span className="grid size-8 place-items-center rounded-md bg-slate-100 text-slate-600">{icon}</span></div><div className="metric-value">{value}</div><div className="metric-footnote">{footnote}</div></div>;
}
