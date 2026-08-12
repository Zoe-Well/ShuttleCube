import { ArrowLeft } from "lucide-react";
import { Link } from "react-router";

import { hasOperationsCapability } from "./access-control";
import { useOperationsContext } from "./api";
import { OperationsSettingsPanel } from "./operations-settings-panel";
import { PolicySettingsPanel } from "./policy-settings-panel";

export function OperationsSettingsPage() {
  const context = useOperationsContext();
  if (context.isPending) return <div className="panel p-8 text-sm text-slate-500">正在加载运营设置…</div>;
  if (context.error || !context.data) {
    return <div className="panel p-8 text-sm text-red-600">{context.error?.message ?? "无法读取运营设置"}</div>;
  }
  const canView = [
    "operations.policy.manage",
    "operations.model.manage",
  ].some((capability) => hasOperationsCapability(context.data!, capability));
  if (!canView) return <div className="panel p-8 text-sm text-slate-600">当前账号没有管理运营设置的权限。</div>;

  return (
    <div className="space-y-5">
      <Link className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900" to="/operations">
        <ArrowLeft size={15} />返回智能运营
      </Link>
      <header>
        <h1 className="text-xl font-semibold text-slate-900">运营设置</h1>
        <p className="mt-1 text-sm text-slate-500">管理自动检查、已审批操作、AI 辅助和提醒规则。</p>
      </header>
      <OperationsSettingsPanel context={context.data} />
      <PolicySettingsPanel context={context.data} />
    </div>
  );
}
