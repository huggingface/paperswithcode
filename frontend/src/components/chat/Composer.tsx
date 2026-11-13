/** Native textarea chat composer with structured inline paper mentions. */

import React, { useEffect, useRef, useState } from "react";

import { DictationButton } from "@/components/chat/DictationButton";
import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { PaperMentionHighlights } from "@/components/chat/PaperMentionHighlights";
import { PaperSelectionCard } from "@/components/chat/PaperSelectionCard";
import { ArrowUpIcon, PaperclipIcon, Spinner } from "@/components/chat/icons";
import { completedScrollHeight, isCompletionKey, useChatCompletion } from "@/components/chat/useChatCompletion";
import { useComposerDictation } from "@/components/chat/useComposerDictation";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import { formatFileSize, withoutSelection, type ChatDraft, type ChatUploadedFile } from "@/lib/chat";
import { ApiError } from "@/lib/apiTransport";
import { emptyChatDraft } from "@/lib/paperSelection";

interface ComposerProps {
  onSend: (draft: ChatDraft) => void;
  busy?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  draft?: ChatDraft;
  onDraftChange?: (value: ChatDraft) => void;
  onStop?: () => void;
  disabled?: boolean;
  describedBy?: string;
  paperMentionsEnabled?: boolean;
  paperSelectionEnabled?: boolean;
  paperArtifactsEnabled?: boolean;
  /** Present only on surfaces that accept uploads (/chat and the reader). */
  fileUploads?: ComposerFileUploads;
}

export interface ComposerFileUploads {
  /** Uploads to the given chat, or creates one first, and returns both. */
  upload: (file: File, sessionId?: string) => Promise<{ sessionId: string; file: ChatUploadedFile }>;
  remove: (sessionId: string, fileId: string) => void;
}

/** The composer started over while this upload ran; drop it silently. */
export class UploadAbandoned extends Error {}

export const MAX_CHAT_FILES = 5;
const ACCEPTED_FILES = ".pdf,.png,.jpg,.jpeg,.webp,.txt,.md,.tex,.bib,.csv,.tsv,.json,.py,.ipynb,.yaml,.yml";

const EMPTY_DRAFT: ChatDraft = emptyChatDraft();

/** Scroll the whole composer, not just the caret, into the visible chat. */
function revealComposer(textarea: HTMLTextAreaElement) {
  textarea.closest(".chat-composer")?.scrollIntoView({ block: "nearest" });
}

const Composer: React.FC<ComposerProps> = ({
  onSend, busy, placeholder, autoFocus, draft, onDraftChange, onStop,
  disabled = false, describedBy,
  paperMentionsEnabled = false,
  paperSelectionEnabled = true,
  paperArtifactsEnabled = false,
  fileUploads,
}) => {
  const [localDraft, setLocalDraft] = useState<ChatDraft>(EMPTY_DRAFT);
  const value = draft ?? localDraft;
  const ref = useRef<HTMLTextAreaElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const change = (next: ChatDraft) => {
    if (!draft) setLocalDraft(next);
    onDraftChange?.(next);
  };
  // Uploads finish after later renders; they extend the latest draft.
  const latest = useRef({ value, change });
  latest.current = { value, change };
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(0);
  const [fileError, setFileError] = useState("");
  const files = value.files ?? [];
  const attachFiles = async (selected: File[]) => {
    if (!fileUploads) return;
    setFileError("");
    for (const file of selected) {
      if ((latest.current.value.files?.length ?? 0) + 1 > MAX_CHAT_FILES) {
        setFileError(`A chat can hold at most ${MAX_CHAT_FILES} files.`);
        return;
      }
      setUploading((count) => count + 1);
      try {
        const uploaded = await fileUploads.upload(file, latest.current.value.fileSessionId);
        const current = latest.current.value;
        latest.current.change({
          ...current,
          files: [...(current.files ?? []), uploaded.file],
          fileSessionId: uploaded.sessionId,
        });
      } catch (error) {
        if (error instanceof UploadAbandoned) return;
        setFileError(error instanceof ApiError ? error.displayMessage : `${file.name} could not be uploaded.`);
      } finally {
        setUploading((count) => count - 1);
      }
    }
  };
  const removeFile = (fileId: string) => {
    if (value.fileSessionId) fileUploads?.remove(value.fileSessionId, fileId);
    change({ ...value, files: files.filter((file) => file.id !== fileId) });
  };
  const mentions = usePaperMentions({
    draft: value,
    onChange: change,
    enabled: paperMentionsEnabled,
    textareaRef: ref,
  });
  // Enter while dictating finishes the recording, then sends the final text.
  const sendAfterDictation = useRef(false);
  const [sendQueued, setSendQueued] = useState(false);
  const dictation = useComposerDictation({
    draft: value,
    onChange: change,
    textareaRef: ref,
    onEnd: (cancelled) => {
      if (sendAfterDictation.current && !cancelled) setSendQueued(true);
      sendAfterDictation.current = false;
    },
  });
  const slashCommandOpen = paperArtifactsEnabled && value.text === "/";
  const { completion, trackCaret } = useChatCompletion(value, mentions.open || slashCommandOpen);

  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(completedScrollHeight(el), 200)}px`;
      if (document.activeElement === el) revealComposer(el);
    }
  }, [value.text, completion]);

  // A mobile keyboard shrinks the chat page; keep the focused composer above it.
  // Observe the page itself so the scroll runs after its new height is laid out.
  useEffect(() => {
    const page = ref.current?.closest(".chat-page, .shared-chat-page");
    if (!page) return;
    const observer = new ResizeObserver(() => {
      if (ref.current && document.activeElement === ref.current) revealComposer(ref.current);
    });
    observer.observe(page);
    return () => observer.disconnect();
  }, []);

  useEffect(() => { if (autoFocus) ref.current?.focus(); }, [autoFocus]);

  const submit = () => {
    const leading = value.text.length - value.text.trimStart().length;
    const text = value.text.trim();
    const selectionBlocked = Boolean(value.paperSelection) && !paperSelectionEnabled;
    if (!text || busy || disabled || selectionBlocked || uploading > 0) return;
    const end = leading + text.length;
    const normalized: ChatDraft = {
      text,
      paperMentions: value.paperMentions
        .filter((mention) => mention.start >= leading && mention.end <= end)
        .map((mention) => ({ ...mention, start: mention.start - leading, end: mention.end - leading })),
      ...(value.paperSelection ? { paperSelection: value.paperSelection } : {}),
      ...(files.length ? { files } : {}),
      ...(value.fileSessionId ? { fileSessionId: value.fileSessionId } : {}),
    };
    onSend(normalized);
  };

  useEffect(() => {
    if (!sendQueued) return;
    setSendQueued(false);
    submit();
    // submit reads the draft rendered with the final transcript.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sendQueued]);

  const selectionBlocked = Boolean(value.paperSelection) && !paperSelectionEnabled;
  const canSend = dictation.active
    ? dictation.phase === "recording" && !selectionBlocked
    : Boolean(value.text.trim()) && !selectionBlocked && uploading === 0;
  const sendAfterRecording = () => {
    sendAfterDictation.current = true;
    dictation.finish();
  };

  return (
    <div
      className="chat-composer ph-no-capture"
      data-ph-no-autocapture="true"
      data-ph-no-capture="true"
    >
      {value.paperSelection && (
        <PaperSelectionCard
          selection={value.paperSelection}
          editable
          onRemove={() => {
            change(withoutSelection(value));
            ref.current?.focus();
          }}
        />
      )}
      {selectionBlocked && (
        <div className="chat-paper-selection-disabled" role="status">
          Paper selection is currently disabled. Remove the selected passage or wait for the feature to recover.
        </div>
      )}
      {(files.length > 0 || uploading > 0) && (
        <ul className="chat-composer-files" aria-label="Attached files">
          {files.map((file) => (
            <li key={file.id} className="chat-file-chip">
              <span className="chat-file-chip-name" title={file.filename}>{file.filename}</span>
              <span className="chat-file-chip-size">{formatFileSize(file.size_bytes)}</span>
              <button type="button" className="chat-file-chip-remove" onClick={() => removeFile(file.id)} aria-label={`Remove ${file.filename}`}>×</button>
            </li>
          ))}
          {uploading > 0 && <li className="chat-file-chip chat-file-chip-pending"><Spinner /> Uploading…</li>}
        </ul>
      )}
      {fileError && <div className="chat-paper-mention-message" role="alert">{fileError}</div>}
      <div className="chat-composer-textarea-wrap">
        <PaperMentionHighlights text={value.text} mentions={value.paperMentions} scrollTop={scrollTop} completion={completion} />
        <textarea
          className="ph-no-capture"
          data-ph-no-autocapture="true"
          data-ph-no-capture="true"
          ref={ref}
          rows={1}
          readOnly={dictation.active}
          value={value.text}
          placeholder={placeholder || (value.paperSelection ? "Ask about this selection…" : "Ask anything about research…")}
          onChange={(event) => {
            mentions.updateText(event.target.value, event.target.selectionStart);
            trackCaret(event.target);
          }}
          onSelect={(event) => {
            mentions.refresh(event.currentTarget.selectionStart);
            trackCaret(event.currentTarget);
          }}
          onClick={(event) => {
            mentions.refresh(event.currentTarget.selectionStart);
            trackCaret(event.currentTarget);
          }}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          onBlur={(event) => {
            if (!event.relatedTarget?.closest?.(".chat-paper-picker, .chat-slash-command")) window.setTimeout(mentions.close, 0);
          }}
          onKeyDown={(event) => {
            if (dictation.active) {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (canSend && !busy && !disabled) sendAfterRecording();
              }
              return;
            }
            if (mentions.keyDown(event)) return;
            if (isCompletionKey(event) && completion) {
              event.preventDefault();
              const text = value.text + completion;
              mentions.updateText(text, text.length);
              window.requestAnimationFrame(() => ref.current?.setSelectionRange(text.length, text.length));
              return;
            }
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          role="combobox"
          aria-expanded={mentions.open || slashCommandOpen}
          aria-controls={mentions.open ? mentions.pickerId : slashCommandOpen ? "chat-write-paper-command" : undefined}
          aria-activedescendant={mentions.open && mentions.results.length ? `${mentions.optionIdPrefix}-${mentions.activeIndex}` : slashCommandOpen ? "chat-write-paper-command" : undefined}
          aria-autocomplete="list"
          aria-describedby={[describedBy, mentions.message ? "chat-paper-mention-message" : null].filter(Boolean).join(" ") || undefined}
        />
        <PaperMentionPicker
          open={mentions.open}
          query={mentions.query}
          results={mentions.results}
          activeIndex={mentions.activeIndex}
          loading={mentions.loading}
          error={mentions.error}
          onSelect={mentions.select}
          id={mentions.pickerId}
          optionIdPrefix={mentions.optionIdPrefix}
        />
        {slashCommandOpen && (
          <button
            type="button"
            id="chat-write-paper-command"
            className="chat-slash-command"
            role="option"
            onMouseDown={(event) => {
              event.preventDefault();
              change({ ...value, text: "/write-paper " });
              ref.current?.focus();
            }}
          >
            <code>/write-paper</code><span>Draft a paper from this research chat</span>
          </button>
        )}
      </div>
      {mentions.message && <div id="chat-paper-mention-message" className="chat-paper-mention-message" role="alert">{mentions.message}</div>}
      {dictation.error && <div className="chat-paper-mention-message" role="alert">{dictation.error}</div>}
      <div className="chat-composer-row">
        <div className="chat-composer-tools">
          <span className="chat-composer-hint">{completion ? "Tab to complete · " : ""}Enter to send · Shift+Enter for newline</span>
        </div>
        <div className="chat-composer-actions">
          {fileUploads && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                hidden
                accept={ACCEPTED_FILES}
                onChange={(event) => {
                  const selected = Array.from(event.target.files ?? []);
                  event.target.value = "";
                  void attachFiles(selected);
                }}
              />
              <button
                type="button"
                className="chat-attach"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || busy || uploading > 0 || files.length >= MAX_CHAT_FILES}
                aria-label="Attach files"
                title="Attach PDF, image, or text files"
              >
                <PaperclipIcon />
              </button>
            </>
          )}
          <DictationButton dictation={dictation} disabled={disabled} />
          <button type="button" className={`chat-send${(busy || canSend) ? " chat-send-on" : ""}`} onClick={busy ? onStop : dictation.active ? sendAfterRecording : submit} disabled={disabled || (busy ? !onStop : !canSend)} aria-label={busy ? "Stop generating" : "Send message"}>
            {busy ? (onStop ? <span aria-hidden="true">■</span> : <Spinner light />) : <ArrowUpIcon />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Composer;
