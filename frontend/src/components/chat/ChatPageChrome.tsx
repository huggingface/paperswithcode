import React from "react";
import { Link } from "react-router-dom";
import { MoreVertical, X } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ChatModelProvider } from "@/lib/api/chat.types";
import {
  dismissOpenAICreditsNotice,
  openAiCreditsNotice,
  readDismissedOpenAICreditsNotice,
  useOpenAIUsage,
} from "@/lib/openaiCredits";
import { ArtifactWorkspace } from "./ArtifactWorkspace";
import { ArtifactPanelProvider, canNavigateAwayFromArtifact } from "./useArtifactPanel";

/* Page chrome around the chat conversation, shared by /chat and the paper reader. */

export const GeneralArtifactProvider: React.FC<{
  enabled: boolean;
  workspaceKey: string;
  children: React.ReactNode;
  onAskAiFix?: (prompt: string) => void;
}> = ({ enabled, workspaceKey, children, onAskAiFix }) => enabled
  ? <ArtifactPanelProvider workspaceKey={workspaceKey} onAskAiFix={onAskAiFix}>{children}</ArtifactPanelProvider>
  : <>{children}</>;

export const GeneralArtifactWorkspace: React.FC<{
  enabled: boolean;
  children: React.ReactNode;
}> = ({ enabled, children }) => enabled
  ? <ArtifactWorkspace variant="chat">{children}</ArtifactWorkspace>
  : <>{children}</>;

/** The direct OpenAI allowance notice, dismissible until its allowance resets. */
export const OpenAICreditsNotice: React.FC<{ provider: ChatModelProvider; enabled: boolean }> = ({ provider, enabled }) => {
  const usageQuery = useOpenAIUsage(enabled);
  const [dismissed, setDismissed] = React.useState(() => readDismissedOpenAICreditsNotice());
  const notice = openAiCreditsNotice(usageQuery.data, provider, dismissed);
  if (!notice) return null;
  return <div className="chat-credits-notice" role="status">
    <span>{notice.message}</span>
    <button
      type="button"
      className="chat-credits-notice-close"
      aria-label="Dismiss credits notice"
      onClick={() => {
        dismissOpenAICreditsNotice(notice.resetsAt);
        setDismissed(notice.resetsAt);
      }}
    >
      ×
    </button>
  </div>;
};

export const ReaderChatMenu: React.FC<{ onNewChat: () => void; onClose?: () => void }> = ({ onNewChat, onClose }) => <>
  <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <button type="button" className="icon-btn chat-reader-icon-btn" aria-label="Chat options" title="Chat options">
        <MoreVertical aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem onSelect={onNewChat}>New chat</DropdownMenuItem>
      <DropdownMenuItem asChild><Link to="/chat">All chats</Link></DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
  {onClose && (
    <button type="button" className="icon-btn chat-reader-icon-btn" onClick={onClose} aria-label="Close chat" title="Close chat">
      <X aria-hidden="true" />
    </button>
  )}
</>;

/** Opens the conversation's paper in the reader, which resumes this chat on its last page. */
export const OpenReaderLink: React.FC<{ routeId: string; sessionId: string; page?: number }> = ({ routeId, sessionId, page }) => (
  <Link
    className="chat-reader-action"
    to={`/pdf/${routeId}`}
    onClick={(event) => {
      if (!canNavigateAwayFromArtifact()) {
        event.preventDefault();
        return;
      }
      sessionStorage.setItem(`pwc:reader:session:${routeId}`, sessionId);
      if (page) {
        sessionStorage.setItem(`pwc:reader:page:${routeId}`, String(page));
      }
    }}
  >Open reader</Link>
);

export const ChatEmptyState: React.FC<{
  mode: "general" | "paper";
  staging: boolean;
  children: React.ReactNode;
}> = ({ mode, staging, children }) => <div className="chat-empty"><div className="chat-empty-inner">
  <div className="chat-empty-eyebrow">{mode === "paper" ? "Paper chat" : "Research chat"}</div>
  <h1 className="chat-empty-title">{mode === "paper" ? "Ask about this paper" : <>Ask <em>Papers With Code</em></>}</h1>
  <p className="chat-empty-sub">{mode === "paper" ? "Questions are grounded in the open paper. Add up to three other papers with @." : "Answers are grounded in a live hybrid search over papers, tasks, and benchmarks — with citations you can follow."}</p>
  {staging && <p className="chat-staging-access-note">
    This is a limited staging preview. Only approved Hugging Face users can start chats.
  </p>}
  {children}
</div></div>;
