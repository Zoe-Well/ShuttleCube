import { Archive, CalendarPlus, UsersRound } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";

type Enrollment = {
  id: string;
  student_name: string;
  unit_price: number;
  status: string;
};

export function ClassManagementActions({
  classId,
  version,
  capacity,
  status,
  enrollments,
  onDone,
}: {
  classId: string;
  version: number;
  capacity: number;
  status: string;
  enrollments: Enrollment[];
  onDone: () => void;
}) {
  const [mode, setMode] = useState<"renew" | "capacity" | "archive" | null>(null);
  const [additionalSessions, setAdditionalSessions] = useState(4);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const activeEnrollments = useMemo(
    () => enrollments.filter((item) => item.status === "active"),
    [enrollments],
  );

  const close = () => {
    setMode(null);
    setError("");
    setSelected(new Set());
  };
  const run = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError("");
    try {
      if (mode === "capacity") {
        await api(`/classes/${classId}/capacity`, {
          method: "PATCH",
          body: JSON.stringify({ capacity: Number(data.get("capacity")), version }),
        });
      } else if (mode === "archive") {
        await api(`/classes/${classId}/archive`, {
          method: "POST",
          body: JSON.stringify({ reason: String(data.get("reason")), version }),
        });
      } else if (mode === "renew") {
        await api(`/classes/${classId}/renew`, {
          method: "POST",
          body: JSON.stringify({
            additional_sessions: additionalSessions,
            version,
            enrollment_renewals: activeEnrollments
              .filter((item) => selected.has(item.id))
              .map((item) => ({
                enrollment_id: item.id,
                added_units: Number(data.get(`units-${item.id}`)),
                added_actual_amount: Number(data.get(`amount-${item.id}`)),
                adjustment_reason: String(data.get(`reason-${item.id}`) || "") || null,
              })),
          }),
        });
      }
      close();
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败");
    }
  };

  if (status === "archived") return null;
  return (
    <>
      <div className="flex gap-2">
        <button className="btn" onClick={() => setMode("renew")} type="button">
          <CalendarPlus size={14} /> 固定班续期
        </button>
        <button className="btn" onClick={() => setMode("capacity")} type="button">
          <UsersRound size={14} /> 修改容量
        </button>
        <button className="btn btn-danger" onClick={() => setMode("archive")} type="button">
          <Archive size={14} /> 归档
        </button>
      </div>
      <Drawer
        open={mode !== null}
        title={mode === "renew" ? "固定班续期" : mode === "capacity" ? "修改班级容量" : "归档固定班"}
        description={
          mode === "renew"
            ? "新增课程计划，并选择需要同步增加课时和应收的学员"
            : mode === "capacity"
              ? "新容量不能低于当前有效学员人数"
              : "归档后未来课程释放排期，学员权益失效但历史课时和财务保留"
        }
        onClose={close}
      >
        <form className="grid gap-4" onSubmit={(event) => void run(event)}>
          {mode === "renew" ? (
            <>
              <label className="field-label">
                新增课程数量
                <input
                  className="field"
                  min="1"
                  type="number"
                  value={additionalSessions}
                  onChange={(event) => setAdditionalSessions(Number(event.target.value))}
                  required
                />
              </label>
              <div>
                <div className="mb-2 text-xs font-semibold text-slate-700">同步续期学员（可不选择）</div>
                <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {activeEnrollments.map((item) => {
                    const checked = selected.has(item.id);
                    return (
                      <div className="grid gap-2 p-3" key={item.id}>
                        <label className="flex items-center gap-2 text-sm font-medium">
                          <input
                            checked={checked}
                            type="checkbox"
                            onChange={(event) =>
                              setSelected((current) => {
                                const next = new Set(current);
                                if (event.target.checked) next.add(item.id);
                                else next.delete(item.id);
                                return next;
                              })
                            }
                          />
                          {item.student_name}
                        </label>
                        {checked ? (
                          <div className="grid grid-cols-3 gap-2" key={`${item.id}-${additionalSessions}`}>
                            <input className="field" defaultValue={additionalSessions} min="1" name={`units-${item.id}`} type="number" required />
                            <input className="field" defaultValue={(item.unit_price * additionalSessions).toFixed(2)} min="0" name={`amount-${item.id}`} step="0.01" type="number" required />
                            <input className="field" name={`reason-${item.id}`} placeholder="调价时填写原因" />
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          ) : mode === "capacity" ? (
            <label className="field-label">
              班级最大人数
              <input className="field" defaultValue={capacity} min="1" name="capacity" type="number" required />
            </label>
          ) : (
            <label className="field-label">
              归档原因
              <textarea className="field" name="reason" required />
            </label>
          )}
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <button className="btn" onClick={close} type="button">返回</button>
            <button className={mode === "archive" ? "btn btn-danger" : "btn btn-primary"}>确认</button>
          </div>
        </form>
      </Drawer>
    </>
  );
}
