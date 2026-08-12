import { Archive, CalendarPlus, UsersRound } from "lucide-react";
import { type FormEvent, useState } from "react";

import { api } from "@/api/client";
import { Drawer } from "@/components/operations/drawer";
import { FixedClassRenewalForm } from "./fixed-class-renewal-form";

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
  const [error, setError] = useState("");

  const close = () => {
    setMode(null);
    setError("");
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
        {mode === "renew" ? (
          <FixedClassRenewalForm
            classId={classId}
            version={version}
            enrollments={enrollments}
            onCancel={close}
            onDone={() => {
              close();
              onDone();
            }}
          />
        ) : (
          <form className="grid gap-4" onSubmit={(event) => void run(event)}>
          {mode === "capacity" ? (
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
        )}
      </Drawer>
    </>
  );
}
