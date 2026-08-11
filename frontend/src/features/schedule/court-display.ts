import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { ScheduleItem } from "./schedule-calendar";

export type CourtDirectoryItem = {
  id: string;
  code?: string;
  name: string;
  is_active?: boolean;
};

export function useCourtDirectory() {
  return useQuery({
    queryKey: ["courts"],
    queryFn: () => api<CourtDirectoryItem[]>("/courts"),
  });
}

export function courtForReference(
  reference: string,
  courts: CourtDirectoryItem[],
) {
  const value = reference.trim().toLocaleLowerCase();
  return courts.find((court) =>
    [court.id, court.code, court.name]
      .filter((candidate): candidate is string => Boolean(candidate))
      .some((candidate) => candidate.trim().toLocaleLowerCase() === value),
  );
}

export function canonicalCourtId(reference: string, courts: CourtDirectoryItem[]) {
  return courtForReference(reference, courts)?.id ?? reference;
}

function fallbackCourtName(reference: string) {
  return /^\d+$/.test(reference.trim()) ? `${reference.trim()} 号场地` : reference;
}

export function formatCourtNames(
  references: string[],
  courts: CourtDirectoryItem[] | undefined,
) {
  if (!references.length) return "未分配场地";
  if (!courts) return "场地信息加载中…";
  return [...new Set(references.map((reference) =>
    courtForReference(reference, courts)?.name ?? fallbackCourtName(reference),
  ))].join("、");
}

export function scheduleCourtReferences(item: ScheduleItem) {
  return (item.resources ?? [])
    .filter((resource) => (resource.type ?? resource.resource_type) === "court")
    .map((resource) => resource.id ?? resource.resource_id)
    .filter((reference): reference is string => Boolean(reference));
}

export function formatScheduleCourtNames(
  item: ScheduleItem,
  courts: CourtDirectoryItem[] | undefined,
) {
  return formatCourtNames(scheduleCourtReferences(item), courts);
}
