import { http } from "msw";
import { setupServer } from "msw/node";

export const testServer = setupServer();

export type TestApiResolver = (url: string, init: RequestInit) => Response | undefined | Promise<Response | undefined>;

export function mockApi(resolver: TestApiResolver) {
  testServer.use(http.all("*", async ({ request }) => {
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.clone().text();
    return resolver(request.url, {
      method: request.method,
      headers: request.headers,
      body: body || undefined,
      cache: request.cache,
      credentials: request.credentials,
    });
  }));
}
