import { useQuery } from "@tanstack/react-query";

import { chatApi } from "@/lib/api/chat";

const OPENROUTER_USAGE_QUERY_KEY = ["chat", "openrouter", "usage"] as const;
export const OPENROUTER_CREDENTIAL_QUERY_KEY = ["chat", "openrouter", "credential"] as const;

export function useOpenRouterUsage(enabled = true) {
  return useQuery({
    queryKey: OPENROUTER_USAGE_QUERY_KEY,
    queryFn: () => chatApi.getUsage(),
    enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

export function useOpenRouterCredential(enabled = true) {
  return useQuery({
    queryKey: OPENROUTER_CREDENTIAL_QUERY_KEY,
    queryFn: () => chatApi.getOpenRouterCredential(),
    enabled,
    refetchOnWindowFocus: true,
  });
}

export function resetTimeLabels(value: string): { local: string; utc: string } {
  const reset = new Date(value);
  return {
    local: new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(reset),
    utc: `${reset.toLocaleString("en-GB", {
      timeZone: "UTC",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })} UTC`,
  };
}
