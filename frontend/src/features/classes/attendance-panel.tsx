import { useState } from "react";

import { api } from "@/api/client";

type Enrollment = { id: string; student_id: string; student_name?: string };

export function AttendancePanel({
  sessionId,
  enrollments,
  onDone,
}: {
  sessionId: string;
  enrollments: Enrollment[];
  onDone: () => void;
}) {
  const [rows, setRows] = useState(
    enrollments.map((enrollment) => ({
      ...enrollment,
      status: "present",
      deduct_units: 1,
    })),
  );
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      await api(`/class-sessions/${sessionId}/attendance:finalize`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          decisions: rows.map((row) => ({
            enrollment_id: row.id,
            student_id: row.student_id,
            status: row.status,
            deduct_units: row.deduct_units,
          })),
        }),
      });
      onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "考勤提交失败");
    }
  }

  return (
    <div className="grid gap-3">
      <p className="text-xs text-slate-500">
        请假且不扣课时会保留剩余课时，之后可用于原班续期课程或转移到其他班级。
      </p>
      {rows.map((row, index) => (
        <div
          className="grid grid-cols-[minmax(120px,1fr)_140px_120px] items-center gap-3 rounded-lg bg-zinc-50 p-3"
          key={row.id}
        >
          <span className="text-sm font-medium">{row.student_name ?? row.student_id}</span>
          <select
            aria-label={`${row.student_name ?? row.student_id}出勤状态`}
            className="field"
            value={row.status}
            onChange={(event) =>
              setRows((current) =>
                current.map((item, itemIndex) =>
                  itemIndex === index ? { ...item, status: event.target.value } : item,
                ),
              )
            }
          >
            <option value="present">正常出勤</option>
            <option value="leave">请假</option>
            <option value="absent">缺席</option>
          </select>
          <label className="text-xs">
            <input
              checked={row.deduct_units === 1}
              onChange={(event) =>
                setRows((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index
                      ? { ...item, deduct_units: event.target.checked ? 1 : 0 }
                      : item,
                  ),
                )
              }
              type="checkbox"
            />{" "}
            扣本节课时
          </label>
        </div>
      ))}
      {error ? <p className="text-xs text-red-600" role="alert">{error}</p> : null}
      <button
        className="btn btn-primary"
        disabled={!rows.length}
        onClick={() => void submit()}
        type="button"
      >
        完成考勤并生成教练费用
      </button>
    </div>
  );
}
