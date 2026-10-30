import React from "react";

import type { ChatMessage } from "@/lib/chat";
import { chatErrorActions, displayedChatError, type ChatErrorAction } from "@/lib/chatErrors";

const HF_PRO_URL = "https://huggingface.co/pro";
const HF_PRICING_URL = "https://huggingface.co/docs/inference-providers/pricing";
const PRODUCTION_CHAT_URL = "https://paperswithcode.co/chat";

export interface HfBillingGuidance {
  account_type: "Free" | "PRO" | "Organization" | null;
  bill_to: string | null;
  usage_url: string;
}

interface AssistantErrorProps {
  msg: ChatMessage & { error: string };
  onRetryCompaction?: () => void;
  onRetryWithLuna?: () => void;
  onArchiveOldChats?: () => void;
  onArchiveOldestChats?: () => void;
  archivePending: "old" | "oldest" | null;
  hfBilling: HfBillingGuidance | null;
  openRouterFallbackEnabled: boolean;
}

/** Recovery affordances for one error code; see `CHAT_ERRORS`. */
const ErrorAction: React.FC<AssistantErrorProps & { action: Exclude<ChatErrorAction, "retry"> }> = ({
  action, onRetryWithLuna, onArchiveOldChats, onArchiveOldestChats, archivePending, hfBilling, openRouterFallbackEnabled,
}) => {
  switch (action) {
    case "reauthorize":
      return <a href="/settings">
        Re-sign in with Hugging Face
      </a>;
    case "hf_billing":
      return <>
        {onRetryWithLuna && <button type="button" onClick={onRetryWithLuna}>Retry with GPT-6 Luna</button>}
        {hfBilling?.account_type === "Free" && !hfBilling.bill_to
          ? <a href={HF_PRO_URL} target="_blank" rel="noreferrer">
              Upgrade to Hugging Face PRO — $9/month for 20× more included credits
            </a>
          : <a href={hfBilling?.usage_url ?? "/settings"} target={hfBilling ? "_blank" : undefined} rel={hfBilling ? "noreferrer" : undefined}>
              Review Hugging Face usage and billing
            </a>}
        <a href={HF_PRICING_URL} target="_blank" rel="noreferrer">
          Inference Providers pricing and billing details
        </a>
      </>;
    case "retry_with_luna":
      return onRetryWithLuna ? <button type="button" onClick={onRetryWithLuna}>Retry with GPT-6 Luna</button> : null;
    case "openrouter_budget":
      return <>
        {openRouterFallbackEnabled
          ? <span>This response started on the shared allowance. Your connected OpenRouter key will be used when you explicitly retry.</span>
          : <a href="/settings#openrouter-byok">Connect your own OpenRouter key</a>}
        <span>Or select a Hugging Face-backed model and explicitly retry.</span>
      </>;
    case "continue_on_production":
      return <a href={PRODUCTION_CHAT_URL}>Continue on paperswithcode.co</a>;
    case "openrouter_unavailable":
      return <>
        <a href="/settings#openrouter-byok">Bring your own key in Settings</a>
        <a href="https://github.com/huggingface/paperswithcode-feedback" target="_blank" rel="noreferrer">File an issue</a>
      </>;
    case "openrouter_billing":
      return <a href="https://openrouter.ai/settings/credits" target="_blank" rel="noreferrer">Review OpenRouter billing</a>;
    case "openrouter_settings":
      return <a href="/settings#openrouter-byok">Review OpenRouter settings</a>;
    case "archive_chats":
      return (onArchiveOldChats || onArchiveOldestChats) ? <span className="chat-error-actions">
        {onArchiveOldChats && (
          <button type="button" disabled={archivePending !== null} onClick={onArchiveOldChats}>
            {archivePending === "old" ? "Archiving…" : "Archive chats older than 30 days"}
          </button>
        )}
        {onArchiveOldestChats && (
          <button type="button" disabled={archivePending !== null} onClick={onArchiveOldestChats}>
            {archivePending === "oldest" ? "Archiving…" : "Archive oldest 50 chats"}
          </button>
        )}
      </span> : null;
  }
};

export const AssistantError: React.FC<AssistantErrorProps> = (props) => {
  const { msg, onRetryCompaction } = props;
  const actions = chatErrorActions(msg.errorCode);
  return <div className="chat-error">
    {msg.blocks?.some((block) => block.kind === "answer" && block.text.trim()) && <strong>Incomplete—response interrupted. </strong>}
    {actions.includes("retry") && onRetryCompaction && <button type="button" onClick={onRetryCompaction}>Retry</button>}
    <span>{displayedChatError(msg.errorCode, msg.error)}</span>
    {actions.map((action) => action === "retry" ? null : <ErrorAction key={action} {...props} action={action} />)}
  </div>;
};
