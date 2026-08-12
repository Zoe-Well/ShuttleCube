import { ApiProblem, type Problem } from "./problem";

let csrfToken = "";
export function setCsrfToken(value: string) { csrfToken = value; }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrfToken && init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    const fallback: Problem = {
      type: "https://shuttlecube.local/problems/server_error",
      title: "server_error",
      status: response.status,
      detail: response.status >= 500
        ? "服务器暂时无法完成请求，请稍后重试"
        : `请求失败（${response.status}）`,
    };
    try {
      const contentType = response.headers.get("content-type") ?? "";
      if (contentType.includes("json")) {
        throw new ApiProblem(await response.json() as Problem);
      }
      const detail = (await response.text()).trim();
      if (detail && detail !== "Internal Server Error") fallback.detail = detail;
    } catch (error) {
      if (error instanceof ApiProblem) throw error;
    }
    throw new ApiProblem(fallback);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
