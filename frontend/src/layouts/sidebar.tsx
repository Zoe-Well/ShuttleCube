import {
  BarChart3,
  Bot,
  Building2,
  CalendarRange,
  ChevronRight,
  CircleGauge,
  FileClock,
  GraduationCap,
  MapPinned,
  ReceiptText,
  Settings2,
  Trophy,
  UserRoundCog,
  UsersRound,
  WalletCards,
} from "lucide-react";
import { NavLink } from "react-router";

import { hasOperationsCapability } from "@/features/intelligent-operations/access-control";
import { useOperationsContext } from "@/features/intelligent-operations/api";

const sections = [
  {
    label: "运营中心",
    items: [
      { to: "/", label: "经营工作台", icon: CircleGauge },
      { to: "/schedule", label: "统一排期", icon: CalendarRange },
      { to: "/reports", label: "经营报表", icon: BarChart3 },
    ],
  },
  {
    label: "业务管理",
    items: [
      { to: "/classes", label: "固定班", icon: GraduationCap },
      { to: "/private-lessons", label: "私教课程", icon: UserRoundCog },
      { to: "/bookings", label: "场地预订", icon: MapPinned },
      { to: "/events", label: "临时活动", icon: Trophy },
      { to: "/students", label: "学员档案", icon: UsersRound },
      { to: "/coaches", label: "教练管理", icon: UserRoundCog },
    ],
  },
  {
    label: "财务管理",
    items: [
      { to: "/finance", label: "业务收款", icon: WalletCards },
      { to: "/expenses", label: "日常收支", icon: ReceiptText },
      { to: "/payroll", label: "教练结算", icon: UserRoundCog },
    ],
  },
  {
    label: "系统",
    items: [
      { to: "/audit", label: "操作审计", icon: FileClock },
      { to: "/settings", label: "场馆设置", icon: Settings2 },
    ],
  },
];

export function Sidebar() {
  const context = useOperationsContext();
  const showOperations = Boolean(
    context.data && hasOperationsCapability(context.data, "operations.case.read"),
  );
  const visibleSections = sections.map((section) =>
    section.label === "运营中心" && showOperations
      ? {
          ...section,
          items: [
            section.items[0],
            { to: "/operations", label: "智能运营", icon: Bot },
            ...section.items.slice(1),
          ],
        }
      : section,
  );
  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-[248px] flex-col bg-[var(--nav)] text-white">
      <div className="flex h-[64px] items-center gap-3 border-b border-white/8 px-5">
        <span className="grid size-8 place-items-center rounded-md bg-emerald-500/15 text-emerald-300"><Building2 size={18} /></span>
        <span><b className="block text-sm font-semibold tracking-tight">ShuttleCube</b><small className="text-[10px] text-slate-400">场馆运营管理系统</small></span>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-5">
        {visibleSections.map((section) => (
          <div className="mb-5" key={section.label}>
            <p className="mb-2 px-3 text-[10px] font-semibold tracking-[.14em] text-slate-500">{section.label}</p>
            <nav className="space-y-1">
              {section.items.map(({ to, label, icon: Icon }) => (
                <NavLink
                  className={({ isActive }) => `group flex h-10 items-center gap-3 rounded-md px-3 text-[13px] font-medium transition ${isActive ? "bg-white/10 text-white shadow-inner shadow-white/5" : "text-slate-400 hover:bg-white/5 hover:text-slate-200"}`}
                  end={to === "/"}
                  key={to}
                  to={to}
                >
                  <Icon size={16} /><span className="flex-1">{label}</span><ChevronRight className="opacity-0 transition group-hover:opacity-60" size={13} />
                </NavLink>
              ))}
            </nav>
          </div>
        ))}
      </div>
      {showOperations ? (
        <div className="m-3 border-t border-white/8 pt-3">
          <NavLink className="block rounded-md bg-emerald-400/10 p-3 text-xs text-emerald-200" to="/operations">
            <div className="flex items-center gap-2 font-medium"><Bot size={14} />智能运营</div>
            <p className="mb-0 mt-1 text-[10px] leading-4 text-slate-400">{context.data?.operations_enabled ? "自动检查正在运行，按权限安全处理。" : "自动检查尚未开启，已有事项仍可查看。"}</p>
          </NavLink>
        </div>
      ) : null}
    </aside>
  );
}
