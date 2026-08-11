import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  getOperationsModelSetting,
  getOperationsRuntimeSetting,
  listOperationsMemberships,
  type OperationsContext,
  type OperationsMembership,
  updateOperationsMembership,
  updateOperationsModelSetting,
  updateOperationsRuntimeSetting,
} from "./api";
import { hasOperationsCapability } from "./access-control";

export function OperationsSettingsPanel({ context }: { context: OperationsContext }) {
  const client = useQueryClient();
  const canManageModel = hasOperationsCapability(context, "operations.model.manage");
  const canManageMembership = hasOperationsCapability(
    context,
    "operations.membership.manage",
  );
  const canManageRuntime = hasOperationsCapability(context, "operations.policy.manage");
  const [modelReason, setModelReason] = useState("");
  const [runtimeReason, setRuntimeReason] = useState("");
  const runtime = useQuery({
    queryKey: ["operations-runtime-setting"],
    queryFn: getOperationsRuntimeSetting,
  });
  const model = useQuery({
    queryKey: ["operations-model-setting"],
    queryFn: getOperationsModelSetting,
  });
  const memberships = useQuery({
    queryKey: ["operations-memberships"],
    queryFn: listOperationsMemberships,
    enabled: canManageMembership,
  });
  const updateModel = useMutation({
    mutationFn: (enabled: boolean) => {
      if (!model.data) throw new Error("模型设置尚未加载完成");
      if (!modelReason.trim()) throw new Error("请填写变更原因");
      return updateOperationsModelSetting({
        model_enabled: enabled,
        reason: modelReason.trim(),
        expected_version: model.data.version,
      });
    },
    onSuccess: (next) => {
      client.setQueryData(["operations-model-setting"], next);
      void client.invalidateQueries({ queryKey: ["operations-context"] });
      setModelReason("");
    },
  });
  const updateMembership = useMutation({
    mutationFn: ({
      membership,
      status,
      roleKey,
      reason,
    }: {
      membership: OperationsMembership;
      status: "active" | "disabled";
      roleKey: OperationsMembership["role_key"];
      reason: string;
    }) =>
      updateOperationsMembership(membership.id, {
        status,
        role_key: roleKey,
        reason,
        expected_version: membership.version,
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["operations-memberships"] }),
  });
  const updateRuntime = useMutation({
    mutationFn: ({
      operationsEnabled,
      writeToolsEnabled,
    }: {
      operationsEnabled: boolean;
      writeToolsEnabled: boolean;
    }) => {
      if (!runtime.data) throw new Error("运行设置尚未加载完成");
      if (!runtimeReason.trim()) throw new Error("请填写变更原因");
      return updateOperationsRuntimeSetting({
        operations_enabled: operationsEnabled,
        write_tools_enabled: writeToolsEnabled,
        reason: runtimeReason.trim(),
        expected_version: runtime.data.version,
      });
    },
    onSuccess: (next) => {
      client.setQueryData(["operations-runtime-setting"], next);
      void client.invalidateQueries({ queryKey: ["operations-context"] });
      setRuntimeReason("");
    },
  });

  const submitMembership = (
    event: FormEvent<HTMLFormElement>,
    membership: OperationsMembership,
  ) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const reason = String(data.get("reason") ?? "").trim();
    if (!reason) return;
    updateMembership.mutate({
      membership,
      status: String(data.get("status")) as "active" | "disabled",
      roleKey: String(data.get("role_key")) as OperationsMembership["role_key"],
      reason,
    });
  };

  const modelEnabled = model.data?.model_enabled ?? context.model_enabled;
  const operationsEnabled = runtime.data?.operations_enabled ?? context.operations_enabled;
  const writeToolsEnabled = runtime.data?.write_tools_enabled ?? context.write_tools_enabled;
  return (
    <div className="space-y-6">
      <section aria-labelledby="operations-runtime-title" className="panel p-5">
        <h2 id="operations-runtime-title" className="font-semibold">运行设置</h2>
        <p className="mt-2 text-sm">
          {operationsEnabled ? "确定性运营扫描已启用" : "确定性运营扫描未启用"}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          写工具{writeToolsEnabled ? "已启用，仍需逐次审批" : "保持关闭"}。
        </p>
        {canManageRuntime ? (
          <div className="mt-4 space-y-3">
            <label className="block text-xs font-medium">
              变更原因
              <input
                className="field mt-1"
                value={runtimeReason}
                onChange={(event) => setRuntimeReason(event.target.value)}
              />
            </label>
            <div className="flex flex-wrap gap-3">
              <button
                className="btn btn-primary"
                disabled={updateRuntime.isPending || !runtime.data}
                type="button"
                onClick={() =>
                  updateRuntime.mutate({
                    operationsEnabled: !operationsEnabled,
                    writeToolsEnabled: operationsEnabled ? false : writeToolsEnabled,
                  })
                }
              >
                {operationsEnabled ? "停用智能运营" : "启用智能运营"}
              </button>
              <button
                className="btn"
                disabled={updateRuntime.isPending || !runtime.data || !operationsEnabled}
                type="button"
                onClick={() =>
                  updateRuntime.mutate({
                    operationsEnabled: true,
                    writeToolsEnabled: !writeToolsEnabled,
                  })
                }
              >
                {writeToolsEnabled ? "关闭写工具" : "启用写工具"}
              </button>
            </div>
          </div>
        ) : null}
        {runtime.error ? <p className="mt-2 text-xs text-red-600">{runtime.error.message}</p> : null}
        {updateRuntime.error ? <p className="mt-2 text-xs text-red-600">{updateRuntime.error.message}</p> : null}
      </section>

      <section aria-labelledby="operations-model-title" className="panel p-5">
        <h2 id="operations-model-title" className="font-semibold">模型设置</h2>
        <p className="mt-2 text-sm">
          {modelEnabled ? "模型解释功能已启用" : "模型解释功能未启用"}
        </p>
        {!modelEnabled ? (
          <p className="mt-1 text-xs text-slate-500">确定性扫描、案件和报告仍可使用。</p>
        ) : null}
        {canManageModel ? (
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="min-w-72 flex-1 text-xs font-medium">
              变更原因
              <input
                className="field mt-1"
                value={modelReason}
                onChange={(event) => setModelReason(event.target.value)}
              />
            </label>
            <button
              className="btn btn-primary"
              disabled={updateModel.isPending || !model.data}
              type="button"
              onClick={() => updateModel.mutate(!modelEnabled)}
            >
              {modelEnabled ? "停用模型解释" : "启用模型解释"}
            </button>
          </div>
        ) : null}
        {updateModel.error ? <p className="mt-2 text-xs text-red-600">{updateModel.error.message}</p> : null}
      </section>

      {canManageMembership ? (
        <section aria-labelledby="operations-members-title" className="panel p-5">
          <h2 id="operations-members-title" className="font-semibold">运营成员与权限</h2>
          <p className="mt-1 text-xs text-slate-500">
            停用成员或降低角色后，无法继续处理的案件会自动回到对应工作队列。
          </p>
          <div className="mt-4 space-y-3">
            {memberships.data?.map((membership) => (
              <form
                className="grid gap-3 rounded-lg border p-3 md:grid-cols-[1fr_180px_140px_1fr_auto]"
                key={membership.id}
                onSubmit={(event) => submitMembership(event, membership)}
              >
                <div>
                  <div className="text-sm font-medium">{membership.display_name}</div>
                  <div className="text-xs text-slate-500">{membership.capabilities.length} 项权限</div>
                </div>
                <select className="field" defaultValue={membership.role_key} name="role_key">
                  <option value="owner">负责人</option>
                  <option value="operations_manager">运营经理</option>
                  <option value="operator">运营人员</option>
                  <option value="finance_viewer">财务查看</option>
                </select>
                <select className="field" defaultValue={membership.status === "disabled" ? "disabled" : "active"} name="status">
                  <option value="active">启用</option>
                  <option value="disabled">停用</option>
                </select>
                <input className="field" name="reason" placeholder="填写变更原因" required />
                <button className="btn" disabled={updateMembership.isPending}>保存</button>
              </form>
            ))}
          </div>
          {memberships.error ? <p className="mt-2 text-xs text-red-600">{memberships.error.message}</p> : null}
          {updateMembership.error ? <p className="mt-2 text-xs text-red-600">{updateMembership.error.message}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
