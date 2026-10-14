import type { ComponentProps } from "react";

import Composer from "./Composer";
import { BillingNotice } from "./ChatNotices";
import { isChatLive } from "@/lib/chat";
import type { ChatModelChoice } from "@/lib/chatSessions";

interface ChatComposerSurfaceProps {
  variant: "empty" | "followup";
  composerProps: ComponentProps<typeof Composer>;
  provider: ChatModelChoice["provider"];
  paused: boolean;
  /** Why the last send was rejected; shown next to the restored draft. */
  error?: string;
  suggestions?: readonly string[];
}

export function ChatComposerSurface({
  variant,
  composerProps,
  provider,
  paused,
  error,
  suggestions = [],
}: ChatComposerSurfaceProps) {
  const content = <>
    <BillingNotice provider={provider} />
    {paused && <div
      id="chat-paused-description"
      className="chat-paused-banner"
      role="status"
    >
      Chat is temporarily disabled. You can keep browsing and editing your
      conversations. New research runs will return when chat is restored.
    </div>}
    {error && <div className="chat-composer-error" role="alert">{error}</div>}
    <Composer
      {...composerProps}
      {...(variant === "empty"
        ? { autoFocus: true }
        : { placeholder: composerProps.draft?.text ? "Edit and send again…" : "Ask a follow-up…" })}
    />
    {variant === "empty" && <div className="chat-examples">
      {suggestions.map((example) => <button
        type="button"
        key={example}
        className="chat-example"
        disabled={paused}
        onClick={() => composerProps.onSend({
          text: example,
          paperMentions: [],
          ...(composerProps.draft?.paperSelection
            ? { paperSelection: composerProps.draft.paperSelection }
            : {}),
        })}
      >{example}</button>)}
    </div>}
  </>;

  if (variant === "empty") return content;
  return (
    <div className="chat-composer-wrap">
      <div className="chat-composer-inner">
        {content}
        <div className="chat-composer-foot">{isChatLive() ? <>
          {provider === "huggingface" && <span className="chat-provider-attribution">Powered by 🤗 <a href="https://huggingface.co/docs/inference-providers/en/index" target="_blank" rel="noreferrer">Inference Providers</a>.</span>}
          {provider === "openrouter" && <span className="chat-provider-attribution">Powered by <a href="https://openrouter.ai" target="_blank" rel="noreferrer">OpenRouter</a>.</span>}
          {provider === "openai" && <span className="chat-provider-attribution">Powered by OpenAI.</span>}
          <span>The AI assistant can make mistakes. Double-check responses.</span>
        </> : <>Assistant preview — responses are simulated.</>}</div>
      </div>
    </div>
  );
}
