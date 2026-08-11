import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRightLeft,
  GraduationCap,
  PackagePlus,
  Phone,
  Plus,
  Search,
  Trash2,
  UserRound,
} from "lucide-react";
import { type FormEvent, useState } from "react";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { EmptyState } from "@/components/operations/empty-state";
import { PageHeader, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";

type Student = {
  id: string;
  name: string;
  phone?: string;
  is_active: boolean;
  notes?: string;
  entitlement_summary?: { active_labels: string[]; has_history: boolean; has_invalid: boolean };
};
type Finance = {
  actual_amount: number;
  received_amount: number;
  refunded_amount: number;
  outstanding_amount: number;
  payment_status: string;
};
type Entitlement = {
  id: string;
  fixed_class_id?: string;
  name?: string;
  coach_name?: string;
  purchased_units: number;
  remaining_units: number;
  status: string;
  acquisition_type?: string;
  finance?: Finance | null;
  version: number;
};
type Entitlements = {
  student_id: string;
  fixed_classes: Entitlement[];
  private_packages: Entitlement[];
};
type FixedClass = { id: string; name: string; status: string };
type Coach = { id: string; name: string; is_active?: boolean };

function StudentEntitlementCenter({ student, onClose }: { student: Student; onClose: () => void }) {
  const client = useQueryClient();
  const [adding, setAdding] = useState<"fixed" | "private" | null>(null);
  const [transferring, setTransferring] = useState<Entitlement | null>(null);
  const query = useQuery({
    queryKey: ["student-entitlements", student.id],
    queryFn: () => api<Entitlements>(`/students/${student.id}/entitlements`),
  });
  const classes = useQuery({ queryKey: ["classes"], queryFn: () => api<FixedClass[]>("/classes") });
  const coaches = useQuery({ queryKey: ["coaches"], queryFn: () => api<Coach[]>("/coaches") });
  const refresh = () => {
    setAdding(null);
    void client.invalidateQueries({ queryKey: ["student-entitlements", student.id] });
    void client.invalidateQueries({ queryKey: ["private-packages"] });
  };
  const addFixed = useMutation({
    mutationFn: (payload: object) =>
      api(`/students/${student.id}/entitlements/fixed-classes`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  });
  const addPrivate = useMutation({
    mutationFn: (payload: object) =>
      api(`/students/${student.id}/entitlements/private-packages`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: refresh,
  });
  const terminate = useMutation({
    mutationFn: ({ type, item, reason }: { type: string; item: Entitlement; reason: string }) =>
      api(`/students/${student.id}/entitlements/${type}/${item.id}/terminate`, {
        method: "POST",
        body: JSON.stringify({ version: item.version, reason }),
      }),
    onSuccess: refresh,
  });
  const transfer = useMutation({
    mutationFn: (payload: {
      item: Entitlement;
      target_fixed_class_id: string;
      target_units: number;
      reason: string;
    }) =>
      api(`/students/${student.id}/entitlements/fixed-classes/${payload.item.id}/transfer`, {
        method: "POST",
        body: JSON.stringify({
          target_fixed_class_id: payload.target_fixed_class_id,
          target_units: payload.target_units,
          reason: payload.reason,
          version: payload.item.version,
        }),
      }),
    onSuccess: () => {
      setTransferring(null);
      refresh();
    },
  });
  const remove = (type: string, item: Entitlement) => {
    const reason = window.prompt("请输入删除/终止该培训权益的原因。已有收款时需先完成退款。");
    if (reason) terminate.mutate({ type, item, reason });
  };
  const submitFixed = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const units = String(data.get("purchased_units") || "");
    const amount = String(data.get("actual_receivable") || "");
    addFixed.mutate({
      fixed_class_id: String(data.get("fixed_class_id")),
      enrolled_on: String(data.get("enrolled_on")),
      ...(units ? { purchased_units: Number(units) } : {}),
      ...(amount ? { actual_receivable: Number(amount) } : {}),
      adjustment_reason: String(data.get("adjustment_reason") || "") || null,
    });
  };
  const submitPrivate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const amount = String(data.get("actual_receivable") || "");
    addPrivate.mutate({
      coach_id: String(data.get("coach_id")),
      purchased_units: Number(data.get("purchased_units")),
      unit_price: Number(data.get("unit_price")),
      ...(amount ? { actual_receivable: Number(amount) } : {}),
    });
  };
  const rows = [
    ...(query.data?.fixed_classes ?? []).map((item) => ({
      type: "fixed_class",
      kind: "固定班",
      item,
    })),
    ...(query.data?.private_packages ?? []).map((item) => ({
      type: "private_package",
      kind: "私教课包",
      item,
    })),
  ];
  return (
    <div>
      <div className="mb-4 flex gap-2">
        <button className="btn" onClick={() => setAdding("fixed")}>
          <GraduationCap size={14} />
          添加固定班权益
        </button>
        <button className="btn" onClick={() => setAdding("private")}>
          <PackagePlus size={14} />
          添加私教课包
        </button>
      </div>
      {rows.length ? (
        <div className="divide-y divide-slate-100 rounded-md border border-slate-200">
          {rows.map(({ type, kind, item }) => (
            <div
              className={`grid grid-cols-[1fr_100px_100px_30px] items-center gap-3 p-3 ${
                item.status === "active" ? "" : "bg-amber-50"
              }`}
              key={`${type}-${item.id}`}
            >
              <div>
                <div className="text-xs font-semibold text-slate-700">
                  {item.name ?? item.coach_name ?? kind}
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  {kind} · {item.status} ·{" "}
                  {item.acquisition_type === "transfer"
                    ? "权益转入，不新增应收"
                    : item.finance?.payment_status ?? "无财务记录"}
                </div>
                {type === "fixed_class" &&
                ["active", "expired"].includes(item.status) &&
                item.remaining_units > 0 ? (
                  <button
                    className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-sky-700"
                    onClick={() => setTransferring(item)}
                    type="button"
                  >
                    <ArrowRightLeft size={12} /> 转移到其他班
                  </button>
                ) : null}
              </div>
              <div className="text-xs">
                剩余 {item.remaining_units}/{item.purchased_units}
              </div>
              <div className="text-xs text-amber-700">
                欠费 ¥{(item.finance?.outstanding_amount ?? 0).toFixed(2)}
              </div>
              <button
                aria-label="删除权益"
                className="text-slate-400 hover:text-red-600"
                onClick={() => remove(type, item)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState title="暂无培训权益" description="可为该学员关联多个固定班和私教课包。" />
      )}
      {terminate.error && (
        <p className="mt-3 text-xs text-red-600" role="alert">
          {terminate.error.message}
        </p>
      )}
      {transfer.error ? (
        <p className="mt-3 text-xs text-red-600" role="alert">
          {transfer.error.message}
        </p>
      ) : null}
      <Drawer
        open={transferring !== null}
        title="转移固定班培训权益"
        description="保留原班已上课时历史，由管理员设置转入新班后的课时数量"
        onClose={() => setTransferring(null)}
      >
        {transferring ? (
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              transfer.mutate({
                item: transferring,
                target_fixed_class_id: String(data.get("target_fixed_class_id")),
                target_units: Number(data.get("target_units")),
                reason: String(data.get("reason")),
              });
            }}
          >
            <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
              原权益剩余 {transferring.remaining_units} 节；转移不会重复生成收入或应收。
            </div>
            <label className="field-label">
              目标固定班
              <select className="field" name="target_fixed_class_id" required>
                {classes.data
                  ?.filter(
                    (item) => item.status === "active" && item.id !== transferring.fixed_class_id,
                  )
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </label>
            <label className="field-label">
              转移后的新课时数量
              <input
                className="field"
                defaultValue={transferring.remaining_units}
                min="1"
                name="target_units"
                type="number"
                required
              />
            </label>
            <label className="field-label">
              转移原因
              <textarea className="field" name="reason" required />
            </label>
            <div className="flex justify-end gap-2">
              <button className="btn" onClick={() => setTransferring(null)} type="button">返回</button>
              <button className="btn btn-primary" disabled={transfer.isPending}>确认转移</button>
            </div>
          </form>
        ) : null}
      </Drawer>
      <Drawer
        open={adding === "fixed"}
        title="添加固定班权益"
        description={`为 ${student.name} 创建一笔独立报名权益`}
        onClose={() => setAdding(null)}
      >
        <form className="grid gap-4" onSubmit={submitFixed}>
          <label className="field-label">
            固定班
            <select className="field" name="fixed_class_id" required>
              {classes.data
                ?.filter((item) => item.status === "active")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="field-label">
            报名日期
            <input
              className="field"
              name="enrolled_on"
              type="date"
              defaultValue={new Date().toISOString().slice(0, 10)}
              required
            />
          </label>
          <label className="field-label">
            购买课时
            <input
              className="field"
              name="purchased_units"
              type="number"
              min="1"
              placeholder="留空按剩余课次"
            />
          </label>
          <label className="field-label">
            实际应收
            <input
              className="field"
              name="actual_receivable"
              type="number"
              min="0"
              step="0.01"
              placeholder="留空使用建议金额"
            />
          </label>
          <label className="field-label">
            调整原因
            <textarea className="field" name="adjustment_reason" />
          </label>
          <button className="btn btn-primary">确认添加</button>
        </form>
      </Drawer>
      <Drawer
        open={adding === "private"}
        title="添加私教课包"
        description={`为 ${student.name} 创建可预约扣课的私教权益`}
        onClose={() => setAdding(null)}
      >
        <form className="grid gap-4" onSubmit={submitPrivate}>
          <label className="field-label">
            绑定教练
            <select className="field" name="coach_id" required>
              {coaches.data
                ?.filter((item) => item.is_active !== false)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="field-label">
            购买课时
            <input
              className="field"
              name="purchased_units"
              type="number"
              min="1"
              defaultValue="10"
              required
            />
          </label>
          <label className="field-label">
            课时单价
            <input
              className="field"
              name="unit_price"
              type="number"
              min="0"
              step="0.01"
              defaultValue="300"
              required
            />
          </label>
          <label className="field-label">
            实际应收
            <input
              className="field"
              name="actual_receivable"
              type="number"
              min="0"
              step="0.01"
              placeholder="留空按课时 × 单价"
            />
          </label>
          <button className="btn btn-primary">确认添加</button>
        </form>
      </Drawer>
      <div className="mt-5 flex justify-end">
        <button className="btn" onClick={onClose}>
          关闭
        </button>
      </div>
    </div>
  );
}

export function StudentsPage() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const query = useQuery({
    queryKey: ["students"],
    queryFn: () => api<{ items: Student[] }>("/students"),
  });
  const add = useMutation({
    mutationFn: () =>
      api<Student>("/students", { method: "POST", body: JSON.stringify({ name, phone, notes }) }),
    onSuccess: (student) => {
      setName("");
      setPhone("");
      setNotes("");
      setOpen(false);
      setSelectedStudent(student);
      void client.invalidateQueries({ queryKey: ["students"] });
    },
  });
  const rows = (query.data?.items ?? []).filter((student) =>
    `${student.name}${student.phone ?? ""}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <section>
      <PageHeader
        eyebrow="Customer records"
        title="学员档案"
        description="集中维护学员联系方式、培训权益与业务往来"
        actions={
          <button className="btn btn-primary" onClick={() => setOpen(true)}>
            <Plus size={15} />
            新增学员
          </button>
        }
      />
      <Panel>
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
          <div className="relative w-72">
            <input
              className="field h-9 pr-8"
              placeholder="搜索姓名或手机号"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
              size={14}
            />
          </div>
          <span className="text-xs text-slate-500">共 {rows.length} 名学员</span>
        </div>
        {rows.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>学员</th>
                <th>联系方式</th>
                <th>培训权益</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((student) => (
                <tr key={student.id}>
                  <td>
                    <div className="flex items-center gap-3">
                      <span className="grid size-8 place-items-center rounded-full bg-emerald-50 text-emerald-700">
                        <UserRound size={14} />
                      </span>
                      <div>
                        <div className="table-primary">{student.name}</div>
                        <div className="table-secondary">档案号 {student.id.slice(0, 8)}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    {student.phone ? (
                      <span className="inline-flex items-center gap-1.5">
                        <Phone size={12} className="text-slate-400" />
                        {student.phone}
                      </span>
                    ) : (
                      <span className="text-slate-400">未填写</span>
                    )}
                  </td>
                  <td>
                    <button
                      className="max-w-72 text-left text-xs font-semibold text-emerald-700"
                      onClick={() => setSelectedStudent(student)}
                    >
                      <span>
                        {student.entitlement_summary?.active_labels.length
                          ? student.entitlement_summary.active_labels.join("；")
                          : student.entitlement_summary?.has_history
                            ? "权益已失效"
                            : "无权益"}
                      </span>
                      {student.entitlement_summary?.has_invalid ? (
                        <span className="mt-1 block text-amber-700">存在失效权益</span>
                      ) : null}
                    </button>
                  </td>
                  <td>
                    <StatusBadge status={student.is_active === false ? "inactive" : "active"} />
                  </td>
                  <td>
                    <button
                      className="text-xs font-semibold text-emerald-700"
                      onClick={() => setSelectedStudent(student)}
                    >
                      权益详情
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState
            title="暂无学员档案"
            description="新增学员后可为其报名固定班、购买私教课包。"
          />
        )}
      </Panel>
      <Drawer
        open={open}
        title="新增学员"
        description="保存基础档案后继续绑定固定班或私教课包权益"
        onClose={() => setOpen(false)}
      >
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            add.mutate();
          }}
        >
          <label className="field-label">
            学员姓名
            <input
              className="field"
              placeholder="请输入真实姓名"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="field-label">
            联系电话
            <input
              className="field"
              placeholder="手机号或其他联系方式"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </label>
          <label className="field-label">
            备注
            <textarea
              className="field"
              placeholder="年龄、水平或需要关注的信息"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>
          <footer className="flex justify-end border-t border-slate-200 pt-4">
            <button className="btn btn-primary">保存并绑定培训权益</button>
          </footer>
        </form>
      </Drawer>
      <Drawer
        open={selectedStudent !== null}
        title={`${selectedStudent?.name ?? "学员"} · 培训权益`}
        description="统一查看并事后添加、终止固定班和私教课包权益"
        onClose={() => setSelectedStudent(null)}
      >
        {selectedStudent && (
          <StudentEntitlementCenter
            student={selectedStudent}
            onClose={() => setSelectedStudent(null)}
          />
        )}
      </Drawer>
    </section>
  );
}
