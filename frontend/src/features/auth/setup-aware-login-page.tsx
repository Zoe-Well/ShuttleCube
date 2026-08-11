import { FirstRunSetup } from "./first-run-setup";
import { LoginPage } from "./login-page";
import { useSetupStatus } from "./session";

export function SetupAwareLoginPage() {
  const setup = useSetupStatus();
  if (setup.isLoading) return <main className="grid min-h-screen place-items-center bg-slate-50 text-sm text-slate-500">正在检查本机数据…</main>;
  if (setup.data?.required) return <FirstRunSetup />;
  return <LoginPage />;
}
