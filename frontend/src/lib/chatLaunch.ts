import { DEFAULT_REASONING_EFFORT, type ChatDraft, type ReasoningEffort } from "@/lib/chat";
import { emptyChatDraft, parseChatDraft } from "@/lib/paperSelection";

export const CHAT_DRAFT_KEY = "pwc:chat-oauth-draft";
export const CHAT_MODEL_KEY = "pwc:chat-oauth-model";
export const CHAT_AUTO_SEND_KEY = "pwc:chat-oauth-auto-send";
export const CHAT_AUTH_ATTEMPTED_KEY = "pwc:chat-oauth-attempted";
export const CHAT_REASONING_EFFORT_KEY = "pwc:chat-reasoning-effort";

export interface QueuedChatLaunch {
  draft: ChatDraft;
  model: string | null;
}

/** Stored drafts are JSON when they carry mentions or a selection, else plain text. */
function parseStoredDraft(stored: string): ChatDraft {
  try {
    return parseChatDraft(JSON.parse(stored), stored) ?? emptyChatDraft(stored);
  } catch { /* Legacy and mention-free launches store plain text. */ }
  return emptyChatDraft(stored);
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
  const draft = parseStoredDraft(stored);
  const prompt = draft.text.trim();
  if (!prompt) return null;
  return {
    draft: { ...draft, text: prompt },
    model: sessionStorage.getItem(CHAT_MODEL_KEY),
  };
}

/** The draft kept across a chat launch or authorization, whether or not it auto-sends. */
export function readStoredChatDraft(): { draft: ChatDraft; autoSend: boolean } | null {
  const stored = sessionStorage.getItem(CHAT_DRAFT_KEY);
  if (!stored) return null;
  return {
    draft: parseStoredDraft(stored),
    autoSend: sessionStorage.getItem(CHAT_AUTO_SEND_KEY) === "1",
  };
}

/** Keep the prompt across the Hugging Face authorization redirect, then send it on return. */
export function queueAuthorizedChatSend(
  draft: ChatDraft,
  model: string,
  reasoningEffort: ReasoningEffort,
): void {
  sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(draft));
  sessionStorage.setItem(CHAT_MODEL_KEY, model);
  sessionStorage.setItem(CHAT_REASONING_EFFORT_KEY, reasoningEffort);
  sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
  sessionStorage.setItem(CHAT_AUTH_ATTEMPTED_KEY, "1");
}

/** Keep the prompt for a manual retry after authorization did not complete. */
export function keepChatDraftForRetry(draft: ChatDraft, model: string): void {
  sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(draft));
  sessionStorage.setItem(CHAT_MODEL_KEY, model);
  sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
  sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
}

export const chatAuthorizationAttempted = (): boolean => (
  sessionStorage.getItem(CHAT_AUTH_ATTEMPTED_KEY) === "1"
);

export const storedChatModel = (): string | null => sessionStorage.getItem(CHAT_MODEL_KEY);

/** The composer now holds the restored prompt; later chat surfaces must not restore it again. */
export const forgetStoredChatDraft = (): void => sessionStorage.removeItem(CHAT_DRAFT_KEY);

/** A send is in flight: a remount must not send the queued prompt again. */
export const stopChatAutoSend = (): void => sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);

export function clearQueuedChatLaunch(): void {
  sessionStorage.removeItem(CHAT_DRAFT_KEY);
  sessionStorage.removeItem(CHAT_MODEL_KEY);
  sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
  sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
  sessionStorage.removeItem(CHAT_REASONING_EFFORT_KEY);
}
