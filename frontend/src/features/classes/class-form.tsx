import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { api } from "@/api/client";

export type ClassInput = {
  name: string;
  class_type: string;
  start_date: string;
  default_start_time: string;
  duration_minutes: number;
  session_count: number;
  capacity: number;
  default_coach_id: string;
  court_ids: string[];
  required_court_count: number;
  student_unit_price: number;
  coach_fee_per_session: number;
};

type Coach = { id: string; name: string; is_active?: boolean; fixed_class_fee: number };
type Court = { id: string; code: string; name: string; is_active: boolean };

export function ClassForm({ onSubmit }: { onSubmit: (value: ClassInput) => void }) {
  const { handleSubmit, register, setValue } = useForm<ClassInput>({
    defaultValues: {
      class_type: "training",
      duration_minutes: 120,
      session_count: 12,
      capacity: 12,
      required_court_count: 1,
      student_unit_price: 100,
      coach_fee_per_session: 0,
      court_ids: [],
    },
  });
  const coaches = useQuery({
    queryKey: ["coaches"],
    queryFn: () => api<Coach[]>("/coaches"),
  });
  const courts = useQuery({
    queryKey: ["courts"],
    queryFn: () => api<Court[]>("/courts"),
  });
  const coachField = register("default_coach_id", { required: true });

  return (
    <form className="grid gap-5" onSubmit={handleSubmit(onSubmit)}>
      <div className="grid grid-cols-2 gap-4">
        <label className="field-label col-span-2">
          班级名称
          <input className="field" placeholder="例如：周六青少年进阶班" {...register("name", { required: true })} />
        </label>
        <label className="field-label">
          开班日期
          <input className="field" type="date" {...register("start_date", { required: true })} />
        </label>
        <label className="field-label">
          每周上课时间
          <input className="field" type="time" step="3600" {...register("default_start_time", { required: true })} />
          <span className="field-hint">按整点选择</span>
        </label>
        <label className="field-label">
          单节时长（分钟）
          <input className="field" type="number" min="60" step="60" {...register("duration_minutes", { valueAsNumber: true })} />
        </label>
        <label className="field-label">
          计划课次
          <input className="field" type="number" {...register("session_count", { valueAsNumber: true })} />
        </label>
        <label className="field-label">
          班级容量
          <input className="field" type="number" {...register("capacity", { valueAsNumber: true })} />
        </label>
        <label className="field-label">
          学员单价
          <input className="field" type="number" min="0" step="0.01" {...register("student_unit_price", { valueAsNumber: true })} />
        </label>
        <label className="field-label">
          授课教练
          <select
            className="field"
            {...coachField}
            onChange={(event) => {
              const selectedCoachId = event.target.value;
              void coachField.onChange(event);
              const coach = coaches.data?.find((item) => item.id === selectedCoachId);
              setValue("coach_fee_per_session", Number(coach?.fixed_class_fee ?? 0), {
                shouldDirty: true,
              });
            }}
          >
            <option value="">请选择系统教练</option>
            {coaches.data?.filter((item) => item.is_active !== false).map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
        </label>
        <label className="field-label">
          单节教练费
          <input className="field" type="number" min="0" step="0.01" {...register("coach_fee_per_session", { valueAsNumber: true, min: 0 })} />
          <span className="field-hint">选择教练后自动带出当前标准，可为本班单独调整</span>
        </label>
        <label className="field-label col-span-2">
          使用场地
          <span className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 bg-white p-3">
            {courts.data?.filter((item) => item.is_active).map((court) => (
              <label className="flex items-center gap-2 text-sm font-normal text-slate-700" key={court.id}>
                <input
                  className="size-4 accent-emerald-600"
                  type="checkbox"
                  value={court.id}
                  {...register("court_ids", { required: true })}
                />
                {court.name}
              </label>
            ))}
          </span>
          <span className="field-hint">勾选几片场地，本班每节课就会同时占用几片场地</span>
        </label>
      </div>
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-500">
        教练费会冻结为本班单节标准；只有课程完成考勤后才逐节生成待结费用。
      </div>
      <footer className="flex justify-end border-t border-slate-200 pt-4">
        <button className="btn btn-primary">创建并生成课程</button>
      </footer>
    </form>
  );
}
