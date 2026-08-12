import { useState } from "react";

import { api } from "@/api/client";

export function NoEnrollmentSessionPanel({
  sessionId,
  version,
  onDone,
  compact = false,
}: {
  sessionId: string;
  version: number;
  onDone: () => void;
  compact?: boolean;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const markNotHeld = async () => {
    if (!window.confirm("确认本节课没有报名学员，并且没有实际开课吗？")) return;
    setSaving(true);
    setError("");
    try {
      await api(`/class-sessions/${sessionId}/no-enrollment:mark-not-held`, {
        method: "POST",
        body: JSON.stringify({ version }),
      });
      onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请刷新后重试");
    } finally {
      setSaving(false);
    }
  };

  if (compact) {
    return (
      <div>
        <button
          className="text-xs font-semibold text-amber-700"
          disabled={saving}
          onClick={() => void markNotHeld()}
          type="button"
        >
          {saving ? "正在处理…" : "标记未开课（无学员）"}
        </button>
        {error ? <p className="mt-1 max-w-52 text-xs text-red-600">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      <h3 className="text-sm font-semibold text-amber-900">本节课没有报名学员</h3>
      <p className="mt-1 text-xs leading-5 text-amber-800">
        无需填写考勤。如果课程确实没有开课，可将本节标记为未开课；系统会释放本节排期，不扣课时，也不会生成教练费用。
      </p>
      <button
        className="btn mt-3"
        disabled={saving}
        onClick={() => void markNotHeld()}
        type="button"
      >
        {saving ? "正在处理…" : "标记本节未开课（无学员）"}
      </button>
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
