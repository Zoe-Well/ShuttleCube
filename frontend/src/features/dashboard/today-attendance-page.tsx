import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "@/api/client";
import { EmptyState } from "@/components/operations/empty-state";
import { PageHeader, Panel } from "@/components/operations/page";
import { formatBeijingTime } from "@/lib/beijing-time";
import { localDateKey } from "@/lib/utils";

type PendingAttendance = {
  session_id: string;
  class_id: string;
  class_name: string;
  sequence_number: number;
  scheduled_start: string;
  scheduled_end: string;
  coach_name: string;
  active_enrollment_count: number;
};

function timeRange(start: string, end: string) {
  return `${formatBeijingTime(start)}–${formatBeijingTime(end)}`;
}

export function TodayAttendancePage() {
  const businessDate = localDateKey(new Date());
  const query = useQuery({
    queryKey: ["pending-attendance", businessDate],
    queryFn: () =>
      api<PendingAttendance[]>(
        `/dashboard/pending-attendance?business_date=${businessDate}`,
      ),
  });
  const rows = query.data ?? [];

  return (
    <section>
      <PageHeader
        eyebrow="Attendance today"
        title="今日待考勤"
        description="集中查看今天尚未完成考勤的固定班课次"
      />
      <Panel title={businessDate} description={`共 ${rows.length} 节课程待处理`}>
        {rows.length ? (
          <table className="data-table">
            <thead>
              <tr><th>上课时间</th><th>来源班级</th><th>课次</th><th>教练</th><th>在班学员</th><th>操作</th></tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.session_id}>
                  <td className="table-primary">{timeRange(item.scheduled_start, item.scheduled_end)}</td>
                  <td>{item.class_name}</td>
                  <td>第 {item.sequence_number} 节</td>
                  <td>{item.coach_name}</td>
                  <td>{item.active_enrollment_count} 人</td>
                  <td>
                    <Link
                      className="text-xs font-semibold text-emerald-700"
                      to={`/classes/${item.class_id}?attendance_session=${item.session_id}`}
                    >
                      去考勤
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="今天没有待考勤课程" description="已完成考勤或今天没有固定班课程。" />
        )}
      </Panel>
    </section>
  );
}
