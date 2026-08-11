import { createContext, useContext, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, setCsrfToken } from "@/api/client";

export type Session = {
  user_id: string;
  username: string;
  display_name: string;
  csrf_token: string;
};
export type SetupStatus = { required: boolean; desktop_mode: boolean };
export type SetupInput = {
  venue_name: string;
  court_count: number;
  username: string;
  display_name: string;
  password: string;
};
type SessionState = { session: Session | null; isLoading: boolean };
const SessionContext = createContext<SessionState>({ session: null, isLoading: true });
export function useSession() {
  return useContext(SessionContext).session;
}
export function useSessionLoading() {
  return useContext(SessionContext).isLoading;
}
export function SessionProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/session"),
    retry: false,
  });
  if (query.data) setCsrfToken(query.data.csrf_token);
  return (
    <SessionContext.Provider value={{ session: query.data ?? null, isLoading: query.isLoading }}>
      {children}
    </SessionContext.Provider>
  );
}
export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { username: string; password: string }) =>
      api<Session>("/session/login", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: (session) => {
      setCsrfToken(session.csrf_token);
      client.setQueryData(["session"], session);
    },
  });
}
export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    queryFn: () => api<SetupStatus>("/setup/status"),
    retry: false,
  });
}
export function useSetup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: SetupInput) =>
      api<Session>("/setup", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: (session) => {
      setCsrfToken(session.csrf_token);
      client.setQueryData(["session"], session);
      client.setQueryData(["setup-status"], { required: false, desktop_mode: true });
    },
  });
}
export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/session/logout", { method: "POST" }),
    onSuccess: () => {
      setCsrfToken("");
      client.setQueryData(["session"], null);
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    },
  });
}
