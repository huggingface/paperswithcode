import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { chatApi } from "@/lib/api/chat";

/** Sends a visitor who cannot open `/chat/:id` to that chat's public share, if one exists. */
export function usePublicShareRedirect(sessionId: string | undefined, notOwned: boolean) {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["chatSessionPublicShare", sessionId],
    queryFn: () => chatApi.getSessionPublicShare(sessionId ?? ""),
    enabled: Boolean(sessionId) && notOwned,
    retry: false,
  });
  const path = query.data?.public_path;
  useEffect(() => {
    if (path) navigate(path, { replace: true });
  }, [navigate, path]);
  return { pending: query.isFetching || Boolean(path) };
}
