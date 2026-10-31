import { e2eAdminCode, e2eAdminPassword, seededAdminDisplayName, seededEventName } from "./constants";
import { expect, test } from "./fixtures";

test.describe("browser smoke", () => {
  test("home renders the seeded event", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("这谱谱这");
    await expect(page.getByRole("heading", { level: 1, name: seededEventName })).toBeVisible();
    await expect(page.getByRole("button", { name: "进入赛事" })).toBeVisible();
  });

  test("auth page renders the login shell", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { level: 1, name: "赛事账号" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "登录" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "注册" })).toBeVisible();
    await expect(page.getByLabel("账号", { exact: true })).toBeVisible();
    await expect(page.getByLabel("密码")).toBeVisible();
    await expect(page.getByRole("button", { name: "登录" })).toBeEnabled();
  });

  test("anonymous account route returns to the login shell", async ({ page }) => {
    await page.goto("/account");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { level: 1, name: "赛事账号" })).toBeVisible();
  });

  test("seeded admin reaches the account shell", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("账号", { exact: true }).fill(e2eAdminCode);
    await page.getByLabel("密码").fill(e2eAdminPassword);
    await page.getByRole("button", { name: "登录" }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1, name: seededEventName })).toBeVisible();
    await expect(page.getByRole("link", { name: "管理", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "退出", exact: true })).toBeVisible();

    await page.goto("/account");
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole("heading", { name: "账号设置" })).toBeVisible();
    await expect(page.getByLabel("登录账号")).toHaveValue(e2eAdminCode);
    await expect(page.getByLabel("显示名")).toHaveValue(seededAdminDisplayName);
  });
});
