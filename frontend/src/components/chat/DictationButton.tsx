/** Mic button that becomes a fixed-size recording pill while dictating. */

import React from "react";

import { CloseIcon, DoneIcon, MicIcon, Spinner } from "@/components/chat/icons";
import type { useComposerDictation } from "@/components/chat/useComposerDictation";
import { useDictationStatus } from "@/hooks/useDictation";
import { hfLoginUrl } from "@/lib/apiUrl";

const BARS = 12;

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

const UNAVAILABLE: Record<string, string> = {
  starting: "Voice input is starting up (about 2 minutes)",
  busy: "Voice input is busy. Try again in a moment.",
  daily_limit: "You've used today's voice input. It resets at midnight UTC.",
};

interface DictationButtonProps {
  dictation: ReturnType<typeof useComposerDictation>;
  disabled?: boolean;
}

export const DictationButton: React.FC<DictationButtonProps> = ({ dictation, disabled }) => {
  const status = useDictationStatus();
  const [levels, setLevels] = React.useState<number[]>(() => Array(BARS).fill(0));
  const { phase, level, active, cancel, finish } = dictation;

  React.useEffect(() => {
    if (!active) {
      setLevels(Array(BARS).fill(0));
      return;
    }
    setLevels((previous) => [...previous.slice(1), Math.min(1, level * 6)]);
  }, [active, level]);

  React.useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        cancel();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, cancel]);

  const data = status.data;
  if (!data?.enabled) return null;

  if (active) {
    const finishing = phase === "finishing";
    return (
      <div className="chat-dictation-pill" role="group" aria-label="Voice input">
        {phase === "connecting" ? (
          <span className="chat-dictation-starting"><Spinner /> Connecting…</span>
        ) : (
          <>
            <span className="chat-dictation-wave" aria-hidden="true">
              {levels.map((value, index) => (
                <span key={index} style={{ transform: `scaleY(${0.15 + value * 0.85})` }} />
              ))}
            </span>
            <span className="chat-dictation-time" aria-live="off">
              {clock(dictation.elapsed)} / {clock(dictation.maxSeconds)}
            </span>
          </>
        )}
        <button type="button" className="chat-dictation-icon" onClick={cancel} aria-label="Cancel voice input" title="Cancel (Esc)">
          <CloseIcon />
        </button>
        <button
          type="button"
          className="chat-dictation-icon chat-dictation-done"
          onClick={finish}
          disabled={finishing || phase === "connecting"}
          aria-label="Finish voice input"
          title="Finish"
        >
          {finishing ? <Spinner light /> : <DoneIcon />}
        </button>
      </div>
    );
  }

  if (!data.signed_in) {
    return (
      <button
        type="button"
        className="chat-dictation-mic"
        onClick={() => window.location.assign(hfLoginUrl(`${window.location.pathname}${window.location.search}`))}
        aria-label="Sign in to use voice input"
        title="Sign in to use voice input"
      >
        <MicIcon />
      </button>
    );
  }

  const unavailable = data.provider ? null : UNAVAILABLE[data.reason ?? ""] ?? "Voice input is unavailable";
  return (
    <button
      type="button"
      className="chat-dictation-mic"
      onClick={dictation.start}
      disabled={disabled || Boolean(unavailable)}
      aria-label={unavailable ?? "Start voice input"}
      title={unavailable ?? "Voice input"}
    >
      {data.reason === "starting" ? <Spinner /> : <MicIcon />}
    </button>
  );
};
