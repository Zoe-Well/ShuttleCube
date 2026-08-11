import { expect, type Page } from "@playwright/test";
export async function login(page:Page){await page.goto("/login");await page.getByLabel("用户名").fill("owner1");await page.getByLabel("密码").fill("password123");await page.getByRole("button",{name:"登录"}).click();await expect(page).toHaveURL(/\/$/)}
