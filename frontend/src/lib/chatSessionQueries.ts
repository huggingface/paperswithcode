import { queryOptions } from "@tanstack/react-query";
import { chatApi } from "@/lib/api/chat";
import { listSessions } from "@/lib/chatSessions";

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
    return chatApi.getSession(id);
  },
  staleTime: 0,
  refetchOnWindowFocus: false,
  retry: false,
});

/** Model discovery for the signed-in user; Settings can share these options. */
export const chatModelsQuery = (userId: string | null) => queryOptions({
  queryKey: ["chat", "models", userId] as const,
  queryFn: () => chatApi.getModels(),
});

/** Deployment chat switches, polled while a chat surface is open. */
export const chatAvailabilityQuery = () => queryOptions({
  queryKey: ["chatAvailability"] as const,
  queryFn: () => chatApi.getAvailability(),
  refetchInterval: 30000,
  retry: false,
});

/** Query keys for private chat artifacts, shared by the poster and paper panels. */
export const chatArtifactKeys = {
  posterVersions: (artifactId: string | undefined) => ["chatArtifact", artifactId, "posterVersions"] as const,
  latexPaper: (artifactId: string | undefined) => ["chatArtifact", artifactId, "latexPaper"] as const,
  history: (artifactId: string | undefined, cursor?: string | null) => (
    cursor === undefined
      ? ["chatArtifact", artifactId, "history"] as const
      : ["chatArtifact", artifactId, "history", cursor] as const
  ),
  manifest: (artifactId: string | undefined, versionId?: string) => (
    versionId === undefined
      ? ["chatArtifact", artifactId, "manifest"] as const
      : ["chatArtifact", artifactId, "manifest", versionId] as const
  ),
  source: (artifactId: string | undefined, versionId: string | undefined, path: string | null) => (
    ["chatArtifact", artifactId, "source", versionId, path] as const
  ),
  sourceFiles: (artifactId: string | undefined, versionId?: string) => (
    versionId === undefined
      ? ["chatArtifact", artifactId, "sourceFiles"] as const
      : ["chatArtifact", artifactId, "sourceFiles", versionId] as const
  ),
};
