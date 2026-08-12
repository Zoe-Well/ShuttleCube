import { type FormEvent, useMemo, useState } from "react";

import { api } from "@/api/client";

export type RenewalEnrollment = {
  id: string;
  student_name: string;
  unit_price: number | string;
  status: string;
};

export function FixedClassRenewalForm({
  classId,
  version,
  enrollments,
  onDone,
  onCancel,
}: {
  classId: string;
  version: number;
  enrollments: RenewalEnrollment[];
  onDone: () => void;
  onCancel?: () => void;
}) {
  const [additionalSessions, setAdditionalSessions] = useState(4);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const activeEnrollments = useMemo(
    () => enrollments.filter((item) => item.status === "active"),
    [enrollments],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError("");
    setSaving(true);
    try {
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
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "续期保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
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
                    <input className="field" aria-label={`${item.student_name}增加课时`} defaultValue={additionalSessions} min="1" name={`units-${item.id}`} type="number" required />
                    <input className="field" aria-label={`${item.student_name}增加应收`} defaultValue={(Number(item.unit_price) * additionalSessions).toFixed(2)} min="0" name={`amount-${item.id}`} step="0.01" type="number" required />
                    <input className="field" aria-label={`${item.student_name}调价原因`} name={`reason-${item.id}`} placeholder="调价时填写原因" />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
      {error ? <p className="text-xs text-red-600" role="alert">{error}</p> : null}
      <div className="flex justify-end gap-2">
        {onCancel ? <button className="btn" onClick={onCancel} type="button">返回</button> : null}
        <button className="btn btn-primary" disabled={saving}>{saving ? "正在保存…" : "确认续期"}</button>
      </div>
    </form>
  );
}
