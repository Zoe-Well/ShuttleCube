import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { StudentsPage } from "./students-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));
afterEach(() => vi.clearAllMocks());

it("shows each student's current entitlement summary in the list", async () => {
  vi.mocked(api).mockResolvedValue({
    items: [
      {
        id: "s1",
        name: "胡东东",
        is_active: true,
        entitlement_summary: {
          active_labels: ["固定班：周末提高班", "私教课包：陈教练"],
          has_history: true,
        },
      },
      {
        id: "s2",
        name: "已失效学员",
        is_active: true,
        entitlement_summary: { active_labels: [], has_history: true },
      },
      {
        id: "s3",
        name: "无权益学员",
        is_active: true,
        entitlement_summary: { active_labels: [], has_history: false },
      },
    ],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <StudentsPage />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("固定班：周末提高班；私教课包：陈教练")).toBeInTheDocument();
  expect(screen.getByText("权益已失效")).toBeInTheDocument();
  expect(screen.getByText("无权益")).toBeInTheDocument();
  expect(screen.queryByText("查看与维护")).not.toBeInTheDocument();
});
