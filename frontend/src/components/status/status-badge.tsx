const styles: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700 ring-emerald-600/10",
  confirmed: "bg-blue-50 text-blue-700 ring-blue-600/10",
  scheduled: "bg-blue-50 text-blue-700 ring-blue-600/10",
  booked: "bg-indigo-50 text-indigo-700 ring-indigo-600/10",
  pending_completion: "bg-amber-50 text-amber-700 ring-amber-600/10",
  completed: "bg-slate-100 text-slate-600 ring-slate-500/10",
  cancelled: "bg-rose-50 text-rose-700 ring-rose-600/10",
  pending: "bg-amber-50 text-amber-700 ring-amber-600/10",
  partial: "bg-amber-50 text-amber-700 ring-amber-600/10",
  partially_refunded: "bg-orange-50 text-orange-700 ring-orange-600/10",
  refunded: "bg-slate-100 text-slate-600 ring-slate-500/10",
  settled: "bg-emerald-50 text-emerald-700 ring-emerald-600/10",
  effective: "bg-emerald-50 text-emerald-700 ring-emerald-600/10",
  void: "bg-slate-100 text-slate-500 ring-slate-500/10",
  paid: "bg-emerald-50 text-emerald-700 ring-emerald-600/10",
  unpaid: "bg-amber-50 text-amber-700 ring-amber-600/10",
  draft: "bg-slate-100 text-slate-600 ring-slate-500/10",
  inactive: "bg-slate-100 text-slate-500 ring-slate-500/10",
  archived: "bg-slate-100 text-slate-500 ring-slate-500/10",
  expired: "bg-amber-50 text-amber-700 ring-amber-600/10",
  transferred: "bg-sky-50 text-sky-700 ring-sky-600/10",
};

const labels: Record<string, string> = {
  active: "启用",
  confirmed: "已确认",
  scheduled: "待上课",
  booked: "已预约",
  pending_completion: "待确认完成",
  completed: "已完成",
  cancelled: "已取消",
  pending: "待处理",
  partial: "部分收款",
  partially_refunded: "部分退款",
  refunded: "已退款",
  settled: "已结算",
  effective: "有效",
  void: "已作废",
  paid: "已收款",
  unpaid: "待收款",
  draft: "草稿",
  inactive: "停用",
  archived: "已归档",
  expired: "已失效",
  transferred: "已转移",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return (
    <span
      className={`inline-flex rounded px-2 py-1 text-[10px] font-semibold ring-1 ring-inset ${
        styles[status] ?? "bg-slate-100 text-slate-600 ring-slate-500/10"
      }`}
    >
      {label ?? labels[status] ?? status}
    </span>
  );
}
