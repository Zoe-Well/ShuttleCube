import { Building2, ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";

import { FormField, Input } from "@/components/forms/form-field";
import { type SetupInput, useSetup } from "./session";

export function FirstRunSetup() {
  const setup = useSetup();
  const { register, handleSubmit, formState: { errors } } = useForm<SetupInput>({
    defaultValues: {
      venue_name: "ShuttleCube 羽毛球馆",
      court_count: 4,
      username: "admin",
      display_name: "管理员",
    },
  });

  return (
    <main className="grid min-h-screen place-items-center bg-slate-50 p-8">
      <form className="w-full max-w-2xl rounded-xl border border-slate-200 bg-white p-8 shadow-sm" onSubmit={handleSubmit((value) => setup.mutate(value))}>
        <div className="mb-7 flex items-start gap-4 border-b border-slate-100 pb-6">
          <span className="grid size-11 place-items-center rounded-lg bg-emerald-50 text-emerald-700"><Building2 size={21}/></span>
          <div><p className="eyebrow">首次启动</p><h1 className="m-0 text-2xl font-semibold text-slate-800">初始化 ShuttleCube</h1><p className="mt-2 text-sm text-slate-500">创建本机场馆和管理员。完成后数据会保存在桌面版专用数据文件夹中。</p></div>
        </div>
        <div className="grid grid-cols-2 gap-5">
          <div className="col-span-2"><FormField label="场馆名称" error={errors.venue_name?.message}><Input {...register("venue_name", { required: "请输入场馆名称" })}/></FormField></div>
          <FormField label="初始场地数量" error={errors.court_count?.message}><Input type="number" min={1} max={50} {...register("court_count", { valueAsNumber: true, min: 1, max: 50 })}/></FormField>
          <FormField label="管理员姓名" error={errors.display_name?.message}><Input {...register("display_name", { required: "请输入管理员姓名" })}/></FormField>
          <FormField label="登录用户名" error={errors.username?.message}><Input autoComplete="username" {...register("username", { required: "请输入用户名" })}/></FormField>
          <FormField label="登录密码" error={errors.password?.message}><Input type="password" autoComplete="new-password" {...register("password", { required: "请输入密码", minLength: { value: 8, message: "密码至少需要 8 位" } })}/></FormField>
        </div>
        {setup.error&&<p role="alert" className="mt-5 rounded-md border border-red-100 bg-red-50 p-3 text-xs text-red-700">{setup.error.message}</p>}
        <footer className="mt-7 flex items-center justify-between border-t border-slate-100 pt-5"><span className="flex items-center gap-2 text-xs text-slate-500"><ShieldCheck size={14} className="text-emerald-600"/>数据仅保存在本机</span><button className="btn btn-primary" disabled={setup.isPending}>{setup.isPending?"正在初始化…":"完成初始化"}</button></footer>
      </form>
    </main>
  );
}
