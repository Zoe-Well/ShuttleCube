import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { VenueHours } from "./schedule-time";

export function useVenueHours() {
  return useQuery({
    queryKey: ["venue-settings"],
    queryFn: () => api<VenueHours>("/venue/settings"),
  });
}
