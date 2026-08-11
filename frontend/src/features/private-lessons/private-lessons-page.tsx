import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, PackagePlus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "@/api/client";
import { BulkCancelBar } from "@/components/operations/bulk-cancel-bar";
import { Drawer } from "@/components/operations/drawer";
import { EmptyState } from "@/components/operations/empty-state";
import { PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { ReceivableDetail } from "@/features/finance/receivable-detail";
import { PackageForm } from "./package-form";
import type { ScheduleItem } from "@/features/schedule/schedule-calendar";
import { ScheduleDetails } from "@/features/schedule/schedule-details";
import { formatCourtNames, useCourtDirectory } from "@/features/schedule/court-display";

type Lesson = {
  id: string;
  schedule_entry_id: string;
  student_id: string;
  student_name: string;
  coach_id: string;
  coach_name: string;
  billing_mode: string;
  package_id?: string | null;
  package_remaining_units?: number | null;
  actual_receivable: number;
  finance?: { receivable_id: string; received_amount: number; outstanding_amount: number; refundable_amount: number; payment_status: string } | null;
  coach_fee: number;
  generated_coach_fee?: { id: string; amount: number; status: string; settlement_id?: string | null } | null;
  starts_at: string;
  ends_at: string;
  court_ids: string[];
  status: string;
};
type Package = { id: string; student_id: string; student_name: string; bound_coach_id: string; coach_name: string; purchased_units: number; remaining_units: number; actual_receivable: number; valid_until?: string|null; status: string; finance?: {receivable_id:string;received_amount:number;outstanding_amount:number;payment_status:string}|null };
type LedgerRow = {id:string;change_type:string;delta:number;balance_after:number;operated_at:string};

function lessonDisplayStatus(item: Lesson) {
  return item.status === "booked" && new Date(item.ends_at).getTime() <= Date.now()
    ? "pending_completion"
    : item.status;
}

function PackageLedger({packageId}:{packageId:string}) {
  const query=useQuery({queryKey:["private-package-ledger",packageId],queryFn:()=>api<LedgerRow[]>(`/private-packages/${packageId}/ledger`)});
  return <div className="mt-4"><h4 className="text-xs font-semibold text-slate-700">扣课流水</h4><div className="mt-2 divide-y divide-slate-100">{query.data?.map((item)=><div className="flex justify-between py-2 text-xs" key={item.id}><span>{new Date(item.operated_at).toLocaleDateString("zh-CN")} · {item.change_type}</span><span className={item.delta<0?"text-amber-700":"text-emerald-700"}>{item.delta>0?"+":""}{item.delta} · 余额 {item.balance_after}</span></div>)}</div></div>;
}

export function PrivateLessonsPage() {
  const client = useQueryClient();
  const [searchParams] = useSearchParams();
  const [drawer, setDrawer] = useState<"package" | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ScheduleItem | null>(null);
  const [selectedPackage, setSelectedPackage] = useState<Package | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const courts = useCourtDirectory();
  const lessons = useQuery({
    queryKey: ["private-lessons"],
    queryFn: () => api<Lesson[]>("/private-lessons"),
  });
  const packages = useQuery({
    queryKey: ["private-packages"],
    queryFn: () => api<Package[]>("/private-packages"),
  });
  const createPackage = useMutation({
    mutationFn: (value: object) =>
      api("/private-packages", { method: "POST", body: JSON.stringify(value) }),
    onSuccess: () => {
      setDrawer(null);
      void client.invalidateQueries({ queryKey: ["private-packages"] });
    },
  });
  const completeLesson = useMutation({
    mutationFn:(id:string)=>api(`/private-lessons/${id}/complete`,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()}}),
    onSuccess:()=>{setSelected(null);void client.invalidateQueries({queryKey:["private-lessons"]});void client.invalidateQueries({queryKey:["private-packages"]});void client.invalidateQueries({queryKey:["coach-fees"]})},
  });
  const normalizedSearch = search.trim().toLowerCase();
  const rows = (lessons.data ?? []).filter((item) =>
    `${item.student_name} ${item.coach_name}`.toLowerCase().includes(normalizedSearch),
  );
  const cancellableIds = rows
    .filter((item) => lessonDisplayStatus(item) === "booked")
    .map((item) => item.id);
  const select = (item: Lesson) =>
    setSelected({
      id: item.schedule_entry_id,
      source_id: item.id,
      source_type: "private_lesson",
      title: `${item.student_name} · 私教课程`,
      starts_at: item.starts_at,
      ends_at: item.ends_at,
      status: lessonDisplayStatus(item),
      resources: [
        ...item.court_ids.map((id) => ({ type: "court", id })),
        { type: "coach", id: item.coach_id },
        { type: "student", id: item.student_id },
      ],
    });
  useEffect(() => {
    const lessonId = searchParams.get("lesson_id");
    const lesson = lessons.data?.find((item) => item.id === lessonId);
    if (lesson) select(lesson);
  }, [lessons.data, searchParams]);
  return (
    <section>
      <PageHeader
        eyebrow="Private coaching"
        title="私教管理"
        description="统一管理私教课包、单次预约和履约扣课"
        actions={
          <>
            <button className="btn" onClick={() => setDrawer("package")}>
              <PackagePlus size={15} />
              销售课包
            </button>
            <Link className="btn btn-primary" to="/schedule">
              <CalendarPlus size={15} />
              预约私教
            </Link>
          </>
        }
      />
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="metric-card">
          <div className="metric-label">有效课包</div>
          <div className="metric-value">
            {(packages.data ?? []).filter((item) => item.status === "active").length}
          </div>
          <div className="metric-footnote">可继续预约和扣课</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">待履约私教</div>
          <div className="metric-value">
            {(lessons.data ?? []).filter((item) => lessonDisplayStatus(item) === "booked").length}
          </div>
          <div className="metric-footnote">已预约、尚未完成</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">已完成课程</div>
          <div className="metric-value">
            {(lessons.data ?? []).filter((item) => item.status === "completed").length}
          </div>
          <div className="metric-footnote">已完成课时核销</div>
        </div>
      </div>
      <Panel className="mb-4" title="私教课包" description="查看每个学员的购买课时、剩余课时和收费状态">
        {(packages.data??[]).length?<table className="data-table"><thead><tr><th>学员</th><th>绑定教练</th><th>课时</th><th>收费</th><th>有效期</th><th>状态</th><th>操作</th></tr></thead><tbody>{packages.data?.map((item)=><tr key={item.id}><td className="table-primary">{item.student_name}</td><td>{item.coach_name}</td><td>{item.remaining_units} / {item.purchased_units} 节</td><td>应收 ¥{item.actual_receivable.toFixed(2)}<div className="table-secondary">欠费 ¥{(item.finance?.outstanding_amount??item.actual_receivable).toFixed(2)}</div></td><td>{item.valid_until?new Date(item.valid_until).toLocaleDateString("zh-CN"):"长期有效"}</td><td><StatusBadge status={item.finance?.payment_status??item.status}/></td><td><button className="text-xs font-semibold text-emerald-700" onClick={()=>setSelectedPackage(item)}>详情/流水</button></td></tr>)}</tbody></table>:<EmptyState title="暂无私教课包" description="销售课包后将在这里展示课时与财务状态。"/>}
      </Panel>
      <Panel>
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
          <div className="relative w-64">
            <input
              className="field h-9 pr-8"
              placeholder="搜索私教预约"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
              size={14}
            />
          </div>
          <BulkCancelBar
            endpoint="/private-lessons/bulk-delete"
            ids={[...selectedIds]}
            onDone={() => {
              setSelectedIds(new Set());
              void client.invalidateQueries({ queryKey: ["private-lessons"] });
              void client.invalidateQueries({ queryKey: ["schedule"] });
            }}
          />
        </div>
        {rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-10">
                  <input
                    aria-label="全选待履约私教"
                    type="checkbox"
                    checked={
                      cancellableIds.length > 0 && cancellableIds.every((id) => selectedIds.has(id))
                    }
                    onChange={(event) =>
                      setSelectedIds(event.target.checked ? new Set(cancellableIds) : new Set())
                    }
                  />
                </th>
                <th>预约时间</th>
                <th>学员</th>
                <th>教练</th>
                <th>场地</th>
                <th>结算方式</th>
                <th>教练费</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id}>
                  <td>
                    <input
                      aria-label={`选择 ${item.student_name}`}
                      disabled={lessonDisplayStatus(item) !== "booked"}
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={(event) =>
                        setSelectedIds((current) => {
                          const next = new Set(current);
                          if (event.target.checked) next.add(item.id);
                          else next.delete(item.id);
                          return next;
                        })
                      }
                    />
                  </td>
                  <td>
                    <div className="table-primary">
                      {new Date(item.starts_at).toLocaleDateString("zh-CN")}
                    </div>
                    <div className="table-secondary">
                      {new Date(item.starts_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      –{" "}
                      {new Date(item.ends_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </td>
                  <td className="table-primary">{item.student_name}</td>
                  <td>{item.coach_name}</td>
                  <td>{formatCourtNames(item.court_ids, courts.data)}</td>
                  <td>{item.billing_mode === "package" ? `课包扣课 · 剩余 ${item.package_remaining_units ?? "—"} 节` : "单次结算"}</td>
                  <td>
                    <div>¥{Number(item.generated_coach_fee?.amount ?? item.coach_fee).toFixed(2)}</div>
                    <div className="table-secondary">
                      {item.generated_coach_fee
                        ? item.generated_coach_fee.status === "settled" ? "已结算" : "待结算"
                        : "预约费用快照"}
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={lessonDisplayStatus(item)} />
                  </td>
                  <td>
                    <button
                      className="text-xs font-semibold text-emerald-700"
                      onClick={() => select(item)}
                      type="button"
                    >
                      {lessonDisplayStatus(item) === "pending_completion" ? "确认完成" : "修改/删除"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="暂无私教预约" description="请前往统一排期选择场地和时间后预约私教。" />
        )}
      </Panel>
      <Drawer
        open={drawer === "package"}
        title="销售私教课包"
        description="创建绑定学员与教练的课时权益"
        onClose={() => setDrawer(null)}
      >
        <PackageForm onSubmit={(value) => createPackage.mutate(value)} />
      </Drawer>
      <Drawer
        open={selected !== null}
        title="私教课程详情"
        description="查看、修改或删除私教课程"
        onClose={() => setSelected(null)}
      >
        {selected && (
          <><ScheduleDetails item={selected} onChanged={() => { setSelected(null); void client.invalidateQueries({ queryKey: ["private-lessons"] }); void client.invalidateQueries({ queryKey: ["schedule"] }); }} />
          {selected.source_id&&<div className="mt-4 rounded-md border border-slate-200 p-3 text-xs text-slate-600"><div>{lessons.data?.find(item=>item.id===selected.source_id)?.billing_mode==="package"?`关联课包：${lessons.data?.find(item=>item.id===selected.source_id)?.package_id} · 当前剩余 ${lessons.data?.find(item=>item.id===selected.source_id)?.package_remaining_units} 节`:`单次收费：¥${lessons.data?.find(item=>item.id===selected.source_id)?.actual_receivable.toFixed(2)}`}</div><div className="mt-1">教练费：¥{Number(lessons.data?.find(item=>item.id===selected.source_id)?.generated_coach_fee?.amount??lessons.data?.find(item=>item.id===selected.source_id)?.coach_fee??0).toFixed(2)} · {lessons.data?.find(item=>item.id===selected.source_id)?.generated_coach_fee?.status==="settled"?"已结算":lessons.data?.find(item=>item.id===selected.source_id)?.generated_coach_fee?"待结算":"完成履约后生成"}</div></div>}
          {selected.source_id && lessons.data?.find(item => item.id === selected.source_id)?.finance?.receivable_id ? <div className="mt-4"><ReceivableDetail receivableId={lessons.data.find(item => item.id === selected.source_id)!.finance!.receivable_id} onChanged={() => void client.invalidateQueries({ queryKey: ["private-lessons"] })} /></div> : null}
          {selected.status==="pending_completion"&&selected.source_id&&<button className="btn btn-primary mt-4 w-full" disabled={completeLesson.isPending} onClick={()=>completeLesson.mutate(selected.source_id!)}>确认完成私教并扣课、生成教练费用</button>}</>
        )}
      </Drawer>
      <Drawer open={selectedPackage!==null} title="私教课包详情" description="课包余额、收费状态和逐笔课时流水" onClose={()=>setSelectedPackage(null)}>{selectedPackage&&<div className="p-1 text-sm"><div className="grid grid-cols-2 gap-3 rounded-md bg-slate-50 p-4"><div><span className="text-xs text-slate-400">学员</span><b className="block">{selectedPackage.student_name}</b></div><div><span className="text-xs text-slate-400">绑定教练</span><b className="block">{selectedPackage.coach_name}</b></div><div><span className="text-xs text-slate-400">剩余课时</span><b className="block">{selectedPackage.remaining_units} / {selectedPackage.purchased_units}</b></div><div><span className="text-xs text-slate-400">待收款</span><b className="block">¥{(selectedPackage.finance?.outstanding_amount??0).toFixed(2)}</b></div></div><PackageLedger packageId={selectedPackage.id}/>{selectedPackage.finance?.receivable_id ? <div className="mt-4"><ReceivableDetail receivableId={selectedPackage.finance.receivable_id} onChanged={() => void client.invalidateQueries({ queryKey: ["private-packages"] })} /></div> : null}</div>}</Drawer>
    </section>
  );
}
