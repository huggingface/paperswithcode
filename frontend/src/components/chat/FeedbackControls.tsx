import React from "react";
import { useMutation } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";

import { chatApi } from "@/lib/api/chat";

/** Thumbs up/down with an optional comment for one completed answer. */
export const FeedbackControls: React.FC<{ messageId: string }> = ({ messageId }) => {
  const [feedback, setFeedback] = React.useState<boolean | null>(null);
  const [composerOpen, setComposerOpen] = React.useState(false);
  const [comment, setComment] = React.useState("");
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const panelId = `chat-feedback-panel-${messageId}`;
  const mutation = useMutation({
    mutationFn: ({ value, comment: note }: { value: boolean; comment?: string }) => (
      note === undefined
        ? chatApi.reportFeedback(messageId, value)
        : chatApi.reportFeedback(messageId, value, note)
    ),
    onSuccess: (_result, { value }) => {
      setFeedback(value);
      setComposerOpen(false);
      setComment("");
    },
  });
  const pending = mutation.isPending;

  React.useEffect(() => {
    if (composerOpen) textareaRef.current?.focus();
  }, [composerOpen]);

  const submit = (value: boolean, note?: string) => {
    if (pending) return;
    mutation.mutate({ value, comment: note });
  };

  return <>
    <div className="chat-feedback" aria-label="Rate this response">
      <span className="chat-feedback-label">
        {feedback === null ? "Was this helpful?" : "Thanks for your feedback"}
      </span>
      <button
        type="button"
        className={`chat-feedback-action${feedback === true ? " chat-feedback-action-selected" : ""}`}
        aria-label="Helpful response"
        aria-pressed={feedback === true}
        disabled={pending}
        onClick={() => {
          setComposerOpen(false);
          submit(true);
        }}
      >
        <ThumbsUp aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`chat-feedback-action${feedback === false ? " chat-feedback-action-selected" : ""}`}
        aria-label="Unhelpful response"
        aria-pressed={feedback === false}
        aria-expanded={composerOpen}
        aria-controls={panelId}
        disabled={pending}
        onClick={() => {
          mutation.reset();
          setComposerOpen(true);
        }}
      >
        <ThumbsDown aria-hidden="true" />
      </button>
      {mutation.isError && <span className="chat-feedback-error" role="status">Couldn’t send feedback.</span>}
    </div>
    {composerOpen && (
      <div className="chat-feedback-panel" id={panelId} role="group" aria-labelledby={`${panelId}-title`}>
        <div className="chat-feedback-panel-title" id={`${panelId}-title`}>Additional feedback</div>
        <label className="chat-feedback-panel-label" htmlFor={`${panelId}-comment`}>
          Tell us what went wrong (optional)
        </label>
        <textarea
          ref={textareaRef}
          id={`${panelId}-comment`}
          className="chat-feedback-comment"
          value={comment}
          maxLength={500}
          rows={4}
          disabled={pending}
          onChange={(event) => setComment(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setComposerOpen(false);
            }
          }}
        />
        <div className="chat-feedback-panel-actions">
          <button
            type="button"
            className="chat-feedback-skip"
            disabled={pending}
            onClick={() => submit(false)}
          >
            Skip
          </button>
          <button
            type="button"
            className="chat-feedback-submit"
            disabled={pending}
            onClick={() => submit(false, comment.trim() || undefined)}
          >
            {pending ? "Submitting…" : "Submit"}
          </button>
        </div>
      </div>
    )}
  </>;
};
