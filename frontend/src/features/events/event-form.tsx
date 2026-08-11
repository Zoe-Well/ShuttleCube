import { useForm } from "react-hook-form";

import {
  HourDateTimeField,
  type ConfirmedScheduleInput,
} from "@/features/schedule/schedule-time-fields";
import type { ScheduleWarningCode, VenueHours } from "@/features/schedule/schedule-time";
import { useScheduleTimeConfirmation } from "@/features/schedule/use-schedule-time-confirmation";
import { CourtFormField } from "@/features/schedule/court-form-field";
import type { CourtItem } from "@/features/schedule/court-schedule-grid";

export type EventFormInput = {
  event_type: string;
  name: string;
  starts_at: string;
  ends_at: string;
  court_ids: string;
  coach_id?: string;
  actual_receivable: number;
  track_participants: boolean;
  requires_attendance: boolean;
  participant_ids: string;
};

export function EventForm({
  onSubmit,
  initialValues,
  venue,
  courts,
  initialWarningAcknowledgements = [],
}: {
  onSubmit: (value: ConfirmedScheduleInput<EventFormInput>) => void;
  initialValues?: Partial<EventFormInput>;
  venue?: VenueHours;
  courts: CourtItem[];
  initialWarningAcknowledgements?: ScheduleWarningCode[];
}) {
  const { register, handleSubmit, setValue, watch } = useForm<EventFormInput>({
    defaultValues: {
      event_type: "experience",
      name: "临时活动",
      actual_receivable: 0,
      track_participants: false,
      requires_attendance: false,
      ...initialValues,
    },
  });
  const time = useScheduleTimeConfirmation(onSubmit, venue, initialWarningAcknowledgements);
  const selectedCourts = watch("court_ids") ?? "";

  return (
    <form className="grid gap-4" onSubmit={handleSubmit(time.submit)}>
      <div className="grid grid-cols-2 gap-4">
        <label className="field-label col-span-2">
          活动名称
          <input className="field" placeholder="例如：暑期青少年体验课" {...register("name", { required: true })} />
        </label>
        <label className="field-label">
          活动类型
          <select className="field" {...register("event_type")}>
            <option value="experience">体验课</option>
            <option value="camp">集训</option>
            <option value="competition">比赛</option>
            <option value="exclusive">包场</option>
          </select>
        </label>
        <CourtFormField courts={courts} locked={Boolean(initialValues?.court_ids)} value={selectedCourts} onChange={(value) => setValue("court_ids", value, { shouldValidate: true })} />
        <input type="hidden" {...register("court_ids", { required: true })} />
        <HourDateTimeField label="开始时间" {...register("starts_at", { required: true })} />
        <HourDateTimeField label="结束时间" {...register("ends_at", { required: true })} />
        <label className="field-label col-span-2">
          负责教练 <span className="field-hint">可选</span>
          <input className="field" placeholder="搜索教练" {...register("coach_id")} />
        </label>
      </div>
      <div className="grid grid-cols-2 gap-3 rounded-md border border-slate-200 bg-slate-50 p-3">
        <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
          <input type="checkbox" {...register("track_participants")} />记录参与人员
        </label>
        <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
          <input type="checkbox" {...register("requires_attendance")} />活动需要考勤
        </label>
      </div>
      <label className="field-label">
        参与学员 <span className="field-hint">多人可用逗号分隔</span>
        <textarea className="field" placeholder="搜索或输入学员" {...register("participant_ids")} />
      </label>
      {time.feedback}
      <footer className="flex justify-end border-t border-slate-200 pt-4">
        <button className="btn btn-primary">创建活动</button>
      </footer>
      {time.dialog}
    </form>
  );
}
