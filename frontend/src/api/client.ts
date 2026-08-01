import createClient from "openapi-fetch";
import type { paths } from "./generated";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const baseUrl = typeof window === "undefined" ? "http://localhost" : window.location.origin;

const client = createClient<paths>({
  baseUrl,
  credentials: "include",
  bodySerializer: JSON.stringify,
  async fetch(input) {
    const apiRequest = input instanceof Request ? input : new Request(input);
    const url = new URL(apiRequest.url);
    const body = apiRequest.method === "GET" || apiRequest.method === "HEAD"
      ? undefined
      : await apiRequest.clone().text();
    return globalThis.fetch(`${url.pathname}${url.search}`, {
      method: apiRequest.method,
      headers: apiRequest.headers,
      body,
      cache: apiRequest.cache,
      credentials: apiRequest.credentials,
      redirect: apiRequest.redirect,
    });
  },
});

function errorMessage(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item))
      .join("；");
  }
  if (typeof detail === "object" && detail && "detail" in detail) return errorMessage(detail.detail);
  return detail ? String(detail) : "请求失败";
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  if ((typeof FormData !== "undefined" && options.body instanceof FormData) || options.signal) {
    const headers = new Headers(options.headers);
    if (typeof options.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await globalThis.fetch(path, { credentials: "include", ...options, headers });
    const data = response.status === 204 ? undefined : await response.json();
    if (!response.ok) throw new ApiError(errorMessage(data), response.status, data);
    return data as T;
  }
  const method = (options.method || "GET").toUpperCase();
  const rawBody = options.body;
  const body = typeof rawBody === "string" ? JSON.parse(rawBody) : rawBody;
  const send = client.request as unknown as (
    method: string,
    url: string,
    init: Record<string, unknown>,
  ) => Promise<{ data?: unknown; error?: unknown; response: Response }>;
  const { data, error, response } = await send(method, path, {
    body,
    headers: options.headers,
    signal: options.signal,
    cache: options.cache,
  });
  if (!response.ok || error !== undefined) {
    throw new ApiError(errorMessage(error), response.status, error);
  }
  return data as T;
}
