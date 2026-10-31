import { defineConfig, devices } from "@playwright/test";
import { e2eAdminCode, e2eAdminPassword, e2eBaseURL, e2ePort } from "./e2e/constants";

const ci = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  forbidOnly: ci,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 15_000 },
  reporter: ci ? [["github"], ["html", { open: "never" }], ["list"]] : "list",
  outputDir: "test-results",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: e2eBaseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: {
    command: "bash ../scripts/e2e_server.sh",
    url: `${e2eBaseURL}/health`,
    reuseExistingServer: !ci,
    timeout: 120_000,
    env: {
      E2E_PORT: e2ePort,
      E2E_BASE_URL: e2eBaseURL,
      E2E_ADMIN_CODE: e2eAdminCode,
      E2E_ADMIN_PASSWORD: e2eAdminPassword,
    },
  },
});
