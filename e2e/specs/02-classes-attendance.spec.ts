import { test,expect } from "@playwright/test";import { login } from "../fixtures/auth";
test("固定班创建入口可用",async({page})=>{await login(page);await page.getByRole("link",{name:"固定班管理"}).click();await expect(page.getByRole("button",{name:"创建并生成课程"})).toBeVisible()});
