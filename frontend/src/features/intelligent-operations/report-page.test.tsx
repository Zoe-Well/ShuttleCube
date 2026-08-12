import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { IntelligentOperationsReportPage } from "./report-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("intelligent operations report AI feedback", () => {
  it("shows generation progress and automatically displays the finished summary", async () => {
    let snapshotReads = 0;
    const report = {
      id: "report-1",
      run_id: "run-1",
      period_type: "month",
      period_start: "2026-08-01",
      period_end: "2026-08-31",
      effective_end: "2026-08-12T00:00:00Z",
      period_state: "in_progress",
      generated_at: "2026-08-12T00:00:00Z",
      business_timezone: "Asia/Shanghai",
      comparison_status: "available",
      evidence_hash: "evidence-hash-for-report",
      narrative_state: "queued",
      metrics: [],
      breakdowns: {},
      anomalies: [],
      narrative: {
        state: "queued",
        summary: null,
        anomaly_explanations: [],
        recommendations: [],
        caveats: [],
      },
      access_projection: {
        financial_metrics_included: true,
        payroll_metrics_included: true,
        omitted_sections: [],
      },
    };
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/operations/reports?period_type=month") {
        return Promise.resolve({
          items: [{
            id: report.id,
            run_id: report.run_id,
            period_type: report.period_type,
            period_start: report.period_start,
            period_end: report.period_end,
            effective_end: report.effective_end,
            period_state: report.period_state,
            generated_at: report.generated_at,
            narrative_state: report.narrative_state,
            evidence_hash: report.evidence_hash,
          }],
          next_cursor: null,
        });
      }
      if (path === "/operations/reports/report-1") {
        snapshotReads += 1;
        return Promise.resolve(snapshotReads === 1 ? report : {
          ...report,
          narrative_state: "available",
          narrative: {
            ...report.narrative,
            state: "available",
            summary: "本月经营情况整体稳定。",
            recommendations: [{ text: "优先跟进逾期应收款。", priority: "high" }],
          },
        });
      }
      return Promise.reject(new Error(`Unexpected API path: ${path}`));
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <IntelligentOperationsReportPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("status")).toHaveTextContent("AI 正在生成总结与建议");
    expect(screen.getByRole("status")).toHaveTextContent("无需刷新页面");
    expect(await screen.findByText("本月经营情况整体稳定。", {}, { timeout: 3500 })).toBeInTheDocument();
    expect(screen.getByText("优先跟进逾期应收款。")).toBeInTheDocument();
    expect(snapshotReads).toBeGreaterThanOrEqual(2);

    client.clear();
  });
});
