import { Bell, CircleHelp } from "lucide-react";
import { AccountMenu } from "@/features/auth/account-menu";
import { formatBeijing } from "@/lib/beijing-time";

export function Topbar() {
  const today = formatBeijing(new Date(), {
    month: "long",
    day: "numeric",
    weekday: "short",
  });
  return (
    <header className="sticky top-0 z-20 flex h-[64px] items-center justify-end border-b border-slate-200 bg-white/95 px-7 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="mr-3 text-xs text-slate-500">{today}</span>
        <button className="icon-btn border-transparent">
          <CircleHelp size={16} />
        </button>
        <button className="icon-btn relative border-transparent">
          <Bell size={16} />
          <i className="absolute right-2 top-2 size-1.5 rounded-full bg-rose-500" />
        </button>
        <span className="mx-2 h-6 w-px bg-slate-200" />
        <AccountMenu />
      </div>
    </header>
  );
}
