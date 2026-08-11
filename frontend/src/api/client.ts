import { ApiProblem, type Problem } from "./problem";

let csrfToken = "";
export function setCsrfToken(value: string) { csrfToken = value; }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrfToken && init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) throw new ApiProblem(await response.json() as Problem);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
