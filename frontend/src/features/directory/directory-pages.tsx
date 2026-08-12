import { useMutation,useQuery,useQueryClient } from "@tanstack/react-query";
import { Bot,Building2,ChevronRight,MapPin,Plus,Search,UserRoundCog } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { EmptyState } from "@/components/operations/empty-state";
import { PageHeader,Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { localDateKey } from "@/lib/utils";
import { VenueHoursForm, type VenueSettings } from "./venue-hours-form";
import { VenuePriceRulesForm } from "./venue-price-rules-form";

type Item={id:string;name:string;code?:string;phone?:string;notes?:string;is_active?:boolean;fixed_class_fee?:number;private_lesson_fee?:number;fixed_class_fee_effective_from?:string|null;private_lesson_fee_effective_from?:string|null;version:number};

function DirectoryPage({title,description,path,code=false}:{title:string;description:string;path:string;code?:boolean}) {
  const client=useQueryClient();
  const [open,setOpen]=useState(false);
  const [editing,setEditing]=useState<Item|null>(null);
  const [search,setSearch]=useState("");
  const [name,setName]=useState("");
  const [itemCode,setCode]=useState("");
  const [phone,setPhone]=useState("");
  const [notes,setNotes]=useState("");
  const [fixedClassFee,setFixedClassFee]=useState(0);
  const [privateLessonFee,setPrivateLessonFee]=useState(0);
  const [rateEffectiveFrom,setRateEffectiveFrom]=useState(()=>localDateKey(new Date()));
  const query=useQuery({queryKey:[path],queryFn:()=>api<Item[]>(path)});
  const reset=()=>{setName("");setCode("");setPhone("");setNotes("");setFixedClassFee(0);setPrivateLessonFee(0);setRateEffectiveFrom(localDateKey(new Date()));setEditing(null);setOpen(false)};
  const save=useMutation({
    mutationFn:()=>api<Item>(editing?`${path}/${editing.id}`:path,{
      method:editing?"PUT":"POST",
      body:JSON.stringify({name,phone,notes,...(code?{code:itemCode}:{fixed_class_fee:fixedClassFee,private_lesson_fee:privateLessonFee,rate_effective_from:rateEffectiveFrom}),...(editing?{version:editing.version}:{})}),
    }),
    onSuccess:()=>{reset();void client.invalidateQueries({queryKey:[path]})},
  });
  const status=useMutation({
    mutationFn:({item,reason}:{item:Item;reason:string})=>api<Item>(`${path}/${item.id}/status`,{method:"PATCH",body:JSON.stringify({is_active:item.is_active===false,reason,version:item.version})}),
    onSuccess:(updated)=>{
      client.setQueryData<Item[]>([path],current=>current?.map(item=>item.id===updated.id?updated:item)??[updated]);
      void client.invalidateQueries({queryKey:[path]});
    },
  });
  const rows=(query.data??[]).filter(item=>`${item.name}${item.code??""}${item.phone??""}`.toLowerCase().includes(search.toLowerCase()));
  const beginCreate=()=>{setEditing(null);setName("");setCode("");setPhone("");setNotes("");setFixedClassFee(0);setPrivateLessonFee(0);setRateEffectiveFrom(localDateKey(new Date()));setOpen(true)};
  const beginEdit=(item:Item)=>{setEditing(item);setName(item.name);setCode(item.code??"");setPhone(item.phone??"");setNotes(item.notes??"");setFixedClassFee(item.fixed_class_fee??0);setPrivateLessonFee(item.private_lesson_fee??0);setRateEffectiveFrom(localDateKey(new Date()));setOpen(true)};
  return <section>
    <PageHeader eyebrow="Venue directory" title={title} description={description} actions={<button className="btn btn-primary" onClick={beginCreate}><Plus size={15}/>新增{code?"场地":"教练"}</button>}/>
    <Panel>
      <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4"><div className="relative w-64"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={14}/><input className="field h-9 pl-8" placeholder={`搜索${code?"场地":"教练"}`} value={search} onChange={event=>setSearch(event.target.value)}/></div><span className="text-xs text-slate-500">{query.isPending?"正在加载…":`共 ${rows.length} 条`}</span></div>
      {query.isPending?<div className="grid min-h-48 place-items-center text-sm text-slate-500" role="status">正在加载{code?"场地":"教练"}…</div>:query.isError&&!query.data?<div className="grid min-h-48 place-items-center px-6 text-center" role="alert"><div><p className="text-sm font-semibold text-red-700">{code?"场地":"教练"}加载失败</p><p className="mt-1 text-xs text-slate-500">{query.error.message}</p><button className="btn mt-3" onClick={()=>void query.refetch()}>重新加载</button></div></div>:rows.length?<table className="data-table"><thead><tr><th>{code?"场地":"教练"}</th>{code?<th>编号</th>:<th>联系电话</th>}{!code&&<th>当前费用标准</th>}<th>资源状态</th><th>排期能力</th><th>操作</th></tr></thead><tbody>{rows.map(item=><tr key={item.id}><td><div className="flex items-center gap-3"><span className="grid size-8 place-items-center rounded-md bg-slate-100 text-slate-500">{code?<MapPin size={14}/>:<UserRoundCog size={14}/>}</span><div><div className="table-primary">{item.name}</div><div className="table-secondary">{item.notes||`ID ${item.id.slice(0,8)}`}</div></div></div></td><td>{code?item.code:item.phone??<span className="text-slate-400">未填写</span>}</td>{!code&&<td><div>固定班 ¥{Number(item.fixed_class_fee??0).toFixed(2)} · {item.fixed_class_fee_effective_from??"未设置生效日"}</div><div className="table-secondary">私教 ¥{Number(item.private_lesson_fee??0).toFixed(2)} · {item.private_lesson_fee_effective_from??"未设置生效日"}</div></td>}<td><StatusBadge status={item.is_active===false?"inactive":"active"}/></td><td className="text-slate-500">{item.is_active===false?"暂停参与排期":"可参与统一排期"}</td><td><div className="flex gap-3">{!code&&<button className="text-xs font-semibold text-emerald-700" onClick={()=>beginEdit(item)}>编辑</button>}<button className="text-xs font-semibold text-slate-600" onClick={()=>{const reason=window.prompt(item.is_active===false?"请输入启用原因":code?"请输入停用原因（场地和历史排期会保留）":"请输入停用原因");if(reason)status.mutate({item,reason})}}>{item.is_active===false?"启用":"停用"}</button></div></td></tr>)}</tbody></table>:search.trim()?<div><EmptyState title={`未找到匹配${code?"场地":"教练"}`} description="请调整搜索条件，原有资料不会被删除。"/><div className="-mt-14 flex justify-center pb-8"><button className="btn" onClick={()=>setSearch("")}>清除搜索</button></div></div>:<EmptyState title={`暂无${code?"场地":"教练"}`} description={`新增后即可用于统一排期和冲突检查。`}/>} 
      {query.isError&&query.data?<p className="border-t border-amber-100 bg-amber-50 px-4 py-2 text-xs text-amber-800" role="alert">刷新失败，当前仍显示上次成功加载的数据。<button className="ml-2 font-semibold" onClick={()=>void query.refetch()}>重试</button></p>:null}
      {status.error?<p className="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700" role="alert">{status.error.message}</p>:null}
    </Panel>
    <Drawer open={open} title={`${editing?"编辑":"新增"}${code?"场地":"教练"}`} description="保存后可立即参与排期资源检查" onClose={reset}><form className="grid gap-4" onSubmit={event=>{event.preventDefault();save.mutate()}}>{code&&<label className="field-label">场地编号<input className="field" placeholder="例如：C01" value={itemCode} onChange={event=>setCode(event.target.value)}/></label>}<label className="field-label">名称<input className="field" required placeholder={code?"例如：1 号标准场":"教练姓名"} value={name} onChange={event=>setName(event.target.value)}/></label>{!code&&<><label className="field-label">联系电话<input className="field" placeholder="手机号" value={phone} onChange={event=>setPhone(event.target.value)}/></label><div className="grid grid-cols-2 gap-3"><label className="field-label">固定班单节费用<input className="field" min="0" step="0.01" type="number" value={fixedClassFee} onChange={event=>setFixedClassFee(Number(event.target.value))}/></label><label className="field-label">私教单节费用<input className="field" min="0" step="0.01" type="number" value={privateLessonFee} onChange={event=>setPrivateLessonFee(Number(event.target.value))}/></label></div><label className="field-label">新标准生效日期<input className="field" type="date" value={rateEffectiveFrom} onChange={event=>setRateEffectiveFrom(event.target.value)}/><span className="field-hint">历史业务保留原费用，新标准只用于之后创建的业务</span></label><label className="field-label">专长与备注<textarea className="field" value={notes} onChange={event=>setNotes(event.target.value)}/></label></>}<footer className="flex justify-end border-t border-slate-200 pt-4"><button className="btn btn-primary" disabled={save.isPending}>保存</button></footer></form></Drawer>
  </section>
}

export const CourtsPage=()=> <DirectoryPage title="场地管理" description="维护场地编号与可用状态；停用只会暂停新排期，不会删除场地及历史记录" path="/courts" code/>;
export const CoachesPage=()=> <DirectoryPage title="教练管理" description="维护教练资料、状态与授课资源" path="/coaches"/>;

export function VenueSettingsPage(){const venue=useQuery({queryKey:["venue-settings"],queryFn:()=>api<VenueSettings>("/venue/settings")});const value=venue.data;return <section><PageHeader eyebrow="System configuration" title="场馆设置" description="维护营业时间、场地和教练等基础运营资源"/><div className="responsive-grid grid grid-cols-[minmax(0,1.35fr)_minmax(320px,.65fr)] gap-4"><Panel title="场馆资料" description="修改场馆营业时间与排期校验规则"><div className="p-5"><div className="flex items-center gap-3 border-b border-slate-100 pb-5"><span className="grid size-10 place-items-center rounded-md bg-emerald-50 text-emerald-700"><Building2 size={18}/></span><div><div className="text-sm font-semibold text-slate-800">{value?.name??"ShuttleCube 羽毛球馆"}</div><div className="mt-1 text-xs text-slate-500">时区：{value?.timezone??"Asia/Shanghai"}</div></div></div><VenueHoursForm value={value}/></div></Panel><Panel title="资源目录" description="参与业务和统一排期的基础资料"><div className="divide-y divide-slate-100"><Link className="flex items-center gap-3 p-4 hover:bg-slate-50" to="/courts"><span className="grid size-9 place-items-center rounded-md bg-slate-100 text-slate-600"><MapPin size={16}/></span><div className="flex-1"><div className="text-xs font-semibold text-slate-700">场地管理</div><div className="mt-1 text-[11px] text-slate-400">维护四片场地及可用状态</div></div><ChevronRight size={14} className="text-slate-400"/></Link><Link className="flex items-center gap-3 p-4 hover:bg-slate-50" to="/coaches"><span className="grid size-9 place-items-center rounded-md bg-slate-100 text-slate-600"><UserRoundCog size={16}/></span><div className="flex-1"><div className="text-xs font-semibold text-slate-700">教练管理</div><div className="mt-1 text-[11px] text-slate-400">维护教练资料与授课资源</div></div><ChevronRight size={14} className="text-slate-400"/></Link><Link className="flex items-center gap-3 p-4 hover:bg-slate-50" to="/settings/ai"><span className="grid size-9 place-items-center rounded-md bg-slate-100 text-slate-600"><Bot size={16}/></span><div className="flex-1"><div className="text-xs font-semibold text-slate-700">AI 服务配置</div><div className="mt-1 text-[11px] text-slate-400">选择服务商、模型并验证 API Key</div></div><ChevronRight size={14} className="text-slate-400"/></Link></div></Panel></div><Panel className="mt-4" title="默认场地价格" description="设置工作日白天、晚间和周末的每小时默认价格"><VenuePriceRulesForm venue={value}/></Panel></section>}
