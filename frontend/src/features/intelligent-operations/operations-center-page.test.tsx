import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { OperationsCenterPage } from "./operations-center-page";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("intelligent operations AI entry", () => {
  it("explains where AI is used and links to the report entry", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/operations/context") return Promise.resolve({
        organization: { id: "org-1", name: "测试机构" },
        venue: { id: "venue-1", name: "测试场馆" },
        user_id: "user-1",
        membership_id: "membership-1",
        capabilities: ["operations.case.read", "operations.report.read"],
        operations_enabled: true,
        write_tools_enabled: false,
        model_enabled: true,
        policy_status: "active",
      });
      if (path.startsWith("/operations/cases")) return Promise.resolve({ items: [], next_cursor: null });
      if (path === "/operations/brief") return Promise.resolve({
        generated_at: "2026-08-12T00:00:00Z",
        total: 0,
        groups: [],
      });
      return Promise.reject(new Error(`Unexpected API path: ${path}`));
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <OperationsCenterPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("AI 没有单独的聊天入口，会在经营报告、欠费／续费案件和数据核对案件中按需出现。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /查看 AI 经营总结/ })).toHaveAttribute("href", "/reports");

    client.clear();
  });
});
