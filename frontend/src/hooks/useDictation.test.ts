import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dictationApi } from "@/lib/api/dictation";
import { useDictation } from "@/hooks/useDictation";

class FakeSocket {
  static last: FakeSocket;
  readyState = 0;
  sent: string[] = [];
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: (event: { code: number }) => void;
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  send(message: string) {
    this.sent.push(message);
  }
  close() {
    this.readyState = 3;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
}

class FakePort {
  static last: FakePort;
  posted: unknown[] = [];
  onmessage?: (event: { data: unknown }) => void;
  constructor() {
    FakePort.last = this;
  }
  postMessage(message: unknown) {
    this.posted.push(message);
    if (message === "flush") this.onmessage?.({ data: { pcm: new ArrayBuffer(0), flushed: true } });
  }
  close() {}
}

const node = () => ({ connect: (next: unknown) => next });

class FakeAudioContext {
  static created = 0;
  static last: FakeAudioContext;
  resume = vi.fn(async () => undefined);
  audioWorklet = { addModule: vi.fn(async () => undefined) };
  destination = {};
  constructor() {
    FakeAudioContext.created += 1;
    FakeAudioContext.last = this;
  }
  createGain() {
    return { gain: { value: 1 }, connect: (next: unknown) => next };
  }
  createMediaStreamSource() {
    return node();
  }
  close() {
    return Promise.resolve();
  }
}

class FakeWorkletNode {
  port = new FakePort();
  connect(next: unknown) {
    return next;
  }
}

const track = { stop: vi.fn(), addEventListener: vi.fn() };

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:pcm-worklet") });
  vi.stubGlobal("WebSocket", Object.assign(FakeSocket, { OPEN: 1, CONNECTING: 0 }));
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("AudioWorkletNode", FakeWorkletNode);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) },
  });
  vi.spyOn(dictationApi, "createSession").mockResolvedValue({
    session_id: "s1",
    ws_url: "/api/v1/dictation/ws?ticket=t",
    provider: "voxtral",
    model: "voxtral",
    sample_rate: 16000,
    max_seconds: 120,
    prompt: null,
  });
  vi.spyOn(dictationApi, "finishSession").mockResolvedValue(undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function started() {
  const onText = vi.fn();
  const onEnd = vi.fn();
  const hook = renderHook(() => useDictation({ onText, onEnd }));
  await act(async () => {
    await hook.result.current.start();
  });
  return { hook, onText, onEnd };
}

describe("useDictation", () => {
  it("creates the audio context before awaiting the microphone, then resumes it", async () => {
    FakeAudioContext.created = 0;
    const getUserMedia = navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>;
    getUserMedia.mockImplementationOnce(async () => {
      expect(FakeAudioContext.created).toBe(1);
      return { getTracks: () => [track] };
    });
    await started();
    // A Blob URL, not a data: URL, which Safari rejects in addModule().
    expect(FakeAudioContext.last.audioWorklet.addModule).toHaveBeenCalledWith("blob:pcm-worklet");
  });

  it("stays connecting until the relay accepts the socket", async () => {
    const { hook } = await started();
    expect(hook.result.current.phase).toBe("connecting");
    expect(FakeSocket.last.url).toMatch(/^ws:\/\/.+\/api\/v1\/dictation\/ws\?ticket=t$/);
    act(() => FakeSocket.last.open());
    expect(hook.result.current.phase).toBe("recording");
  });

  it("finishes once and ends when the final text arrives", async () => {
    const { hook, onText, onEnd } = await started();
    act(() => FakeSocket.last.open());
    act(() => FakeSocket.last.onmessage?.({ data: JSON.stringify({ type: "transcription.delta", delta: " Hi" }) }));
    act(() => {
      hook.result.current.finish();
      hook.result.current.finish();
    });
    const commits = FakeSocket.last.sent.filter((message) => message.includes('"final":true'));
    expect(commits).toHaveLength(1);
    expect(hook.result.current.phase).toBe("finishing");

    act(() => FakeSocket.last.onmessage?.({ data: JSON.stringify({ type: "transcription.done", text: " Hi" }) }));
    expect(onText).toHaveBeenCalledWith(" Hi");
    expect(onEnd).toHaveBeenCalledWith({ cancelled: false });
    expect(hook.result.current.phase).toBe("idle");
    expect(dictationApi.finishSession).toHaveBeenCalledWith("s1", expect.any(Number));
  });

  it("reports a dropped connection as an error", async () => {
    const { onEnd } = await started();
    act(() => FakeSocket.last.open());
    act(() => FakeSocket.last.onclose?.({ code: 1006 }));
    expect(onEnd).toHaveBeenCalledWith({ cancelled: false, error: "Voice input disconnected." });
  });
});
