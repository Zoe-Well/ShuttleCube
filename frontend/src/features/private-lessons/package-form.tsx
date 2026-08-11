import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { api } from "@/api/client";

type Input = {
  student_id: string;
  bound_coach_id: string;
  purchased_units: number;
  unit_price: number;
  actual_receivable?: number;
};
type Student = { id: string; name: string; phone?: string; is_active: boolean };
type Coach = { id: string; name: string; is_active: boolean };

export function PackageForm({ onSubmit }: { onSubmit: (value: Input) => void }) {
  const { register, handleSubmit } = useForm<Input>({
    defaultValues: { purchased_units: 10, unit_price: 300 },
  });
  const students = useQuery({
    queryKey: ["students"],
    queryFn: () => api<{ items: Student[] }>("/students"),
  });
  const coaches = useQuery({ queryKey: ["coaches"], queryFn: () => api<Coach[]>("/coaches") });
  const activeStudents = (students.data?.items ?? []).filter((item) => item.is_active !== false);
  const activeCoaches = (coaches.data ?? []).filter((item) => item.is_active !== false);
  const unavailable =
    students.isLoading ||
    coaches.isLoading ||
    activeStudents.length === 0 ||
    activeCoaches.length === 0;

  return (
    <form className="grid gap-4" onSubmit={handleSubmit(onSubmit)}>
      <label className="field-label">
        学员
        <select className="field" defaultValue="" {...register("student_id", { required: true })}>
          <option value="" disabled>
            {students.isLoading ? "正在加载学员…" : "请选择系统学员"}
          </option>
          {activeStudents.map((student) => (
            <option key={student.id} value={student.id}>
              {student.name}
              {student.phone ? ` · ${student.phone}` : ""}
            </option>
          ))}
        </select>
        {!students.isLoading && activeStudents.length === 0 ? (
          <span className="field-hint">请先在学员档案中新增并启用学员</span>
        ) : null}
      </label>
      <label className="field-label">
        绑定教练
        <select
          className="field"
          defaultValue=""
          {...register("bound_coach_id", { required: true })}
        >
          <option value="" disabled>
            {coaches.isLoading ? "正在加载教练…" : "请选择有效教练"}
          </option>
          {activeCoaches.map((coach) => (
            <option key={coach.id} value={coach.id}>
              {coach.name}
            </option>
          ))}
        </select>
        {!coaches.isLoading && activeCoaches.length === 0 ? (
          <span className="field-hint">请先在教练管理中新增并启用教练</span>
        ) : null}
      </label>
      <div className="grid grid-cols-2 gap-4">
        <label className="field-label">
          购买课时
          <input
            className="field"
            type="number"
            min={1}
            {...register("purchased_units", { required: true, valueAsNumber: true, min: 1 })}
          />
        </label>
        <label className="field-label">
          课时单价
          <input
            className="field"
            type="number"
            min={0}
            step="0.01"
            {...register("unit_price", { required: true, valueAsNumber: true, min: 0 })}
          />
        </label>
      </div>
      <label className="field-label">
        实际应收 <span className="field-hint">不填则按课时 × 单价</span>
        <input
          className="field"
          type="number"
          min={0}
          step="0.01"
          placeholder="自动计算"
          {...register("actual_receivable", {
            setValueAs: (value) => (value === "" ? undefined : Number(value)),
          })}
        />
      </label>
      <footer className="flex justify-end border-t border-slate-200 pt-4">
        <button className="btn btn-primary" disabled={unavailable}>
          创建私教课包
        </button>
      </footer>
    </form>
  );
}
