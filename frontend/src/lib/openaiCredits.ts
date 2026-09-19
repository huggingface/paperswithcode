import { useQuery } from "@tanstack/react-query";

import { chatApi } from "@/lib/api/chat";
import type { OpenAIUsageStatus } from "@/lib/api/chat.types";
import type { ChatModelProvider } from "@/lib/chatSessions";

export const OPENAI_USAGE_QUERY_KEY = ["chat", "openai", "usage"] as const;
export const OPENAI_CREDITS_WARNING_USED_PERCENT = 90;
const DISMISSED_KEY = "pwc:chat:openai-credits-notice:dismissed";

export function useOpenAIUsage(enabled = true) {
  return useQuery({
    queryKey: OPENAI_USAGE_QUERY_KEY,
    queryFn: () => chatApi.getOpenAIUsage(),
    enabled,
    staleTime: 30_000,
    retry: false,
    refetchOnWindowFocus: true,
  });
}

export interface OpenAICreditsNotice {
  message: string;
  resetsAt: string;
}

/** The low-credits notice for the selected model, or null when nothing should show. */
export function openAiCreditsNotice(
  usage: OpenAIUsageStatus | undefined,
  provider: ChatModelProvider,
  dismissedResetsAt: string | null,
): OpenAICreditsNotice | null {
  if (!usage || provider !== "openai") return null;
  if (usage.used_percent < OPENAI_CREDITS_WARNING_USED_PERCENT) return null;
  if (dismissedResetsAt === usage.resets_at) return null;
  const reset = new Intl.DateTimeFormat(undefined, { month: "long", day: "numeric" })
    .format(new Date(usage.resets_at));
  return {
    message: `You have ${usage.remaining_percent}% left of your monthly OpenAI credits. They reset on ${reset}.`,
    resetsAt: usage.resets_at,
  };
}

export function readDismissedOpenAICreditsNotice(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

export function dismissOpenAICreditsNotice(resetsAt: string): void {
  try {
    localStorage.setItem(DISMISSED_KEY, resetsAt);
  } catch {
    // Storage is unavailable; the notice simply reappears next visit.
  }
}
