import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, setCsrfToken } from "./client";

describe("api client",()=>{beforeEach(()=>vi.restoreAllMocks());it("sends same-origin credentials and csrf",async()=>{const fetchMock=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({ok:true}),{status:200,headers:{"Content-Type":"application/json"}}));setCsrfToken("csrf");await api("/test",{method:"POST",body:JSON.stringify({})});expect(fetchMock).toHaveBeenCalledWith("/api/v1/test",expect.objectContaining({credentials:"include"}));expect((fetchMock.mock.calls[0][1]?.headers as Headers).get("X-CSRF-Token")).toBe("csrf")})});
