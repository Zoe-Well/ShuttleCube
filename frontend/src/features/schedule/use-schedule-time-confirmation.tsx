import { useState } from "react";

import {
  TimeValidationAlert,
  TimeWarningDialog,
  type ConfirmedScheduleInput,
  type TimeBoundInput,
} from "./schedule-time-fields";
import {
  analyzeScheduleTime,
  defaultVenueHours,
  type ScheduleWarningCode,
  type ScheduleTimeWarning,
  type VenueHours,
} from "./schedule-time";

export function useScheduleTimeConfirmation<T extends TimeBoundInput>(
  onConfirmed: (value: ConfirmedScheduleInput<T>) => void | Promise<void>,
  venue: VenueHours = defaultVenueHours,
  initialAcknowledgements: ScheduleWarningCode[] = [],
) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ value: T; warnings: ScheduleTimeWarning[] } | null>(null);

  const submit = (value: T) => {
    const analysis = analyzeScheduleTime(value.starts_at, value.ends_at, venue);
    setError(analysis.error);
    if (analysis.error) return;
    const warnings = analysis.warnings.filter(
      (warning) => !initialAcknowledgements.includes(warning.code),
    );
    if (warnings.length) {
      setPending({ value, warnings });
      return;
    }
    void onConfirmed({ ...value, warning_acknowledgements: initialAcknowledgements });
  };

  const feedback = <TimeValidationAlert message={error} />;
  const dialog = pending ? <TimeWarningDialog warnings={pending.warnings} onCancel={() => setPending(null)} onConfirm={() => {
    const current = pending;
    setPending(null);
    void onConfirmed({
      ...current.value,
      warning_acknowledgements: [
        ...new Set([
          ...initialAcknowledgements,
          ...current.warnings.map((warning) => warning.code),
        ]),
      ],
    });
  }}/> : null;

  return { submit, feedback, dialog, setError };
}
