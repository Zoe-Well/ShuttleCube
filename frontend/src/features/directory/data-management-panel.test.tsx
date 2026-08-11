import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { DataManagementPanel } from "./data-management-panel";

vi.mock("@/api/client", () => ({ api: vi.fn() }));

afterEach(() => { vi.clearAllMocks(); delete window.pywebview; });

describe("desktop data management", () => {
  it("exports a migration folder selected by the desktop shell", async () => {
    vi.mocked(api).mockImplementation((path, init) => {
      if (path === "/data-transfer/status") return Promise.resolve({ desktop_mode: true, data_directory: "C:\\Data", database_size_bytes: 1024, attachment_size_bytes: 0, pending_import: false });
      if (path === "/data-transfer/export" && init?.method === "POST") return Promise.resolve({ path: "D:\\Backup\\ShuttleCube-Transfer" });
      return Promise.resolve({});
    });
    window.pywebview = { api: { choose_export_directory: vi.fn().mockResolvedValue("D:\\Backup"), choose_import_directory: vi.fn(), restart_app: vi.fn() } };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><DataManagementPanel/></QueryClientProvider>);

    await screen.findByText("业务数据库");
    fireEvent.click(screen.getByRole("button", { name: "导出迁移文件夹" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith("/data-transfer/export", { method: "POST", body: JSON.stringify({ path: "D:\\Backup" }) }));
    expect(await screen.findByRole("status")).toHaveTextContent("ShuttleCube-Transfer");
    client.clear();
  });
});
