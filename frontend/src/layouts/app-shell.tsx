import { Outlet } from "react-router";
import { SessionGuard } from "@/features/auth/session-guard";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export function AppShell(){return <SessionGuard><Sidebar/><main className="ml-[248px] min-h-screen"><Topbar/><div className="mx-auto max-w-[1560px] px-7 py-6"><Outlet/></div></main></SessionGuard>}
