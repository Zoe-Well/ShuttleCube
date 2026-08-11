import type { ScheduleItem } from "./schedule-calendar";

const bulkDeletableTypes = new Set(["manual", "private_lesson", "venue_booking", "event"]);

export function bulkDeleteBlockedReason(item: ScheduleItem) {
  if (item.status === "completed") return "已完成记录不能删除";
  if (item.source_type === "class_session" || item.source_type === "fixed_class") {
    return "固定班课次请在固定班业务中管理";
  }
  if (!bulkDeletableTypes.has(item.source_type)) return "此类排期请单条处理";
  return null;
}

export function canBulkDeleteSchedule(item: ScheduleItem) {
  return bulkDeleteBlockedReason(item) === null;
}
