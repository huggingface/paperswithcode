import { DEFAULT_REASONING_EFFORT, type ChatDraft, type ReasoningEffort } from "@/lib/chat";
import { emptyChatDraft, parseChatDraft } from "@/lib/paperSelection";

export const CHAT_DRAFT_KEY = "pwc:chat-oauth-draft";
export const CHAT_MODEL_KEY = "pwc:chat-oauth-model";
export const CHAT_AUTO_SEND_KEY = "pwc:chat-oauth-auto-send";
export const CHAT_AUTH_ATTEMPTED_KEY = "pwc:chat-oauth-attempted";
export const CHAT_REASONING_EFFORT_KEY = "pwc:chat-reasoning-effort";

export interface QueuedChatLaunch {
  prompt: string;
  draft: ChatDraft;
  model: string | null;
  reasoningEffort: ReasoningEffort;
}

/**
 * Preserve a prompt while the chat route lazy-loads or completes OAuth.
 * The chat page clears it only after handing it to the streaming client.
 */
export function queueChatLaunch(
  prompt: string | ChatDraft,
  model?: string,
  options: {
    autoSend?: boolean;
    reasoningEffort?: ReasoningEffort;
  } = {},
): void {
  const rawText = typeof prompt === "string" ? prompt : prompt.text;
  const leading = rawText.length - rawText.trimStart().length;
  const question = rawText.trim();
  if (!question) return;
  const trailingBoundary = leading + question.length;
  const paperMentions = typeof prompt === "string"
    ? []
    : prompt.paperMentions
        .filter((mention) => mention.start >= leading && mention.end <= trailingBoundary)
        .map((mention) => ({ ...mention, start: mention.start - leading, end: mention.end - leading }));
  const draft: ChatDraft = {
    text: question,
    paperMentions,
    ...(typeof prompt !== "string" && prompt.paperSelection
      ? { paperSelection: prompt.paperSelection }
      : {}),
  };
  sessionStorage.setItem(
    CHAT_DRAFT_KEY,
    draft.paperMentions.length || draft.paperSelection ? JSON.stringify(draft) : question,
  );
  if (options.autoSend === false) sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
  else sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
  if (model) sessionStorage.setItem(CHAT_MODEL_KEY, model);
  else sessionStorage.removeItem(CHAT_MODEL_KEY);
  sessionStorage.setItem(
    CHAT_REASONING_EFFORT_KEY,
    options.reasoningEffort ?? DEFAULT_REASONING_EFFORT,
  );
}

export function readQueuedChatLaunch(): QueuedChatLaunch | null {
  if (typeof window === "undefined") return null;
  if (sessionStorage.getItem(CHAT_AUTO_SEND_KEY) !== "1") return null;
  const stored = sessionStorage.getItem(CHAT_DRAFT_KEY)?.trim();
  if (!stored) return null;
  let draft: ChatDraft = emptyChatDraft(stored);
  try {
    draft = parseChatDraft(JSON.parse(stored), stored) ?? emptyChatDraft(stored);
  } catch { /* Legacy and mention-free launches store plain text. */ }
  const prompt = draft.text.trim();
  if (!prompt) return null;
  return {
    prompt,
    draft: { ...draft, text: prompt },
    model: sessionStorage.getItem(CHAT_MODEL_KEY),
    reasoningEffort: (
      ["low", "medium", "high", "max"].includes(
        sessionStorage.getItem(CHAT_REASONING_EFFORT_KEY) ?? "",
      )
        ? sessionStorage.getItem(CHAT_REASONING_EFFORT_KEY)
        : "low"
    ) as ReasoningEffort,
  };
}

export function clearQueuedChatLaunch(): void {
  sessionStorage.removeItem(CHAT_DRAFT_KEY);
  sessionStorage.removeItem(CHAT_MODEL_KEY);
  sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
  sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
  sessionStorage.removeItem(CHAT_REASONING_EFFORT_KEY);
}
