import { useMutation, useQuery } from "@tanstack/react-query";
import { Database, Download, FolderOpen, HardDrive, Upload } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { Panel } from "@/components/operations/page";

type TransferStatus = { desktop_mode: boolean; data_directory: string | null; database_size_bytes: number; attachment_size_bytes: number; pending_import: boolean };
type DesktopBridge = { choose_export_directory(): Promise<string | null>; choose_import_directory(): Promise<string | null>; restart_app(): Promise<boolean> };
declare global { interface Window { pywebview?: { api?: DesktopBridge } } }

const size = (bytes: number) => bytes < 1024 * 1024 ? `${Math.max(0, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export function DataManagementPanel() {
  const [message,setMessage]=useState(""); const [error,setError]=useState("");
  const status=useQuery({queryKey:["data-transfer-status"],queryFn:()=>api<TransferStatus>("/data-transfer/status")});
  const exportData=useMutation({mutationFn:(path:string)=>api<{path:string}>("/data-transfer/export",{method:"POST",body:JSON.stringify({path})}),onSuccess:(result)=>{setError("");setMessage(`迁移文件夹已导出到：${result.path}`)},onError:(value:Error)=>{setMessage("");setError(value.message)}});
  const importData=useMutation({mutationFn:(path:string)=>api("/data-transfer/import",{method:"POST",body:JSON.stringify({path})}),onSuccess:async()=>{setError("");setMessage("数据已经通过校验，应用即将重启并完成恢复。");await window.pywebview?.api?.restart_app()},onError:(value:Error)=>{setMessage("");setError(value.message)}});
  const chooseExport=async()=>{const bridge=window.pywebview?.api;if(!bridge)return setError("桌面文件夹选择器尚未就绪，请稍后重试。");const path=await bridge.choose_export_directory();if(path)exportData.mutate(path)};
  const chooseImport=async()=>{const bridge=window.pywebview?.api;if(!bridge)return setError("桌面文件夹选择器尚未就绪，请稍后重试。");const path=await bridge.choose_import_directory();if(path&&window.confirm("导入会完整替换当前业务数据。系统会先自动备份当前数据，是否继续？"))importData.mutate(path)};
  const value=status.data;
  return <Panel className="mt-4" title="本机数据管理" description="导出或恢复完整的 ShuttleCube 迁移文件夹"><div className="grid gap-4 p-5">{value?.desktop_mode?<><div className="grid grid-cols-3 gap-3"><div className="rounded-md border border-slate-200 p-4"><Database size={16} className="text-emerald-700"/><div className="mt-3 text-xs text-slate-500">业务数据库</div><b className="mt-1 block text-sm text-slate-800">{size(value.database_size_bytes)}</b></div><div className="rounded-md border border-slate-200 p-4"><HardDrive size={16} className="text-emerald-700"/><div className="mt-3 text-xs text-slate-500">本地附件</div><b className="mt-1 block text-sm text-slate-800">{size(value.attachment_size_bytes)}</b></div><div className="rounded-md border border-slate-200 p-4"><FolderOpen size={16} className="text-emerald-700"/><div className="mt-3 text-xs text-slate-500">数据目录</div><b className="mt-1 block truncate text-xs text-slate-700" title={value.data_directory??""}>{value.data_directory}</b></div></div><div className="flex gap-3"><button className="btn btn-primary" disabled={exportData.isPending} onClick={chooseExport}><Download size={15}/>{exportData.isPending?"正在导出…":"导出迁移文件夹"}</button><button className="btn" disabled={importData.isPending} onClick={chooseImport}><Upload size={15}/>{importData.isPending?"正在校验…":"从迁移文件夹恢复"}</button></div></>:<div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">当前为服务器或浏览器运行模式。安装单机桌面版后，可以在这里导出和恢复数据文件夹。</div>}{message&&<p role="status" className="m-0 rounded-md border border-emerald-100 bg-emerald-50 p-3 text-xs text-emerald-800">{message}</p>}{error&&<p role="alert" className="m-0 rounded-md border border-red-100 bg-red-50 p-3 text-xs text-red-700">{error}</p>}</div></Panel>;
}
