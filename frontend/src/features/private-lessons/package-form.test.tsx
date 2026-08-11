import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { PackageForm } from "./package-form";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => {
  vi.clearAllMocks();
});

describe("private lesson package form", () => {
  it("only submits an existing active student and coach", async () => {
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/students")
        return Promise.resolve({
          items: [
            { id: "student-active", name: "有效学员", is_active: true },
            { id: "student-inactive", name: "停用学员", is_active: false },
          ],
        });
      if (path === "/coaches")
        return Promise.resolve([
          { id: "coach-active", name: "有效教练", is_active: true },
          { id: "coach-inactive", name: "停用教练", is_active: false },
        ]);
      return Promise.resolve([]);
    });
    const onSubmit = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PackageForm onSubmit={onSubmit} />
      </QueryClientProvider>,
    );

    await screen.findByRole("option", { name: "有效学员" });
    await screen.findByRole("option", { name: "有效教练" });
    const studentSelect = screen.getByRole("combobox", { name: /学员/ });
    const coachSelect = screen.getByRole("combobox", { name: /绑定教练/ });
    expect(screen.queryByRole("option", { name: "停用学员" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "停用教练" })).not.toBeInTheDocument();

    await userEvent.selectOptions(studentSelect, "student-active");
    await userEvent.selectOptions(coachSelect, "coach-active");
    await userEvent.click(screen.getByRole("button", { name: "创建私教课包" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        student_id: "student-active",
        bound_coach_id: "coach-active",
      }),
    );
    client.clear();
  });
});
