import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ErrorBoundary } from "./error-boundary";

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 20_000, retry: 1 } } });
export function Providers({ children }: { children: ReactNode }) { return <ErrorBoundary><QueryClientProvider client={client}>{children}</QueryClientProvider></ErrorBoundary>; }
