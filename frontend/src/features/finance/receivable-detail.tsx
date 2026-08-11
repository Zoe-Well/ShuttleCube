import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { Panel } from "@/components/operations/page";
import { StatusBadge } from "@/components/status/status-badge";
import { AttachmentViewer } from "./attachment-viewer";
import { PaymentDialog } from "./payment-dialog";
import { RefundDialog } from "./refund-dialog";
import type { ReceivableDetail as Detail } from "./types";
import { paymentMethodName, sourceNames, yuan } from "./types";
import { VoidRecordButton } from "./void-record-button";

export function ReceivableDetail({
  receivableId,
  onChanged,
}: {
  receivableId: string;
  onChanged?: () => void;
}) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["receivable", receivableId],
    queryFn: () => api<Detail>(`/receivables/${receivableId}`),
  });
  const item = query.data;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["receivables"] });
    void client.invalidateQueries({ queryKey: ["receivable", receivableId] });
    onChanged?.();
  };
  if (!item) return <p className="p-4 text-sm text-slate-500">正在加载应收详情…</p>;
  return (
    <div className="grid gap-4">
      <Panel
        title={item.business_name ?? sourceNames[item.source_type] ?? item.source_type}
        description="业务应收、收款与退款明细"
      >
        <div className="grid grid-cols-3 gap-3 p-4 text-sm">
          <div>
            <span className="text-slate-400">实际应收</span>
            <b className="mt-1 block">{yuan(item.actual_amount)}</b>
          </div>
          <div>
            <span className="text-slate-400">净实收</span>
            <b className="mt-1 block">{yuan(item.net_received)}</b>
          </div>
          <div>
            <span className="text-slate-400">欠费</span>
            <b className="mt-1 block text-amber-700">{yuan(item.outstanding_amount)}</b>
          </div>
        </div>
        <div className="flex gap-2 border-t border-slate-100 p-4">
          <PaymentDialog
            receivableId={item.receivable_id}
            defaultAmount={item.outstanding_amount || undefined}
            disabled={item.outstanding_amount <= 0}
            onRecorded={refresh}
          />
          <RefundDialog
            receivableId={item.receivable_id}
            disabled={item.refundable_amount <= 0}
            maxAmount={item.refundable_amount}
            lessonBalance={item.lesson_balance}
            onRecorded={refresh}
          />
        </div>
      </Panel>
      <Panel title="资金流水">
        <div className="divide-y divide-slate-100">
          {item.payments.map((payment) => (
            <div className="p-4" key={payment.id}>
              <div className="flex justify-between text-sm">
                <div>
                  <b>收款 · {paymentMethodName(payment.method)}</b>
                  <div className="mt-1 text-xs text-slate-400">
                    {new Date(payment.paid_at).toLocaleString("zh-CN")}
                    {payment.payer_name ? ` · 付款方：${payment.payer_name}` : ""}
                  </div>
                </div>
                <b className="text-emerald-700">+{yuan(payment.amount)}</b>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <StatusBadge status={payment.status} />
                {payment.status === "effective" ? (
                  <VoidRecordButton
                    endpoint={`/payments/${payment.id}/void`}
                    label="作废收款"
                    onVoided={refresh}
                  />
                ) : null}
              </div>
              {payment.notes ? <p className="mt-2 text-xs text-slate-500">{payment.notes}</p> : null}
              {payment.void_reason ? <p className="mt-2 text-xs text-red-600">作废原因：{payment.void_reason}</p> : null}
              <AttachmentViewer ownerType="payment" ownerId={payment.id} />
            </div>
          ))}
          {item.refunds.map((refund) => (
            <div className="p-4 text-sm" key={refund.id}>
              <div className="flex justify-between">
                <div>
                  <b>退款 · {refund.reason}</b>
                  <div className="mt-1 text-xs text-slate-400">
                    {new Date(refund.refunded_at).toLocaleString("zh-CN")}
                  </div>
                </div>
                <b className="text-red-600">-{yuan(refund.actual_amount)}</b>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <StatusBadge status={refund.status} />
                {refund.status === "effective" ? (
                  <VoidRecordButton
                    endpoint={`/refunds/${refund.id}/void`}
                    label="作废退款"
                    onVoided={refresh}
                  />
                ) : null}
              </div>
              {refund.void_reason ? <p className="mt-2 text-xs text-red-600">作废原因：{refund.void_reason}</p> : null}
              <AttachmentViewer ownerType="refund" ownerId={refund.id} />
            </div>
          ))}
          {item.payments.length + item.refunds.length === 0 && (
            <p className="p-4 text-sm text-slate-400">尚无资金流水</p>
          )}
        </div>
      </Panel>
    </div>
  );
}
