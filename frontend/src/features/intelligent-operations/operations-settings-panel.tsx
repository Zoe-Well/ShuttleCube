import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import {
  getOperationsModelSetting,
  getOperationsRuntimeSetting,
  type OperationsContext,
  updateOperationsModelSetting,
  updateOperationsRuntimeSetting,
} from "./api";
import { hasOperationsCapability } from "./access-control";

export function OperationsSettingsPanel({ context }: { context: OperationsContext }) {
  const client = useQueryClient();
  const canManageModel = hasOperationsCapability(context, "operations.model.manage");
  const canManageRuntime = hasOperationsCapability(context, "operations.policy.manage");
  const [confirmExecuteMode, setConfirmExecuteMode] = useState(false);
  const runtime = useQuery({
    queryKey: ["operations-runtime-setting"],
    queryFn: getOperationsRuntimeSetting,
  });
  const model = useQuery({
    queryKey: ["operations-model-setting"],
    queryFn: getOperationsModelSetting,
  });
  const updateModel = useMutation({
    mutationFn: (enabled: boolean) => {
      if (!model.data) throw new Error("AI 辅助设置尚未加载完成");
      return updateOperationsModelSetting({
        model_enabled: enabled,
        expected_version: model.data.version,
      });
    },
    onSuccess: (next) => {
      client.setQueryData(["operations-model-setting"], next);
      void client.invalidateQueries({ queryKey: ["operations-context"] });
    },
  });
  const updateRuntime = useMutation({
    mutationFn: (mode: "off" | "discover" | "execute") => {
      if (!runtime.data) throw new Error("智能运营设置尚未加载完成");
      return updateOperationsRuntimeSetting({
        operations_enabled: mode !== "off",
        write_tools_enabled: mode === "execute",
        expected_version: runtime.data.version,
      });
    },
    onSuccess: (next) => {
      client.setQueryData(["operations-runtime-setting"], next);
      void client.invalidateQueries({ queryKey: ["operations-context"] });
      setConfirmExecuteMode(false);
    },
  });

  const modelEnabled = model.data?.model_enabled ?? context.model_enabled;
  const providerConfigured = model.data?.provider_configured ?? false;
  const operationsEnabled = runtime.data?.operations_enabled ?? context.operations_enabled;
  const writeToolsEnabled = runtime.data?.write_tools_enabled ?? context.write_tools_enabled;
  const runtimeMode = writeToolsEnabled ? "execute" : operationsEnabled ? "discover" : "off";
  const providerSummary = model.data
    ? `${model.data.provider_label} · ${model.data.provider_model_profile}`
    : "";

  return (
    <div className="space-y-6">
      <section aria-labelledby="operations-runtime-title" className="panel p-5">
        <h2 id="operations-runtime-title" className="font-semibold">智能运营</h2>
        <p className="mt-1 text-xs text-slate-500">
          当前模式：{runtimeMode === "off" ? "关闭" : runtimeMode === "discover" ? "自动发现运营问题" : "发现问题并执行已审批操作"}
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {([
            ["off", "关闭智能运营", "不再自动检查；已有事项和报告仍可查看。"],
            ["discover", "自动发现运营问题", "自动检查并生成待处理事项，不执行业务操作。"],
            ["execute", "发现并执行已审批操作", "自动检查，并允许执行人工逐次批准的操作。"],
          ] as const).map(([mode, title, description]) => (
            <button
              className={`rounded-lg border p-4 text-left transition ${runtimeMode === mode ? "border-emerald-500 bg-emerald-50 ring-1 ring-emerald-200" : "border-slate-200 hover:border-slate-300"}`}
              disabled={!canManageRuntime || updateRuntime.isPending || !runtime.data}
              key={mode}
              onClick={() => mode === "execute" && runtimeMode !== "execute" ? setConfirmExecuteMode(true) : updateRuntime.mutate(mode)}
              type="button"
            >
              <span className="block text-sm font-semibold">{title}</span>
              {mode === "discover" ? <span className="mt-1 inline-block rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] text-emerald-700">推荐</span> : null}
              <span className="mt-2 block text-xs leading-5 text-slate-500">{description}</span>
            </button>
          ))}
        </div>
        {confirmExecuteMode ? (
          <div aria-labelledby="execute-risk-title" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4" role="dialog">
            <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl">
              <h3 className="font-semibold" id="execute-risk-title">确认允许执行已审批操作？</h3>
              <p className="mt-2 text-sm text-slate-600">开启后，系统可以执行已经批准的课程补排等操作。</p>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-600">
                <li>每次高风险操作仍须人工单独审批。</li>
                <li>执行前会重新检查时间、场地、教练和数据版本。</li>
                <li>不会自动收款、退款、修改考勤或课时。</li>
                <li>方案过期或发生冲突时会停止执行并等待人工处理。</li>
              </ul>
              <div className="mt-5 flex justify-end gap-2">
                <button className="btn" onClick={() => setConfirmExecuteMode(false)} type="button">取消</button>
                <button className="btn btn-primary" disabled={updateRuntime.isPending} onClick={() => updateRuntime.mutate("execute")} type="button">我已了解，确认开启</button>
              </div>
            </div>
          </div>
        ) : null}
        {runtime.error ? <p className="mt-2 text-xs text-red-600">{runtime.error.message}</p> : null}
        {updateRuntime.error ? <p className="mt-2 text-xs text-red-600">{updateRuntime.error.message}</p> : null}
      </section>

      <section aria-labelledby="operations-model-title" className="panel p-5">
        <h2 id="operations-model-title" className="font-semibold">AI 辅助</h2>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 p-4">
          <div>
            <h3 className="text-sm font-semibold">AI 服务连接</h3>
            {providerConfigured ? (
              <p className="mt-1 text-xs text-emerald-700">✓ 已连接 {providerSummary}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-500">尚未配置 AI 服务</p>
            )}
          </div>
          {canManageModel ? <Link className="btn" to="/settings/ai">前往场馆设置配置</Link> : null}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 p-4">
          <div>
            <h3 className="text-sm font-semibold">启用 AI 服务</h3>
            <p className="mt-1 text-xs text-slate-500">配置成功后，仍可在这里决定是否开启 AI 辅助。</p>
          </div>
          {canManageModel ? (
            <button
              aria-checked={modelEnabled}
              className={`relative h-7 w-12 rounded-full transition ${modelEnabled ? "bg-emerald-600" : "bg-slate-300"}`}
              disabled={updateModel.isPending || !model.data || (!modelEnabled && !providerConfigured)}
              onClick={() => updateModel.mutate(!modelEnabled)}
              role="switch"
              type="button"
            >
              <span className={`absolute top-1 size-5 rounded-full bg-white shadow transition ${modelEnabled ? "left-6" : "left-1"}`} />
              <span className="sr-only">{modelEnabled ? "关闭 AI 服务" : "开启 AI 服务"}</span>
            </button>
          ) : <span className="text-sm text-slate-600">{modelEnabled ? "已开启" : "未开启"}</span>}
        </div>
        {model.error ? <p className="mt-2 text-xs text-red-600">{model.error.message}</p> : null}
        {updateModel.error ? <p className="mt-2 text-xs text-red-600">{updateModel.error.message}</p> : null}
      </section>
    </div>
  );
}
