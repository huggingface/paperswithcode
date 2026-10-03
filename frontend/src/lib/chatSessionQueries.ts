import { queryOptions } from "@tanstack/react-query";
import { getSession, listSessions } from "@/lib/chatSessions";

export const chatSessionKeys = {
  list: (userId: string | null) => ["chatSessions", userId] as const,
  detail: (userId: string | null, id: string | null) => ["chatSession", userId, id] as const,
};

export const chatSessionListQuery = (userId: string | null) => queryOptions({
  queryKey: chatSessionKeys.list(userId),
  queryFn: listSessions,
  staleTime: 0,
  refetchOnWindowFocus: false,
  retry: false,
});

export const chatSessionQuery = (userId: string | null, id: string | null) => queryOptions({
  queryKey: chatSessionKeys.detail(userId, id),
  queryFn: () => {
    if (!id) throw new Error("A saved conversation is required");
    return getSession(id);
  },
  staleTime: 0,
  refetchOnWindowFocus: false,
  retry: false,
});
