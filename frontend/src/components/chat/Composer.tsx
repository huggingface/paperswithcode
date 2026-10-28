/** Native textarea chat composer with structured inline paper mentions. */

import React, { useEffect, useRef, useState } from "react";

import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { PaperMentionHighlights } from "@/components/chat/PaperMentionHighlights";
import { PaperSelectionCard } from "@/components/chat/PaperSelectionCard";
import { ArrowUpIcon, Spinner } from "@/components/chat/icons";
import ModelPicker, { type ModelPickerOption } from "@/components/chat/ModelPicker";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import type { ChatDraft } from "@/lib/chat";
import { emptyChatDraft } from "@/lib/paperSelection";

interface ComposerProps {
  onSend: (draft: ChatDraft) => void;
  busy?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  draft?: ChatDraft;
  onDraftChange?: (value: ChatDraft) => void;
  onStop?: () => void;
  models?: ModelPickerOption[];
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  disabled?: boolean;
  describedBy?: string;
  paperMentionsEnabled?: boolean;
  paperSelectionEnabled?: boolean;
  paperArtifactsEnabled?: boolean;
}

const EMPTY_DRAFT: ChatDraft = emptyChatDraft();

const Composer: React.FC<ComposerProps> = ({
  onSend, busy, placeholder, autoFocus, draft, onDraftChange, onStop,
  models = [], selectedModel, onModelChange, disabled = false, describedBy,
  paperMentionsEnabled = false,
  paperSelectionEnabled = true,
  paperArtifactsEnabled = false,
}) => {
  const [localDraft, setLocalDraft] = useState<ChatDraft>(EMPTY_DRAFT);
  const value = draft ?? localDraft;
  const ref = useRef<HTMLTextAreaElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const change = (next: ChatDraft) => {
    if (!draft) setLocalDraft(next);
    onDraftChange?.(next);
  };
  const mentions = usePaperMentions({
    draft: value,
    onChange: change,
    enabled: paperMentionsEnabled,
    textareaRef: ref,
  });

  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  }, [value.text]);

  useEffect(() => { if (autoFocus) ref.current?.focus(); }, [autoFocus]);

  const submit = () => {
    const leading = value.text.length - value.text.trimStart().length;
    const text = value.text.trim();
    const selectionBlocked = Boolean(value.paperSelection) && !paperSelectionEnabled;
    if (!text || busy || disabled || selectionBlocked) return;
    const end = leading + text.length;
    const normalized: ChatDraft = {
      text,
      paperMentions: value.paperMentions
        .filter((mention) => mention.start >= leading && mention.end <= end)
        .map((mention) => ({ ...mention, start: mention.start - leading, end: mention.end - leading })),
      ...(value.paperSelection ? { paperSelection: value.paperSelection } : {}),
    };
    onSend(normalized);
  };

  const selectionBlocked = Boolean(value.paperSelection) && !paperSelectionEnabled;
  const canSend = Boolean(value.text.trim()) && !selectionBlocked;
  const slashCommandOpen = paperArtifactsEnabled && value.text === "/";

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
            change({ text: value.text, paperMentions: value.paperMentions });
            ref.current?.focus();
          }}
        />
      )}
      {selectionBlocked && (
        <div className="chat-paper-selection-disabled" role="status">
          Paper selection is currently disabled. Remove the selected passage or wait for the feature to recover.
        </div>
      )}
      <div className="chat-composer-textarea-wrap">
        <PaperMentionHighlights text={value.text} mentions={value.paperMentions} scrollTop={scrollTop} />
        <textarea
          className="ph-no-capture"
          data-ph-no-autocapture="true"
          data-ph-no-capture="true"
          ref={ref}
          rows={1}
          value={value.text}
          placeholder={placeholder || (value.paperSelection ? "Ask about this selection…" : "Ask anything about research…")}
          onChange={(event) => mentions.updateText(event.target.value, event.target.selectionStart)}
          onSelect={(event) => mentions.refresh(event.currentTarget.selectionStart)}
          onClick={(event) => mentions.refresh(event.currentTarget.selectionStart)}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          onBlur={(event) => {
            if (!event.relatedTarget?.closest?.(".chat-paper-picker, .chat-slash-command")) window.setTimeout(mentions.close, 0);
          }}
          onKeyDown={(event) => {
            if (mentions.keyDown(event)) return;
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
      <div className="chat-composer-row">
        <div className="chat-composer-tools">
          {models.length > 0 && selectedModel && onModelChange && <ModelPicker models={models} selectedModel={selectedModel} onModelChange={onModelChange} disabled={busy} />}
          <span className="chat-composer-hint">Enter to send · Shift+Enter for newline</span>
        </div>
        <button type="button" className={`chat-send${(busy || canSend) ? " chat-send-on" : ""}`} onClick={busy ? onStop : submit} disabled={disabled || (busy ? !onStop : !canSend)} aria-label={busy ? "Stop generating" : "Send message"}>
          {busy ? (onStop ? <span aria-hidden="true">■</span> : <Spinner light />) : <ArrowUpIcon />}
        </button>
      </div>
    </div>
  );
};

export default Composer;
