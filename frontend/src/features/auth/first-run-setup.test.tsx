import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FirstRunSetup } from "./first-run-setup";

const mutate = vi.fn();
vi.mock("./session", () => ({ useSetup: () => ({ mutate, isPending: false, error: null }) }));

describe("first run setup", () => {
  it("creates the initial venue and administrator", async () => {
    render(<FirstRunSetup/>);
    fireEvent.change(screen.getByLabelText("登录密码"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "完成初始化" }));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith(expect.objectContaining({
      venue_name: "ShuttleCube 羽毛球馆",
      court_count: 4,
      username: "admin",
      display_name: "管理员",
      password: "password123",
    })));
  });
});
