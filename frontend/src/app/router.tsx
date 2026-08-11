import { createBrowserRouter } from "react-router";
import { SetupAwareLoginPage } from "@/features/auth/setup-aware-login-page";
import { SchedulePage } from "@/features/schedule/schedule-page";
import { StudentsPage } from "@/features/customers/students-page";
import { CoachesPage, CourtsPage } from "@/features/directory/directory-pages";
import { DesktopVenueSettingsPage } from "@/features/directory/desktop-venue-settings-page";
import { AppShell } from "@/layouts/app-shell";
import { ClassesPage } from "@/features/classes/classes-page";
import { ClassDetailPage } from "@/features/classes/class-detail-page";
import { PrivateLessonsPage } from "@/features/private-lessons/private-lessons-page";
import { BookingsPage } from "@/features/venue-bookings/bookings-page";
import { EventsPage } from "@/features/events/events-page";
import { DashboardPage } from "@/features/dashboard/dashboard-page";
import { FinancePage } from "@/features/finance/finance-page";
import { ExpensesPage } from "@/features/finance/expenses-page";
import { CoachFeesPage } from "@/features/payroll/coach-fees-page";
import { OperationsReportPage } from "@/features/dashboard/operations-report-page";
import { AuditTimeline } from "@/features/audit/audit-timeline";
import { TodayAttendancePage } from "@/features/dashboard/today-attendance-page";
import { CourtOverviewPage } from "@/features/dashboard/court-overview-page";
import { OperationCaseDetailPage } from "@/features/intelligent-operations/case-detail-page";
import { OperationsCenterPage } from "@/features/intelligent-operations/operations-center-page";
import { IntelligentOperationsReportPage } from "@/features/intelligent-operations/report-page";

export const router = createBrowserRouter([
  { path: "/login", element: <SetupAwareLoginPage /> },
  {
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "attendance/today", element: <TodayAttendancePage /> },
      { path: "schedule", element: <SchedulePage /> },
      { path: "students", element: <StudentsPage /> },
      { path: "courts", element: <CourtsPage /> },
      { path: "courts/overview", element: <CourtOverviewPage /> },
      { path: "coaches", element: <CoachesPage /> },
      { path: "settings", element: <DesktopVenueSettingsPage /> },
      { path: "classes", element: <ClassesPage /> },
      { path: "classes/:id", element: <ClassDetailPage /> },
      { path: "private-lessons", element: <PrivateLessonsPage /> },
      { path: "bookings", element: <BookingsPage /> },
      { path: "events", element: <EventsPage /> },
      { path: "finance", element: <FinancePage /> },
      { path: "expenses", element: <ExpensesPage /> },
      { path: "payroll", element: <CoachFeesPage /> },
      { path: "reports", element: <IntelligentOperationsReportPage /> },
      { path: "reports/legacy", element: <OperationsReportPage /> },
      { path: "operations", element: <OperationsCenterPage /> },
      { path: "operations/cases/:caseId", element: <OperationCaseDetailPage /> },
      { path: "audit", element: <AuditTimeline /> },
    ],
  },
]);
