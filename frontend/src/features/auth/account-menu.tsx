import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, Database, LogOut, Repeat2, ShieldCheck, UserRound } from "lucide-react";
import { useNavigate } from "react-router";

import { useLogout, useSession } from "./session";

export function AccountMenu() {
  const session = useSession();
  const logout = useLogout();
  const navigate = useNavigate();

  if (!session) return null;

  const leaveSession = () => {
    logout.mutate(undefined, {
      onSuccess: () => navigate("/login", { replace: true }),
    });
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          aria-label="管理员账号"
          className="group flex items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-slate-100 data-[state=open]:bg-slate-100"
          type="button"
        >
          <span className="grid size-8 place-items-center rounded-md bg-emerald-700 text-xs font-bold text-white">
            {session.display_name.slice(0, 1)}
          </span>
          <span className="min-w-20 text-xs">
            <b className="block font-semibold text-slate-700">{session.display_name}</b>
            <span className="text-[10px] text-slate-400">场馆管理员</span>
          </span>
          <ChevronDown
            className="text-slate-400 transition-transform group-data-[state=open]:rotate-180"
            size={14}
          />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          className="z-[100] w-72 overflow-hidden rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-900/10"
          sideOffset={8}
        >
          <div className="px-3 py-3">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
                <UserRound size={18} />
              </span>
              <div className="min-w-0">
                <p className="m-0 truncate text-sm font-semibold text-slate-800">
                  {session.display_name}
                </p>
                <p className="m-0 mt-0.5 truncate text-[11px] text-slate-500">
                  用户名：{session.username}
                </p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 rounded-lg bg-slate-50 p-3 text-[11px] text-slate-600">
              <span className="flex items-center gap-2">
                <ShieldCheck className="text-emerald-600" size={14} />
                已登录 · 场馆管理员
              </span>
              <span className="flex items-center gap-2">
                <Database className="text-slate-500" size={14} />
                本机场馆数据由所有账号共享
              </span>
            </div>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-slate-100" />
          <DropdownMenu.Item
            className="flex cursor-pointer select-none items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-medium text-slate-700 outline-none hover:bg-slate-50 focus:bg-slate-50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
            disabled={logout.isPending}
            onSelect={leaveSession}
          >
            <Repeat2 size={15} />
            切换账号
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className="flex cursor-pointer select-none items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-medium text-rose-600 outline-none hover:bg-rose-50 focus:bg-rose-50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
            disabled={logout.isPending}
            onSelect={leaveSession}
          >
            <LogOut size={15} />
            退出登录
          </DropdownMenu.Item>
          {logout.error && (
            <p className="mx-2 mb-1 mt-2 rounded-md bg-red-50 px-2.5 py-2 text-[11px] text-red-700">
              {logout.error.message}
            </p>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
