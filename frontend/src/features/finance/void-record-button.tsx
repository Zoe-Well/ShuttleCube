import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";

export function VoidRecordButton({
  endpoint,
  label = "作废",
  onVoided,
}: {
  endpoint: string;
  label?: string;
  onVoided?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: (reason: string) =>
      api(endpoint, { method: "POST", body: JSON.stringify({ reason }) }),
    onSuccess: () => {
      setOpen(false);
      onVoided?.();
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    mutation.mutate(String(data.get("reason")));
  };

  return (
    <>
      <button
        className="text-xs font-semibold text-red-600"
        type="button"
        onClick={() => setOpen(true)}
      >
        {label}
      </button>
      {open ? (
        <div
          aria-label={`${label}资金记录`}
          className="fixed inset-0 z-[70] grid place-items-center bg-slate-950/30"
          role="dialog"
        >
          <form className="panel w-[420px] p-5" onSubmit={submit}>
            <h3 className="text-base font-semibold">{label}资金记录</h3>
            <p className="mt-1 text-xs text-slate-500">
              原记录仍会保留；作废后不再计入有效资金汇总。
            </p>
            <label className="mt-4 block text-xs font-medium">
              作废原因
              <textarea className="field mt-1" name="reason" required />
            </label>
            {mutation.error ? (
              <p className="mt-3 text-xs text-red-600" role="alert">
                {mutation.error.message}
              </p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button className="btn" type="button" onClick={() => setOpen(false)}>
                取消
              </button>
              <button className="btn btn-primary" disabled={mutation.isPending}>
                确认作废
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
