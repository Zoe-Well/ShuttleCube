import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { CourtsPage } from "./directory-pages";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

function renderCourts(client: QueryClient) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <CourtsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("court directory", () => {
  it("does not describe a pending request as an empty court directory", () => {
    vi.mocked(api).mockImplementation(() => new Promise(() => undefined));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = renderCourts(client);

    expect(screen.getByRole("status")).toHaveTextContent("正在加载场地");
    expect(screen.queryByText("暂无场地")).not.toBeInTheDocument();

    view.unmount();
    client.clear();
  });

  it("keeps the complete list visible while a stopped court is refreshed", async () => {
    const courts = [1, 2, 3, 4, 5].map((number) => ({
      id: `court-${number}`,
      code: String(number),
      name: `${number} 号场地`,
      is_active: true,
      version: 1,
    }));
    const stopped = { ...courts[4], is_active: false, version: 2 };
    let listCalls = 0;
    vi.mocked(api).mockImplementation((path, init) => {
      if (path === "/courts/court-5/status" && init?.method === "PATCH") {
        return Promise.resolve(stopped);
      }
      if (path === "/courts") {
        listCalls += 1;
        return listCalls === 1 ? Promise.resolve(courts) : new Promise(() => undefined);
      }
      return Promise.resolve([]);
    });
    vi.spyOn(window, "prompt").mockReturnValue("测试停用");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = renderCourts(client);

    expect(await screen.findByText("1 号场地")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "停用" })[4]);

    await waitFor(() => expect(screen.getByRole("button", { name: "启用" })).toBeInTheDocument());
    expect(screen.queryByText("暂无场地")).not.toBeInTheDocument();
    for (const number of [1, 2, 3, 4, 5]) {
      expect(screen.getByText(`${number} 号场地`)).toBeInTheDocument();
    }
    expect(api).toHaveBeenCalledWith("/courts/court-5/status", {
      method: "PATCH",
      body: JSON.stringify({ is_active: false, reason: "测试停用", version: 1 }),
    });

    fireEvent.change(screen.getByPlaceholderText("搜索场地"), {
      target: { value: "不存在的场地" },
    });
    expect(screen.getByText("未找到匹配场地")).toBeInTheDocument();
    expect(screen.queryByText("暂无场地")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清除搜索" }));
    expect(screen.getByText("1 号场地")).toBeInTheDocument();

    view.unmount();
    client.clear();
  });
});
