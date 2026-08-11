import { test,expect } from "@playwright/test";import { login } from "../fixtures/auth";
test("统一排期入口和日历可用",async({page})=>{await login(page);await page.getByRole("link",{name:"统一排期"}).click();await expect(page.getByRole("heading",{name:"统一排期"})).toBeVisible();await expect(page.getByText("固定班、私教、订场和活动使用同一资源视图")).toBeVisible()});
