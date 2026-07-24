/**
 * Message rendering for the assistant chat: user bubbles plus the assistant's
 * ordered stream blocks — live/collapsed reasoning, `search_papers` tool-call
 * accordions with ranked hits, and the final cited answer.
 */

import React from "react";

import { ChatMarkdown, PaperCitation } from "@/components/chat/ChatMarkdown";
import { CheckIcon, Chevron, SearchIcon, Spinner } from "@/components/chat/icons";
import { authorsLine, excerpt, venueLine } from "@/components/chat/paperDisplay";
import type {
  AnswerBlock,
  ChatMessage as ChatMessageType,
  ChatPaperHit,
  ReasoningBlock,
  ToolBlock,
} from "@/lib/chat";

const Caret: React.FC = () => <span className="chat-caret" />;

const RestrictedReasoning: React.FC<{
  text: string;
  papers: Record<string, ChatPaperHit>;
  validCitationIds: Set<string>;
}> = ({ text, papers, validCitationIds }) => {
  const parts: React.ReactNode[] = [];
  const pattern = /\[([^\]\n]+)\]\(paper:([^) \t\n]+)\)/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    parts.push(text.slice(cursor, index));
    const [, label, routeId] = match;
    parts.push(
      validCitationIds.has(routeId) || papers[routeId]
        ? <PaperCitation key={`${index}-${routeId}`} routeId={routeId} paper={papers[routeId]}>{label}</PaperCitation>
        : <span key={`${index}-${routeId}`}>{label}</span>,
    );
    cursor = index + match[0].length;
  }
  parts.push(text.slice(cursor));
  return <>{parts}</>;
};

const ReasoningBlockView: React.FC<{
  block: ReasoningBlock;
  papers: Record<string, ChatPaperHit>;
  validCitationIds: Set<string>;
  onToggle: () => void;
}> = ({ block, papers, validCitationIds, onToggle }) => {
  if (block.active) {
    return (
      <div className="chat-reason-live">
        <div className="chat-reason-live-head">
          <Spinner /> <span>Thinking…</span>
        </div>
        <div className="chat-reason-live-body">
          {block.text}
          <Caret />
        </div>
      </div>
    );
  }
  return (
    <div className="chat-reason-done">
      <button type="button" className="chat-reason-done-head" onClick={onToggle}>
        <CheckIcon />
        <span>Thought for a few seconds</span>
        <Chevron open={block.open} />
      </button>
      {block.open && (
        <div className="chat-reason-done-body">
          <RestrictedReasoning text={block.text} papers={papers} validCitationIds={validCitationIds} />
        </div>
      )}
    </div>
  );
};

const ToolBlockView: React.FC<{
  block: ToolBlock;
  papers: Record<string, ChatPaperHit>;
  onToggle: () => void;
}> = ({ block, papers, onToggle }) => {
  const running = block.status === "running";
  const generic = block.schema_version === 2 || Boolean(block.content);
  const failed = block.status === "error" || block.status === "denied";
  const query = typeof block.args.query === "string" ? block.args.query : "";
  const command = typeof block.args.command === "string"
    ? block.args.command
    : typeof block.args.file_path === "string"
      ? block.args.file_path
      : query;
  const output = block.content?.map((item) => item.text).join("") ?? "";
  const statusText = running
    ? "running…"
    : generic
      ? `${block.status} · ${block.took_ms ?? 0} ms`
      : `${block.hits} results · ${block.took_ms} ms`;
  return (
    <div className={`chat-tool${running ? " chat-tool-running" : ""}${failed ? " chat-tool-failed" : ""}`}>
      <button
        type="button"
        className="chat-tool-head"
        onClick={onToggle}
        disabled={running}
        aria-expanded={!running ? block.open : undefined}
      >
        <span className="chat-tool-head-left">
          {running ? <Spinner /> : <SearchIcon />}
          <code className="chat-tool-name">{block.name}</code>
          <span className="chat-tool-query">{generic ? command : `("${query}")`}</span>
        </span>
        <span className="chat-tool-head-right">
          <span className="chat-tool-status">{statusText}</span>
          {!running && <Chevron open={block.open} />}
        </span>
      </button>
      {!running && block.open && (
        <div className="chat-tool-body">
          <div className="chat-tool-args">
            <span className="chat-tool-label">arguments</span>
            <pre>{JSON.stringify(block.args, null, 2)}</pre>
          </div>
          {generic ? (
            <>
              <div className="chat-tool-output-head">
                <span className="chat-tool-label">result</span>
                <button
                  type="button"
                  className="chat-tool-copy"
                  onClick={() => void navigator.clipboard.writeText(output)}
                >
                  Copy
                </button>
              </div>
              <pre className="chat-tool-output"><code>{output}</code></pre>
              {block.metadata?.output_truncated && (
                <div className="chat-tool-truncated">Output was truncated.</div>
              )}
            </>
          ) : (
            <>
              <div className="chat-tool-label chat-tool-results-label">
                returned {block.results?.length ?? 0} papers
              </div>
              <ol className="chat-tool-results">
                {block.results?.map((r) => (
                  <li key={r.route_id} className="chat-hit">
                    <div className="chat-hit-top">
                      <PaperCitation
                        routeId={r.route_id}
                        paper={papers[r.route_id]}
                        className="chat-hit-title"
                      >
                        {r.title}
                      </PaperCitation>
                    </div>
                    <div className="chat-hit-meta">
                      {[authorsLine(r.metadata), venueLine(r.metadata)]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                    <div className="chat-hit-snippet">
                      {excerpt(r)}
                      {r.content_truncated && <span className="chat-hit-truncated"> (truncated)</span>}
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </div>
  );
};

const AnswerBlockView: React.FC<{
  block: AnswerBlock;
  papers: Record<string, ChatPaperHit>;
  validCitationIds: Set<string>;
}> = ({ block, papers, validCitationIds }) => (
  <div className="chat-answer">
    <ChatMarkdown text={block.text} streaming={!block.done} papers={papers} validCitationIds={validCitationIds} />
    {!block.done && Boolean(block.text.trim()) && <Caret />}
  </div>
);

export const UserMessage: React.FC<{ text: string }> = ({ text }) => (
  <div className="chat-msg chat-msg-user">
    <div className="chat-bubble">{text}</div>
  </div>
);

export const AssistantMessage: React.FC<{
  msg: ChatMessageType;
  papers: Record<string, ChatPaperHit>;
  onToggleBlock: (messageId: string, blockIndex: number) => void;
}> = ({ msg, papers, onToggleBlock }) => (
  <div className="chat-msg chat-msg-assistant">
    <div className="chat-msg-blocks">
      {msg.streaming && (msg.blocks?.length ?? 0) === 0 && (
        <div className="chat-reason-live-head">
          <Spinner /> <span>Thinking…</span>
        </div>
      )}
      {msg.blocks?.map((b, i) => {
        const key = `${msg.id}-${i}`;
        const citationSnapshot =
          "citations" in b && b.citations !== undefined
            ? b.citations
            : msg.citations ?? [];
        const validCitationIds = new Set(
          citationSnapshot.map((citation) => citation.route_id),
        );
        if (b.kind === "reasoning") {
          return <ReasoningBlockView key={key} block={b} papers={papers} validCitationIds={validCitationIds} onToggle={() => onToggleBlock(msg.id, i)} />;
        }
        if (b.kind === "tool") {
          return (
            <ToolBlockView key={key} block={b} papers={papers} onToggle={() => onToggleBlock(msg.id, i)} />
          );
        }
        return <AnswerBlockView key={key} block={b} papers={papers} validCitationIds={validCitationIds} />;
      })}
      {msg.error && <div className="chat-error">The assistant hit an error: {msg.error}</div>}
      {!msg.streaming && msg.finishReason && msg.finishReason !== "success" && (
        <div className="chat-finish-note">
          {["tool_limit", "max_turns"].includes(msg.finishReason)
            ? "The assistant stopped at the execution limit."
            : `The assistant stopped early (${msg.finishReason.replace(/_/g, " ")}).`}
        </div>
      )}
    </div>
  </div>
);
