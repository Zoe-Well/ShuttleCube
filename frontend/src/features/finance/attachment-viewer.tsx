import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

import { api } from "@/api/client";

type Attachment = { id: string; original_filename: string; uploaded_at: string; size_bytes: number };

export function AttachmentViewer({ ownerType, ownerId }: { ownerType: string; ownerId: string }) {
  const input = useRef<HTMLInputElement>(null);
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["attachments", ownerType, ownerId], queryFn: () => api<Attachment[]>(`/attachments?owner_type=${ownerType}&owner_id=${ownerId}`) });
  const upload = useMutation({
    mutationFn: (file: File) => { const body = new FormData(); body.append("owner_type", ownerType); body.append("owner_id", ownerId); body.append("file", file); return api("/attachments", { method: "POST", body }); },
    onSuccess: () => void client.invalidateQueries({ queryKey: ["attachments", ownerType, ownerId] }),
  });
  return <div className="mt-3 rounded-md border border-slate-200 p-3"><div className="flex items-center justify-between"><b className="text-xs">付款凭证</b><><input ref={input} className="hidden" accept="image/jpeg,image/png,image/webp" type="file" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} /><button className="text-xs font-semibold text-emerald-700" type="button" onClick={() => input.current?.click()}>上传凭证</button></></div><div className="mt-2 grid gap-1">{(query.data ?? []).map((item) => <a className="text-xs text-slate-600 hover:text-emerald-700" href={`/api/v1/attachments/${item.id}/content`} key={item.id} target="_blank" rel="noreferrer">{item.original_filename}</a>)}{query.data?.length === 0 && <span className="text-xs text-slate-400">暂无凭证</span>}</div></div>;
}
