import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  configureOperationsModelCredential,
  getOperationsModelSetting,
} from "@/features/intelligent-operations/api";
import { AiServiceSettingsPage } from "./ai-service-settings-page";

vi.mock("@/features/intelligent-operations/api", () => ({
  configureOperationsModelCredential: vi.fn(),
  deleteOperationsModelCredential: vi.fn(),
  getOperationsModelSetting: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("AI service settings", () => {
  it("uses the DeepSeek endpoint and Chat Completions protocol", async () => {
    const initial = {
      model_enabled: false,
      provider_configured: false,
      provider_editable: true,
      provider_source: null,
      provider_verified_at: null,
      provider_key: "openai" as const,
      provider_label: "OpenAI",
      provider_base_url: "https://api.openai.com/v1",
      provider_api_mode: "responses" as const,
      provider_model_profile: "gpt-5.6",
      enabled_by: null,
      enabled_at: null,
      updated_at: "2026-08-12T00:00:00Z",
      version: 1,
    };
    vi.mocked(getOperationsModelSetting).mockResolvedValue(initial);
    vi.mocked(configureOperationsModelCredential).mockResolvedValue({
      ...initial,
      provider_configured: true,
      provider_source: "desktop",
      provider_verified_at: "2026-08-12T01:00:00Z",
      provider_key: "deepseek",
      provider_label: "DeepSeek",
      provider_base_url: "https://api.deepseek.com",
      provider_api_mode: "chat_completions",
      provider_model_profile: "deepseek-chat",
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <MemoryRouter>
        <QueryClientProvider client={client}>
          <AiServiceSettingsPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await screen.findByLabelText("AI 服务商");
    fireEvent.change(screen.getByLabelText("AI 服务商"), { target: { value: "deepseek" } });
    expect(screen.getByLabelText("API 地址")).toHaveValue("https://api.deepseek.com");
    expect(screen.getByLabelText("API 协议")).toHaveValue("chat_completions");
    expect(screen.getByLabelText("模型名称")).toHaveValue("deepseek-chat");
    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "sk-deepseek-test" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并验证" }));

    await waitFor(() => expect(configureOperationsModelCredential).toHaveBeenCalledWith({
      provider: "deepseek",
      base_url: "https://api.deepseek.com",
      api_mode: "chat_completions",
      model_profile: "deepseek-chat",
      api_key: "sk-deepseek-test",
    }));
    expect(await screen.findByText("✓ API Key 验证成功")).toHaveClass("text-emerald-800");
    expect(screen.getByText("DeepSeek")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-deepseek-test")).toBeNull();

    client.clear();
  });
});
