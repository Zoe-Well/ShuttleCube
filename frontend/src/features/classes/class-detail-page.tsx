import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarDays,
  CircleDollarSign,
  Clock3,
  ReceiptText,
  UsersRound,
  WalletCards,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { EmptyState } from "@/components/operations/empty-state";
import { MetricCard, Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { ReceivableDetail } from "@/features/finance/receivable-detail";
import { yuan } from "@/features/finance/types";
import { CancelReplaceDialog } from "./cancel-replace-dialog";
import { ClassManagementActions } from "./class-management-actions";
import { SessionTimeEditor } from "./session-time-editor";
import { AttendancePanel } from "./attendance-panel";

type EnrollmentFinance = {
  receivable_id: string;
  actual_amount: number;
  received_amount: number;
  refunded_amount: number;
  net_received: number;
  outstanding_amount: number;
  payment_status: string;
};

type Detail = {
  id: string;
  name: string;
  status: string;
  version: number;
  session_count: number;
  capacity: number;
  coach_fee_per_session: number;
  finance: {
    actual_amount: number;
    received_amount: number;
    refunded_amount: number;
    net_received: number;
    outstanding_amount: number;
  };
  sessions: Array<{
    id: string;
    version: number;
    sequence_number: number;
    scheduled_start: string;
    scheduled_end: string;
    status: string;
    replacement_for_session_id: string | null;
    replacement_for_sequence: number | null;
    replacement_decision: string | null;
    attendance_finalized_at: string | null;
    attendance: Array<{
      id: string;
      student_id: string;
      student_name: string;
      status: string;
      deduct_units: number;
      decision_note: string | null;
    }>;
    coach_fee: {
      id: string;
      base_amount: number;
      adjustment_amount: number;
      amount: number;
      status: string;
      settlement_id: string | null;
    } | null;
  }>;
  enrollments: Array<{
    id: string;
    student_id: string;
    student_name: string;
    purchased_units: number;
    remaining_units: number;
    unit_price: number;
    status: string;
    acquisition_type: string;
    finance: EnrollmentFinance | null;
  }>;
};

export function ClassDetailPage() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const [selectedReceivable, setSelectedReceivable] = useState<string | null>(null);
  const [attendanceSession, setAttendanceSession] = useState<string | null>(() =>
    searchParams.get("attendance_session"),
  );
  const [attendanceResultSession, setAttendanceResultSession] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["class", id],
    queryFn: () => api<Detail>(`/classes/${id}`),
    enabled: Boolean(id),
  });
  if (!query.data) return <p className="text-sm text-slate-500">正在加载班级信息…</p>;

  const detail = query.data;
  const completed = detail.sessions.filter((item) => item.status === "completed").length;
  const activeEnrollmentCount = detail.enrollments.filter((item) => item.status === "active").length;
  const nextSession = detail.sessions.find((item) => item.status === "scheduled");
  const attendanceResult = detail.sessions.find((item) => item.id === attendanceResultSession);

  return (
    <section>
      <Link
        className="mb-4 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700"
        to="/classes"
      >
        <ArrowLeft size={13} />返回固定班
      </Link>
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="page-title">{detail.name}</h1>
            <StatusBadge status={detail.status} />
          </div>
          <p className="page-subtitle">班级课程、报名学员、收费和课时履约详情 · 单节教练费 {yuan(detail.coach_fee_per_session)}</p>
        </div>
        <ClassManagementActions
          classId={detail.id}
          version={detail.version}
          capacity={detail.capacity}
          status={detail.status}
          enrollments={detail.enrollments}
          onDone={() => void query.refetch()}
        />
      </header>

      <div className="grid grid-cols-3 gap-3">
        <MetricCard
          label="课程进度"
          value={`${completed}/${detail.session_count}`}
          footnote="已完成 / 全部课次"
          icon={<CalendarDays size={15} />}
        />
        <MetricCard
          label="当前学员"
          value={String(activeEnrollmentCount)}
          footnote={`班级容量 ${detail.capacity ?? "—"} 人`}
          icon={<UsersRound size={15} />}
        />
        <MetricCard
          label="下次课程"
          value={
            nextSession
              ? new Date(nextSession.scheduled_start).toLocaleDateString("zh-CN", {
                  month: "numeric",
                  day: "numeric",
                })
              : "—"
          }
          footnote="最近一节待上课程"
          icon={<Clock3 size={15} />}
        />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        <MetricCard
          label="班级应收"
          value={yuan(detail.finance.actual_amount)}
          footnote="全部报名实际应收"
          icon={<ReceiptText size={15} />}
        />
        <MetricCard
          label="班级净实收"
          value={yuan(detail.finance.net_received)}
          footnote={`累计收款 ${yuan(detail.finance.received_amount)} · 退款 ${yuan(detail.finance.refunded_amount)}`}
          icon={<CircleDollarSign size={15} />}
        />
        <MetricCard
          label="班级欠费"
          value={yuan(detail.finance.outstanding_amount)}
          footnote="仍需跟进的报名款项"
          icon={<WalletCards size={15} />}
        />
      </div>

      <div className="responsive-grid mt-4 grid grid-cols-[minmax(0,1.35fr)_minmax(420px,1fr)] gap-4">
        <Panel title="课程计划" description="按课次查看排期、状态和异常操作">
          {detail.sessions.length ? (
            <table className="data-table">
              <thead><tr><th>课次</th><th>日期与时间</th><th>状态</th><th>教练费</th><th>操作</th></tr></thead>
              <tbody>
                {detail.sessions.map((item) => (
                  <tr key={item.id}>
                    <td className="table-primary">第 {item.sequence_number} 节</td>
                    <td>
                      {item.replacement_for_sequence ? (
                        <div className="mb-1 text-[11px] font-semibold text-amber-700">
                          补排原第 {item.replacement_for_sequence} 节
                        </div>
                      ) : null}
                      <div>{new Date(item.scheduled_start).toLocaleDateString("zh-CN")}</div>
                      <div className="table-secondary">
                        {new Date(item.scheduled_start).toLocaleTimeString("zh-CN", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                    </td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>
                      {item.coach_fee ? (
                        <div>
                          <span className="font-semibold text-slate-700">{yuan(item.coach_fee.amount)}</span>
                          <div className="table-secondary">{item.coach_fee.status === "settled" ? "已结算" : "待结算"}</div>
                        </div>
                      ) : item.status === "scheduled" ? (
                        <span className="text-xs text-slate-500">预计 {yuan(detail.coach_fee_per_session)}</span>
                      ) : (
                        <span className="text-xs text-slate-400">未生成</span>
                      )}
                    </td>
                    <td>
                      {item.status === "scheduled" ? (
                        <div className="flex flex-wrap gap-3">
                          <button className="text-xs font-semibold text-emerald-700" onClick={() => setAttendanceSession(item.id)} type="button">完成考勤</button>
                          <SessionTimeEditor session={item} onDone={() => void query.refetch()} />
                          <CancelReplaceDialog
                            sessionId={item.id}
                            version={item.version}
                            scheduledStart={item.scheduled_start}
                            scheduledEnd={item.scheduled_end}
                            onDone={() => void query.refetch()}
                          />
                        </div>
                      ) : item.status === "cancelled" && item.replacement_decision === "pending" ? (
                        <CancelReplaceDialog
                          sessionId={item.id}
                          version={item.version}
                          scheduledStart={item.scheduled_start}
                          scheduledEnd={item.scheduled_end}
                          mode="replacement"
                          onDone={() => void query.refetch()}
                        />
                      ) : item.status === "completed" && item.attendance.length ? (
                        <button
                          className="text-xs font-semibold text-emerald-700"
                          onClick={() => setAttendanceResultSession(item.id)}
                          type="button"
                        >
                          查看考勤（{item.attendance.length}人）
                        </button>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <EmptyState />}
        </Panel>

        <Panel
          title="报名与收费"
          description={`${detail.enrollments.length} 人在班 · 请从学员档案绑定固定班权益完成报名`}
        >
          {detail.enrollments.length ? (
            <div className="divide-y divide-slate-100">
              {detail.enrollments.map((item, index) => (
                <div className="grid grid-cols-[36px_minmax(120px,1fr)_140px_80px] items-center gap-3 px-4 py-3" key={item.id}>
                  <span className="grid size-8 place-items-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600">{index + 1}</span>
                  <div className="min-w-0">
                    <div className="truncate text-xs font-semibold text-slate-700">{item.student_name}</div>
                    <div className="mt-0.5 text-[11px] text-slate-400">购买权益 {item.purchased_units} 节</div>
                  </div>
                  {item.finance ? (
                    <div className="text-[11px] text-slate-500">
                      <div>应收 {yuan(item.finance.actual_amount)}</div>
                      <div>净实收 {yuan(item.finance.net_received)}</div>
                      <div className={item.finance.outstanding_amount > 0 ? "font-semibold text-amber-700" : ""}>
                        欠费 {yuan(item.finance.outstanding_amount)}
                      </div>
                    </div>
                  ) : <span className="text-[11px] text-red-600">应收未初始化</span>}
                  <div className="grid justify-items-end gap-2">
                    <StatusBadge status={item.finance?.payment_status ?? item.status} />
                    {item.finance && (
                      <button
                        className="text-xs font-semibold text-emerald-700"
                        onClick={() => setSelectedReceivable(item.finance?.receivable_id ?? null)}
                        type="button"
                      >
                        收费/流水
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState title="尚未报名" description="请在学员档案中新增学员并绑定该固定班权益。" />}
        </Panel>
      </div>
      <Drawer
        open={attendanceSession !== null}
        title="完成课程考勤"
        description="请假时可选择不扣课时，余额将继续保留在该培训权益中"
        onClose={() => setAttendanceSession(null)}
      >
        {attendanceSession && (
          <AttendancePanel
            sessionId={attendanceSession}
            enrollments={detail.enrollments.filter((item) => item.status === "active")}
            onDone={() => {
              setAttendanceSession(null);
              void query.refetch();
            }}
          />
        )}
      </Drawer>
      <Drawer
        open={attendanceResultSession !== null}
        title="课程考勤结果"
        description={
          attendanceResult
            ? `第 ${attendanceResult.sequence_number} 节 · ${new Date(attendanceResult.scheduled_start).toLocaleString("zh-CN")}`
            : "查看已完成课程的学员考勤与课时处理"
        }
        onClose={() => setAttendanceResultSession(null)}
      >
        {attendanceResult?.attendance.length ? (
          <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {attendanceResult.attendance.map((record) => (
              <div
                className="grid grid-cols-[minmax(120px,1fr)_100px_minmax(140px,auto)] items-center gap-3 px-4 py-3"
                key={record.id}
              >
                <div>
                  <div className="text-sm font-semibold text-slate-700">{record.student_name}</div>
                  {record.decision_note ? (
                    <div className="mt-0.5 text-xs text-slate-400">{record.decision_note}</div>
                  ) : null}
                </div>
                <span className="text-xs text-slate-600">
                  {record.status === "present"
                    ? "正常出勤"
                    : record.status === "leave"
                      ? "请假"
                      : record.status === "absent"
                        ? "缺席"
                        : record.status}
                </span>
                <div className="flex flex-wrap justify-end gap-1.5 text-[11px]">
                  <span className="rounded bg-slate-100 px-2 py-1 text-slate-600">
                    {record.deduct_units ? `扣 ${record.deduct_units} 课时` : "未扣课时"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="暂无考勤结果" description="这节课程尚未保存学员考勤明细。" />
        )}
      </Drawer>
      <Drawer
        open={selectedReceivable !== null}
        title="报名收费与流水"
        description="登记历史或当前收款，并查看退款与凭证"
        onClose={() => setSelectedReceivable(null)}
      >
        {selectedReceivable && (
          <ReceivableDetail
            receivableId={selectedReceivable}
            onChanged={() => void query.refetch()}
          />
        )}
      </Drawer>
    </section>
  );
}
