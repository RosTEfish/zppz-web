import { expect, test as base } from "@playwright/test";

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route("**/*", (route) => {
      const { hostname, protocol } = new URL(route.request().url());
      if (protocol === "data:" || protocol === "blob:" || hostname === "127.0.0.1" || hostname === "localhost") {
        return route.continue();
      }
      return route.abort("blockedbyclient");
    });
    await use(page);
  },
});

export { expect };
