import { CompactionStatus } from "./CompactionStatus";
/**
 * Message rendering for the assistant chat: user bubbles plus the assistant's
 * ordered stream blocks — live/collapsed reasoning, `search_papers` tool-call
 * accordions with ranked hits, and the final cited answer.
 */

import React from "react";
import { Check, Copy, FileText, Pencil, ThumbsDown, ThumbsUp } from "lucide-react";

import { ChatMarkdown, PaperCitation } from "@/components/chat/ChatMarkdown";
import { McpAppFrame } from "@/components/chat/McpAppFrame";
import { PosterArtifact } from "@/components/chat/PosterArtifact";
import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { PaperMentionHighlights } from "@/components/chat/PaperMentionHighlights";
import { PaperSelectionCard } from "@/components/chat/PaperSelectionCard";
import { CheckIcon, Chevron, SearchIcon, Spinner } from "@/components/chat/icons";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import { PaperPreviewLink } from "@/components/paper-preview/PaperPreviewLink";
import { authorsLine, excerpt, venueLine } from "@/components/chat/paperDisplay";
import { chatApi } from "@/lib/api/chat";
import type {
  AnswerBlock,
  AppBlock,
  ChatMessage as ChatMessageType,
  ChatCitation,
  ChatPaperHit,
  ChatDraft,
  PaperMentionDraft,
  PaperSelectionDraft,
  ReasoningBlock,
  ToolBlock,
} from "@/lib/chat";

const HF_PRO_URL = "https://huggingface.co/pro";
const HF_PRICING_URL = "https://huggingface.co/docs/inference-providers/pricing";
const PRODUCTION_CHAT_URL = "https://paperswithcode.co/chat";

export interface HfBillingGuidance {
  account_type: "Free" | "PRO" | "Organization" | null;
  bill_to: string | null;
  usage_url: string;
}

const Caret: React.FC = () => <span className="chat-caret" />;

const isWaitingForAssistant = (msg: ChatMessageType): boolean => {
  if (!msg.streaming) return false;
  const last = msg.blocks?.at(-1);
  if (!last) return true;
  if (last.kind === "reasoning") return !last.active;
  if (last.kind === "tool") return last.status !== "running";
  return false;
};

const selectDoubleClickedWord = (event: React.MouseEvent<HTMLDivElement>) => {
  const element = event.currentTarget;
  const document = element.ownerDocument;
  const point = document.caretPositionFromPoint?.(event.clientX, event.clientY);
  const fallbackRange = point
    ? null
    : document.caretRangeFromPoint?.(event.clientX, event.clientY);
  const node = point?.offsetNode ?? fallbackRange?.startContainer;
  const rawOffset = point?.offset ?? fallbackRange?.startOffset;
  if (!(node instanceof Text) || rawOffset === undefined || !element.contains(node)) return;

  const text = node.data;
  const wordCharacter = /[\p{L}\p{M}\p{N}_'-]/u;
  let start = Math.min(rawOffset, text.length);
  let end = start;
  while (start > 0 && wordCharacter.test(text[start - 1])) start -= 1;
  while (end < text.length && wordCharacter.test(text[end])) end += 1;
  if (start === end) return;

  const selection = document.getSelection();
  if (!selection) return;
  const range = document.createRange();
  range.setStart(node, start);
  range.setEnd(node, end);
  selection.removeAllRanges();
  selection.addRange(range);
};

const URL_PATTERN = /\bhttps?:\/\/[^\s<>"]+/gi;
// Sentence punctuation that usually ends a sentence rather than the URL.
const URL_TRAILING_PUNCTUATION = /[.,;:!?'"\]}>*_]+$/;

const trimUrl = (url: string) => {
  let trimmed = url.replace(URL_TRAILING_PUNCTUATION, "");
  // Keep a closing parenthesis only when the URL itself opened one.
  while (trimmed.endsWith(")") && trimmed.split("(").length < trimmed.split(")").length) {
    trimmed = trimmed.slice(0, -1).replace(URL_TRAILING_PUNCTUATION, "");
  }
  return trimmed;
};

const linkifyText = (text: string, keyPrefix: string): React.ReactNode[] => {
  const pieces: React.ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    const url = trimUrl(match[0]);
    if (url.endsWith("://")) continue;
    pieces.push(text.slice(cursor, match.index));
    pieces.push(
      <a className="chat-user-link" href={url} target="_blank" rel="noopener noreferrer" key={`${keyPrefix}-${match.index}`}>
        {url}
      </a>,
    );
    cursor = match.index + url.length;
  }
  pieces.push(text.slice(cursor));
  return pieces;
};

const InlinePaperMentions: React.FC<{
  text: string;
  mentions: PaperMentionDraft[];
}> = ({ text, mentions }) => {
  const pieces: React.ReactNode[] = [];
  let cursor = 0;
  for (const mention of [...mentions].sort((a, b) => a.start - b.start)) {
    const marker = text.slice(mention.start, mention.end);
    if (
      mention.start < cursor
      || mention.end > text.length
      || (marker !== mention.title && marker !== `@${mention.title}`)
    ) continue;
    pieces.push(...linkifyText(text.slice(cursor, mention.start), `text-${cursor}`));
    pieces.push(
      <span className="chat-inline-paper-mention" key={mention.key}>
        <FileText size={13} aria-hidden="true" />
        <PaperPreviewLink routeId={mention.route_id} className="chat-inline-paper-link">
          {marker.startsWith("@") ? marker.slice(1) : marker}
        </PaperPreviewLink>
      </span>,
    );
    cursor = mention.end;
  }
  pieces.push(...linkifyText(text.slice(cursor), `text-${cursor}`));
  return <>{pieces}</>;
};

const ReasoningBlockView: React.FC<{
  block: ReasoningBlock;
  papers: Record<string, ChatPaperHit>;
  citations: Record<string, ChatCitation>;
  webCitations: Record<string, ChatCitation>;
  onToggle: () => void;
}> = ({ block, papers, citations, webCitations, onToggle }) => {
  if (block.active) {
    return (
      <div className="chat-reason-live">
        <div className="chat-reason-live-head">
          <Spinner /> <span>Thinking…</span>
        </div>
        <div className="chat-reason-live-body chat-answer chat-reason-markdown">
          <ChatMarkdown
            text={block.text}
            streaming
            papers={papers}
            citations={citations}
            webCitations={webCitations}
          />
          <Caret />
        </div>
      </div>
    );
  }
  return (
    <div className="chat-reason-done">
      <button
        type="button"
        className="chat-reason-done-head"
        onClick={onToggle}
        aria-expanded={block.open}
      >
        <CheckIcon />
        <span>Thought for a few seconds</span>
        <Chevron open={block.open} />
      </button>
      {block.open && (
        <div className="chat-reason-done-body chat-answer chat-reason-markdown">
          <ChatMarkdown
            text={block.text}
            papers={papers}
            citations={citations}
            webCitations={webCitations}
          />
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
  const streamingArguments = running && block.argumentState === "streaming";
  const generic = block.schema_version === 2 || Boolean(block.content);
  const failed = block.status === "error" || block.status === "denied";
  const query = typeof block.args.query === "string" ? block.args.query : "";
  const command = typeof block.args.command === "string"
    ? block.args.command
    : typeof block.args.file_path === "string"
      ? block.args.file_path
      : query;
  const argumentSummary = block.name.startsWith("pwc_")
    ? Object.entries(block.args)
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
      .join(" · ")
    : generic ? command : `("${query}")`;
  const output = block.content?.map((item) => item.text).join("") ?? "";
  const statusText = streamingArguments
    ? "streaming arguments…"
    : running
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
        aria-expanded={block.open}
      >
        <span className="chat-tool-head-left">
          {running ? <Spinner /> : <SearchIcon />}
          <code className="chat-tool-name">{block.name}</code>
          <span className="chat-tool-query" title={argumentSummary}>{argumentSummary}</span>
        </span>
        <span className="chat-tool-head-right">
          <span className="chat-tool-status">{statusText}</span>
          <Chevron open={block.open} />
        </span>
      </button>
      {block.open && (
        <div className="chat-tool-body">
          <div className="chat-tool-args">
            <span className="chat-tool-label">
              arguments{block.arguments_redacted ? " · redacted" : ""}
            </span>
            <pre>{block.argumentState === "streaming" && !block.arguments_redacted
              ? (block.argumentText || JSON.stringify(block.args, null, 2))
              : JSON.stringify(block.args, null, 2)}</pre>
          </div>
          {!running && generic ? (
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
          ) : !running ? (
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
          ) : null}
        </div>
      )}
    </div>
  );
};

const AnswerBlockView: React.FC<{
  block: AnswerBlock;
  papers: Record<string, ChatPaperHit>;
  citations: Record<string, ChatCitation>;
  webCitations: Record<string, ChatCitation>;
  streaming: boolean;
}> = ({ block, papers, citations, webCitations, streaming }) => (
  <div className="chat-answer">
    <ChatMarkdown text={block.text} streaming={streaming} papers={papers} citations={citations} webCitations={webCitations} />
    {streaming && Boolean(block.text.trim()) && <Caret />}
  </div>
);

const AppBlockView: React.FC<{ block: AppBlock }> = ({ block }) => <McpAppFrame block={block} />;

interface UserEditorProps {
  id?: string;
  text: string;
  paperSelection?: PaperSelectionDraft;
  editNotice?: string;
  onCancel?: () => void;
  onResend?: (text: string) => boolean;
  onResendDraft?: (draft: ChatDraft) => boolean;
}

const useEditorTextarea = (text: string) => {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const resize = React.useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const maximum = Math.max(120, window.innerHeight * 0.4);
    textarea.style.height = `${Math.min(textarea.scrollHeight, maximum)}px`;
    textarea.style.overflowY = textarea.scrollHeight > maximum ? "auto" : "hidden";
  }, []);
  React.useLayoutEffect(() => {
    textareaRef.current?.focus();
    textareaRef.current?.setSelectionRange(text.length, text.length);
    resize();
  }, [resize, text.length]);
  return { textareaRef, resize };
};

const PlainUserEditor: React.FC<UserEditorProps> = ({ id, text, paperSelection, editNotice, onCancel, onResend, onResendDraft }) => {
  const [value, setValue] = React.useState(text);
  const [selection, setSelection] = React.useState(paperSelection);
  const [submitting, setSubmitting] = React.useState(false);
  const { textareaRef, resize } = useEditorTextarea(text);
  React.useLayoutEffect(resize, [resize, value]);
  const valid = Boolean(value.trim()) && value.length <= 8_000;
  const resend = () => {
    if (!valid || submitting) return;
    setSubmitting(true);
    const accepted = onResendDraft?.({
      text: value,
      paperMentions: [],
      ...(selection ? { paperSelection: selection } : {}),
    }) ?? onResend?.(value) ?? false;
    if (!accepted) setSubmitting(false);
  };
  return <div className="chat-msg chat-msg-user chat-msg-user-editing" data-message-id={id}>
    <div className="chat-inline-editor">
      {selection && <PaperSelectionCard selection={selection} editable onRemove={() => setSelection(undefined)} />}
      <textarea ref={textareaRef} className="chat-inline-editor-textarea" aria-label="Edit message" value={value} maxLength={8_000}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") { event.preventDefault(); onCancel?.(); }
          else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); resend(); }
        }} />
      {editNotice && <div className="chat-inline-editor-notice">{editNotice}</div>}
      <div className="chat-inline-editor-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button type="button" className="chat-inline-editor-send" disabled={!valid || submitting} onClick={resend}>Send</button>
      </div>
    </div>
  </div>;
};

const MentionUserEditor: React.FC<UserEditorProps & { paperMentions: PaperMentionDraft[]; enabled: boolean }> = ({
  id, text, paperMentions, paperSelection, enabled, editNotice, onCancel, onResend, onResendDraft,
}) => {
  const [value, setValue] = React.useState<ChatDraft>({
    text,
    paperMentions,
    ...(paperSelection ? { paperSelection } : {}),
  });
  const [submitting, setSubmitting] = React.useState(false);
  const [scrollTop, setScrollTop] = React.useState(0);
  const { textareaRef, resize } = useEditorTextarea(text);
  const editor = usePaperMentions({ draft: value, onChange: setValue, enabled, textareaRef });
  React.useLayoutEffect(resize, [resize, value.text]);
  const valid = Boolean(value.text.trim()) && value.text.length <= 8_000 && (enabled || value.paperMentions.length === 0);
  const resend = () => {
    if (!valid || submitting) return;
    setSubmitting(true);
    const accepted = onResendDraft?.(value) ?? onResend?.(value.text) ?? false;
    if (!accepted) setSubmitting(false);
  };
  return <div className="chat-msg chat-msg-user chat-msg-user-editing" data-message-id={id}>
    <div className="chat-inline-editor">
      {value.paperSelection && (
        <PaperSelectionCard
          selection={value.paperSelection}
          editable
          onRemove={() => setValue({ text: value.text, paperMentions: value.paperMentions })}
        />
      )}
      <div className="chat-inline-editor-textarea-wrap">
        <PaperMentionHighlights text={value.text} mentions={value.paperMentions} scrollTop={scrollTop} variant="editor" />
        <textarea ref={textareaRef} className="chat-inline-editor-textarea" aria-label="Edit message" value={value.text} maxLength={8_000}
          role="combobox" aria-autocomplete="list" aria-expanded={editor.open}
          aria-controls={editor.open ? editor.pickerId : undefined}
          aria-activedescendant={editor.open && editor.results.length ? `${editor.optionIdPrefix}-${editor.activeIndex}` : undefined}
          onChange={(event) => editor.updateText(event.target.value, event.target.selectionStart)}
          onSelect={(event) => editor.refresh(event.currentTarget.selectionStart)}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          onKeyDown={(event) => {
            if (editor.keyDown(event)) return;
            if (event.key === "Escape") { event.preventDefault(); onCancel?.(); }
            else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); resend(); }
          }} />
        <PaperMentionPicker open={editor.open} query={editor.query} results={editor.results} activeIndex={editor.activeIndex} loading={editor.loading} error={editor.error} onSelect={editor.select} id={editor.pickerId} optionIdPrefix={editor.optionIdPrefix} />
      </div>
      {!enabled && value.paperMentions.length > 0 && <div className="chat-inline-editor-notice" role="status">Paper mentions are currently disabled. Remove them before sending.</div>}
      {editNotice && <div className="chat-inline-editor-notice">{editNotice}</div>}
      <div className="chat-inline-editor-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button type="button" className="chat-inline-editor-send" disabled={!valid || submitting} onClick={resend}>Send</button>
      </div>
    </div>
  </div>;
};

export const UserMessage: React.FC<{
  id?: string;
  text: string;
  paperMentions?: PaperMentionDraft[];
  paperSelection?: PaperSelectionDraft;
  paperMentionsEnabled?: boolean;
  isInitial?: boolean;
  editingAllowed?: boolean;
  editing?: boolean;
  editNotice?: string;
  onEdit?: () => void;
  onCancel?: () => void;
  onResend?: (text: string) => boolean;
  onResendDraft?: (draft: ChatDraft) => boolean;
}> = ({
  id,
  text,
  paperMentions = [],
  paperSelection,
  paperMentionsEnabled = false,
  editingAllowed = false,
  editing = false,
  editNotice,
  onEdit,
  onCancel,
  onResend,
  onResendDraft,
}) => {
  const [copied, setCopied] = React.useState(false);
  const copiedTimerRef = React.useRef<number | null>(null);

  React.useEffect(() => () => {
    if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
  }, []);

  const copyMessage = async () => {
    if (!navigator.clipboard?.writeText) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (copiedTimerRef.current !== null) window.clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = window.setTimeout(() => setCopied(false), 1_500);
    } catch {
      // Clipboard access can be denied by browser permissions; leave the action retryable.
    }
  };

  if (editing) {
    if (!paperMentionsEnabled && paperMentions.length === 0) {
      return <PlainUserEditor id={id} text={text} paperSelection={paperSelection} editNotice={editNotice} onCancel={onCancel} onResend={onResend} onResendDraft={onResendDraft} />;
    }
    return <MentionUserEditor id={id} text={text} paperMentions={paperMentions} paperSelection={paperSelection} enabled={paperMentionsEnabled} editNotice={editNotice} onCancel={onCancel} onResend={onResend} onResendDraft={onResendDraft} />;
  }

  return (
    <div className="chat-msg chat-msg-user" data-message-id={id}>
      <div className="chat-user-message-wrap">
        {paperSelection && <PaperSelectionCard selection={paperSelection} />}
        <div className="chat-bubble" onDoubleClick={selectDoubleClickedWord}>
          <InlinePaperMentions text={text} mentions={paperMentions} />
        </div>
        <div className="chat-user-actions">
          <button
            type="button"
            className="chat-user-action"
            aria-label={copied ? "Message copied" : "Copy message"}
            title={copied ? "Copied" : "Copy"}
            onClick={() => void copyMessage()}
          >
            {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          </button>
          {editingAllowed && (
            <button
              type="button"
              className="chat-user-action"
              aria-label="Edit message"
              title="Edit"
              onClick={onEdit}
            >
              <Pencil aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export const AssistantMessage: React.FC<{
  msg: ChatMessageType;
  papers: Record<string, ChatPaperHit>;
  onToggleBlock: (messageId: string, blockIndex: number) => void;
  onRetryCompaction?: () => void;
  onRetryWithLuna?: () => void;
  onArchiveOldChats?: () => void;
  onArchiveOldestChats?: () => void;
  archivePending?: "old" | "oldest" | null;
  hfBilling?: HfBillingGuidance | null;
  openRouterFallbackEnabled?: boolean;
  feedbackEnabled?: boolean;
}> = ({ msg, papers, onToggleBlock, onRetryCompaction, onRetryWithLuna, onArchiveOldChats, onArchiveOldestChats, archivePending = null, hfBilling = null, openRouterFallbackEnabled = false, feedbackEnabled = false }) => {
  const [feedback, setFeedback] = React.useState<boolean | null>(null);
  const [feedbackPending, setFeedbackPending] = React.useState(false);
  const [feedbackError, setFeedbackError] = React.useState(false);
  const [feedbackComposerOpen, setFeedbackComposerOpen] = React.useState(false);
  const [feedbackComment, setFeedbackComment] = React.useState("");
  const feedbackTextareaRef = React.useRef<HTMLTextAreaElement>(null);
  const feedbackPanelId = `chat-feedback-panel-${msg.id}`;
  const canRate = feedbackEnabled
    && !msg.streaming
    && !msg.error
    && Boolean(msg.blocks?.some((block) => block.kind === "answer" && block.text.trim()));

  React.useEffect(() => {
    if (feedbackComposerOpen) feedbackTextareaRef.current?.focus();
  }, [feedbackComposerOpen]);

  const submitFeedback = async (value: boolean, comment?: string) => {
    if (feedbackPending) return;
    setFeedbackPending(true);
    setFeedbackError(false);
    try {
      if (comment === undefined) await chatApi.reportFeedback(msg.id, value);
      else await chatApi.reportFeedback(msg.id, value, comment);
      setFeedback(value);
      setFeedbackComposerOpen(false);
      setFeedbackComment("");
    } catch {
      setFeedbackError(true);
    } finally {
      setFeedbackPending(false);
    }
  };

  return (
  <div className="chat-msg chat-msg-assistant">
    <div className="chat-msg-blocks">
      {msg.blocks?.map((b, i) => {
        const key = `${msg.id}-${i}`;
        const citationSnapshot =
          "citations" in b && b.citations !== undefined
            ? b.citations
            : msg.citations ?? [];
        const citations = Object.fromEntries(
          citationSnapshot
            .filter((citation) => (
              citation.kind === "catalog_paper"
              || citation.kind === "paper"
              || (!citation.kind && citation.route_id)
            ) && citation.route_id)
            .map((citation) => [citation.route_id as string, citation]),
        );
        const webCitations = Object.fromEntries(
          citationSnapshot
            .filter((citation) => (
              citation.kind === "external_source"
              || citation.kind === "web"
            ) && citation.url)
            .map((citation) => [citation.url as string, citation]),
        );
        if (b.kind === "reasoning") {
          return (
            <ReasoningBlockView
              key={key}
              block={b}
              papers={papers}
              citations={citations}
              webCitations={webCitations}
              onToggle={() => onToggleBlock(msg.id, i)}
            />
          );
        }
        if (b.kind === "tool") {
          return (
            <ToolBlockView key={key} block={b} papers={papers} onToggle={() => onToggleBlock(msg.id, i)} />
          );
        }
        if (b.kind === "app") return <AppBlockView key={b.instance_id || key} block={b} />;
        if (b.kind === "artifact") return <PosterArtifact key={b.publication_id || b.version_id || key} block={b} />;
        return (
          <AnswerBlockView
            key={key}
            block={b}
            papers={papers}
            citations={citations}
            webCitations={webCitations}
            streaming={Boolean(msg.streaming && i === (msg.blocks?.length ?? 0) - 1)}
          />
        );
      })}
      {msg.streaming && msg.compacting && <CompactionStatus />}
      {!msg.compacting && isWaitingForAssistant(msg) && (
        <div className="chat-waiting" role="status" aria-live="polite">
          <span className="chat-thinking">
            {(msg.blocks?.length ?? 0) === 0 ? (msg.status ?? "Thinking…") : "Thinking…"}
          </span>
        </div>
      )}
      {msg.error && <div className="chat-error">
        {msg.blocks?.some((block) => block.kind === "answer" && block.text.trim()) && <strong>Incomplete—response interrupted. </strong>}
        {["context_too_large", "provider_error", "persistence_error"].includes(msg.errorCode ?? "") && onRetryCompaction && <button type="button" onClick={onRetryCompaction}>Retry</button>}
        <span>{msg.errorCode === "chat_disabled_interrupted"
          ? "Chat was disabled while this response was running. The partial response is saved. Please try again later."
          : msg.errorCode === "chat_session_quota_exceeded"
          ? msg.error
          : `The assistant hit an error: ${msg.error}`}</span>
        {["hf_inference_billing_required", "hf_inference_credential_expired"].includes(msg.errorCode ?? "") && (
          <a href="/settings">
            Re-sign in with Hugging Face
          </a>
        )}
        {msg.errorCode === "hf_inference_billing_exhausted" && <>
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
        </>}
        {msg.errorCode === "hf_sponsored_unavailable" && onRetryWithLuna && (
          <button type="button" onClick={onRetryWithLuna}>Retry with GPT-6 Luna</button>
        )}
        {msg.errorCode === "openrouter_monthly_budget_exhausted" && <>
          {openRouterFallbackEnabled
            ? <span>This response started on the shared allowance. Your connected OpenRouter key will be used when you explicitly retry.</span>
            : <a href="/settings#openrouter-byok">Connect your own OpenRouter key</a>}
          <span>Or select a Hugging Face-backed model and explicitly retry.</span>
        </>}
        {msg.errorCode === "openrouter_staging_funding_disabled" && (
          <a href={PRODUCTION_CHAT_URL}>Continue on paperswithcode.co</a>
        )}
        {msg.errorCode === "openrouter_unavailable" && <>
          <a href="/settings#openrouter-byok">Bring your own key in Settings</a>
          <a href="https://github.com/huggingface/paperswithcode-feedback" target="_blank" rel="noreferrer">File an issue</a>
        </>}
        {msg.errorCode === "openrouter_byok_billing_error" && (
          <a href="https://openrouter.ai/settings/credits" target="_blank" rel="noreferrer">Review OpenRouter billing</a>
        )}
        {["openrouter_byok_credential_invalid", "openrouter_byok_rate_limit"].includes(msg.errorCode ?? "") && (
          <a href="/settings#openrouter-byok">Review OpenRouter settings</a>
        )}
        {msg.errorCode === "chat_session_quota_exceeded" && (onArchiveOldChats || onArchiveOldestChats) && (
          <span className="chat-error-actions">
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
          </span>
        )}
      </div>}
      {!msg.streaming && msg.finishReason && !["success", "scope_blocked"].includes(msg.finishReason) && (
        <div className="chat-finish-note">
          {["tool_limit", "max_turns"].includes(msg.finishReason)
            ? "The assistant stopped at the execution limit."
            : `The assistant stopped early (${msg.finishReason.replace(/_/g, " ")}).`}
        </div>
      )}
      {canRate && (
        <div className="chat-feedback" aria-label="Rate this response">
          <span className="chat-feedback-label">
            {feedback === null ? "Was this helpful?" : "Thanks for your feedback"}
          </span>
          <button
            type="button"
            className={`chat-feedback-action${feedback === true ? " chat-feedback-action-selected" : ""}`}
            aria-label="Helpful response"
            aria-pressed={feedback === true}
            disabled={feedbackPending}
            onClick={() => {
              setFeedbackComposerOpen(false);
              void submitFeedback(true);
            }}
          >
            <ThumbsUp aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`chat-feedback-action${feedback === false ? " chat-feedback-action-selected" : ""}`}
            aria-label="Unhelpful response"
            aria-pressed={feedback === false}
            aria-expanded={feedbackComposerOpen}
            aria-controls={feedbackPanelId}
            disabled={feedbackPending}
            onClick={() => {
              setFeedbackError(false);
              setFeedbackComposerOpen(true);
            }}
          >
            <ThumbsDown aria-hidden="true" />
          </button>
          {feedbackError && <span className="chat-feedback-error" role="status">Couldn’t send feedback.</span>}
        </div>
      )}
      {canRate && feedbackComposerOpen && (
        <div className="chat-feedback-panel" id={feedbackPanelId} role="group" aria-labelledby={`${feedbackPanelId}-title`}>
          <div className="chat-feedback-panel-title" id={`${feedbackPanelId}-title`}>Additional feedback</div>
          <label className="chat-feedback-panel-label" htmlFor={`${feedbackPanelId}-comment`}>
            Tell us what went wrong (optional)
          </label>
          <textarea
            ref={feedbackTextareaRef}
            id={`${feedbackPanelId}-comment`}
            className="chat-feedback-comment"
            value={feedbackComment}
            maxLength={500}
            rows={4}
            disabled={feedbackPending}
            onChange={(event) => setFeedbackComment(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                setFeedbackComposerOpen(false);
              }
            }}
          />
          <div className="chat-feedback-panel-actions">
            <button
              type="button"
              className="chat-feedback-skip"
              disabled={feedbackPending}
              onClick={() => void submitFeedback(false)}
            >
              Skip
            </button>
            <button
              type="button"
              className="chat-feedback-submit"
              disabled={feedbackPending}
              onClick={() => void submitFeedback(false, feedbackComment.trim() || undefined)}
            >
              {feedbackPending ? "Submitting…" : "Submit"}
            </button>
          </div>
        </div>
      )}
    </div>
  </div>
  );
};
