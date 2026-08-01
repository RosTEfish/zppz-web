import { describe, expect, it } from "vitest";
import { mockApi } from "./testServer";
import { api } from "./api/v1";

describe("MSW test server", () => {
  it("routes browser API requests through the node interceptor", async () => {
    mockApi((path) => new Response(JSON.stringify({ path }), { headers: { "content-type": "application/json" } }));
    const response = await fetch("http://localhost/api/v1/bootstrap");
    expect(await response.json()).toEqual({ path: "http://localhost/api/v1/bootstrap" });
  });

  it("supports the generated API client", async () => {
    mockApi((path) => path.endsWith("/bootstrap")
      ? new Response(JSON.stringify({ event: { id: 1, name: "test" }, user: null }), { headers: { "content-type": "application/json" } })
      : new Response(JSON.stringify({ detail: "not found" }), { status: 404, headers: { "content-type": "application/json" } }));
    await expect(api.bootstrap()).resolves.toMatchObject({ event: { name: "test" }, user: null });
  });
});
