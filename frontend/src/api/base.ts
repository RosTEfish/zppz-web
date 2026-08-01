import { request } from "./client";

export const API_PREFIX = "/api/v1";

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  return request<T>(`${API_PREFIX}${path}`, options);
}
