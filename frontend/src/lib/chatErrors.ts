/**
 * Everything the chat UI knows about backend error codes, in one place:
 * how a failed admission is classified, what a failed turn restored from
 * history says, and which recovery actions an assistant error offers.
 */

/** How a rejected stream request is handled by the active turn. */
export type ChatErrorClass =
  /** Provider/credential state changed; refresh it after the turn. */
  | "provider"
  /** The draft itself was refused; restore it for editing. */
  | "draft";

/** Recovery affordances rendered under an assistant error. */
export type ChatErrorAction =
  | "retry"
  | "reauthorize"
  | "hf_billing"
  | "retry_with_luna"
  | "openrouter_budget"
  | "continue_on_production"
  | "openrouter_unavailable"
  | "openrouter_billing"
  | "openrouter_settings"
  | "archive_chats";

interface ChatErrorInfo {
  class?: ChatErrorClass;
  /** Text for a failed turn restored from the saved transcript. */
  restoredMessage?: string;
  /** Live error text; by default it is prefixed with "The assistant hit an error:". */
  display?: { kind: "raw" } | { kind: "fixed"; text: string };
  actions?: readonly ChatErrorAction[];
}

const DRAFT: ChatErrorInfo = { class: "draft" };

export const CHAT_ERRORS: Readonly<Record<string, ChatErrorInfo>> = {
  // Provider and credential failures.
  hf_inference_billing_exhausted: {
    class: "provider",
    restoredMessage: "Hugging Face could not bill this request. Your included credits may be exhausted; enable or review pay-as-you-go billing in Settings.",
    actions: ["hf_billing"],
  },
  hf_inference_billing_required: { actions: ["reauthorize"] },
  hf_inference_credential_expired: {
    restoredMessage: "Your Hugging Face Inference Providers authorization is missing or expired. Re-sign in with Hugging Face to continue.",
    actions: ["reauthorize"],
  },
  hf_sponsored_unavailable: { actions: ["retry_with_luna"] },
  openrouter_monthly_budget_exhausted: {
    class: "provider",
    restoredMessage: "The remaining shared Papers With Code OpenRouter allowance was not enough to continue this response.",
    actions: ["openrouter_budget"],
  },
  openrouter_staging_funding_disabled: {
    restoredMessage: "Shared staging credits have ended because chat is now live on paperswithcode.co. Continue there with your included monthly allowance.",
    actions: ["continue_on_production"],
  },
  openrouter_unavailable: {
    class: "provider",
    restoredMessage: "OpenRouter is currently unavailable. However, you can still bring your own key in Settings.",
    actions: ["openrouter_unavailable"],
  },
  openrouter_byok_credential_invalid: {
    class: "provider",
    restoredMessage: "Your OpenRouter API key is no longer valid. Reconnect it in Settings, then try again.",
    actions: ["openrouter_settings"],
  },
  openrouter_byok_billing_error: {
    class: "provider",
    restoredMessage: "Your OpenRouter key is connected, but OpenRouter rejected billing for the account behind it. A key spending limit is not an account credit balance. Add credits or enable pay-as-you-go in OpenRouter, then try again.",
    actions: ["openrouter_billing"],
  },
  openrouter_byok_rate_limit: {
    class: "provider",
    restoredMessage: "Your OpenRouter API key is temporarily rate-limited.",
    actions: ["openrouter_settings"],
  },
  openai_budget_exhausted: {
    restoredMessage: "The Papers With Code direct OpenAI allowance is exhausted. Select another model or try again later.",
  },
  provider_rate_limit: { restoredMessage: "The selected model is temporarily rate-limited. Try again shortly." },
  provider_timeout: { restoredMessage: "The model provider timed out. Try again shortly." },
  provider_error: {
    restoredMessage: "The model provider failed before completing the response. You can edit and retry your question.",
    actions: ["retry"],
  },
  provider_unavailable: {
    restoredMessage: "The model provider failed before completing the response. You can edit and retry your question.",
  },

  // Conversation and persistence failures.
  context_too_large: {
    restoredMessage: "This conversation is too large for the selected model. Start a new chat or shorten the context.",
    actions: ["retry"],
  },
  persistence_error: {
    restoredMessage: "The response could not be saved. You can edit and retry your question.",
    actions: ["retry"],
  },
  transcript_mirror_error: { restoredMessage: "The conversation could not be saved. Please try again in a new chat." },
  external_worker_lost: {
    restoredMessage: "The assistant worker lost contact before the response could be saved. You can edit and retry your question.",
  },
  chat_disabled_interrupted: {
    display: {
      kind: "fixed",
      text: "Chat was disabled while this response was running. The partial response is saved. Please try again later.",
    },
  },
  chat_session_quota_exceeded: { display: { kind: "raw" }, actions: ["archive_chats"] },

  // Drafts the backend refused before admission.
  paper_context_unavailable: DRAFT,
  paper_mention_unavailable: DRAFT,
  paper_mentions_disabled: DRAFT,
  paper_selection_disabled: DRAFT,
  paper_selection_requires_reader: DRAFT,
  paper_selection_paper_mismatch: DRAFT,
  paper_selection_version_mismatch: DRAFT,
  paper_selection_page_invalid: DRAFT,
  paper_selection_too_large: DRAFT,
  chat_storage_quota_exceeded: DRAFT,
};

const info = (code: string | null | undefined): ChatErrorInfo | undefined => (
  code && Object.prototype.hasOwnProperty.call(CHAT_ERRORS, code) ? CHAT_ERRORS[code] : undefined
);

export function chatErrorClass(code: string | null | undefined): ChatErrorClass | undefined {
  return info(code)?.class;
}

/** Text for a failed turn restored from history. */
export function restoredChatErrorMessage(code: string | null | undefined): string {
  return info(code)?.restoredMessage
    ?? "The response did not complete. You can edit and retry your question.";
}

/** Text for an assistant error shown in the transcript. */
export function displayedChatError(code: string | undefined, message: string): string {
  const display = info(code)?.display;
  if (display?.kind === "fixed") return display.text;
  if (display?.kind === "raw") return message;
  return `The assistant hit an error: ${message}`;
}

export function chatErrorActions(code: string | undefined): readonly ChatErrorAction[] {
  return info(code)?.actions ?? [];
}
