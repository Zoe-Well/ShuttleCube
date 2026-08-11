import { useRef, useState } from "react";
import { useForm } from "react-hook-form";

import {
  HourDateTimeField,
  TimeValidationAlert,
  type ConfirmedScheduleInput,
} from "@/features/schedule/schedule-time-fields";
import { analyzeScheduleTime, type ScheduleWarningCode, type VenueHours } from "@/features/schedule/schedule-time";
import { useScheduleTimeConfirmation } from "@/features/schedule/use-schedule-time-confirmation";
import { CourtFormField } from "@/features/schedule/court-form-field";
import type { CourtItem } from "@/features/schedule/court-schedule-grid";

export type BookingInput = {
  customer_name: string;
  customer_phone?: string;
  starts_at: string;
  ends_at: string;
  court_ids: string;
  actual_receivable?: number;
  price_adjustment_reason?: string;
};

export function BookingForm({
  onQuote,
  onSubmit,
  initialValues,
  venue,
  courts,
  initialWarningAcknowledgements = [],
}: {
  onQuote: (value: BookingInput) => Promise<number>;
  onSubmit: (value: ConfirmedScheduleInput<BookingInput>) => void;
  initialValues?: Partial<BookingInput>;
  venue?: VenueHours;
  courts: CourtItem[];
  initialWarningAcknowledgements?: ScheduleWarningCode[];
}) {
  const { register, handleSubmit, getValues, setValue, watch } = useForm<BookingInput>({ defaultValues: initialValues });
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const lastSuggested = useRef<number | null>(null);
  const time = useScheduleTimeConfirmation(onSubmit, venue, initialWarningAcknowledgements);
  const selectedCourts = watch("court_ids") ?? "";
  const quote = async () => {
    const value = getValues();
    const analysis = analyzeScheduleTime(value.starts_at, value.ends_at, venue);
    setQuoteError(analysis.error);
    if (analysis.error) return;
    try {
      const suggested = await onQuote(value);
      if (!Number.isFinite(value.actual_receivable) || value.actual_receivable === lastSuggested.current) {
        setValue("actual_receivable", suggested);
      }
      lastSuggested.current = suggested;
      setQuoteError(null);
    } catch (caught) {
      setQuoteError(caught instanceof Error ? caught.message : "默认价格计算失败");
    }
  };

  return (
    <form className="grid gap-4" onSubmit={handleSubmit(time.submit)}>
      <div className="grid grid-cols-2 gap-4">
        <label className="field-label">
          客户姓名
          <input className="field" placeholder="散客姓名" {...register("customer_name", { required: true })} />
        </label>
        <label className="field-label">
          联系电话
          <input className="field" placeholder="手机号" {...register("customer_phone")} />
        </label>
        <HourDateTimeField label="开始时间" {...register("starts_at", { required: true })} />
        <HourDateTimeField label="结束时间" {...register("ends_at", { required: true })} />
        <div className="col-span-2"><CourtFormField courts={courts} label="使用场地" locked={Boolean(initialValues?.court_ids)} value={selectedCourts} onChange={(value) => setValue("court_ids", value, { shouldValidate: true })} /></div>
        <input type="hidden" {...register("court_ids", { required: true })} />
        <label className="field-label">
          实际应收 <span className="field-hint">留空使用建议金额</span>
          <input className="field" type="number" placeholder="¥ 0.00" {...register("actual_receivable", { valueAsNumber: true })} />
        </label>
        <label className="field-label">
          调价原因
          <input className="field" placeholder="实际金额变化时填写" {...register("price_adjustment_reason")} />
        </label>
      </div>
      <TimeValidationAlert message={quoteError} />
      {time.feedback}
      <footer className="flex justify-end gap-2 border-t border-slate-200 pt-4">
        <button type="button" className="btn" onClick={() => void quote()}>计算建议金额</button>
        <button className="btn btn-primary">确认订场</button>
      </footer>
      {time.dialog}
    </form>
  );
}
