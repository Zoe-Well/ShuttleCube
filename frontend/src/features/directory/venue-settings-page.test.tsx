import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { VenueSettingsPage } from "./directory-pages";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("venue settings", () => {
  it("validates and saves weekday and weekend business hours", async () => {
    const venue = {
      id: "venue-1",
      name: "ShuttleCube 羽毛球馆",
      timezone: "Asia/Shanghai",
      weekday_open_time: "14:00:00",
      weekday_close_time: "22:00:00",
      weekend_open_time: "08:00:00",
      weekend_close_time: "22:00:00",
      version: 1,
    };
    vi.mocked(api).mockImplementation((path, init) => {
      if (path === "/venue/settings" && init?.method === "PUT") {
        return Promise.resolve({ ...venue, ...JSON.parse(String(init.body)), version: 2 });
      }
      if (path === "/venue/settings") return Promise.resolve(venue);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <VenueSettingsPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("工作日开门时间")).toHaveValue("14:00"));
    expect(screen.getByRole("link", { name: /AI 服务配置/ })).toHaveAttribute(
      "href",
      "/settings/ai",
    );
    fireEvent.change(screen.getByLabelText("工作日关门时间"), { target: { value: "13:30" } });
    fireEvent.click(screen.getByRole("button", { name: "保存营业时间" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("工作日关门时间必须晚于开门时间");

    fireEvent.change(screen.getByLabelText("工作日开门时间"), { target: { value: "13:30" } });
    fireEvent.change(screen.getByLabelText("工作日关门时间"), { target: { value: "23:00" } });
    fireEvent.change(screen.getByLabelText("周末开门时间"), { target: { value: "07:30" } });
    fireEvent.change(screen.getByLabelText("周末关门时间"), { target: { value: "23:30" } });
    fireEvent.click(screen.getByRole("button", { name: "保存营业时间" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/venue/settings",
      {
        method: "PUT",
        body: JSON.stringify({
          name: venue.name,
          timezone: venue.timezone,
          weekday_open_time: "13:30:00",
          weekday_close_time: "23:00:00",
          weekend_open_time: "07:30:00",
          weekend_close_time: "23:30:00",
          version: 1,
        }),
      },
    ));
    expect(await screen.findByRole("status")).toHaveTextContent("营业时间已保存");

    view.unmount();
    client.clear();
  });

  it("edits and saves the three default court price periods", async () => {
    const venue = {
      id: "venue-1",
      name: "ShuttleCube 羽毛球馆",
      timezone: "Asia/Shanghai",
      weekday_open_time: "08:00:00",
      weekday_close_time: "22:00:00",
      weekend_open_time: "08:00:00",
      weekend_close_time: "22:00:00",
      version: 1,
    };
    const rules = [
      { id: "day", period_type: "weekday_day", name: "工作日白天场", time_start: "08:00:00", time_end: "18:00:00", price_per_court_hour: 50, version: 1 },
      { id: "evening", period_type: "weekday_evening", name: "工作日晚间场", time_start: "18:00:00", time_end: "22:00:00", price_per_court_hour: 80, version: 1 },
      { id: "weekend", period_type: "weekend", name: "周末场", time_start: "08:00:00", time_end: "22:00:00", price_per_court_hour: 100, version: 1 },
    ];
    vi.mocked(api).mockImplementation((path, init) => {
      if (path === "/venue/settings") return Promise.resolve(venue);
      if (path === "/venue-price-rules/defaults" && init?.method === "PUT") {
        return Promise.resolve(rules);
      }
      if (path === "/venue-price-rules/defaults") return Promise.resolve(rules);
      return Promise.resolve([]);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <VenueSettingsPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByDisplayValue("50")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("工作日白天场结束时间"), { target: { value: "19:00" } });
    fireEvent.click(screen.getByRole("button", { name: "保存默认价格" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("工作日白天与晚间价格时段不能重叠");

    fireEvent.change(screen.getByLabelText("工作日白天场结束时间"), { target: { value: "18:00" } });
    fireEvent.change(screen.getByLabelText("工作日晚间场每小时价格"), { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: "保存默认价格" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/venue-price-rules/defaults",
      expect.objectContaining({ method: "PUT" }),
    ));
    expect(await screen.findByRole("status")).toHaveTextContent("默认场地价格已保存");
    view.unmount();
    client.clear();
  });
});
