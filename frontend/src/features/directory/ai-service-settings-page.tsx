import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { formatBeijingDateTime } from "@/lib/beijing-time";

import {
  configureOperationsModelCredential,
  deleteOperationsModelCredential,
  getOperationsModelSetting,
  type OperationsModelSetting,
} from "@/features/intelligent-operations/api";

type Provider = OperationsModelSetting["provider_key"];
type ApiMode = OperationsModelSetting["provider_api_mode"];

const presets: Record<Exclude<Provider, "custom">, { baseUrl: string; apiMode: ApiMode; model: string }> = {
  openai: { baseUrl: "https://api.openai.com/v1", apiMode: "responses", model: "gpt-5.6" },
  deepseek: { baseUrl: "https://api.deepseek.com", apiMode: "chat_completions", model: "deepseek-chat" },
};

export function AiServiceSettingsPage() {
  const client = useQueryClient();
  const setting = useQuery({ queryKey: ["operations-model-setting"], queryFn: getOperationsModelSetting });
  const [provider, setProvider] = useState<Provider>("openai");
  const [baseUrl, setBaseUrl] = useState(presets.openai.baseUrl);
  const [apiMode, setApiMode] = useState<ApiMode>("responses");
  const [model, setModel] = useState(presets.openai.model);
  const [apiKey, setApiKey] = useState("");
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!setting.data) return;
    setProvider(setting.data.provider_key);
    setBaseUrl(setting.data.provider_base_url);
    setApiMode(setting.data.provider_api_mode);
    setModel(setting.data.provider_model_profile);
  }, [setting.data]);

  const configure = useMutation({
    mutationFn: () => configureOperationsModelCredential({
      provider,
      base_url: baseUrl.trim(),
      api_mode: apiMode,
      model_profile: model.trim(),
      api_key: apiKey.trim(),
    }),
    onSuccess: (next) => {
      client.setQueryData(["operations-model-setting"], next);
      setApiKey("");
      setEditing(false);
    },
  });
  const remove = useMutation({
    mutationFn: deleteOperationsModelCredential,
    onSuccess: (next) => {
      client.setQueryData(["operations-model-setting"], next);
      void client.invalidateQueries({ queryKey: ["operations-context"] });
      setEditing(false);
      setApiKey("");
    },
  });

  const selectProvider = (next: Provider) => {
    setProvider(next);
    if (next !== "custom") {
      const preset = presets[next];
      setBaseUrl(preset.baseUrl);
      setApiMode(preset.apiMode);
      setModel(preset.model);
    }
  };
  const save = () => {
    if (provider !== "openai" && !window.confirm(
      "使用非 OpenAI 服务后，AI 总结所需的业务信息会发送给所选服务商。确认继续保存并验证吗？",
    )) return;
    configure.mutate();
  };

  return (
    <section className="space-y-5">
      <Link className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900" to="/settings">
        <ArrowLeft size={15} />返回场馆设置
      </Link>
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900"><Bot size={20} />AI 服务配置</h1>
        <p className="mt-1 text-sm text-slate-500">选择服务商、模型并验证 API Key。配置成功后，可在运营设置中决定是否启用 AI。</p>
      </header>

      <div className="panel p-5">
        {setting.isPending ? <p className="text-sm text-slate-500">正在读取 AI 配置…</p> : null}
        {setting.error ? <p className="text-sm text-red-600">{setting.error.message}</p> : null}
        {setting.data?.provider_configured && !editing ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-sm font-semibold text-emerald-800">✓ API Key 验证成功</p>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-xs text-slate-500">服务商</dt><dd className="mt-1 font-medium">{setting.data.provider_label}</dd></div>
                <div><dt className="text-xs text-slate-500">模型</dt><dd className="mt-1 font-medium">{setting.data.provider_model_profile}</dd></div>
                <div><dt className="text-xs text-slate-500">API 地址</dt><dd className="mt-1 break-all font-medium">{setting.data.provider_base_url}</dd></div>
                <div><dt className="text-xs text-slate-500">最近验证</dt><dd className="mt-1 font-medium">{setting.data.provider_verified_at ? formatBeijingDateTime(setting.data.provider_verified_at) : "由服务器管理员配置"}</dd></div>
              </dl>
            </div>
            <div className="flex gap-2">
              {setting.data.provider_editable ? <button className="btn" onClick={() => setEditing(true)}>重新配置</button> : null}
              {setting.data.provider_editable ? (
                <button className="btn" disabled={remove.isPending} onClick={() => window.confirm("移除 API Key 后会同时关闭 AI 服务，是否继续？") && remove.mutate()}>移除配置</button>
              ) : null}
            </div>
          </div>
        ) : setting.data?.provider_editable ? (
          <div className="grid gap-4">
            <label className="field-label">AI 服务商
              <select aria-label="AI 服务商" className="field" value={provider} onChange={(event) => selectProvider(event.target.value as Provider)}>
                <option value="openai">OpenAI</option>
                <option value="deepseek">DeepSeek</option>
                <option value="custom">其他 OpenAI 兼容服务</option>
              </select>
            </label>
            <label className="field-label">API 地址
              <input aria-label="API 地址" className="field" disabled={provider !== "custom"} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
              <span className="field-hint">OpenAI 和 DeepSeek 使用官方地址；自定义服务须填写完整基础地址。</span>
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="field-label">模型名称
                <input aria-label="模型名称" className="field" value={model} onChange={(event) => setModel(event.target.value)} />
              </label>
              <label className="field-label">API 协议
                <select aria-label="API 协议" className="field" disabled={provider !== "custom"} value={apiMode} onChange={(event) => setApiMode(event.target.value as ApiMode)}>
                  <option value="responses">Responses API</option>
                  <option value="chat_completions">Chat Completions API</option>
                </select>
              </label>
            </div>
            <label className="field-label">API Key
              <input aria-label="API Key" autoComplete="off" className="field" placeholder="输入服务商提供的 API Key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} />
              <span className="field-hint">密钥不会回显，桌面版使用当前 Windows 账号加密保存。</span>
            </label>
            {provider !== "openai" ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">AI 总结所需的业务信息将发送给该服务商，请确认其数据与隐私政策符合你的要求。</p> : null}
            <div className="flex gap-2">
              <button className="btn btn-primary" disabled={apiKey.trim().length < 8 || !model.trim() || !baseUrl.trim() || configure.isPending} onClick={save} type="button">{configure.isPending ? "正在验证…" : "保存并验证"}</button>
              {editing ? <button className="btn" onClick={() => { setEditing(false); setApiKey(""); }} type="button">取消</button> : null}
            </div>
            {configure.error ? <p className="text-sm text-red-600">{configure.error.message}</p> : null}
          </div>
        ) : (
          <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">服务器版 AI 凭据由部署管理员配置，当前页面仅显示配置状态。</p>
        )}
        {remove.error ? <p className="mt-3 text-sm text-red-600">{remove.error.message}</p> : null}
      </div>
    </section>
  );
}
