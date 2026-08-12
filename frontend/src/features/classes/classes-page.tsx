import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { EmptyState } from "@/components/operations/empty-state";
import { PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { formatBeijing, formatBusinessDate } from "@/lib/beijing-time";
import { localDateKey } from "@/lib/utils";
import { ClassForm, type ClassInput } from "./class-form";

type FixedClass = {
  id: string;
  name: string;
  class_type: string;
  start_date: string;
  default_start_time: string;
  session_count: number;
  capacity: number;
  default_coach_id: string;
  status: string;
};

type EndingClass = FixedClass & {
  last_scheduled_end: string;
  remaining_scheduled_sessions: number;
};

type EndingWithinDays = 7 | 15 | 30;

function dateTime(value: string | null) {
  return value
    ? formatBeijing(value, {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}

export function ClassesPage() {
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const attention = searchParams.get("attention");
  const requestedDays = Number(searchParams.get("days"));
  const endingWithinDays: EndingWithinDays =
    requestedDays === 7 || requestedDays === 15 ? requestedDays : 30;
  const businessDate = localDateKey(new Date());

  const classesQuery = useQuery({
    queryKey: ["classes"],
    queryFn: () => api<FixedClass[]>("/classes"),
    enabled: attention !== "ending",
  });
  const endingQuery = useQuery({
    queryKey: ["classes", "ending", businessDate, endingWithinDays],
    queryFn: () =>
      api<EndingClass[]>(
        `/classes?business_date=${businessDate}&ending_within_days=${endingWithinDays}`,
      ),
    enabled: attention === "ending",
  });
  const create = useMutation({
    mutationFn: (value: ClassInput) =>
      api("/classes", {
        method: "POST",
        body: JSON.stringify({
          ...value,
          required_court_count: value.court_ids.length,
        }),
      }),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({ queryKey: ["classes"] });
    },
  });

  const normalizedSearch = search.trim().toLowerCase();
  const rows = (classesQuery.data ?? []).filter((item) =>
    item.name.toLowerCase().includes(normalizedSearch),
  );
  const endingRows = (endingQuery.data ?? []).filter((item) =>
    item.name.toLowerCase().includes(normalizedSearch),
  );
  const isAttentionView = attention === "ending";

  return (
    <section>
      <PageHeader
        eyebrow="Class operations"
        title={attention === "ending" ? "即将结束班级" : "固定班管理"}
        description={
          attention === "ending"
              ? `仅展示最后一节未来课程在 ${endingWithinDays} 天内的班级`
              : "管理周期班级、课程实例、报名与课时权益"
        }
        actions={
          isAttentionView ? (
            <Link className="btn" to="/classes">
              返回全部固定班
            </Link>
          ) : (
            <button className="btn btn-primary" onClick={() => setOpen(true)}>
              <Plus size={15} />
              新建固定班
            </button>
          )
        }
      />
      <Panel>
        <div className="flex min-h-14 items-center justify-between gap-3 border-b border-slate-200 px-4 py-2">
          <div className="relative w-64">
            <input
              className="field h-9 pr-8"
              placeholder="搜索班级"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
              size={14}
            />
          </div>
          {attention === "ending" ? (
            <div className="flex gap-1" aria-label="即将结束班级范围筛选">
              {([7, 15, 30] as const).map((days) => (
                <button
                  aria-pressed={endingWithinDays === days}
                  className={`btn ${endingWithinDays === days ? "btn-primary" : ""}`}
                  key={days}
                  onClick={() => setSearchParams({ attention: "ending", days: String(days) })}
                  type="button"
                >
                  {days} 天
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {attention === "ending" ? (
          endingRows.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>班级</th>
                  <th>最后一节未来课程</th>
                  <th>剩余课程</th>
                  <th>状态</th>
                  <th className="w-20">操作</th>
                </tr>
              </thead>
              <tbody>
                {endingRows.map((item) => (
                  <tr key={item.id}>
                    <td className="table-primary">{item.name}</td>
                    <td>{dateTime(item.last_scheduled_end)}</td>
                    <td>{item.remaining_scheduled_sessions} 节</td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>
                      <Link className="text-xs font-semibold text-emerald-700" to={`/classes/${item.id}`}>
                        查看
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              title={`${endingWithinDays} 天内暂无即将结束班级`}
              description="这里只统计仍有未来待上课程的有效固定班。"
            />
          )
        ) : rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>班级</th>
                <th>开班日期</th>
                <th>课程计划</th>
                <th>容量</th>
                <th>状态</th>
                <th className="w-20">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link className="table-primary hover:text-emerald-700" to={`/classes/${item.id}`}>
                      {item.name}
                    </Link>
                    <div className="table-secondary">
                      {item.class_type === "training" ? "常规培训班" : item.class_type}
                    </div>
                  </td>
                  <td>{formatBusinessDate(item.start_date)}</td>
                  <td>{item.session_count} 节课</td>
                  <td>{item.capacity} 人</td>
                  <td><StatusBadge status={item.status} /></td>
                  <td>
                    <Link className="text-xs font-semibold text-emerald-700" to={`/classes/${item.id}`}>
                      查看
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="暂无固定班" description="点击右上角新建固定班并批量生成课程。" />
        )}
      </Panel>
      <Drawer
        open={open}
        title="新建固定班"
        description="创建后将按周批量生成课程与资源占用"
        onClose={() => setOpen(false)}
      >
        <ClassForm onSubmit={(value) => create.mutate(value)} />
      </Drawer>
    </section>
  );
}
