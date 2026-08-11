import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { useSession, useSessionLoading } from "./session";
export function SessionGuard({ children }: { children: ReactNode }) { const session=useSession();const isLoading=useSessionLoading();if(isLoading)return <div className="grid min-h-screen place-items-center bg-slate-50 text-sm text-slate-500">正在加载场馆数据…</div>;return session ? children : <Navigate to="/login" replace />; }
