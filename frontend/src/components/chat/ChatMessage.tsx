import { CompactionStatus } from "./CompactionStatus";
/**
 * Message rendering for the assistant chat: user bubbles plus the assistant's
 * ordered stream blocks — live/collapsed reasoning, `search_papers` tool-call
 * accordions with ranked hits, and the final cited answer.
 */

import React from "react";
import { Check, Copy, FileText, Pencil } from "lucide-react";

import { AssistantError, type HfBillingGuidance } from "@/components/chat/AssistantError";
import { ChatMarkdown, PaperCitation } from "@/components/chat/ChatMarkdown";
import { FeedbackControls } from "@/components/chat/FeedbackControls";
import { McpAppFrame } from "@/components/chat/McpAppFrame";
import { PosterArtifact } from "@/components/chat/PosterArtifact";
import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { PaperMentionHighlights } from "@/components/chat/PaperMentionHighlights";
import { PaperSelectionCard } from "@/components/chat/PaperSelectionCard";
import { CheckIcon, Chevron, SearchIcon, Spinner } from "@/components/chat/icons";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import { PaperPreviewLink } from "@/components/paper-preview/PaperPreviewLink";
import { authorsLine, excerpt, venueLine } from "@/components/chat/paperDisplay";
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

/** Escape cancels; Enter sends unless composing or adding a newline. */
const editorKeyDown = (
  event: React.KeyboardEvent<HTMLTextAreaElement>,
  onCancel: (() => void) | undefined,
  resend: () => void,
) => {
  if (event.key === "Escape") { event.preventDefault(); onCancel?.(); }
  else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); resend(); }
};

const EditorActions: React.FC<{
  editNotice?: string;
  canSend: boolean;
  onCancel?: () => void;
  onSend: () => void;
}> = ({ editNotice, canSend, onCancel, onSend }) => <>
  {editNotice && <div className="chat-inline-editor-notice">{editNotice}</div>}
  <div className="chat-inline-editor-actions">
    <button type="button" onClick={onCancel}>Cancel</button>
    <button type="button" className="chat-inline-editor-send" disabled={!canSend} onClick={onSend}>Send</button>
  </div>
</>;

/** Submits an edited draft once; a refused draft can be sent again. */
const useEditorSubmit = (
  valid: boolean,
  draft: () => ChatDraft,
  { onResend, onResendDraft }: Pick<UserEditorProps, "onResend" | "onResendDraft">,
) => {
  const [submitting, setSubmitting] = React.useState(false);
  const resend = () => {
    if (!valid || submitting) return;
    setSubmitting(true);
    const next = draft();
    const accepted = onResendDraft?.(next) ?? onResend?.(next.text) ?? false;
    if (!accepted) setSubmitting(false);
  };
  return { resend, canSend: valid && !submitting };
};

/** The editor without paper mentions, which needs no search client. */
const PlainUserEditor: React.FC<UserEditorProps> = ({ id, text, paperSelection, editNotice, onCancel, onResend, onResendDraft }) => {
  const [value, setValue] = React.useState(text);
  const [selection, setSelection] = React.useState(paperSelection);
  const { textareaRef, resize } = useEditorTextarea(text);
  React.useLayoutEffect(resize, [resize, value]);
  const { resend, canSend } = useEditorSubmit(
    Boolean(value.trim()) && value.length <= 8_000,
    () => ({ text: value, paperMentions: [], ...(selection ? { paperSelection: selection } : {}) }),
    { onResend, onResendDraft },
  );
  return <div className="chat-msg chat-msg-user chat-msg-user-editing" data-message-id={id}>
    <div className="chat-inline-editor">
      {selection && <PaperSelectionCard selection={selection} editable onRemove={() => setSelection(undefined)} />}
      <textarea ref={textareaRef} className="chat-inline-editor-textarea" aria-label="Edit message" value={value} maxLength={8_000}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => editorKeyDown(event, onCancel, resend)} />
      <EditorActions editNotice={editNotice} canSend={canSend} onCancel={onCancel} onSend={resend} />
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
  const [scrollTop, setScrollTop] = React.useState(0);
  const { textareaRef, resize } = useEditorTextarea(text);
  const editor = usePaperMentions({ draft: value, onChange: setValue, enabled, textareaRef });
  React.useLayoutEffect(resize, [resize, value.text]);
  const { resend, canSend } = useEditorSubmit(
    Boolean(value.text.trim()) && value.text.length <= 8_000 && (enabled || value.paperMentions.length === 0),
    () => value,
    { onResend, onResendDraft },
  );
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
            editorKeyDown(event, onCancel, resend);
          }} />
        <PaperMentionPicker open={editor.open} query={editor.query} results={editor.results} activeIndex={editor.activeIndex} loading={editor.loading} error={editor.error} onSelect={editor.select} id={editor.pickerId} optionIdPrefix={editor.optionIdPrefix} />
      </div>
      {!enabled && value.paperMentions.length > 0 && <div className="chat-inline-editor-notice" role="status">Paper mentions are currently disabled. Remove them before sending.</div>}
      <EditorActions editNotice={editNotice} canSend={canSend} onCancel={onCancel} onSend={resend} />
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

const citationMaps = (snapshot: ChatCitation[]) => ({
  citations: Object.fromEntries(
    snapshot
      .filter((citation) => (
        citation.kind === "catalog_paper"
        || citation.kind === "paper"
        || (!citation.kind && citation.route_id)
      ) && citation.route_id)
      .map((citation) => [citation.route_id as string, citation]),
  ),
  webCitations: Object.fromEntries(
    snapshot
      .filter((citation) => (
        citation.kind === "external_source"
        || citation.kind === "web"
      ) && citation.url)
      .map((citation) => [citation.url as string, citation]),
  ),
});

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
  const canRate = feedbackEnabled
    && !msg.streaming
    && !msg.error
    && Boolean(msg.blocks?.some((block) => block.kind === "answer" && block.text.trim()));

  return (
  <div className="chat-msg chat-msg-assistant">
    <div className="chat-msg-blocks">
      {msg.blocks?.map((b, i) => {
        const key = `${msg.id}-${i}`;
        const { citations, webCitations } = citationMaps(
          "citations" in b && b.citations !== undefined
            ? b.citations
            : msg.citations ?? [],
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
      {msg.error && <AssistantError
        msg={{ ...msg, error: msg.error }}
        onRetryCompaction={onRetryCompaction}
        onRetryWithLuna={onRetryWithLuna}
        onArchiveOldChats={onArchiveOldChats}
        onArchiveOldestChats={onArchiveOldestChats}
        archivePending={archivePending}
        hfBilling={hfBilling}
        openRouterFallbackEnabled={openRouterFallbackEnabled}
      />}
      {!msg.streaming && msg.finishReason && !["success", "scope_blocked"].includes(msg.finishReason) && (
        <div className="chat-finish-note">
          {["tool_limit", "max_turns"].includes(msg.finishReason)
            ? "The assistant stopped at the execution limit."
            : `The assistant stopped early (${msg.finishReason.replace(/_/g, " ")}).`}
        </div>
      )}
      {canRate && <FeedbackControls messageId={msg.id} />}
    </div>
  </div>
  );
};
