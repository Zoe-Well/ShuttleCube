import { type FormEvent, useState } from "react";

import { api } from "@/api/client";
import { beijingDateTimeInputToIso } from "@/lib/beijing-time";

export function PackageRenewalForm({
  studentId,
  studentName,
  coachId,
  coachName,
  defaultUnitPrice,
  onDone,
}: {
  studentId: string;
  studentName: string;
  coachId: string;
  coachName: string;
  defaultUnitPrice: number;
  onDone: () => void;
}) {
  const [units, setUnits] = useState(10);
  const [unitPrice, setUnitPrice] = useState(defaultUnitPrice);
  const [actualReceivable, setActualReceivable] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/private-packages", {
        method: "POST",
        body: JSON.stringify({
          student_id: studentId,
          bound_coach_id: coachId,
          purchased_units: units,
          unit_price: unitPrice,
          actual_receivable: actualReceivable === "" ? undefined : Number(actualReceivable),
          valid_until: validUntil ? beijingDateTimeInputToIso(`${validUntil}T23:59:59`) : undefined,
          notes: notes.trim() || undefined,
        }),
      });
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新课包创建失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
      <div className="grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-4 text-sm">
        <div><span className="text-xs text-slate-500">学员</span><strong className="mt-1 block">{studentName}</strong></div>
        <div><span className="text-xs text-slate-500">教练</span><strong className="mt-1 block">{coachName}</strong></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="field-label">新购课时<input className="field" min="1" type="number" value={units} onChange={(event) => setUnits(Number(event.target.value))} required /></label>
        <label className="field-label">课时单价<input className="field" min="0" step="0.01" type="number" value={unitPrice} onChange={(event) => setUnitPrice(Number(event.target.value))} required /></label>
      </div>
      <label className="field-label">实际应收<span className="field-hint">不填则按课时 × 单价</span><input className="field" min="0" placeholder={(units * unitPrice).toFixed(2)} step="0.01" type="number" value={actualReceivable} onChange={(event) => setActualReceivable(event.target.value)} /></label>
      <label className="field-label">新课包有效期<input className="field" type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} /></label>
      <label className="field-label">备注<textarea className="field" value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
      {error ? <p className="text-xs text-red-600" role="alert">{error}</p> : null}
      <button className="btn btn-primary" disabled={saving}>{saving ? "正在创建…" : "确认创建续费课包"}</button>
    </form>
  );
}
