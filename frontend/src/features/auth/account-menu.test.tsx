import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountMenu } from "./account-menu";

const { logout } = vi.hoisted(() => ({
  logout: vi.fn((_input, options?: { onSuccess?: () => void }) => options?.onSuccess?.()),
}));

vi.mock("./session", () => ({
  useSession: () => ({
    user_id: "user-1",
    username: "owner1",
    display_name: "聂老板",
    csrf_token: "csrf-token",
  }),
  useLogout: () => ({ mutate: logout, isPending: false, error: null }),
}));

describe("account menu", () => {
  it("shows current login information and allows account switching", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AccountMenu />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "管理员账号" }));

    expect(screen.getByText("用户名：owner1")).toBeInTheDocument();
    expect(screen.getByText("本机场馆数据由所有账号共享")).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "切换账号" }));
    expect(logout).toHaveBeenCalledOnce();
  });
});
