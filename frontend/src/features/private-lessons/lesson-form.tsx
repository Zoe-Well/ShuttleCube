import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

import {
  HourDateTimeField,
  type ConfirmedScheduleInput,
} from "@/features/schedule/schedule-time-fields";
import type { ScheduleWarningCode, VenueHours } from "@/features/schedule/schedule-time";
import { useScheduleTimeConfirmation } from "@/features/schedule/use-schedule-time-confirmation";
import { CourtFormField } from "@/features/schedule/court-form-field";
import type { CourtItem } from "@/features/schedule/court-schedule-grid";

export type LessonInput = {
  student_id: string;
  coach_id: string;
  package_id?: string;
  billing_mode: string;
  starts_at: string;
  ends_at: string;
  court_ids: string;
  actual_receivable: number;
  coach_fee: number;
};

type Student = { id: string; name: string };
type Coach = { id: string; name: string; private_lesson_fee?: number };
type Package = { id: string; student_id: string; student_name: string; bound_coach_id: string; coach_name: string; remaining_units: number; status: string; valid_until?: string | null };

export function LessonForm({
  onSubmit,
  initialValues,
  venue,
  courts,
  initialWarningAcknowledgements = [],
}: {
  onSubmit: (value: ConfirmedScheduleInput<LessonInput>) => void;
  initialValues?: Partial<LessonInput>;
  venue?: VenueHours;
  courts: CourtItem[];
  initialWarningAcknowledgements?: ScheduleWarningCode[];
}) {
  const {
    clearErrors,
    formState: { errors },
    handleSubmit,
    register,
    setValue,
    watch,
  } = useForm<LessonInput>({
    defaultValues: {
      billing_mode: "package",
      actual_receivable: 0,
      coach_fee: 0,
      ...initialValues,
    },
  });
  const billingMode = watch("billing_mode");
  const studentId = watch("student_id");
  const coachId = watch("coach_id");
  const packageId = watch("package_id");
  const selectedCourts = watch("court_ids") ?? "";
  const time = useScheduleTimeConfirmation(onSubmit, venue, initialWarningAcknowledgements);
  const students = useQuery({ queryKey: ["students"], queryFn: () => api<{items:Student[]}>("/students") });
  const coaches = useQuery({ queryKey: ["coaches"], queryFn: () => api<Coach[]>("/coaches") });
  const packages = useQuery({ queryKey: ["private-packages"], queryFn: () => api<Package[]>("/private-packages") });
  const eligiblePackages = (packages.data ?? []).filter((item) => item.status === "active" && item.remaining_units > 0 && (!studentId || item.student_id === studentId) && (!coachId || item.bound_coach_id === coachId));

  useEffect(() => {
    if (billingMode !== "package") {
      clearErrors("package_id");
      setValue("package_id", "");
    }
  }, [billingMode, clearErrors, setValue]);

  useEffect(() => {
    if (!packageId) return;
    const selected = packages.data?.find((item) => item.id === packageId);
    if (selected) {
      setValue("student_id", selected.student_id);
      setValue("coach_id", selected.bound_coach_id);
    }
  }, [packageId, packages.data, setValue]);

  useEffect(() => {
    const selected = coaches.data?.find((item) => item.id === coachId);
    if (selected) setValue("coach_fee", Number(selected.private_lesson_fee ?? 0));
  }, [coachId, coaches.data, setValue]);

  return (
    <form className="grid gap-4" onSubmit={handleSubmit(time.submit)}>
      <div className="grid grid-cols-2 gap-4">
        <label className="field-label">
          学员
          <select className="field" {...register("student_id", { required: true })}><option value="">请选择学员</option>{students.data?.items.map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        </label>
        <label className="field-label">
          教练
          <select className="field" {...register("coach_id", { required: true })}><option value="">请选择教练</option>{coaches.data?.map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        </label>
        <label className="field-label">
          结算方式
          <select className="field" {...register("billing_mode")}>
            <option value="package">课包扣课</option>
            <option value="single">单次结算</option>
          </select>
        </label>
        <label className="field-label">
          关联课包
          <span className="field-hint">
            {billingMode === "package" ? "必选" : "单次结算可留空"}
          </span>
          <select
            aria-invalid={Boolean(errors.package_id)}
            className="field"
            disabled={billingMode !== "package"}
            {...register("package_id", {
              validate: (value) =>
                billingMode !== "package" ||
                Boolean(value?.trim()) ||
                "课包扣课模式下必须选择关联课包",
            })}
          ><option value="">请选择已有课包</option>{eligiblePackages.map((item)=><option key={item.id} value={item.id}>{item.student_name} · {item.coach_name} · 剩余 {item.remaining_units} 节</option>)}</select>
          {errors.package_id && (
            <span className="text-xs font-medium text-red-600" role="alert">
              {errors.package_id.message}
            </span>
          )}
        </label>
        <HourDateTimeField label="开始时间" {...register("starts_at", { required: true })} />
        <HourDateTimeField label="结束时间" {...register("ends_at", { required: true })} />
        <CourtFormField courts={courts} locked={Boolean(initialValues?.court_ids)} value={selectedCourts} onChange={(value) => setValue("court_ids", value, { shouldValidate: true })} />
        <input type="hidden" {...register("court_ids", { required: true })} />
        <label className="field-label">
          教练费
          <input
            className="field"
            min="0"
            step="0.01"
            type="number"
            {...register("coach_fee", { valueAsNumber: true })}
          />
          <span className="field-hint">自动带出教练当前标准，本次预约可单独调整</span>
        </label>
        {billingMode === "single" && <label className="field-label">本次应收<input className="field" min="0" step="0.01" type="number" {...register("actual_receivable", { valueAsNumber: true })}/></label>}
      </div>
      {time.feedback}
      <footer className="flex justify-end border-t border-slate-200 pt-4">
        <button className="btn btn-primary">预约私教</button>
      </footer>
      {time.dialog}
    </form>
  );
}
