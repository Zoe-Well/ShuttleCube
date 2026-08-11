import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { CoachesPage } from "./directory-pages";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => vi.mocked(api).mockReset());

describe("coach rate directory", () => {
  it("shows both current fee standards and their effective dates", async () => {
    vi.mocked(api).mockResolvedValue([
      {
        id: "coach-1",
        name: "陈教练",
        is_active: true,
        fixed_class_fee: 180,
        private_lesson_fee: 220,
        fixed_class_fee_effective_from: "2026-08-01",
        private_lesson_fee_effective_from: "2026-08-01",
        version: 1,
      },
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <CoachesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/固定班 ¥180.00 · 2026-08-01/)).toBeInTheDocument();
    expect(screen.getByText(/私教 ¥220.00 · 2026-08-01/)).toBeInTheDocument();

    view.unmount();
    client.clear();
  });
});
