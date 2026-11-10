import { describe, expect, it, vi } from "vitest";

import type { DictationSession } from "@/lib/api/dictation";
import { createProtocol } from "@/lib/dictation/protocol";

const base: DictationSession = {
  session_id: "s",
  ws_url: "/api/v1/dictation/ws?ticket=t",
  provider: "voxtral",
  model: "mistralai/Voxtral-Mini-4B-Realtime-2602",
  sample_rate: 16000,
  max_seconds: 120,
  prompt: null,
};

function setup(session: DictationSession) {
  const events = { onText: vi.fn(), onDone: vi.fn(), onError: vi.fn() };
  return { protocol: createProtocol(session, events), events };
}

const send = (value: object) => JSON.stringify(value);

describe("voxtral protocol", () => {
  it("opens the session, streams appended text and ends on done", () => {
    const { protocol, events } = setup(base);
    expect(protocol.open().map((message) => JSON.parse(message).type)).toEqual([
      "session.update",
      "input_audio_buffer.commit",
    ]);
    expect(JSON.parse(protocol.audio("AAA="))).toEqual({ type: "input_audio_buffer.append", audio: "AAA=" });

    protocol.receive(send({ type: "transcription.delta", delta: " He" }));
    protocol.receive(send({ type: "transcription.delta", delta: "" }));
    protocol.receive(send({ type: "transcription.delta", delta: " hoped" }));
    expect(events.onText.mock.calls.map(([delta]) => delta)).toEqual([" He", " hoped"]);

    expect(JSON.parse(protocol.finish()[0])).toEqual({ type: "input_audio_buffer.commit", final: true });
    protocol.receive(send({ type: "transcription.done", text: " He hoped" }));
    expect(events.onDone).toHaveBeenCalledOnce();
  });

  it("reports errors in either shape", () => {
    const { protocol, events } = setup(base);
    protocol.receive(send({ type: "error", error: "soundfile missing" }));
    protocol.receive(send({ type: "error", error: { message: "bad audio" } }));
    expect(events.onError.mock.calls).toEqual([["soundfile missing"], ["bad audio"]]);
  });

  it("ignores malformed messages", () => {
    const { protocol, events } = setup(base);
    protocol.receive("not json");
    expect(events.onText).not.toHaveBeenCalled();
    expect(events.onError).not.toHaveBeenCalled();
  });
});

describe("openai protocol", () => {
  const session: DictationSession = {
    ...base,
    provider: "openai",
    model: "gpt-4o-mini-transcribe",
    sample_rate: 24000,
    prompt: "LoRA, DeepSeek",
  };

  it("configures a transcription session with the vocabulary prompt", () => {
    const { protocol } = setup(session);
    const update = JSON.parse(protocol.open()[0]);
    expect(update.session.type).toBe("transcription");
    expect(update.session.audio.input.format).toEqual({ type: "audio/pcm", rate: 24000 });
    expect(update.session.audio.input.transcription).toEqual({ model: "gpt-4o-mini-transcribe", prompt: "LoRA, DeepSeek" });
  });

  it("separates utterances with a space and waits for every committed one", () => {
    const { protocol, events } = setup(session);
    protocol.receive(send({ type: "input_audio_buffer.committed", item_id: "a" }));
    protocol.receive(send({ type: "conversation.item.input_audio_transcription.delta", item_id: "a", delta: "He" }));
    protocol.receive(send({ type: "conversation.item.input_audio_transcription.delta", item_id: "a", delta: " hoped." }));
    protocol.receive(send({ type: "conversation.item.input_audio_transcription.completed", item_id: "a" }));
    expect(events.onDone).not.toHaveBeenCalled();

    protocol.finish();
    protocol.receive(send({ type: "input_audio_buffer.committed", item_id: "b" }));
    protocol.receive(send({ type: "conversation.item.input_audio_transcription.delta", item_id: "b", delta: "Stew" }));
    expect(events.onDone).not.toHaveBeenCalled();
    protocol.receive(send({ type: "conversation.item.input_audio_transcription.completed", item_id: "b" }));

    expect(events.onText.mock.calls.map(([delta]) => delta).join("")).toBe("He hoped. Stew");
    expect(events.onDone).toHaveBeenCalledOnce();
  });

  it("treats an empty final commit as done", () => {
    const { protocol, events } = setup(session);
    protocol.finish();
    protocol.receive(send({ type: "error", error: { code: "input_audio_buffer_commit_empty", message: "empty" } }));
    expect(events.onDone).toHaveBeenCalledOnce();
    expect(events.onError).not.toHaveBeenCalled();
  });
});
