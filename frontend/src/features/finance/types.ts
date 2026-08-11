export type ReceivableSummary = {
  receivable_id: string;
  source_type: string;
  source_id: string;
  business_name: string;
  suggested_amount: number;
  actual_amount: number;
  received_amount: number;
  refunded_amount: number;
  net_received: number;
  outstanding_amount: number;
  refundable_amount: number;
  payment_status: string;
  status: string;
  version: number;
};

export type ReceivableDetail = ReceivableSummary & {
  lesson_balance?: number | null;
  payments: Array<{
    id: string;
    paid_at: string;
    amount: number;
    method: string;
    payer_name?: string | null;
    received_by?: string | null;
    status: string;
    notes?: string | null;
    void_reason?: string | null;
  }>;
  refunds: Array<{
    id: string;
    refunded_at: string;
    payment_id?: string | null;
    suggested_amount?: number | null;
    actual_amount: number;
    reason: string;
    status: string;
    void_reason?: string | null;
  }>;
};

export const sourceNames: Record<string, string> = {
  enrollment: "固定班报名",
  private_package: "私教课包",
  private_lesson: "单次私教",
  venue_booking: "场地预订",
  event: "临时活动",
  other: "其他应收",
};

export function yuan(value: number) {
  return `¥${Number(value).toFixed(2)}`;
}

const paymentMethodLabels: Record<string, string> = {
  wechat: "微信",
  alipay: "支付宝",
  cash: "现金",
  bank: "银行转账",
  payroll: "教练结算",
};

export function paymentMethodName(value: string) {
  return paymentMethodLabels[value] ?? value;
}
