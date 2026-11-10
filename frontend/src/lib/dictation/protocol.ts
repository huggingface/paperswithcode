/**
 * Wire protocols of the two dictation providers behind the same-origin relay.
 *
 * Voxtral (vLLM `/v1/realtime`): append-only `transcription.delta` events while
 * audio streams, then one `transcription.done` after `commit { final: true }`.
 *
 * OpenAI Realtime transcription: server VAD cuts the audio into utterances;
 * each committed utterance streams `…input_audio_transcription.delta` events
 * and ends with `.completed`. Stopping commits the last utterance.
 */

import type { DictationSession } from "@/lib/api/dictation";

export interface ProtocolEvents {
  /** Text to append to what has been transcribed so far. */
  onText: (delta: string) => void;
  /** Every utterance is transcribed after `finish()`; the socket can close. */
  onDone: () => void;
  onError: (message: string) => void;
}

export interface DictationProtocol {
  /** Messages to send once the socket opens. */
  open(): string[];
  /** Message carrying one chunk of PCM16 audio. */
  audio(base64: string): string;
  /** Messages that ask the provider to transcribe what remains. */
  finish(): string[];
  /** Handle one server message. */
  receive(data: string): void;
}

export function createProtocol(session: DictationSession, events: ProtocolEvents): DictationProtocol {
  return session.provider === "openai" ? openaiProtocol(session, events) : voxtralProtocol(session, events);
}

function parse(data: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(data);
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function errorMessage(event: Record<string, unknown>): string {
  const error = event.error;
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && typeof (error as { message?: unknown }).message === "string") {
    return (error as { message: string }).message;
  }
  return "Speech recognition failed";
}

function voxtralProtocol(session: DictationSession, events: ProtocolEvents): DictationProtocol {
  return {
    open: () => [
      JSON.stringify({ type: "session.update", model: session.model }),
      JSON.stringify({ type: "input_audio_buffer.commit" }),
    ],
    audio: (audio) => JSON.stringify({ type: "input_audio_buffer.append", audio }),
    finish: () => [JSON.stringify({ type: "input_audio_buffer.commit", final: true })],
    receive(data) {
      const event = parse(data);
      if (!event) return;
      if (event.type === "transcription.delta" && typeof event.delta === "string") {
        if (event.delta) events.onText(event.delta);
      } else if (event.type === "transcription.done") {
        events.onDone();
      } else if (event.type === "error") {
        events.onError(errorMessage(event));
      }
    },
  };
}

function openaiProtocol(session: DictationSession, events: ProtocolEvents): DictationProtocol {
  const pending = new Set<string>();
  const started = new Set<string>();
  let finishing = false;
  let wroteText = false;
  const settle = () => {
    if (finishing && pending.size === 0) events.onDone();
  };
  return {
    open: () => [
      JSON.stringify({
        type: "session.update",
        session: {
          type: "transcription",
          audio: {
            input: {
              format: { type: "audio/pcm", rate: session.sample_rate },
              transcription: { model: session.model, ...(session.prompt ? { prompt: session.prompt } : {}) },
              turn_detection: { type: "server_vad", silence_duration_ms: 500 },
            },
          },
        },
      }),
    ],
    audio: (audio) => JSON.stringify({ type: "input_audio_buffer.append", audio }),
    finish: () => {
      finishing = true;
      return [JSON.stringify({ type: "input_audio_buffer.commit" })];
    },
    receive(data) {
      const event = parse(data);
      if (!event) return;
      const itemId = typeof event.item_id === "string" ? event.item_id : "";
      switch (event.type) {
        case "input_audio_buffer.committed":
          if (itemId) pending.add(itemId);
          return;
        case "conversation.item.input_audio_transcription.delta": {
          const delta = typeof event.delta === "string" ? event.delta : "";
          if (!delta) return;
          // Utterances arrive without a leading space; separate them.
          const separator = wroteText && !started.has(itemId) && !/^\s/.test(delta) ? " " : "";
          started.add(itemId);
          wroteText = true;
          events.onText(separator + delta);
          return;
        }
        case "conversation.item.input_audio_transcription.completed":
        case "conversation.item.input_audio_transcription.failed":
          pending.delete(itemId);
          settle();
          return;
        case "error": {
          const code = (event.error as { code?: unknown } | undefined)?.code;
          // Stopping right after an utterance leaves nothing to commit.
          if (finishing && code === "input_audio_buffer_commit_empty") {
            settle();
            return;
          }
          events.onError(errorMessage(event));
          return;
        }
        default:
      }
    },
  };
}
