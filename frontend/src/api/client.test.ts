import { describe, expect, it, vi } from "vitest";

import { api } from "./client";

describe("API client errors", () => {
  it("shows a readable message when the server returns a plain-text 500", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Internal Server Error", { status: 500 })));

    await expect(api("/operations/policies/example:activate", { method: "POST" }))
      .rejects.toThrow("服务器暂时无法完成请求，请稍后重试");

    vi.unstubAllGlobals();
  });
});
